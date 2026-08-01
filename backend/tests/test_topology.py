from app.topology import PoleRecord, resolve_dt_topology, subtree_pole_ids


def test_known_topology_passes_through_untouched():
    poles = [
        PoleRecord("P1", 12.0001, 77.0000, seq_on_line=1, parent_pole_id=None),
        PoleRecord("P2", 12.0002, 77.0000, seq_on_line=2, parent_pole_id="P1"),
        PoleRecord("P3", 12.0003, 77.0000, seq_on_line=3, parent_pole_id="P2"),
    ]
    res = resolve_dt_topology("D1", 12.0000, 77.0000, poles)
    assert res.topology_source == "known"
    assert res.nodes["P2"].resolved_parent_pole_id == "P1"
    assert res.nodes["P2"].topology_source == "known"
    assert res.nodes["P1"].resolved_parent_pole_id is None


def test_fully_unknown_topology_is_inferred_geometrically():
    poles = [
        PoleRecord("Q1", 12.0001, 77.0000),
        PoleRecord("Q2", 12.0002, 77.0000),
        PoleRecord("Q3", 12.0003, 77.0000),
    ]
    res = resolve_dt_topology("D2", 12.0000, 77.0000, poles)
    assert res.topology_source == "inferred"
    # Chain should reconstruct the physical line order from coordinates alone.
    assert res.nodes["Q2"].resolved_parent_pole_id == "Q1"
    assert res.nodes["Q3"].resolved_parent_pole_id == "Q2"
    assert all(n.topology_source == "inferred" for n in res.nodes.values())


def test_mixed_known_and_unknown_is_partial():
    poles = [
        PoleRecord("K1", 12.0001, 77.0000, seq_on_line=1, parent_pole_id=None),
        PoleRecord("U1", 12.0002, 77.0000),  # unknown, geometrically right after K1
    ]
    res = resolve_dt_topology("D3", 12.0000, 77.0000, poles)
    assert res.topology_source == "partial"
    assert res.nodes["U1"].resolved_parent_pole_id == "K1"
    assert res.nodes["U1"].topology_source == "inferred"


def test_cyclic_registry_data_is_severed_not_crashed():
    poles = [
        PoleRecord("R1", 12.0001, 77.0000, seq_on_line=2, parent_pole_id="R2"),
        PoleRecord("R2", 12.0002, 77.0000, seq_on_line=1, parent_pole_id="R1"),
    ]
    res = resolve_dt_topology("D4", 12.0000, 77.0000, poles)
    # Whatever the resolution, it must be a valid tree: exactly one root.
    roots = [pid for pid, n in res.nodes.items() if n.resolved_parent_pole_id is None]
    assert len(roots) == 1


def test_subtree_pole_ids_includes_branches():
    poles = [
        PoleRecord("P1", 12.0001, 77.0000, seq_on_line=1),
        PoleRecord("P2", 12.0002, 77.0000, seq_on_line=2, parent_pole_id="P1"),
        PoleRecord("P3", 12.0003, 77.0001, seq_on_line=3, parent_pole_id="P2"),
        PoleRecord("P4", 12.0003, 77.0002, seq_on_line=3, parent_pole_id="P2"),
    ]
    res = resolve_dt_topology("D5", 12.0000, 77.0000, poles)
    sub = subtree_pole_ids(res.children_index, "P2")
    assert set(sub) == {"P2", "P3", "P4"}
