"""
Everything in localization.py is pure and stateless. This module is where
state, time, and persistence enter the picture: it's the only place that
knows what tick we're on, what was already open, and what's still pending
debounce. Kept deliberately thin and easy to read against
04-evaluation.md's scripted checks (storm test, silent-failure test, false
positive tests, restoration test) — each one maps to a specific branch here.
"""
import asyncio
import datetime as dt
import types

from sqlalchemy import select

from app import ai_briefing, scheduled_outages, tickets, timeutil
from app.config import settings
from app.db import session_scope
from app.localization import DtMeta, PoleSnapshot, classify_raw, run_localization
from app.models import Feeder, Incident, Pole, PoleState, ScheduledOutage, Transformer
from app.topology import PoleRecord, resolve_dt_topology

_dt_topologies: dict[str, DtMeta] = {}
_feeder_dt_ids: dict[str, list[str]] = {}
_pending_candidates: dict[str, dt.datetime] = {}  # identity_key -> first_seen, debounce state


def build_topology_cache(db):
    """Run once at startup (after seeding). Resolves every DT's tree once —
    known topology passed through, gaps filled geometrically — and writes
    the resolution back onto Pole rows so the API/UI can show it. Re-run
    only if the registry itself changes, which it doesn't in this exercise
    after boot; a real deployment would re-run this on registry import."""
    global _dt_topologies, _feeder_dt_ids
    transformers = db.execute(select(Transformer)).scalars().all()
    poles = db.execute(select(Pole)).scalars().all()

    poles_by_dt: dict[str, list[Pole]] = {}
    for p in poles:
        poles_by_dt.setdefault(p.dt_id, []).append(p)

    dt_meta: dict[str, DtMeta] = {}
    for t in transformers:
        records = [
            PoleRecord(pole_id=p.pole_id, lat=p.lat, lon=p.lon,
                       seq_on_line=p.seq_on_line, parent_pole_id=p.parent_pole_id)
            for p in poles_by_dt.get(t.dt_id, [])
        ]
        topo = resolve_dt_topology(t.dt_id, t.lat, t.lon, records)
        dt_meta[t.dt_id] = DtMeta(dt_id=t.dt_id, feeder_id=t.feeder_id, lat=t.lat, lon=t.lon,
                                   households_served=t.households_served or 0, topology=topo)
        for p in poles_by_dt.get(t.dt_id, []):
            node = topo.nodes.get(p.pole_id)
            if node:
                p.resolved_parent_pole_id = node.resolved_parent_pole_id
                p.topology_source = node.topology_source
                p.depth = node.depth
        t.topology_source = topo.topology_source

    feeder_dt_ids: dict[str, list[str]] = {}
    for t in transformers:
        feeder_dt_ids.setdefault(t.feeder_id, []).append(t.dt_id)

    _dt_topologies = dt_meta
    _feeder_dt_ids = feeder_dt_ids


def get_dt_meta(dt_id: str) -> DtMeta | None:
    return _dt_topologies.get(dt_id)


def all_dt_ids() -> list[str]:
    return list(_dt_topologies.keys())


def dt_ids_for_feeder(feeder_id: str) -> list[str]:
    return list(_feeder_dt_ids.get(feeder_id, []))


def _snapshot(pole: Pole, ps: PoleState | None, now, cfg) -> PoleSnapshot:
    has_device = pole.device_id is not None
    energized = ps.energized if ps else None
    last_received_at = ps.last_received_at if ps else None
    raw = classify_raw(has_device, energized, last_received_at, now, cfg)
    return PoleSnapshot(
        pole_id=pole.pole_id, dt_id=pole.dt_id, feeder_id=pole.feeder_id,
        lat=pole.lat, lon=pole.lon, pincode=pole.pincode, has_device=has_device,
        energized=energized, last_received_at=last_received_at, raw_status=raw,
    )


