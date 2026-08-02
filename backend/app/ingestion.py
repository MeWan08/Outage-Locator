"""
Ingestion is split into two halves on purpose:

1. The HTTP handler (app/routers/telemetry.py) does almost nothing: it
   validates the payload and drops it on an in-memory asyncio.Queue, then
   returns 202 immediately. This is what lets us accept a 5,000-message
   burst in a few seconds even though the actual writer is a single SQLite
   connection — the queue absorbs the burst, the writer smooths it out.

2. `batched_writer_loop` (started once at app startup) drains the queue in
   batches (size- or time-bounded, whichever comes first) and commits each
   batch as one transaction. One transaction per ~300 messages instead of
   one per message is the difference between "fine" and "database is
   locked" on SQLite under load — see scripts/loadtest.py for measured
   numbers, reported honestly in ARCHITECTURE.md rather than assumed.

Ordering/dedup: authoritative ordering is `(device_id, seq)`, not the
device's own timestamp (`ts`), which can drift on cheap hardware — see
02-data-and-systems.md. `boot` resets a device's sequence counter, so a
boot event is always applied regardless of the seq it carries; every other
event is only applied if seq is strictly greater than the last seq accepted
for that device. Anything else is logged (for audit) but does not touch
PoleState. Location always comes from `pole_id`, never inferred from
`device_id`, because devices can be swapped without a pole_id change.
"""
import asyncio
import datetime as dt

from sqlalchemy import select

from app.config import settings
from app.db import session_scope
from app.models import Device, Pole, PoleState, TelemetryEvent
from app.timeutil import as_naive_utc, utcnow

_queue: asyncio.Queue | None = None
_known_pole_ids: set[str] = set()


def get_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue(maxsize=settings.INGEST_QUEUE_MAXSIZE)
    return _queue


def refresh_known_pole_ids():
    """Called once at startup after seeding. Avoids a DB round-trip per
    ingested event just to check 'is this a real pole'."""
    global _known_pole_ids
    with session_scope() as db:
        _known_pole_ids = {row[0] for row in db.execute(select(Pole.pole_id)).all()}


async def enqueue(event: dict) -> int:
    """Returns the queue depth after enqueueing, for the API's ack payload."""
    q = get_queue()
    await q.put(event)
    return q.qsize()


async def batched_writer_loop():
    q = get_queue()
    while True:
        batch = [await q.get()]
        loop = asyncio.get_event_loop()
        deadline = loop.time() + settings.INGEST_BATCH_MAX_WAIT_SECONDS
        while len(batch) < settings.INGEST_BATCH_MAX_SIZE:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                batch.append(await asyncio.wait_for(q.get(), timeout=remaining))
            except asyncio.TimeoutError:
                break
        try:
            apply_batch(batch)
        except Exception as exc:  # noqa: BLE001 — never let a bad batch kill the writer loop
            print(f"[ingestion] batch of {len(batch)} failed: {exc!r}")


def apply_batch(events: list[dict]):
    if not events:
        return
    now = utcnow()
    with session_scope() as db:
        device_ids = {e["device_id"] for e in events}
        devices = {d.device_id: d for d in db.execute(
            select(Device).where(Device.device_id.in_(device_ids))
        ).scalars().all()}

        pole_ids = {e["pole_id"] for e in events if e["pole_id"] in _known_pole_ids}
        pole_states = {ps.pole_id: ps for ps in db.execute(
            select(PoleState).where(PoleState.pole_id.in_(pole_ids))
        ).scalars().all()}

        for ev in events:
            _apply_single(db, ev, devices, pole_states, now)

        for dvc in devices.values():
            db.add(dvc)
        for ps in pole_states.values():
            db.add(ps)


def _apply_single(db, ev: dict, devices: dict, pole_states: dict, received_at: dt.datetime):
    device_id, pole_id = ev["device_id"], ev["pole_id"]
    seq, event_type = ev["seq"], ev["event"]
    device_ts = as_naive_utc(ev["ts"])

    device = devices.get(device_id)
    if device is None:
        device = Device(device_id=device_id, current_pole_id=pole_id, last_seq=None, boot_count=0)
        devices[device_id] = device

    is_boot = event_type == "boot"
    is_duplicate = False
    is_out_of_order = False
    applied = True

    if not is_boot and device.last_seq is not None:
        if seq <= device.last_seq:
            applied = False
            is_duplicate = seq == device.last_seq
            is_out_of_order = not is_duplicate

    pole_known = pole_id in _known_pole_ids
    if not pole_known:
        applied = False

    db.add(TelemetryEvent(
        device_id=device_id, pole_id=pole_id, event=event_type, energized=ev["energized"],
        device_ts=device_ts, seq=seq, battery_mv=ev.get("battery_mv"), rssi=ev.get("rssi"),
        fw=ev.get("fw"), received_at=received_at, is_duplicate=is_duplicate,
        is_out_of_order=is_out_of_order, applied=applied,
    ))

    if is_boot:
        device.boot_count = (device.boot_count or 0) + 1
        device.last_seq = seq
    elif applied:
        device.last_seq = seq
    device.current_pole_id = pole_id
    device.last_fw = ev.get("fw") or device.last_fw
    device.last_seen_at = received_at
    if device.first_seen_at is None:
        device.first_seen_at = received_at

    if not applied or not pole_known:
        return

    ps = pole_states.get(pole_id)
    if ps is None:
        ps = PoleState(pole_id=pole_id)
        pole_states[pole_id] = ps

    was_energized = ps.energized
    ps.device_id = device_id
    ps.energized = ev["energized"]
    ps.last_event = event_type
    ps.last_device_ts = device_ts
    ps.last_received_at = received_at
    ps.last_seq = seq
    ps.battery_mv = ev.get("battery_mv")
    ps.rssi = ev.get("rssi")
    ps.fw = ev.get("fw")

    if ev["energized"] and was_energized is not True:
        ps.became_live_at = received_at
    if not ev["energized"] and was_energized is not False:
        ps.became_dark_at = received_at
