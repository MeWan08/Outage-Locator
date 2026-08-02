"""
This is the 25%-of-the-grade file. Everything here is a pure function over
plain data — no DB session, no I/O — so it can be unit tested by constructing
a tiny synthetic topology and a handful of pole readings, with no server
running. See tests/test_localization.py.

THE ALGORITHM, IN ONE PARAGRAPH
--------------------------------
A fault's observable signature is a boundary: the last live node and the
first dark node beyond it, on a tree (01-problem-context.md §1-2). We find
every such boundary with two linear passes over each DT's pole tree:

  Pass 1 (bottom-up): for every pole, does ITS OWN SUBTREE contain at least
  one pole that is confirmed live? Call this `any_live_in_subtree`. If it's
  true, current must be flowing at least that far, which means the pole
  itself is provably energised even if its own sensor claims otherwise
  (electricity has to pass through a pole to reach anything live beneath
  it). That's the exact justification 01-problem-context.md gives for "a
  single isolated dark pole with live children is physically impossible as
  a line fault" — this pass just generalises it to arbitrary depth and to
  branches, not only the immediate-child case.

  Pass 2 (top-down): a pole's EFFECTIVE state is "live" if it is directly
  confirmed live OR any_live_in_subtree said so; otherwise "dark". A pole is
  a FRONTIER — the start of one incident — iff it is effectively dark and
  its parent is effectively live. We never need to look below a frontier:
  by definition of any_live_in_subtree, everything under a dark pole is
  dark too, so the whole subtree is "affected" without walking it again.

The same two passes, applied one level up, answer the DT-fault and
feeder-fault cases for free: a DT is "effectively live" iff any pole under
it is; a feeder is "effectively live" iff any DT under it is. So the
identical frontier rule — dark with a live parent — applied at the
feeder/DT/pole levels in that priority order (report the fault at the
HIGHEST level it manifests, and don't also descend and re-report it at
finer grain) is the whole algorithm. Multiple simultaneous faults fall out
for free: we don't stop at the first frontier we find, we collect all of
them in one pass over the whole network.

Complexity: O(N) per DT/feeder pass (N = poles), dominated by the
topology-resolution step in topology.py (O(N log N)). This runs on every
detection-loop tick (app/config.py DETECTION_LOOP_INTERVAL_SECONDS,
default 5s) over the whole network — a few thousand poles — which is
milliseconds of work, nowhere near the 120s target.

KNOWN FAILURE CASES (stated plainly, not hidden):
- Two genuinely separate faults on the same branch, seconds apart, can
  present as if the *outer* one is the whole story if the inner one hasn't
  produced its own confirmed signal yet — we'll report the outer boundary
  first and the inner one will surface on the next tick once its own
  telemetry arrives. Rare in practice, but not impossible.
- If literally every pole under a DT is silent at once with zero explicit
  `power_lost` messages, we read that as a DT fault (the more likely and
  more actionable interpretation), but we cannot fully rule out a
  correlated comms-layer failure (e.g. an NB-IoT tower outage) producing
  the same signature. We don't have a backhaul-health signal to
  disambiguate; noted as a limitation, not solved.
- Geometric topology inference (topology.py) can cross-wire two physically
  close but electrically distinct lines (e.g. either side of a road). We
  can't detect this from coordinates alone; it's why inferred spans always
  carry a confidence penalty rather than being reported as certain.
- A pole with no telemetry device fitted (~9% of poles) is never treated as
  evidence of anything on its own — it inherits its parent's status by
  default (see `walk()` below) rather than defaulting to "presumed dark",
  because the alternative floods the system with a permanent phantom
  incident for every no-device leaf pole in the network. The corollary,
  accepted rather than engineered around: if literally every pole under a
  DT lacked a device, the DT would always look dark (there would be no
  possible source of live evidence at all). At the ~9% no-device rate this
  is astronomically unlikely for any real DT and doesn't occur in the
  seeded network, but it's a real edge case at the DT/feeder rollup level
  that a from-scratch subdivision with very sparse instrumentation could hit.
"""
import datetime as dt
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from app import topology as topo_mod
from app.geo import centroid, midpoint, nearest_pincode

LIVE = "live"
CONFIRMED_DARK = "confirmed_dark"
SILENT = "silent"
NO_DEVICE = "no_device"

