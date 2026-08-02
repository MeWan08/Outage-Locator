from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import tickets
from app.db import get_db
from app.models import Incident, IncidentEvent, PoleState
from app.schemas import AssignCrewIn, IncidentOut, ResolveResult

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentOut])
def list_incidents(status: str | None = None, db: Session = Depends(get_db)):
    q = select(Incident).order_by(Incident.updated_at.desc())
    if status:
        q = q.where(Incident.status.in_(status.split(",")))
    else:
        q = q.where(Incident.status != "suppressed_scheduled")
    return db.execute(q).scalars().all()


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise HTTPException(404, "incident not found")
    return inc


@router.get("/{incident_id}/events")
def get_incident_events(incident_id: str, db: Session = Depends(get_db)):
    rows = db.execute(
        select(IncidentEvent).where(IncidentEvent.incident_id == incident_id).order_by(IncidentEvent.at)
    ).scalars().all()
    return [{"at": r.at, "actor": r.actor, "action": r.action, "note": r.note} for r in rows]


@router.post("/{incident_id}/acknowledge", response_model=IncidentOut)
def acknowledge(incident_id: str, db: Session = Depends(get_db)):
    inc = _get_or_404(db, incident_id)
    tickets.acknowledge(db, inc)
    db.commit()
    db.refresh(inc)
    return inc


@router.post("/{incident_id}/assign-crew", response_model=IncidentOut)
def assign_crew(incident_id: str, payload: AssignCrewIn, db: Session = Depends(get_db)):
    inc = _get_or_404(db, incident_id)
    tickets.assign_crew(db, inc, payload.crew_name)
    db.commit()
    db.refresh(inc)
    return inc


@router.post("/{incident_id}/resolve", response_model=ResolveResult)
def resolve(incident_id: str, db: Session = Depends(get_db)):
    """Records the operator/crew's claim that this is fixed. Does not force
    verification — see app/tickets.py. The response tells the operator
    immediately if telemetry disagrees, rather than letting them find out
    later that the ticket never actually verified."""
    inc = _get_or_404(db, incident_id)
    affected = set(inc.affected_pole_ids or [])
    states = db.execute(select(PoleState).where(PoleState.pole_id.in_(affected))).scalars().all()
    live_ids = {s.pole_id for s in states if s.energized is True}
    currently_dark = affected - live_ids
    still_dark, total = tickets.mark_resolved(db, inc, currently_dark)
    db.commit()
    if still_dark:
        message = (f"Marked resolved, but {still_dark} of {total} affected poles are still reporting "
                   "dark. This ticket will stay unverified until telemetry confirms restoration.")
    else:
        message = "Marked resolved. All affected poles are already reporting live — verification should follow shortly."
    return ResolveResult(incident_id=incident_id, status=inc.status, poles_still_dark=still_dark,
                          poles_total=total, message=message)


@router.post("/{incident_id}/close", response_model=IncidentOut)
def close(incident_id: str, db: Session = Depends(get_db)):
    inc = _get_or_404(db, incident_id)
    if not tickets.close(db, inc):
        raise HTTPException(400, "Incident must be telemetry-verified before it can be closed.")
    db.commit()
    db.refresh(inc)
    return inc


def _get_or_404(db: Session, incident_id: str) -> Incident:
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise HTTPException(404, "incident not found")
    return inc
