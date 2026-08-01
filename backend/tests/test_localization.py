import datetime as dt

from app.localization import (
    CONFIRMED_DARK, DT, FEEDER, LIVE, NO_DEVICE, SILENT, SPAN,
    classify_raw, run_localization,
)
from app.topology import PoleRecord
from tests.helpers import NOW, cfg, make_dt_meta, snap


def test_known_topology_simple_span_fault():
    """The canonical case: a known line, one break, one ticket."""
    records = [
        PoleRecord("P1", 12.0001, 77.0000, seq_on_line=1),
        PoleRecord("P2", 12.0002, 77.0000, seq_on_line=2, parent_pole_id="P1"),
        PoleRecord("P3", 12.0003, 77.0000, seq_on_line=3, parent_pole_id="P2"),
        PoleRecord("P4", 12.0004, 77.0000, seq_on_line=4, parent_pole_id="P3"),
    ]
    dt_meta = make_dt_meta("D1", "F1", 12.0000, 77.0000, 40, records)
    snaps = [
        snap("P1", "D1", "F1", 12.0001, 77.0000, LIVE, last_received_at=NOW),
        snap("P2", "D1", "F1", 12.0002, 77.0000, LIVE, last_received_at=NOW),
        snap("P3", "D1", "F1", 12.0003, 77.0000, CONFIRMED_DARK),
        snap("P4", "D1", "F1", 12.0004, 77.0000, SILENT),
    ]
    candidates, flags = run_localization(snaps, {"D1": dt_meta}, {"F1": ["D1"]}, NOW, cfg())

    assert len(candidates) == 1
    inc = candidates[0]
    assert inc.type == SPAN
    assert inc.span_from_pole_id == "P2"
    assert inc.span_to_pole_id == "P3"
    assert inc.poles_affected == 2  # P3, P4
    assert inc.confidence_label == "high"
    assert flags == []


def test_dt_level_fault_is_one_incident_not_many():
    records = [
        PoleRecord(f"P{i}", 12.0000 + i * 0.0001, 77.0000, seq_on_line=i,
                    parent_pole_id=(f"P{i-1}" if i > 1 else None))
        for i in range(1, 6)
    ]
    dt_meta = make_dt_meta("D1", "F1", 12.0000, 77.0000, 100, records)
    # A second, unrelated, healthy DT on the same feeder — otherwise "the
    # whole DT is dark" and "the whole feeder is dark" are indistinguishable
    # and the (correct) feeder-level rollup would mask what this test wants
    # to isolate.
    other_dt = make_dt_meta("D2", "F1", 12.0100, 77.0100, 50,
                             [PoleRecord("Q1", 12.0101, 77.0100, seq_on_line=1)])
    snaps = [
        snap(f"P{i}", "D1", "F1", 12.0000 + i * 0.0001, 77.0000, CONFIRMED_DARK)
        for i in range(1, 6)
    ] + [snap("Q1", "D2", "F1", 12.0101, 77.0100, LIVE, last_received_at=NOW)]

    candidates, flags = run_localization(snaps, {"D1": dt_meta, "D2": other_dt}, {"F1": ["D1", "D2"]}, NOW, cfg())

    assert len(candidates) == 1
    assert candidates[0].type == DT
    assert candidates[0].dt_id == "D1"
    assert candidates[0].poles_affected == 5
    assert candidates[0].households_affected_estimate == 100


def test_feeder_level_fault_subsumes_its_dts():
    dt1 = make_dt_meta("D1", "F1", 12.0000, 77.0000, 20, [PoleRecord("A1", 12.0001, 77.0000, seq_on_line=1)])
    dt2 = make_dt_meta("D2", "F1", 12.0010, 77.0010, 30, [PoleRecord("B1", 12.0011, 77.0010, seq_on_line=1)])
    snaps = [
        snap("A1", "D1", "F1", 12.0001, 77.0000, CONFIRMED_DARK),
        snap("B1", "D2", "F1", 12.0011, 77.0010, CONFIRMED_DARK),
    ]
    candidates, flags = run_localization(snaps, {"D1": dt1, "D2": dt2}, {"F1": ["D1", "D2"]}, NOW, cfg())

    assert len(candidates) == 1
    assert candidates[0].type == FEEDER
    assert candidates[0].poles_affected == 2
    assert candidates[0].households_affected_estimate == 50


