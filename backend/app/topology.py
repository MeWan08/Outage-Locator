"""
The central design problem of the assignment (02-data-and-systems.md §3):
for ~60% of transformers we know every pole's location but not which pole
feeds which. This module is where that gets resolved.

Approach: geometric minimum-spanning-tree inference, rooted at the
transformer, for the poles that are missing a recorded parent. Where a
parent IS recorded, we trust it completely and never override it — inference
only fills gaps, never second-guesses the survey.

Why MST and not, say, nearest-neighbour-only chaining: nearest-neighbour
greedily picks whatever is closest to the LAST pole added, which can produce
long unrealistic detours on branchy networks. A minimum spanning tree rooted
at the DT asks a better question — "what is the cheapest way to connect
every pole back to the transformer" — which matches the physical reality
that LT lines are built to minimise conductor run, and it naturally produces
branches (a real property of these networks, see 01-problem-context.md §1)
wherever that's cheaper than one long line.

Complexity: O(N log N) per DT with a binary heap (N = poles on that DT, up
to ~240 per 02-data-and-systems.md §1), run once at boot and cached. Re-run
only if the registry changes.

Known failure mode, stated plainly: geometric proximity is a proxy for
"probably the same line," not a certainty. Two parallel LT lines running
close together (e.g. either side of a road) will fool this into cross-wiring
poles that are geometrically near each other but electrically on different
lines. We can't detect that from coordinates alone — it's why inferred spans
carry a confidence penalty and why `04-evaluation` explicitly does not
require a perfect answer, only an honest one. See DECISIONS.md for the
alternative we considered (learn topology from correlated outage history)
and why we scoped it out.
"""
from dataclasses import dataclass, field
from typing import Optional
import heapq

from app.geo import haversine_m

DT_ROOT = "__DT_ROOT__"

# If the runner-up candidate parent is within this ratio of the best
# candidate's distance, the inferred edge is flagged ambiguous (two poles
# about equally plausible as the true parent).
AMBIGUITY_RATIO = 1.4


@dataclass
class PoleRecord:
    pole_id: str
    lat: float
    lon: float
    seq_on_line: Optional[int] = None
    parent_pole_id: Optional[str] = None


@dataclass
class ResolvedNode:
    pole_id: str
    resolved_parent_pole_id: Optional[str]  # None means "parents directly to the DT"
    topology_source: str  # 'known' | 'inferred'
    depth: int = 0
    ambiguous: bool = False
    runner_up_parent_pole_id: Optional[str] = None


@dataclass
class DtTopologyResult:
    dt_id: str
    nodes: dict = field(default_factory=dict)  # pole_id -> ResolvedNode
    topology_source: str = "known"  # 'known' | 'inferred' | 'partial'
    children_index: dict = field(default_factory=dict)  # pole_id_or_DT_ROOT -> [child pole_id, ...]


def resolve_dt_topology(dt_id: str, dt_lat: float, dt_lon: float, poles: list[PoleRecord]) -> DtTopologyResult:
    if not poles:
        return DtTopologyResult(dt_id=dt_id, nodes={}, topology_source="known", children_index={})

    known = [p for p in poles if p.seq_on_line is not None]
    unknown = [p for p in poles if p.seq_on_line is None]

    nodes: dict[str, ResolvedNode] = {}

    # Known poles pass through untouched. seq_on_line == 1 (or an explicit
    # parent of None with a known seq) means "roots directly at the DT."
    known_ids = {p.pole_id for p in known}
    for p in known:
        parent = p.parent_pole_id
        if parent is not None and parent not in known_ids and parent not in {u.pole_id for u in unknown}:
            # Defensive: registry points to a pole outside this DT's set.
            # Treat as a root rather than crash the whole DT's resolution.
            parent = None
        nodes[p.pole_id] = ResolvedNode(
            pole_id=p.pole_id,
            resolved_parent_pole_id=parent,
            topology_source="known",
        )

    if unknown:
        _infer_unknown_parents(dt_lat, dt_lon, known, unknown, nodes)

    _assign_depth_and_detect_cycles(nodes)

    children_index = _build_children_index(nodes)

    if not unknown:
        source = "known"
    elif not known:
        source = "inferred"
    else:
        source = "partial"

    return DtTopologyResult(dt_id=dt_id, nodes=nodes, topology_source=source, children_index=children_index)


