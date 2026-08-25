"""
Two jobs, both important for the same reason: G5 in 03-deliverables-and-
submission.md says the system will be evaluated by literally injecting
faults and watching what happens, and everything here goes through
app.ingestion.enqueue() — the exact same path a real device's HTTP request
would take. If the simulator special-cased its way around ingestion, a
passing demo wouldn't actually prove the pipeline works.

1. fleet_heartbeat_loop(): a continuous background task that keeps every
   device-equipped pole heartbeating on its real ~15-minute cadence
   (app/config.py), skipping anything currently simulated as faulted.
   Without this, every pole drifts into SILENT ~31 minutes after boot
   whether or not anything is actually wrong, which would make the
   silence-based detection path (and the DT/feeder rollups) meaningless
   in anything other than a five-minute demo window.

2. inject_fault() / repair(): on-demand fault injection for the operator
   console's simulator panel (or curl, per 03-deliverables-and-
   submission.md's "one documented command" allowance). Each affected
   device independently has a chance of skipping its dying `power_lost`
   message — 100% for devices on a firmware version that never sends one,
   otherwise the ~30% baseline from 02-data-and-systems.md — so the
   silence-only code path gets exercised on every run, not just when
   explicitly asked for via `silent_failure`.
"""
import asyncio
import datetime as dt
import random

from sqlalchemy import select

from app import background, ingestion, timeutil
from app.config import settings
from app.db import session_scope
from app.models import Device, Incident, Pole
from app.topology import subtree_pole_ids

BUGGY_FIRMWARE_VERSIONS = {"1.2.0", "1.2.1"}
RANDOM_SILENT_PROBABILITY = 0.30

_faulted_pole_ids: set[str] = set()
_active_faults: list[set[str]] = []
_device_seq: dict[str, int] = {}
_fw_cache: dict[str, str] = {}
_next_due: dict[str, dt.datetime] = {}


def _seq_next(db, device_id: str) -> int:
    if device_id not in _device_seq:
        dvc = db.get(Device, device_id)
        _device_seq[device_id] = dvc.last_seq if (dvc and dvc.last_seq is not None) else -1
    _device_seq[device_id] += 1
    return _device_seq[device_id]


def _seq_reset_for_boot(device_id: str) -> int:
    _device_seq[device_id] = 0
    return 0


def _fw_for(db, device_id: str) -> str:
    if device_id not in _fw_cache:
        dvc = db.get(Device, device_id)
        _fw_cache[device_id] = (dvc.last_fw if dvc else None) or "2.1.0"
    return _fw_cache[device_id]


def _build_event(db, pole: Pole, event_type: str, energized: bool, now, *, reset_seq=False) -> dict:
    device_id = pole.device_id
    seq = _seq_reset_for_boot(device_id) if reset_seq else _seq_next(db, device_id)
    return {
        "device_id": device_id, "pole_id": pole.pole_id, "event": event_type,
        "energized": energized, "ts": now, "seq": seq,
        "battery_mv": random.randint(3200, 4100), "rssi": random.randint(-110, -60),
        "fw": _fw_for(db, device_id),
    }


def _pick_interesting_pole(meta, exclude: set) -> str | None:
    nodes = meta.topology.nodes
    children_index = meta.topology.children_index
    candidates = [pid for pid in nodes if pid not in exclude]
    if not candidates:
        return None
    with_children = [pid for pid in candidates if children_index.get(pid)]
    return random.choice(with_children or candidates)