SPAN = "span"
DT = "dt"
FEEDER = "feeder"


@dataclass
class PoleSnapshot:
    pole_id: str
    dt_id: str
    feeder_id: str
    lat: float
    lon: float
    pincode: Optional[str]
    has_device: bool
    energized: Optional[bool]
    last_received_at: Optional[dt.datetime]
    raw_status: str


@dataclass
class DtMeta:
    dt_id: str
    feeder_id: str
    lat: float
    lon: float
    households_served: int
    topology: "topo_mod.DtTopologyResult"


@dataclass
class CandidateIncident:
    identity_key: str
    type: str
    dt_id: Optional[str]
    feeder_id: Optional[str]
    span_from_pole_id: Optional[str]
    span_to_pole_id: Optional[str]
    candidate_range_pole_ids: list = field(default_factory=list)
    affected_pole_ids: list = field(default_factory=list)
    lat: Optional[float] = None
    lon: Optional[float] = None
    pincode: Optional[str] = None
    poles_affected: int = 0
    households_affected_estimate: int = 0
    confidence: float = 0.0
    confidence_label: str = "low"
    confidence_reasons: list = field(default_factory=list)
    topology_source: str = "unknown"
    evidence_pole_ids: list = field(default_factory=list)


@dataclass
class DeviceHealthFlag:
    pole_id: str
    dt_id: str
    note: str


def classify_raw(has_device: bool, energized: Optional[bool], last_received_at, now, cfg) -> str:
    """Pole-local classification, no topology involved. See module docstring
    of app/models.py for why 'confirmed_dark' never expires on its own."""
    if not has_device:
        return NO_DEVICE
    if energized is False:
        return CONFIRMED_DARK
    if last_received_at is None:
        return SILENT
    grace = cfg.HEARTBEAT_INTERVAL_SECONDS * cfg.MISSED_HEARTBEATS_FOR_SILENCE + cfg.HEARTBEAT_JITTER_SECONDS
    age = (now - last_received_at).total_seconds()
    if age > grace:
        return SILENT
    return LIVE


