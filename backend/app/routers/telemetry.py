from fastapi import APIRouter

from app import ingestion
from app.schemas import IngestAck, TelemetryBatchIn, TelemetryIn

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.post("", response_model=IngestAck, status_code=202)
async def ingest_one(payload: TelemetryIn):
    depth = await ingestion.enqueue(payload.model_dump())
    return IngestAck(accepted=1, queue_depth=depth)


@router.post("/batch", response_model=IngestAck, status_code=202)
async def ingest_batch(payload: TelemetryBatchIn):
    depth = 0
    for ev in payload.events:
        depth = await ingestion.enqueue(ev.model_dump())
    return IngestAck(accepted=len(payload.events), queue_depth=depth)