def detection_tick(db, now, cfg) -> list[str]:
    """One pass: localize, debounce, suppress/promote against schedules,
    upsert tickets, check restorations. Returns ids of incidents that just
    became newly visible (freshly detected, or promoted out of suppression)
    — those get an AI briefing queued by the caller."""
    poles = db.execute(select(Pole)).scalars().all()
    pole_states = {ps.pole_id: ps for ps in db.execute(select(PoleState)).scalars().all()}
    snapshots = [_snapshot(p, pole_states.get(p.pole_id), now, cfg) for p in poles]

    candidates, _health_flags = run_localization(snapshots, _dt_topologies, _feeder_dt_ids, now, cfg)

    schedules = db.execute(select(ScheduledOutage)).scalars().all()
    open_incidents = db.execute(
        select(Incident).where(Incident.status.notin_(["verified", "closed"]))
    ).scalars().all()
    open_by_key = {inc.identity_key: inc for inc in open_incidents}

    seen_keys: set[str] = set()
    newly_visible: list[str] = []

    for cand in candidates:
        seen_keys.add(cand.identity_key)
        existing = open_by_key.get(cand.identity_key)

        schedule = scheduled_outages.matching_schedule(cand, schedules, now, cfg)
        if schedule is not None:
            tickets.suppress_scheduled(db, cand, existing, schedule)
            continue

        if existing is not None:
            tickets.upsert_from_candidate(db, cand, existing, status=existing.status)
            continue

        first_seen = _pending_candidates.get(cand.identity_key)
        if first_seen is None:
            _pending_candidates[cand.identity_key] = now
            continue
        if (now - first_seen).total_seconds() < cfg.DEBOUNCE_SECONDS:
            continue

        inc = tickets.upsert_from_candidate(db, cand, None, status="detected")
        _pending_candidates.pop(cand.identity_key, None)
        newly_visible.append(inc.id)

    for key in list(_pending_candidates.keys()):
        if key not in seen_keys:
            _pending_candidates.pop(key, None)  # transient blip that never confirmed — drop it

    for inc in open_incidents:
        if inc.status == "suppressed_scheduled" and inc.identity_key in seen_keys:
            sched = next((s for s in schedules if s.id == inc.suppressed_by_schedule_id), None)
            if sched and scheduled_outages.is_past_grace(sched, now, cfg):
                tickets.promote_from_suppressed(db, inc, sched)
                newly_visible.append(inc.id)

    db.flush()  # autoflush is off; the escalation check below needs to see this tick's writes
    still_open = db.execute(
        select(Incident).where(Incident.status.notin_(["verified", "closed"]))
    ).scalars().all()
    coarse_open = [i for i in still_open if i.type in ("dt", "feeder") and i.identity_key in seen_keys]
    for inc in still_open:
        if inc.identity_key in seen_keys or inc.type not in ("span", "dt"):
            continue
        affected = set(inc.affected_pole_ids or [])
        if not affected:
            continue
        for coarse in coarse_open:
            if coarse.id != inc.id and affected <= set(coarse.affected_pole_ids or []):
                tickets.supersede(db, inc, coarse)
                break

    pole_has_device = {s.pole_id: s.has_device for s in snapshots}
    live_since_lookup = {pid: ps.became_live_at for pid, ps in pole_states.items() if ps.energized is True}

    def pole_restored(pid: str) -> bool:
        if not pole_has_device.get(pid, False):
            return True  # no device was ever fitted -- can never prove it, so don't require it
        live_since = live_since_lookup.get(pid)
        if live_since is None:
            return False
        return (now - live_since).total_seconds() >= cfg.RESTORATION_STABILITY_SECONDS

    for inc in open_incidents:
        if inc.status == "suppressed_scheduled":
            continue
        tickets.check_restoration(db, inc, pole_restored, now)

    return newly_visible


async def _generate_and_store_briefing(incident_id: str):
    with session_scope() as db:
        inc = db.get(Incident, incident_id)
        if inc is None:
            return
        snap = types.SimpleNamespace(
            type=inc.type, dt_id=inc.dt_id, feeder_id=inc.feeder_id,
            span_from_pole_id=inc.span_from_pole_id, span_to_pole_id=inc.span_to_pole_id,
            pincode=inc.pincode, poles_affected=inc.poles_affected,
            households_affected_estimate=inc.households_affected_estimate,
            confidence=inc.confidence, confidence_label=inc.confidence_label,
            confidence_reasons=inc.confidence_reasons, topology_source=inc.topology_source,
        )
    text, source = await ai_briefing.generate_briefing(snap)
    with session_scope() as db:
        inc = db.get(Incident, incident_id)
        if inc is not None:
            inc.ai_briefing = text
            inc.ai_briefing_source = source
            inc.ai_briefing_generated_at = timeutil.utcnow()


async def run_forever():
    while True:
        try:
            now = timeutil.utcnow()
            with session_scope() as db:
                newly_visible = detection_tick(db, now, settings)
            for inc_id in newly_visible:
                asyncio.create_task(_generate_and_store_briefing(inc_id))
        except Exception as exc:  # noqa: BLE001 — one bad tick must never kill the loop
            print(f"[background] detection tick failed: {exc!r}")
        await asyncio.sleep(settings.DETECTION_LOOP_INTERVAL_SECONDS)