async def inject_fault(kind: str, *, dt_id=None, feeder_id=None, pole_id=None, silent_failure=False) -> dict:
    now = timeutil.utcnow()

    if kind == "device_only":
        if pole_id is None:
            raise ValueError("device_only fault needs a pole_id")
        with session_scope() as db:
            pole = db.get(Pole, pole_id)
            if pole is None or pole.device_id is None:
                raise ValueError("pole not found or has no device fitted")
        _faulted_pole_ids.add(pole_id)
        _active_faults.append({pole_id})
        # No telemetry sent at all: nothing about the pole's power state
        # changes, it just stops reporting — exactly what an unrelated dead
        # sensor looks like. This is what test_sensor_only_fault exercises.
        return {"kind": kind, "pole_id": pole_id, "affected_pole_ids": [pole_id],
                "explicit_signal_count": 0, "silent_count": 1}

    events = []
    with session_scope() as db:
        if kind == "span":
            meta = background.get_dt_meta(dt_id)
            if meta is None:
                raise ValueError(f"unknown dt_id {dt_id}")
            target = pole_id or _pick_interesting_pole(meta, _faulted_pole_ids)
            if target is None:
                raise ValueError("no eligible (unfaulted) pole on this transformer")
            affected = subtree_pole_ids(meta.topology.children_index, target)
            summary = {"kind": kind, "dt_id": dt_id, "pole_id": target}

        elif kind == "dt":
            meta = background.get_dt_meta(dt_id)
            if meta is None:
                raise ValueError(f"unknown dt_id {dt_id}")
            affected = list(meta.topology.nodes.keys())
            summary = {"kind": kind, "dt_id": dt_id}

        elif kind == "feeder":
            affected = []
            for d in background.dt_ids_for_feeder(feeder_id):
                meta = background.get_dt_meta(d)
                if meta:
                    affected.extend(meta.topology.nodes.keys())
            if not affected:
                raise ValueError(f"unknown or empty feeder {feeder_id}")
            summary = {"kind": kind, "feeder_id": feeder_id}

        else:
            raise ValueError(f"unknown fault kind '{kind}'")

        for pid in affected:
            pole = db.get(Pole, pid)
            if pole is None or pole.device_id is None:
                continue
            fw = _fw_for(db, pole.device_id)
            send_explicit = not (
                silent_failure or fw in BUGGY_FIRMWARE_VERSIONS or random.random() < RANDOM_SILENT_PROBABILITY
            )
            if send_explicit:
                events.append(_build_event(db, pole, "power_lost", False, now))
            _faulted_pole_ids.add(pid)

    for ev in events:
        await ingestion.enqueue(ev)

    _active_faults.append(set(affected))

    summary["affected_pole_ids"] = affected
    summary["explicit_signal_count"] = len(events)
    summary["silent_count"] = len(affected) - len(events)
    return summary


async def repair(*, incident_id: str | None = None, pole_ids: list[str] | None = None) -> dict:
    now = timeutil.utcnow()
    targets = list(pole_ids or [])
    with session_scope() as db:
        if incident_id:
            inc = db.get(Incident, incident_id)
            if inc is None:
                raise ValueError(f"unknown incident {incident_id}")
            targets.extend(inc.affected_pole_ids or [])
        
        # If any requested pole intersects with an injected fault, repair the entire fault
        for pid in list(targets):
            for fault_set in list(_active_faults):
                if pid in fault_set:
                    targets.extend(list(fault_set))
                    _active_faults.remove(fault_set)
                    
        targets = list(dict.fromkeys(targets))

        events = []
        for pid in targets:
            pole = db.get(Pole, pid)
            _faulted_pole_ids.discard(pid)
            if pole is None or pole.device_id is None:
                continue
            events.append(_build_event(db, pole, "boot", True, now, reset_seq=True))
            events.append(_build_event(db, pole, "power_restored", True, now))
            _next_due[pid] = now  # resume normal heartbeat cadence immediately

    for ev in events:
        await ingestion.enqueue(ev)
    return {"repaired_pole_ids": targets, "events_sent": len(events)}


async def storm(count: int = 3) -> list[dict]:
    dt_ids = background.all_dt_ids()
    random.shuffle(dt_ids)
    results = []
    for d in dt_ids:
        if len(results) >= count:
            break
        try:
            results.append(await inject_fault("span", dt_id=d))
        except ValueError:
            continue
    return results


async def fleet_heartbeat_loop():
    with session_scope() as db:
        poles = db.execute(select(Pole).where(Pole.device_id.isnot(None))).scalars().all()
        now = timeutil.utcnow()
        # Spread initial heartbeats across a short window (30 s) so all
        # poles reach LIVE quickly after startup, rather than waiting up
        # to a full HEARTBEAT_INTERVAL which left most poles "silent".
        initial_spread = min(30, settings.HEARTBEAT_INTERVAL_SECONDS)
        for p in poles:
            _next_due[p.pole_id] = now + dt.timedelta(seconds=random.uniform(0, initial_spread))

    while True:
        try:
            now = timeutil.utcnow()
            due = [pid for pid, when in _next_due.items() if when <= now and pid not in _faulted_pole_ids]
            if due:
                events = []
                with session_scope() as db:
                    for pid in due:
                        pole = db.get(Pole, pid)
                        if pole is None or pole.device_id is None:
                            continue
                        events.append(_build_event(db, pole, "heartbeat", True, now))
                        jitter = random.uniform(-settings.HEARTBEAT_JITTER_SECONDS, settings.HEARTBEAT_JITTER_SECONDS)
                        _next_due[pid] = now + dt.timedelta(seconds=settings.HEARTBEAT_INTERVAL_SECONDS + jitter)
                for ev in events:
                    await ingestion.enqueue(ev)
        except Exception as exc:  # noqa: BLE001 — one bad tick must never kill the heartbeat loop
            print(f"[simulator] heartbeat tick failed: {exc!r}")
        await asyncio.sleep(5)


def status() -> dict:
    return {"currently_faulted_pole_count": len(_faulted_pole_ids),
            "currently_faulted_pole_ids": sorted(_faulted_pole_ids)[:200]}
