"""
channels.py — channel assignment by iterated MIS (graph colouring)
==================================================================

One MIS is one channel: a set of cells whose coverage does not conflict, so they
can reuse the same frequency simultaneously. The full operational problem is
COLOURING — partition the whole conflict graph into independent sets, one per
channel, so no two overlapping cells share a frequency. The standard heuristic is
literally "extract an MIS, delete it, repeat"; MIS is the inner loop, colouring is
the car. (See MIS-telecom-demo-notes.docx §5.)

Two things the notes insist on, both enforced here:
  * DELETE NODES, not edges. Removing only a selected node's edges would leave it
    as an isolated vertex that a later round happily re-selects — putting one tower
    on two channels while another gets none. Deleting the node keeps every tower in
    exactly one round, so the colouring is a clean partition with no repair step.
  * ITERATE UNTIL NO NODES REMAIN. An MIS on a non-empty graph is non-empty, so
    every round removes >=1 tower and the loop terminates. Once the residual graph
    is edgeless, the final MIS is all remaining towers -> the last channel.

Repeated-MIS is greedy: taking the largest set first can strand an awkward tower
and force an extra channel, so it does not guarantee the minimum (chromatic
number). `clique_lower_bound` gives omega(G) <= chi(G) to quantify the gap.
"""

from __future__ import annotations

import networkx as nx

import towers as tw


def _round_mis(H: nx.Graph, solver: str, exact_timeout: float) -> list:
    """One channel's independent set on the residual graph H."""
    if solver == "greedy":
        return list(tw.greedy_mis(H))
    S, _wall, _done = tw.exact_mis(H, timeout_s=exact_timeout)
    return list(S) if S else list(tw.greedy_mis(H))  # greedy fallback if exact stalls


def iterated_mis_coloring(
    G: nx.Graph, first_set=None, solver: str = "exact", exact_timeout: float = 10.0
):
    """Assign every node a channel by repeated MIS.

    Args:
        G          : the coverage-conflict graph.
        first_set  : optional round-1 independent set used verbatim (e.g. the QuEra
                     Aquila-measured MIS). Must be independent in G; becomes channel 0.
        solver     : 'exact' (max-clique on the complement) or 'greedy'.

    Returns (channels, channel_of, provenance):
        channels    list[list[node]]  — channels[c] = towers on channel c (0-indexed).
        channel_of  dict node -> channel index.
        provenance  list[dict] per round (size, source, residual sizes before removal).
    """
    H = G.copy()
    channels: list[list] = []
    channel_of: dict = {}
    provenance: list[dict] = []

    while H.number_of_nodes() > 0:
        if not channels and first_set is not None:
            S = [v for v in first_set if v in H]
            if not tw.verify_independent_set(H, S):
                raise ValueError("first_set is not an independent set of G")
            source = "QPU (Aquila, measured)"
        else:
            S = _round_mis(H, solver, exact_timeout)
            source = f"classical ({solver})"

        S = sorted(set(int(v) for v in S))
        c = len(channels)
        provenance.append(
            {
                "channel": c,
                "size": len(S),
                "source": source,
                "residual_nodes": H.number_of_nodes(),
                "residual_edges": H.number_of_edges(),
            }
        )
        channels.append(S)
        for v in S:
            channel_of[v] = c
        H.remove_nodes_from(S)  # nodes AND their edges leave together

    return channels, channel_of, provenance


def verify_coloring(G: nx.Graph, channel_of: dict):
    """A valid channel plan: every tower has a channel and no conflict edge is
    monochromatic (no two overlapping cells share a frequency).

    Returns (ok, problems)."""
    uncoloured = [v for v in G.nodes() if v not in channel_of]
    monochromatic = [(u, v) for u, v in G.edges() if channel_of.get(u) == channel_of.get(v)]
    return (not uncoloured and not monochromatic), {
        "uncoloured": uncoloured,
        "monochromatic_edges": monochromatic,
    }


def clique_lower_bound(G: nx.Graph) -> int:
    """omega(G) <= chi(G): every tower in a clique mutually conflicts, so each needs
    its own channel — the largest clique is a floor on the channels any plan can use."""
    clique, _ = nx.max_weight_clique(G, weight=None)
    return len(clique)


def chromatic_number(G: nx.Graph) -> int:
    """Exact minimum number of channels (chromatic number), as the ILP-baseline the
    notes call for — computed here with a clique-lower-bounded, DSATUR-ordered
    backtracking search. Exact and fast for the small unit-disk instances here
    (tens of nodes); worst-case exponential, so not for large graphs.

    Lets us state the greedy-MIS overspend rigorously (chi, not just omega)."""
    if G.number_of_nodes() == 0:
        return 0
    order = [v for v, _ in sorted(G.degree(), key=lambda kv: -kv[1])]  # hardest first
    adj = {v: set(G[v]) for v in G}
    col: dict = {}

    def colourable(k: int) -> bool:
        col.clear()

        def bt(i: int) -> bool:
            if i == len(order):
                return True
            v = order[i]
            used = {col[u] for u in adj[v] if u in col}
            for c in range(k):
                if c not in used:
                    col[v] = c
                    if bt(i + 1):
                        return True
                    del col[v]
            return False

        return bt(0)

    k = clique_lower_bound(G)  # chi >= omega — start there
    while not colourable(k):
        k += 1
    return k