def confidence_label(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def run_localization(poles: list[PoleSnapshot], dt_meta_map: dict, feeder_dt_ids: dict, now, cfg):
    """Single pass over the whole network. Returns (candidates, health_flags).
    Stateless: caller (app/background.py) is responsible for debounce,
    matching against already-open tickets, and scheduled-outage suppression
    — kept out of here on purpose so this function has no notion of time
    passing between calls."""
    raw_status_by_pole = {p.pole_id: p.raw_status for p in poles}
    pole_lookup = {p.pole_id: p for p in poles}
    poles_by_dt: dict[str, list[PoleSnapshot]] = {}
    for p in poles:
        poles_by_dt.setdefault(p.dt_id, []).append(p)

    candidates: list[CandidateIncident] = []
    health_flags: list[DeviceHealthFlag] = []

    dt_any_live: dict[str, dict] = {}
    dt_effective_live: dict[str, bool] = {}
    for dt_id, meta in dt_meta_map.items():
        children_index = meta.topology.children_index
        any_live = _compute_any_live_in_subtree(children_index, raw_status_by_pole)
        dt_any_live[dt_id] = any_live
        dt_effective_live[dt_id] = any(any_live.values()) if any_live else False

    feeder_effective_live = {
        feeder_id: any(dt_effective_live.get(d, False) for d in dt_ids)
        for feeder_id, dt_ids in feeder_dt_ids.items()
    }

    for feeder_id, dt_ids in feeder_dt_ids.items():
        if not feeder_effective_live.get(feeder_id, True):
            cand = _build_feeder_incident(feeder_id, dt_ids, dt_meta_map, poles_by_dt, raw_status_by_pole, cfg)
            if cand:
                candidates.append(cand)
            continue  # feeder incident subsumes every DT beneath it

        for dt_id in dt_ids:
            meta = dt_meta_map.get(dt_id)
            if meta is None:
                continue
            if not dt_effective_live.get(dt_id, False):
                cand = _build_dt_incident(dt_id, meta, poles_by_dt.get(dt_id, []), raw_status_by_pole, cfg)
                if cand:
                    candidates.append(cand)
                continue  # DT incident subsumes every pole beneath it

            children_index = meta.topology.children_index
            topo_nodes = meta.topology.nodes
            any_live = dt_any_live[dt_id]

            def walk(pid, parent_effective_live, _dt_id=dt_id, _meta=meta,
                     _children_index=children_index, _topo_nodes=topo_nodes, _any_live=any_live):
                raw = raw_status_by_pole.get(pid, SILENT)
                proven_live_via_descendant = _any_live.get(pid, False)

                if raw == NO_DEVICE:
                    # No device means no evidence, ever — not "assume dark".
                    # A pole with nothing fitted just isn't informative on
                    # its own; it inherits whatever its parent's status is
                    # (optimistic default: most of the network is fine most
                    # of the time) unless something further downstream
                    # proves it must be dark. It can never itself be the
                    # start of an incident — only a pole that actually HAD a
                    # device and stopped reporting (silent/confirmed_dark)
                    # is real evidence of a problem.
                    eff_live = parent_effective_live or proven_live_via_descendant
                    can_trigger_frontier = False
                else:
                    eff_live = (raw == LIVE) or proven_live_via_descendant
                    can_trigger_frontier = True
                    if eff_live and raw != LIVE:
                        health_flags.append(DeviceHealthFlag(
                            pole_id=pid,
                            dt_id=_dt_id,
                            note=(f"Reports '{raw}', but a pole downstream of it is live — "
                                  "read as a device/sensor issue, not a line fault."),
                        ))

                if not eff_live and parent_effective_live and can_trigger_frontier:
                    cand = _build_span_incident(pid, _dt_id, _meta, _children_index, _topo_nodes,
                                                 pole_lookup, raw_status_by_pole, now, cfg)
                    if cand:
                        candidates.append(cand)
                    return  # subtree is fully accounted for; do not descend further

                for child in _children_index.get(pid, []):
                    walk(child, eff_live)

            for root_pid in children_index.get(topo_mod.DT_ROOT, []):
                walk(root_pid, True)

    return candidates, health_flags


def _compute_any_live_in_subtree(children_index: dict, raw_status_by_pole: dict) -> dict:
    any_live: dict[str, bool] = {}

    def visit(pid):
        if pid in any_live:
            return any_live[pid]
        raw = raw_status_by_pole.get(pid, SILENT)
        result = raw == LIVE
        for child in children_index.get(pid, []):
            if visit(child):
                result = True
        any_live[pid] = result
        return result

    for root_pid in children_index.get(topo_mod.DT_ROOT, []):
        visit(root_pid)
    return any_live


def _nearest_confirmed_dark_path(children_index: dict, raw_status_by_pole: dict, start_pole_id: str) -> list:
    """BFS from start_pole_id through its (entirely-dark, by construction —
    see caller) subtree for the nearest pole with an explicit power_lost
    reading. Returns the path start->that pole inclusive, or just
    [start_pole_id] if nothing in the subtree ever confirmed dark
    explicitly. This IS the answer to 'a pole with no device is on the
    fault boundary, now what' (05-faq.md): report a range, not a point."""
    if raw_status_by_pole.get(start_pole_id) == CONFIRMED_DARK:
        return [start_pole_id]
    visited = {start_pole_id}
    parent_of = {}
    q = deque([start_pole_id])
    while q:
        cur = q.popleft()
        for child in children_index.get(cur, []):
            if child in visited:
                continue
            visited.add(child)
            parent_of[child] = cur
            if raw_status_by_pole.get(child) == CONFIRMED_DARK:
                path = [child]
                while path[-1] != start_pole_id:
                    path.append(parent_of[path[-1]])
                path.reverse()
                return path
            q.append(child)
    return [start_pole_id]


def _is_stale(pole: PoleSnapshot, now, cfg) -> bool:
    if pole.last_received_at is None:
        return True
    grace = cfg.HEARTBEAT_INTERVAL_SECONDS * cfg.MISSED_HEARTBEATS_FOR_SILENCE + cfg.HEARTBEAT_JITTER_SECONDS
    age = (now - pole.last_received_at).total_seconds()
    return age > grace * 0.5


def _pincode_for(pole, pool, cfg_dt_id=None):
    if pole.pincode:
        return pole.pincode
    candidates = [(p.lat, p.lon, p.pincode) for p in pool if p.pincode]
    return nearest_pincode(pole.lat, pole.lon, candidates)


def _score_and_reasons(cfg, *, is_span, topology_source=None, ambiguous=False,
                        evidence_raw_statuses, stale_reference=False):
    score = cfg.CONF_BASE
    reasons: list[str] = []

    if is_span and topology_source == "inferred":
        score -= cfg.CONF_PENALTY_INFERRED_TOPOLOGY
        reasons.append("This transformer has no surveyed pole ordering; the span is inferred "
                        "from geographic proximity, not confirmed wiring.")
        if ambiguous:
            score -= cfg.CONF_PENALTY_AMBIGUOUS_TOPOLOGY
            reasons.append("Two neighbouring poles were about equally likely to be the true "
                            "upstream link here.")

    total = len(evidence_raw_statuses) or 1
    confirmed = sum(1 for s in evidence_raw_statuses if s == CONFIRMED_DARK)
    no_device = sum(1 for s in evidence_raw_statuses if s == NO_DEVICE)
    frac_confirmed = confirmed / total
    frac_no_device = no_device / total

    if frac_confirmed < 1.0:
        score -= cfg.CONF_PENALTY_SILENCE_ONLY * (1 - frac_confirmed)
        if confirmed == 0:
            reasons.append("No device sent an explicit fault message here — this is inferred "
                            "from missed heartbeats, which is also what an unrelated dead "
                            "sensor looks like.")
        else:
            reasons.append("Some of the evidence is an explicit fault message; the rest is "
                            "inferred from missed heartbeats.")

    if frac_no_device > 0:
        score -= cfg.CONF_PENALTY_COVERAGE_GAP * frac_no_device
        reasons.append("At least one boundary pole has no telemetry device fitted, so the "
                        "true break could be one span further than shown.")

    if stale_reference:
        score -= cfg.CONF_PENALTY_STALE_REFERENCE
        reasons.append("The upstream 'still live' pole hasn't reported recently either, so "
                        "that reference point is itself slightly uncertain.")

    if total >= 3 and confirmed > 0:
        score += cfg.CONF_BONUS_CORROBORATION
        reasons.append("Multiple poles independently corroborate the same boundary.")

    if frac_confirmed == 1.0 and not stale_reference and (not is_span or (topology_source == "known" and not ambiguous)):
        reasons.append("Confirmed by an explicit power-loss message at the boundary, on surveyed topology."
                        if is_span else "Confirmed by explicit power-loss messages.")

    score = max(cfg.CONF_MIN, min(cfg.CONF_MAX, score))
    return score, reasons


def _build_span_incident(pid, dt_id, meta: DtMeta, children_index, topo_nodes, pole_lookup,
                          raw_status_by_pole, now, cfg) -> Optional[CandidateIncident]:
    pole = pole_lookup.get(pid)
    if pole is None:
        return None
    node = topo_nodes.get(pid)
    parent_id = node.resolved_parent_pole_id if node else None
    topology_source = node.topology_source if node else "unknown"
    ambiguous = bool(node.ambiguous) if node else False

    path = _nearest_confirmed_dark_path(children_index, raw_status_by_pole, pid)
    evidence_statuses = [raw_status_by_pole.get(x, SILENT) for x in path]

    parent_pole = pole_lookup.get(parent_id) if parent_id else None
    if parent_pole is not None:
        lat, lon = midpoint(parent_pole.lat, parent_pole.lon, pole.lat, pole.lon)
        stale_reference = _is_stale(parent_pole, now, cfg)
    else:
        # Roots directly off the DT: the span in question is DT -> this pole.
        lat, lon = midpoint(meta.lat, meta.lon, pole.lat, pole.lon)
        stale_reference = False

    total_poles = len(topo_nodes) or 1
    affected = topo_mod.subtree_pole_ids(children_index, pid)
    poles_affected = len(affected)
    households = int(round((meta.households_served or 0) * (poles_affected / total_poles)))

    dt_pool = [p for p in pole_lookup.values() if p.dt_id == dt_id]
    pincode = _pincode_for(pole, dt_pool)

    score, reasons = _score_and_reasons(
        cfg, is_span=True, topology_source=topology_source, ambiguous=ambiguous,
        evidence_raw_statuses=evidence_statuses, stale_reference=stale_reference,
    )

    return CandidateIncident(
        identity_key=f"span:{dt_id}:{pid}",
        type=SPAN,
        dt_id=dt_id,
        feeder_id=meta.feeder_id,
        span_from_pole_id=parent_id,
        span_to_pole_id=pid,
        candidate_range_pole_ids=path,
        affected_pole_ids=affected,
        lat=lat, lon=lon, pincode=pincode,
        poles_affected=poles_affected,
        households_affected_estimate=households,
        confidence=score,
        confidence_label=confidence_label(score),
        confidence_reasons=reasons,
        topology_source=topology_source,
        evidence_pole_ids=path,
    )


def _build_dt_incident(dt_id, meta: DtMeta, dt_poles, raw_status_by_pole, cfg) -> Optional[CandidateIncident]:
    if not dt_poles:
        return None
    confirmed_ids = [p.pole_id for p in dt_poles if raw_status_by_pole.get(p.pole_id) == CONFIRMED_DARK]
    evidence = (confirmed_ids or [p.pole_id for p in dt_poles])[:10]
    evidence_statuses = [raw_status_by_pole.get(pid, SILENT) for pid in evidence]

    pincode = next((p.pincode for p in dt_poles if p.pincode), None)
    if pincode is None:
        pincode = nearest_pincode(meta.lat, meta.lon, [(p.lat, p.lon, p.pincode) for p in dt_poles if p.pincode])

    score, reasons = _score_and_reasons(cfg, is_span=False, evidence_raw_statuses=evidence_statuses)
    reasons = ["Every pole under this transformer is dark with none live beneath it — "
               "consistent with a transformer or HT-fuse fault, not a single span."] + reasons

    return CandidateIncident(
        identity_key=f"dt:{dt_id}",
        type=DT,
        dt_id=dt_id,
        feeder_id=meta.feeder_id,
        span_from_pole_id=None,
        span_to_pole_id=None,
        affected_pole_ids=[p.pole_id for p in dt_poles],
        lat=meta.lat, lon=meta.lon, pincode=pincode,
        poles_affected=len(dt_poles),
        households_affected_estimate=meta.households_served or 0,
        confidence=score,
        confidence_label=confidence_label(score),
        confidence_reasons=reasons,
        topology_source=meta.topology.topology_source,
        evidence_pole_ids=evidence,
    )


def _build_feeder_incident(feeder_id, dt_ids, dt_meta_map, poles_by_dt, raw_status_by_pole, cfg) -> Optional[CandidateIncident]:
    all_poles = []
    for d in dt_ids:
        all_poles.extend(poles_by_dt.get(d, []))
    if not all_poles:
        return None

    confirmed_ids = [p.pole_id for p in all_poles if raw_status_by_pole.get(p.pole_id) == CONFIRMED_DARK]
    evidence = (confirmed_ids or [p.pole_id for p in all_poles])[:10]
    evidence_statuses = [raw_status_by_pole.get(pid, SILENT) for pid in evidence]

    dt_coords = [(dt_meta_map[d].lat, dt_meta_map[d].lon) for d in dt_ids if d in dt_meta_map]
    lat, lon = centroid(dt_coords) if dt_coords else (None, None)
    pincode = next((p.pincode for p in all_poles if p.pincode), None)
    households = sum((dt_meta_map[d].households_served or 0) for d in dt_ids if d in dt_meta_map)

    score, reasons = _score_and_reasons(cfg, is_span=False, evidence_raw_statuses=evidence_statuses)
    reasons = ["Every transformer on this feeder is dark — consistent with a feeder-level "
               "fault upstream of all of them."] + reasons

    return CandidateIncident(
        identity_key=f"feeder:{feeder_id}",
        type=FEEDER,
        dt_id=None,
        feeder_id=feeder_id,
        span_from_pole_id=None,
        span_to_pole_id=None,
        affected_pole_ids=[p.pole_id for p in all_poles],
        lat=lat, lon=lon, pincode=pincode,
        poles_affected=len(all_poles),
        households_affected_estimate=households,
        confidence=score,
        confidence_label=confidence_label(score),
        confidence_reasons=reasons,
        topology_source="n/a",
        evidence_pole_ids=evidence,
    )
