#!/usr/bin/env python3
"""
prerun_experiments.py
=====================

Builds the demo instances and the committed pre-run RESULT stores so the notebook
replays end-to-end WITHOUT a QPU. Run once ahead of the event.

Outputs (under results/):
    sukhumvit_150.json          instance: atoms, graph, classical optima
    sukhumvit_20.json           instance (live-demo size, deck headline)
    sukhumvit_16.json           instance (safe live-cell default)
    prerun_150_results.json     150-atom shots  — SIMULATED_STANDIN (phenomenological)
    localsim_20_results.json    20-atom shots   — LOCAL_AHS_SIM (real Rydberg simulation)
    localsim_16_results.json    16-atom shots   — LOCAL_AHS_SIM

HONESTY
-------
* 16/20-atom results are REAL Braket local Rydberg (AHS) simulations — the most
  faithful stand-in for the QPU that exists without submitting a job.
* The 150-atom store is a PHENOMENOLOGICAL stand-in: the local simulator cannot
  reach 150 atoms (the independent-set subspace is astronomically large), and we
  have read-only QPU access, so we cannot produce real 150-atom measurements.
  Its shots are drawn by a documented model (random-order greedy independent sets
  + atom-loading defects) calibrated to a realistic approximation ratio. It is
  flagged source="SIMULATED_STANDIN" and the notebook prints a loud banner. It is
  a PLACEHOLDER to be overwritten by the real pre-run before the event.

Nothing here submits a QPU job.
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import sleepcells as sc  # noqa: E402

DATA_CSV = os.path.join(HERE, "data", "watthana_cells.csv")
RESULTS = os.path.join(HERE, "results")
CENTER = (13.731, 100.575)


# --------------------------------------------------------------------------
# Instance construction (shared pipeline)
# --------------------------------------------------------------------------
def build_atoms():
    df = sc.load_cells(DATA_CSV)
    fdf = sc.filter_cells(df)
    sites = sc.cluster_cells_to_sites(fdf, CENTER[0], CENTER[1], radius_m=50.0)
    atoms = sc.merge_close_sites(sites)
    provenance = {
        "data_csv": os.path.basename(DATA_CSV),
        "data_kind": "REPRESENTATIVE (synthetic positions on real Watthana geography)",
        "n_cells": int(sites.n_cells),
        "n_sites": int(sites.n),
        "n_atoms_total": int(atoms.n),
        "coverage_overlap_m": sc.COVERAGE_OVERLAP_M,
        "merge_threshold_m": sc.MERGE_THRESHOLD_M,
    }
    return atoms, provenance


def make_instance(atoms, k, name, provenance, exact_timeout=40.0):
    sub = sc.select_densest(atoms, k)
    reg = sc.affine_to_atoms(sub)                       # snapped onto Aquila's row lattice
    sc.assert_valid_register(reg)                       # fail loudly if not Aquila-legal
    G = sc.build_graph_from_register(reg)               # graph from the ACTUAL atom positions

    exact_set, exact_wall, completed = sc.exact_mis(G, timeout_s=exact_timeout)
    greedy = sc.greedy_mis(G)
    rgreedy = sc.randomized_greedy_mis(G, restarts=300)
    classical = {
        "exact_set": exact_set,
        "exact_size": (len(exact_set) if exact_set else None),
        "exact_wall_s": exact_wall,
        "exact_completed": completed,
        "greedy_set": greedy,
        "greedy_size": len(greedy),
        "rgreedy_set": rgreedy,
        "rgreedy_size": len(rgreedy),
    }
    path = os.path.join(RESULTS, f"{name}.json")
    prov = dict(provenance, n_atoms_selected=int(reg.n))
    sc.save_instance(path, name, sub, reg, G, classical, prov)
    print(f"  {name}: {reg.n} atoms, avg_deg={2*G.number_of_edges()/reg.n:.1f}, "
          f"exact_MIS={classical['exact_size']} (completed={completed}, {exact_wall:.2f}s), "
          f"greedy={classical['greedy_size']} -> {path}")
    return sub, reg, G, classical


# --------------------------------------------------------------------------
# REAL local-AHS-simulator shots (honest QPU stand-in) for small instances
# --------------------------------------------------------------------------
def local_ahs_shots(reg: sc.Register, shots=1000, steps=100, seed=None):
    from braket.devices import LocalSimulator
    ahs = sc.build_ahs_program(reg)
    sim = LocalSimulator("braket_ahs")
    kwargs = dict(shots=shots, blockade_radius=sc.BLOCKADE_RADIUS_UM * 1e-6, steps=steps)
    res = sim.run(ahs, **kwargs).result()
    measurements = [{"pre": [int(x) for x in m.pre_sequence],
                     "post": [int(x) for x in m.post_sequence]}
                    for m in res.measurements]
    return measurements


# --------------------------------------------------------------------------
# PHENOMENOLOGICAL 150-atom stand-in (documented; clearly NOT a quantum sim)
# --------------------------------------------------------------------------
def phenomenological_shots(G, n_atoms, shots=1000, p_empty=0.02,
                           drop_prob=0.09, rand_frac=0.35, seed=0):
    """Draw Aquila-like shots for a size the local simulator cannot reach.

    Model per shot (documented, phenomenological — this is NOT solving the
    Schrodinger equation, and it is NOT QPU data):
      1. Atom loading: each trap loads with prob (1 - p_empty); empty -> pre=0.
      2. Excitation: build a maximal independent set on the LOADED sub-graph by
         min-degree-first greedy, but with probability rand_frac at each step pick
         a random vertex instead. Pure min-degree greedy is near-optimal; the
         random admixture degrades it to a realistic approximation ratio (~0.9),
         modelling a good-but-imperfect quasi-adiabatic sweep.
      3. Adiabatic imperfection: independently drop each selected atom with prob
         drop_prob (excitation/decay failures). We never ADD a blockade violation
         — the blockade physically forbids two neighbours both being excited, so
         every shot is a valid independent set by construction.
    Calibrated (p_empty=0.02, drop=0.09, rand=0.35) so the post-selected best is ~0.9x
    the exact optimum, matching the deck's ~0.9x placeholder. Selection is
    pre==1 and post==0.
    """
    rng = np.random.default_rng(seed)
    measurements = []
    for _ in range(shots):
        loaded = rng.random(n_atoms) >= p_empty
        H = G.subgraph([v for v in range(n_atoms) if loaded[v]]).copy()
        selected = set()
        while H.number_of_nodes() > 0:
            degs = dict(H.degree())
            if rng.random() < rand_frac:
                v = int(rng.choice(list(degs)))
            else:
                mind = min(degs.values())
                v = int(rng.choice([u for u, d in degs.items() if d == mind]))
            selected.add(v)
            H.remove_nodes_from(list(H.neighbors(v)) + [v])
        selected = {v for v in selected if rng.random() >= drop_prob}
        pre = [int(bool(loaded[k])) for k in range(n_atoms)]
        post = [0 if (k in selected or not loaded[k]) else 1 for k in range(n_atoms)]
        measurements.append({"pre": pre, "post": post})
    return measurements


def main():
    os.makedirs(RESULTS, exist_ok=True)
    print("Building instances ...")
    atoms, provenance = build_atoms()
    print(f"  cells {provenance['n_cells']} -> sites {provenance['n_sites']} "
          f"-> atoms {provenance['n_atoms_total']}")

    sub150, reg150, G150, cl150 = make_instance(atoms, 150, "sukhumvit_150", provenance)
    sub20, reg20, G20, cl20 = make_instance(atoms, 20, "sukhumvit_20", provenance)
    sub16, reg16, G16, cl16 = make_instance(atoms, 16, "sukhumvit_16", provenance)

    # ---- REAL local AHS simulations for the small instances ----
    print("Running local AHS simulations (real Rydberg dynamics) ...")
    for name, reg in [("localsim_20_results", reg20), ("localsim_16_results", reg16)]:
        t0 = time.time()
        meas = local_ahs_shots(reg, shots=1000, steps=100)
        dt = time.time() - t0
        sc.save_results(
            os.path.join(RESULTS, f"{name}.json"),
            instance_name=name.replace("localsim_", "sukhumvit_").replace("_results", ""),
            n_atoms=reg.n, source="LOCAL_AHS_SIM",
            tasks=[{"task_id": f"localsim-{reg.n}", "shots": 1000, "measurements": meas}],
            note="Real Braket local Rydberg (AHS) simulation; stand-in for the QPU.",
        )
        sizes = [sum(1 for k in range(reg.n) if m["pre"][k] == 1 and m["post"][k] == 0)
                 for m in meas]
        print(f"  {name}: {dt:.1f}s  best={max(sizes)} mean={np.mean(sizes):.2f}")

    # ---- PHENOMENOLOGICAL 150-atom stand-in (3 tasks x 1000 shots) ----
    print("Generating phenomenological 150-atom stand-in (LABELLED, not a quantum sim) ...")
    tasks = []
    for t in range(3):
        meas = phenomenological_shots(G150, reg150.n, shots=1000, seed=100 + t)
        tasks.append({"task_id": f"standin-150-{t}", "shots": 1000, "measurements": meas})
    sc.save_results(
        os.path.join(RESULTS, "prerun_150_results.json"),
        instance_name="sukhumvit_150", n_atoms=reg150.n, source="SIMULATED_STANDIN",
        tasks=tasks,
        note=("PLACEHOLDER. Phenomenological stand-in (random-order greedy independent "
              "sets + loading defects), NOT a quantum simulation and NOT QPU data. "
              "Overwrite with the real Aquila pre-run before the event."),
    )
    allsizes = [sum(1 for k in range(reg150.n) if m["pre"][k] == 1 and m["post"][k] == 0)
                for tk in tasks for m in tk["measurements"]]
    exact = cl150["exact_size"]
    print(f"  prerun_150_results: 3000 shots  best={max(allsizes)} mean={np.mean(allsizes):.1f} "
          f"exact={exact}  approx_ratio(best/exact)={max(allsizes)/exact:.2f}")


if __name__ == "__main__":
    main()
