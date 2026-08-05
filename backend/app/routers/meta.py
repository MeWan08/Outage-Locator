from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import background
from app.config import settings
from app.db import get_db
from app.localization import classify_raw
from app.models import Incident, Pole, PoleState
from app.timeutil import utcnow

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/poles")
def list_poles(dt_id: str | None = None, db: Session = Depends(get_db)):
    now = utcnow()
    q = select(Pole, PoleState).outerjoin(PoleState, PoleState.pole_id == Pole.pole_id)
    if dt_id:
        q = q.where(Pole.dt_id == dt_id)
    rows = db.execute(q).all()
    return [
        {
            "pole_id": pole.pole_id, "lat": pole.lat, "lon": pole.lon, "dt_id": pole.dt_id,
            "feeder_id": pole.feeder_id, "has_device": pole.device_id is not None,
            "topology_source": pole.topology_source,
            "resolved_parent_pole_id": pole.resolved_parent_pole_id,
            "seq_on_line": pole.seq_on_line,
            "energized": ps.energized if ps else None,
            "last_received_at": ps.last_received_at if ps else None,
            "raw_status": classify_raw(
                pole.device_id is not None,
                ps.energized if ps else None,
                ps.last_received_at if ps else None,
                now, settings,
            ),
        }
        for pole, ps in rows
    ]


@router.get("/topology/{dt_id}")
def get_topology(dt_id: str):
    meta = background.get_dt_meta(dt_id)
    if meta is None:
        return {"error": "unknown dt_id"}
    nodes = {
        pid: {"resolved_parent_pole_id": n.resolved_parent_pole_id, "topology_source": n.topology_source,
              "depth": n.depth, "ambiguous": n.ambiguous}
        for pid, n in meta.topology.nodes.items()
    }
    return {"dt_id": dt_id, "topology_source": meta.topology.topology_source, "nodes": nodes}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    now = utcnow()
    total_poles = db.execute(select(func.count(Pole.pole_id))).scalar_one()
    open_incidents = db.execute(
        select(func.count(Incident.id)).where(Incident.status.notin_(["verified", "closed", "suppressed_scheduled"]))
    ).scalar_one()
    # Count dark poles using real-time classification (heartbeat-aware),
    # not the stale PoleState.energized DB column which misses silent faults.
    rows = db.execute(
        select(Pole, PoleState).outerjoin(PoleState, PoleState.pole_id == Pole.pole_id)
        .where(Pole.device_id.isnot(None))
    ).all()
    dark_now = sum(
        1 for pole, ps in rows
        if classify_raw(True, ps.energized if ps else None, ps.last_received_at if ps else None, now, settings)
        in ("confirmed_dark", "silent")
    )
    return {
        "total_poles": total_poles,
        "open_incidents": open_incidents,
        "poles_reporting_dark": dark_now,
        "dt_count": len(background.all_dt_ids()),
    }


@router.get("/stats/history")
def stats_history(limit: int = 60):
    from app import stats_history as sh
    return sh.get_history(limit)