def test_sensor_only_fault_is_not_reported_as_outage():
    """The doc's core example, generalised: a pole reads dark/silent but a
    descendant is confirmed live — electrically impossible as a real fault,
    so it must be flagged as a device issue, not turned into a ticket."""
    records = [
        PoleRecord("P1", 12.0001, 77.0000, seq_on_line=1),
        PoleRecord("P2", 12.0002, 77.0000, seq_on_line=2, parent_pole_id="P1"),
        PoleRecord("P3", 12.0003, 77.0000, seq_on_line=3, parent_pole_id="P2"),
    ]
    dt_meta = make_dt_meta("D1", "F1", 12.0000, 77.0000, 40, records)
    snaps = [
        snap("P1", "D1", "F1", 12.0001, 77.0000, LIVE, last_received_at=NOW),
        snap("P2", "D1", "F1", 12.0002, 77.0000, SILENT),   # P2's own sensor died
        snap("P3", "D1", "F1", 12.0003, 77.0000, LIVE, last_received_at=NOW),  # but downstream is fine
    ]
    candidates, flags = run_localization(snaps, {"D1": dt_meta}, {"F1": ["D1"]}, NOW, cfg())

    assert candidates == []
    assert len(flags) == 1
    assert flags[0].pole_id == "P2"


def test_branch_point_only_the_dark_branch_is_reported():
    records = [
        PoleRecord("R", 12.0000, 77.0000, seq_on_line=1),
        PoleRecord("A1", 12.0010, 77.0000, seq_on_line=2, parent_pole_id="R"),   # live branch
        PoleRecord("B1", 12.0000, 77.0010, seq_on_line=2, parent_pole_id="R"),   # dark branch
        PoleRecord("B2", 12.0000, 77.0020, seq_on_line=3, parent_pole_id="B1"),
    ]
    dt_meta = make_dt_meta("D1", "F1", 11.9990, 76.9990, 80, records)
    snaps = [
        snap("R", "D1", "F1", 12.0000, 77.0000, LIVE, last_received_at=NOW),
        snap("A1", "D1", "F1", 12.0010, 77.0000, LIVE, last_received_at=NOW),
        snap("B1", "D1", "F1", 12.0000, 77.0010, CONFIRMED_DARK),
        snap("B2", "D1", "F1", 12.0000, 77.0020, SILENT),
    ]
    candidates, flags = run_localization(snaps, {"D1": dt_meta}, {"F1": ["D1"]}, NOW, cfg())

    assert len(candidates) == 1
    inc = candidates[0]
    assert inc.span_from_pole_id == "R"
    assert inc.span_to_pole_id == "B1"
    assert inc.poles_affected == 2  # B1, B2 — A1's live branch is untouched
    assert flags == []  # R is genuinely live (proven via A1), no false device flag


def test_coverage_gap_widens_range_and_lowers_confidence():
    records = [
        PoleRecord("P1", 12.0001, 77.0000, seq_on_line=1),
        PoleRecord("P2", 12.0002, 77.0000, seq_on_line=2, parent_pole_id="P1"),  # no device fitted
        PoleRecord("P3", 12.0003, 77.0000, seq_on_line=3, parent_pole_id="P2"),  # confirmed dark
    ]
    dt_meta = make_dt_meta("D1", "F1", 12.0000, 77.0000, 40, records)
    snaps = [
        snap("P1", "D1", "F1", 12.0001, 77.0000, LIVE, last_received_at=NOW),
        snap("P2", "D1", "F1", 12.0002, 77.0000, NO_DEVICE, has_device=False),
        snap("P3", "D1", "F1", 12.0003, 77.0000, CONFIRMED_DARK),
    ]
    candidates, flags = run_localization(snaps, {"D1": dt_meta}, {"F1": ["D1"]}, NOW, cfg())

    assert len(candidates) == 1
    inc = candidates[0]
    assert inc.span_to_pole_id == "P2"                       # frontier: first non-live pole
    assert inc.candidate_range_pole_ids == ["P2", "P3"]       # widened to the nearest confirmed signal
    assert inc.poles_affected == 2
    assert inc.confidence < 0.90
    assert any("no telemetry device" in r for r in inc.confidence_reasons)


