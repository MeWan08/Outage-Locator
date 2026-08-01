"""
Schema notes (see ARCHITECTURE.md for the full rationale):

- Pole is the one node type the algorithm reasons about. Substations, feeders
  and transformers are mostly bookkeeping / grouping — the radial network
  property (§1 of 01-problem-context.md) means every pole has at most one
  parent, so `resolved_parent_pole_id` is enough to reconstruct the whole
  tree per DT with a single indexed self-join / in-memory walk.

- `parent_pole_id` / `seq_on_line` are exactly what the registry CSV gives us
  (nullable for ~60% of DTs). `resolved_parent_pole_id` / `topology_source`
  are what topology.py computes at boot: pass the known value through
  untouched, or fill the gap with a geometry-inferred parent. Keeping both
  means we never lose the distinction between "the department told us this"
  and "we guessed this from coordinates" — that distinction is what feeds
  the confidence score.

- PoleState holds the latest raw facts per pole. Deliberately dumb: it does
  not store a computed "is this pole dark" boolean, because that computation
  depends on the current time and on config (heartbeat interval, grace
  windows). Storing a derived boolean invites it to go stale. Derivation
  lives in localization.py as a pure function over (PoleState, now, config).

- TelemetryEvent is an append-only log, kept even for duplicates /
  out-of-order messages (flagged, not dropped) so the system's decisions are
  auditable after the fact.
"""
import datetime as dt

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON
)
from sqlalchemy.orm import relationship

from app.db import Base


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


class Substation(Base):
    __tablename__ = "substations"
    substation_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)


class Feeder(Base):
    __tablename__ = "feeders"
    feeder_id = Column(String, primary_key=True)
    substation_id = Column(String, ForeignKey("substations.substation_id"), nullable=False)
    name = Column(String, nullable=False)


