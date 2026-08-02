import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field

EventType = Literal["heartbeat", "power_lost", "power_restored", "boot"]


class TelemetryIn(BaseModel):
    """One message as a pole-top device would actually send it. `pole_id` is
    trusted for location; `device_id`+`seq` is trusted for ordering/dedup —
    see app/ingestion.py."""
    device_id: str
    pole_id: str
    event: EventType
    energized: bool
    ts: dt.datetime = Field(description="Device clock — can drift, don't trust for ordering")
    seq: int = Field(description="Monotonic per device, resets to 0 on boot")
    battery_mv: Optional[int] = None
    rssi: Optional[int] = None
    fw: Optional[str] = None


class TelemetryBatchIn(BaseModel):
    events: list[TelemetryIn]


class IngestAck(BaseModel):
    accepted: int
    queue_depth: int


class IncidentOut(BaseModel):
    id: str
    type: str
    dt_id: Optional[str]
    feeder_id: Optional[str]
    span_from_pole_id: Optional[str]
    span_to_pole_id: Optional[str]
    candidate_range_pole_ids: list
    lat: Optional[float]
    lon: Optional[float]
    pincode: Optional[str]
    poles_affected: int
    households_affected_estimate: int
    confidence: float
    confidence_label: str
    confidence_reasons: list
    topology_source: str
    status: str
    suppressed_by_schedule_id: Optional[str]
    crew_name: Optional[str]
    evidence_pole_ids: list
    ai_briefing: Optional[str]
    ai_briefing_source: Optional[str]
    first_detected_at: dt.datetime
    acknowledged_at: Optional[dt.datetime]
    crew_assigned_at: Optional[dt.datetime]
    resolved_marked_at: Optional[dt.datetime]
    verified_at: Optional[dt.datetime]
    closed_at: Optional[dt.datetime]
    updated_at: dt.datetime

    class Config:
        from_attributes = True


class AssignCrewIn(BaseModel):
    crew_name: str


class ResolveResult(BaseModel):
    incident_id: str
    status: str
    poles_still_dark: int
    poles_total: int
    message: str


class ScheduledOutageIn(BaseModel):
    scope: Literal["feeder", "dt"]
    target_id: str
    start: dt.datetime
    end: dt.datetime
    reason: Optional[str] = None


class SimulatorFaultIn(BaseModel):
    kind: Literal["span", "dt", "feeder", "device_only"]
    dt_id: Optional[str] = None
    feeder_id: Optional[str] = None
    pole_id: Optional[str] = None
    # If true, the affected devices never send their dying `power_lost`
    # message (the ~30% case from 02-data-and-systems.md) — the fault only
    # shows up as a missed heartbeat.
    silent_failure: bool = False


class SimulatorRepairIn(BaseModel):
    incident_id: str


class SimulatorStormIn(BaseModel):
    count: int = 3