def _infer_unknown_parents(dt_lat, dt_lon, known: list[PoleRecord], unknown: list[PoleRecord], nodes: dict):
    """Prim's MST growth. The 'in-tree' frontier starts as the DT root plus
    every known pole (they already have a confirmed path home); we then
    repeatedly attach whichever remaining unknown pole is closest to
    anything already in the tree."""
    coords = {p.pole_id: (p.lat, p.lon) for p in known + unknown}
    coords[DT_ROOT] = (dt_lat, dt_lon)

    in_tree = {DT_ROOT} | {p.pole_id for p in known}
    remaining = {p.pole_id for p in unknown}

    # heap of (distance, candidate_pole_id, from_node_id)
    heap = []

    def push_candidates(from_id):
        flat, flon = coords[from_id]
        for rid in remaining:
            rlat, rlon = coords[rid]
            d = haversine_m(flat, flon, rlat, rlon)
            heapq.heappush(heap, (d, rid, from_id))

    for seed in in_tree:
        push_candidates(seed)

    # Standard lazy-deletion Prim's: pop the globally nearest (in-tree-node,
    # remaining-node) pair; if the remaining-node was already attached since
    # this heap entry was pushed, it's stale — skip it.
    while remaining:
        dist, cand_id, from_id = heapq.heappop(heap)
        if cand_id not in remaining:
            continue  # stale heap entry from before cand_id was attached

        parent = from_id if from_id != DT_ROOT else None
        nodes[cand_id] = ResolvedNode(
            pole_id=cand_id,
            resolved_parent_pole_id=parent,
            topology_source="inferred",
        )
        remaining.discard(cand_id)
        in_tree.add(cand_id)
        push_candidates(cand_id)

    # Ambiguity pass: for each inferred pole, compare its chosen parent's
    # distance against the next-nearest in-tree-at-the-time alternative.
    # We approximate "in tree at the time" with "in tree at the end minus
    # the pole itself," which is a conservative (slightly pessimistic, i.e.
    # flags a bit more as ambiguous) stand-in that avoids re-running the
    # whole growth order-sensitively — documented as an approximation.
    all_ids = list(coords.keys())
    for p in unknown:
        node = nodes[p.pole_id]
        chosen_parent = node.resolved_parent_pole_id or DT_ROOT
        plat, plon = coords[p.pole_id]
        best_dist = haversine_m(plat, plon, *coords[chosen_parent])
        runner_up_id, runner_up_dist = None, float("inf")
        for other_id in all_ids:
            if other_id in (p.pole_id, chosen_parent):
                continue
            d = haversine_m(plat, plon, *coords[other_id])
            if d < runner_up_dist:
                runner_up_dist, runner_up_id = d, other_id
        if runner_up_id and best_dist > 0 and (runner_up_dist / best_dist) < AMBIGUITY_RATIO:
            node.ambiguous = True
            node.runner_up_parent_pole_id = None if runner_up_id == DT_ROOT else runner_up_id


def _assign_depth_and_detect_cycles(nodes: dict[str, ResolvedNode]):
    """Walk each pole's parent chain to compute depth from the DT root, and
    defensively sever any cycle or dangling pointer encountered along the
    way. Inferred edges can't form a cycle by construction (Prim's only ever
    attaches a new node to something already confirmed in-tree) — this only
    guards against malformed 'known' data from the registry (e.g. two poles
    each listed as the other's parent). Better to silently re-root a bad
    sub-chain than to crash or infinite-loop on one bad CSV row."""
    for pole_id in nodes:
        seen = {pole_id}
        cur = pole_id
        depth = 0
        while True:
            cur_node = nodes[cur]
            parent = cur_node.resolved_parent_pole_id
            if parent is None:
                break
            if parent not in nodes or parent in seen:
                cur_node.resolved_parent_pole_id = None  # sever at the source of the problem
                break
            seen.add(parent)
            cur = parent
            depth += 1
        nodes[pole_id].depth = depth


def _build_children_index(nodes: dict[str, ResolvedNode]) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for pole_id, node in nodes.items():
        parent = node.resolved_parent_pole_id or DT_ROOT
        idx.setdefault(parent, []).append(pole_id)
    return idx


def subtree_pole_ids(children_index: dict, root_id: str) -> list[str]:
    """All poles in the subtree rooted at root_id, root_id itself included."""
    out = []
    stack = [root_id]
    while stack:
        cur = stack.pop()
        out.append(cur)
        stack.extend(children_index.get(cur, []))
    return out
