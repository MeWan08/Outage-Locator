"""
02-data-and-systems.md is explicit that the load-shedding feed cannot be
trusted blindly: shutdowns start late, overrun, and roughly one in ten are
cancelled without the feed being updated. The design here is deliberately
narrow so it never suppresses a real fault:

- Suppression only ever fires for an EXACT match between a candidate
  incident's own scope (dt/feeder) and target id and a schedule's declared
  scope/target — never a fuzzy "somewhere in the area" match, and never for
  span-level faults (a snapped LT line inside a DT that also has an
  unrelated scheduled shutdown elsewhere is still real and still reported).
- A schedule counts as "active" from `start - grace` to `end + grace`
  (default 40 min either side) so an early/late start or a typical overrun
  doesn't cause a suppress/un-suppress flicker.
- If a schedule was silently cancelled, nothing ever goes dark for it, so
  there's nothing to suppress and nothing to falsely alert on — the
  cancellation case needs no special handling, it falls out of only ever
  reacting to observed telemetry.
- If the affected footprint is STILL dark after `end + grace`, that's the
  "shedding window elapsed and nothing came back" signal — the caller
  (app/background.py) promotes it out of suppression into a normal ticket.
"""
import datetime as dt


def matching_schedule(candidate, schedules, now, cfg):
    """candidate: a localization.CandidateIncident (or an object with the
    same .type/.dt_id/.feeder_id attributes). Returns the matching
    ScheduledOutage row, or None.

    Suppresses at ALL levels beneath the scheduled scope:
    - A DT schedule suppresses dt AND span incidents on that DT.
    - A feeder schedule suppresses feeder, dt, AND span incidents on that feeder.
    """
    for s in schedules:
        if not is_active(s, now, cfg):
            continue
        # DT-scope schedule: suppress dt-level AND span-level incidents on this DT
        if s.scope == "dt" and candidate.dt_id and s.target_id == candidate.dt_id:
            return s
        # Feeder-scope schedule: suppress feeder, dt, and span incidents on this feeder
        if s.scope == "feeder" and candidate.feeder_id and s.target_id == candidate.feeder_id:
            return s
    return None


def is_active(schedule, now, cfg) -> bool:
    grace = dt.timedelta(seconds=cfg.SCHEDULED_OUTAGE_GRACE_SECONDS)
    return (schedule.start - grace) <= now <= (schedule.end + grace)


def is_past_grace(schedule, now, cfg) -> bool:
    grace = dt.timedelta(seconds=cfg.SCHEDULED_OUTAGE_GRACE_SECONDS)
    return now > (schedule.end + grace)
