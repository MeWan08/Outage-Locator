import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app import simulator, timeutil
from app.db import session_scope
from app.models import ScheduledOutage
from app.schemas import ScheduledOutageIn, SimulatorFaultIn, SimulatorRepairIn, SimulatorStormIn

router = APIRouter(prefix="/api/simulator", tags=["simulator"])


@router.post("/fault")
async def fault(payload: SimulatorFaultIn):
    try:
        return await simulator.inject_fault(
            payload.kind, dt_id=payload.dt_id, feeder_id=payload.feeder_id,
            pole_id=payload.pole_id, silent_failure=payload.silent_failure,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/repair")
async def repair(payload: SimulatorRepairIn):
    try:
        return await simulator.repair(incident_id=payload.incident_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/storm")
async def storm(payload: SimulatorStormIn):
    return await simulator.storm(payload.count)


@router.get("/status")
def status():
    return simulator.status()


@router.get("/scheduled-outages")
def list_scheduled_outages():
    with session_scope() as db:
        rows = db.execute(select(ScheduledOutage)).scalars().all()
        return [
            {"id": r.id, "scope": r.scope, "target_id": r.target_id, "start": r.start,
             "end": r.end, "reason": r.reason}
            for r in rows
        ]


@router.post("/scheduled-outages")
def create_scheduled_outage(payload: ScheduledOutageIn):
    new_id = f"SO-{uuid.uuid4().hex[:8]}"
    with session_scope() as db:
        db.add(ScheduledOutage(id=new_id, scope=payload.scope, target_id=payload.target_id.strip().upper(),
                                start=timeutil.as_naive_utc(payload.start), 
                                end=timeutil.as_naive_utc(payload.end), 
                                reason=payload.reason))
    return {"id": new_id}