def test_inferred_topology_is_less_confident_than_known_for_the_same_pattern():
    known = make_dt_meta("DK", "F1", 12.0000, 77.0000, 40, [
        PoleRecord("K1", 12.0001, 77.0000, seq_on_line=1),
        PoleRecord("K2", 12.0002, 77.0000, seq_on_line=2, parent_pole_id="K1"),
    ])
    unknown = make_dt_meta("DU", "F2", 12.0000, 77.0000, 40, [
        PoleRecord("U1", 12.0001, 77.0000),
        PoleRecord("U2", 12.0002, 77.0000),
    ])
    snaps_known = [
        snap("K1", "DK", "F1", 12.0001, 77.0000, LIVE, last_received_at=NOW),
        snap("K2", "DK", "F1", 12.0002, 77.0000, CONFIRMED_DARK),
    ]
    snaps_unknown = [
        snap("U1", "DU", "F2", 12.0001, 77.0000, LIVE, last_received_at=NOW),
        snap("U2", "DU", "F2", 12.0002, 77.0000, CONFIRMED_DARK),
    ]
    known_cands, _ = run_localization(snaps_known, {"DK": known}, {"F1": ["DK"]}, NOW, cfg())
    unknown_cands, _ = run_localization(snaps_unknown, {"DU": unknown}, {"F2": ["DU"]}, NOW, cfg())

    assert known_cands[0].topology_source == "known"
    assert unknown_cands[0].topology_source == "inferred"
    assert unknown_cands[0].confidence < known_cands[0].confidence


def test_multiple_simultaneous_faults_are_all_found_independently():
    records = [
        PoleRecord("R", 12.0000, 77.0000, seq_on_line=1),
        PoleRecord("A1", 12.0010, 77.0000, seq_on_line=2, parent_pole_id="R"),
        PoleRecord("A2", 12.0020, 77.0000, seq_on_line=3, parent_pole_id="A1"),  # dark branch A
        PoleRecord("B1", 12.0000, 77.0010, seq_on_line=2, parent_pole_id="R"),
        PoleRecord("B2", 12.0000, 77.0020, seq_on_line=3, parent_pole_id="B1"),  # dark branch B
    ]
    dt_meta = make_dt_meta("D1", "F1", 11.9990, 76.9990, 120, records)
    snaps = [
        snap("R", "D1", "F1", 12.0000, 77.0000, LIVE, last_received_at=NOW),
        snap("A1", "D1", "F1", 12.0010, 77.0000, LIVE, last_received_at=NOW),
        snap("A2", "D1", "F1", 12.0020, 77.0000, CONFIRMED_DARK),
        snap("B1", "D1", "F1", 12.0000, 77.0010, LIVE, last_received_at=NOW),
        snap("B2", "D1", "F1", 12.0000, 77.0020, CONFIRMED_DARK),
    ]
    candidates, flags = run_localization(snaps, {"D1": dt_meta}, {"F1": ["D1"]}, NOW, cfg())

    assert len(candidates) == 2
    assert {c.span_to_pole_id for c in candidates} == {"A2", "B2"}
    assert all(c.type == SPAN for c in candidates)


def test_everything_live_produces_nothing():
    records = [
        PoleRecord("P1", 12.0001, 77.0000, seq_on_line=1),
        PoleRecord("P2", 12.0002, 77.0000, seq_on_line=2, parent_pole_id="P1"),
    ]
    dt_meta = make_dt_meta("D1", "F1", 12.0000, 77.0000, 40, records)
    snaps = [
        snap("P1", "D1", "F1", 12.0001, 77.0000, LIVE, last_received_at=NOW),
        snap("P2", "D1", "F1", 12.0002, 77.0000, LIVE, last_received_at=NOW),
    ]
    candidates, flags = run_localization(snaps, {"D1": dt_meta}, {"F1": ["D1"]}, NOW, cfg())
    assert candidates == []
    assert flags == []


# --- classify_raw: the pole-local, topology-free classifier ---

def test_classify_raw_no_device():
    assert classify_raw(False, None, None, NOW, cfg()) == NO_DEVICE


def test_classify_raw_explicit_power_lost_never_expires():
    old = NOW - dt.timedelta(hours=5)
    assert classify_raw(True, False, old, NOW, cfg()) == CONFIRMED_DARK


def test_classify_raw_recent_heartbeat_is_live():
    recent = NOW - dt.timedelta(minutes=5)
    assert classify_raw(True, True, recent, NOW, cfg()) == LIVE


def test_classify_raw_overdue_heartbeat_is_silent():
    old = NOW - dt.timedelta(hours=2)
    assert classify_raw(True, True, old, NOW, cfg()) == SILENT


def test_classify_raw_never_heard_from_is_silent():
    assert classify_raw(True, None, None, NOW, cfg()) == SILENT