class Transformer(Base):
    __tablename__ = "transformers"
    dt_id = Column(String, primary_key=True)
    feeder_id = Column(String, ForeignKey("feeders.feeder_id"), nullable=False, index=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    capacity_kva = Column(Integer, nullable=True)
    households_served = Column(Integer, nullable=True)
    # Filled by topology.py at boot: 'known' if >=95% of its poles carry a
    # recorded parent_pole_id, else 'inferred'.
    topology_source = Column(String, default="unknown")


class Pole(Base):
    __tablename__ = "poles"
    pole_id = Column(String, primary_key=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    feeder_id = Column(String, ForeignKey("feeders.feeder_id"), nullable=False, index=True)
    dt_id = Column(String, ForeignKey("transformers.dt_id"), nullable=False, index=True)

    # As imported from the registry CSV. Null for the ~60% missing case.
    seq_on_line = Column(Integer, nullable=True)
    parent_pole_id = Column(String, nullable=True)

    # As resolved by topology.py at boot.
    resolved_parent_pole_id = Column(String, nullable=True, index=True)
    topology_source = Column(String, nullable=False, default="unknown")  # 'known' | 'inferred'
    depth = Column(Integer, nullable=True)  # distance from DT root in the resolved tree

    pole_type = Column(String, nullable=True)
    ward = Column(String, nullable=True)
    pincode = Column(String, nullable=True)
    pincode_source = Column(String, nullable=True)  # 'registry' | 'nearest-neighbour'

    device_id = Column(String, nullable=True, unique=True, index=True)


class Device(Base):
    """
    Tracks per-device sequence/boot state, used purely for de-duplication and
    ordering. Kept separate from Pole/PoleState because `device_id` is the
    unstable identifier (devices get swapped) while `pole_id` is the stable
    one we trust for location, per 02-data-and-systems.md §2.
    """
    __tablename__ = "devices"
    device_id = Column(String, primary_key=True)
    current_pole_id = Column(String, nullable=True, index=True)
    last_seq = Column(Integer, nullable=True)
    boot_count = Column(Integer, default=0)
    last_fw = Column(String, nullable=True)
    first_seen_at = Column(DateTime(timezone=True), default=utcnow)
    last_seen_at = Column(DateTime(timezone=True), default=utcnow)


class PoleState(Base):
    """One row per pole: the latest raw facts we have heard. See module
    docstring — no derived status is stored here on purpose."""
    __tablename__ = "pole_states"
    pole_id = Column(String, ForeignKey("poles.pole_id"), primary_key=True)
    device_id = Column(String, nullable=True)
    energized = Column(Boolean, nullable=True)  # None = never heard from
    last_event = Column(String, nullable=True)  # heartbeat|power_lost|power_restored|boot
    last_device_ts = Column(DateTime(timezone=True), nullable=True)
    last_received_at = Column(DateTime(timezone=True), nullable=True)
    last_seq = Column(Integer, nullable=True)
    battery_mv = Column(Integer, nullable=True)
    rssi = Column(Integer, nullable=True)
    fw = Column(String, nullable=True)
    # Timestamp of the most recent power_lost -> power_restored transition,
    # used by the restoration-stability check.
    became_live_at = Column(DateTime(timezone=True), nullable=True)
    became_dark_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TelemetryEvent(Base):
    """Append-only raw log. Nothing is ever deleted from this table."""
    __tablename__ = "telemetry_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String, index=True, nullable=False)
    pole_id = Column(String, index=True, nullable=False)
    event = Column(String, nullable=False)
    energized = Column(Boolean, nullable=False)
    device_ts = Column(DateTime(timezone=True), nullable=False)
    seq = Column(Integer, nullable=False)
    battery_mv = Column(Integer, nullable=True)
    rssi = Column(Integer, nullable=True)
    fw = Column(String, nullable=True)
    received_at = Column(DateTime(timezone=True), default=utcnow, index=True)
    is_duplicate = Column(Boolean, default=False)
    is_out_of_order = Column(Boolean, default=False)
    applied = Column(Boolean, default=True)  # False if dropped as dup/stale-boot


class ScheduledOutage(Base):
    __tablename__ = "scheduled_outages"
    id = Column(String, primary_key=True)
    scope = Column(String, nullable=False)  # 'feeder' | 'dt'
    target_id = Column(String, nullable=False, index=True)
    start = Column(DateTime(timezone=True), nullable=False)
    end = Column(DateTime(timezone=True), nullable=False)
    reason = Column(String, nullable=True)


class Incident(Base):
    """A located fault, i.e. what the brief calls a 'ticket'."""
    __tablename__ = "incidents"
    id = Column(String, primary_key=True)  # e.g. INC-000123
    type = Column(String, nullable=False)  # 'span' | 'dt' | 'feeder' | 'sensor_fault'
    dt_id = Column(String, nullable=True, index=True)
    feeder_id = Column(String, nullable=True, index=True)

    span_from_pole_id = Column(String, nullable=True)
    span_to_pole_id = Column(String, nullable=True)
    candidate_range_pole_ids = Column(JSON, nullable=True)  # widened boundary if coverage gap

    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    pincode = Column(String, nullable=True)

    poles_affected = Column(Integer, default=0)
    households_affected_estimate = Column(Integer, default=0)

    confidence = Column(Float, nullable=False)
    confidence_label = Column(String, nullable=False)  # high|medium|low
    confidence_reasons = Column(JSON, nullable=False, default=list)
    topology_source = Column(String, nullable=False, default="unknown")

    status = Column(String, nullable=False, default="detected")
    # detected -> acknowledged -> crew_assigned -> resolved -> verified -> closed
    suppressed_by_schedule_id = Column(String, nullable=True)

    crew_name = Column(String, nullable=True)
    evidence_pole_ids = Column(JSON, nullable=False, default=list)

    ai_briefing = Column(Text, nullable=True)
    ai_briefing_generated_at = Column(DateTime(timezone=True), nullable=True)
    ai_briefing_source = Column(String, nullable=True)  # 'model' | 'template-fallback'

    first_detected_at = Column(DateTime(timezone=True), default=utcnow)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    crew_assigned_at = Column(DateTime(timezone=True), nullable=True)
    resolved_marked_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    events = relationship("IncidentEvent", back_populates="incident", cascade="all, delete-orphan")


class IncidentEvent(Base):
    """Audit trail: every automatic or operator action on an incident."""
    __tablename__ = "incident_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String, ForeignKey("incidents.id"), nullable=False, index=True)
    at = Column(DateTime(timezone=True), default=utcnow)
    actor = Column(String, nullable=False)  # 'system' | 'operator'
    action = Column(String, nullable=False)
    note = Column(Text, nullable=True)

    incident = relationship("Incident", back_populates="events")
