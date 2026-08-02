"""
Lifecycle: detected -> acknowledged -> crew_assigned -> resolved -> verified -> closed
                                                            ^
                                    an operator can also mark 'resolved' directly
                                    from 'detected'/'acknowledged' if that's how the
                                    crew actually reported it back

'verified' is the one status this module will never set in response to a
human action — it is only ever set by check_restoration(), which looks at
live telemetry for every pole the incident said was affected. Marking a
ticket 'resolved' records what a lineman claimed; it does not make the
poles come back on. If they're still dark, resolve() says so in its return
value and the ticket sits at 'resolved' (visibly unverified) until either
the telemetry catches up or an operator/lineman corrects the record — see
04-evaluation.md's own scripted check: "Marked a ticket resolved while the
poles were still dark. The system pushed back."
"""
import datetime as dt
import random
import string

from app.models import Incident, IncidentEvent
from app import timeutil


def new_incident_id() -> str:
    today = timeutil.utcnow().strftime("%Y%m%d")
    suffix = "".join(random.choices(string.hexdigits.upper()[:16], k=4))
    return f"INC-{today}-{suffix}"


def upsert_from_candidate(db, candidate, existing: Incident | None, status="detected") -> Incident:
    """Create a new ticket, or refresh a still-open one that matches the
    same fault (same identity_key). Refreshing (not recreating) is what
    keeps a single ongoing fault as a single ticket across many detection
    ticks instead of spawning duplicates."""
    if existing is None:
        inc = Incident(id=new_incident_id(), identity_key=candidate.identity_key, status=status)
        db.add(inc)
        _log(db, inc, "system", "detected", f"New {candidate.type} incident, confidence {candidate.confidence:.2f}")
    else:
        inc = existing

    inc.type = candidate.type
    inc.dt_id = candidate.dt_id
    inc.feeder_id = candidate.feeder_id
    inc.span_from_pole_id = candidate.span_from_pole_id
    inc.span_to_pole_id = candidate.span_to_pole_id
    inc.candidate_range_pole_ids = candidate.candidate_range_pole_ids
    inc.affected_pole_ids = candidate.affected_pole_ids
    inc.lat = candidate.lat
    inc.lon = candidate.lon
    inc.pincode = candidate.pincode
    inc.poles_affected = candidate.poles_affected
    inc.households_affected_estimate = candidate.households_affected_estimate
    inc.confidence = candidate.confidence
    inc.confidence_label = candidate.confidence_label
    inc.confidence_reasons = candidate.confidence_reasons
    inc.topology_source = candidate.topology_source
    inc.evidence_pole_ids = candidate.evidence_pole_ids
    return inc


def suppress_scheduled(db, candidate, existing: Incident | None, schedule) -> Incident:
    inc = upsert_from_candidate(db, candidate, existing, status="suppressed_scheduled")
    if inc.suppressed_by_schedule_id != schedule.id:
        inc.suppressed_by_schedule_id = schedule.id
        _log(db, inc, "system", "suppressed_scheduled",
             f"Matches active scheduled outage {schedule.id} ({schedule.scope}={schedule.target_id}); not raised as a ticket.")
    return inc


def promote_from_suppressed(db, inc: Incident, schedule):
    inc.status = "detected"
    inc.suppressed_by_schedule_id = None
    _log(db, inc, "system", "promoted",
         f"Scheduled outage {schedule.id} window elapsed but poles are still dark — raising as a real ticket.")


def acknowledge(db, inc: Incident):
    if inc.status in ("detected",):
        inc.status = "acknowledged"
    inc.acknowledged_at = inc.acknowledged_at or timeutil.utcnow()
    _log(db, inc, "operator", "acknowledged", None)


def assign_crew(db, inc: Incident, crew_name: str):
    inc.crew_name = crew_name
    inc.crew_assigned_at = timeutil.utcnow()
    if inc.status in ("detected", "acknowledged"):
        inc.status = "crew_assigned"
    _log(db, inc, "operator", "crew_assigned", f"Assigned to {crew_name}")


def mark_resolved(db, inc: Incident, currently_dark_pole_ids: set[str]) -> tuple[int, int]:
    """Records that someone (usually the crew, via the operator) claims the
    fault is fixed. Does NOT set verified_at — see module docstring.
    Returns (poles_still_dark, poles_total) so the caller can push back
    immediately in the API response, not just eventually on the next tick."""
    inc.resolved_marked_at = timeutil.utcnow()
    if inc.status not in ("verified", "closed"):
        inc.status = "resolved"
    affected = set(inc.affected_pole_ids or [])
    still_dark = affected & currently_dark_pole_ids
    _log(db, inc, "operator", "marked_resolved",
         f"{len(still_dark)} of {len(affected)} affected poles still reporting dark at the time of marking."
         if still_dark else "All affected poles were already live at the time of marking.")
    return len(still_dark), len(affected)


def check_restoration(db, inc: Incident, pole_restored_fn, now) -> bool:
    """`pole_restored_fn(pole_id) -> bool` encapsulates everything about
    what 'restored' means for one pole — including that a pole with no
    device fitted can never prove it either way and must count as
    vacuously restored (see app/background.py). Without that, any incident
    whose affected subtree includes even one no-device pole — which is most
    of them, at a ~9% no-device rate — could never auto-verify at all.
    Returns True if this call just verified the incident."""
    if inc.status in ("verified", "closed", "suppressed_scheduled"):
        return False
    affected = inc.affected_pole_ids or []
    if not affected:
        return False
    if not all(pole_restored_fn(pid) for pid in affected):
        return False
    inc.verified_at = now
    was_resolved_by_human = inc.status == "resolved"
    inc.status = "verified"
    _log(db, inc, "system", "verified",
         "Telemetry confirms all affected poles have been live and stable."
         + ("" if was_resolved_by_human else " (Poles recovered on their own — no one had marked this resolved yet.)"))
    return True


def close(db, inc: Incident) -> bool:
    if inc.status != "verified":
        return False
    inc.status = "closed"
    inc.closed_at = timeutil.utcnow()
    _log(db, inc, "operator", "closed", None)
    return True


def supersede(db, old: Incident, new: "Incident"):
    """A fault's granularity can coarsen as ambiguous silent poles cross
    into confirmed-dark — several span tickets on one DT can end up all
    genuinely belonging to one DT-level fault once enough evidence is in.
    Rather than leave the narrower ticket open and orphaned (duplicate
    alerts for the same root cause — exactly what 01-problem-context.md
    calls worse than no system), it's closed here with a pointer to the
    ticket that now covers it."""
    now = timeutil.utcnow()
    old.verified_at = old.verified_at or now
    old.status = "closed"
    old.closed_at = now
    _log(db, old, "system", "superseded",
         f"Escalated into {new.id} ({new.type}-level) as more evidence arrived; closing this narrower ticket.")


def _log(db, inc: Incident, actor: str, action: str, note: str | None):
    db.add(IncidentEvent(incident_id=inc.id, actor=actor, action=action, note=note))
