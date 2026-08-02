#!/usr/bin/env python3
"""
run_headline_qpu.py — the 90-atom Sukhumvit headline on QuEra Aquila (standalone)
=================================================================================

A ONE-OFF experiment, deliberately OUTSIDE the presentation notebook: the notebook
must never depend on a live submission. Here we (optionally) submit the 90-atom
headline instance to Aquila, then collect the REAL measurements and save them in the
notebook's results schema so the headline can replay genuine QPU data instead of the
phenomenological SIMULATED_STANDIN.

The instance is loaded from results/sukhumvit_90.json — the EXACT register and
coverage graph the notebook uses — so the device solves the same problem the
classical baseline and the figures use. 90 atoms is the largest sub-district that
fits Aquila's 75 um field at the honest fixed scale (the full 116-atom district
spans ~87 um and is physically un-loadable).

Phases
------
  --dry-run (default) : build the AHS program, assert it is Aquila-legal, resolve the
                        device read-only, and print the credit cost. NOTHING is
                        submitted. Safe to run anywhere.
  --submit            : submit the job (SPENDS CREDITS). Prints the task id and writes
                        it to results/headline_qpu_task.json. This is the ONLY code
                        path that talks to the QPU — run it yourself.
  --collect           : load the completed job by task id (read-only), decode with
                        blockade-violation rejection, save real shots to
                        results/headline_qpu_90_results.json (source="QPU"), summarise.
  --display           : offline — render the payoff map + summary from the saved shots.

Nothing in this file is imported by the notebook.

Usage
-----
    python scripts/run_headline_qpu.py                       # dry-run (validate + price)
    python scripts/run_headline_qpu.py --submit --shots 1000 # YOU run this (spends credits)
    python scripts/run_headline_qpu.py --collect             # after it COMPLETES
    python scripts/run_headline_qpu.py --display             # show the result
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import sleepcells as sc  # noqa: E402

RESULTS = os.path.join(HERE, "results")
INSTANCE = os.path.join(RESULTS, "sukhumvit_90.json")
TASK_FILE = os.path.join(RESULTS, "headline_qpu_task.json")
OUT_RESULTS = os.path.join(RESULTS, "headline_qpu_90_results.json")
OUT_FIG = os.path.join(RESULTS, "headline_qpu_90.png")
DEFAULT_SHOTS = 1000  # Aquila max; ~15-40% survive full-load post-selection at 90 atoms


def _load_instance():
    inst = sc.load_instance(INSTANCE)
    reg = sc.register_from_instance(inst)
    G = inst["graph"]
    exact = inst["classical"]["exact_size"]
    return inst, reg, G, exact


def _build_and_validate(shots):
    """Offline: load the committed instance, assert Aquila-legality, build the AHS
    program, print the cost. Submits nothing."""
    inst, reg, G, exact = _load_instance()
    sc.assert_valid_register(reg)  # loud failure if not Aquila-legal
    ahs = sc.build_ahs_program(reg)
    span = reg.coords_um.max(axis=0) - reg.coords_um.min(axis=0)
    print(f"instance   : {os.path.basename(INSTANCE)}  "
          f"({reg.n} atoms, {G.number_of_edges()} coverage edges, exact MIS = {exact})")
    print(f"register   : {span[0]:.1f} x {span[1]:.1f} um  "
          f"(Aquila field {sc.FIELD_UM} um)  ->  LEGAL")
    print(f"shots      : {shots}   cost = {sc.task_credits(shots)} credits "
          f"({sc.CREDITS_PER_TASK} + {shots}x{sc.CREDITS_PER_SHOT})")
    return inst, reg, G, exact, ahs


def _summarise(inst, G, exact):
    """Decode the saved shots with blockade-violation rejection and print a summary."""
    loaded = sc.load_results(OUT_RESULTS)
    sel, ret, tot, defect = sc.decode_shots(loaded["shots"], inst["n_atoms"], policy="postselect")
    best, viol, nvalid = sc.best_valid_set(sel, G)
    ok = sc.verify_independent_set(G, best)
    print(f"source     : {loaded['source']}  ({tot} shots)")
    print(f"post-select: {ret}/{tot} fully-loaded shots kept (defect {defect:.1%})")
    print(f"blockade   : {viol}/{ret} shots had adjacent excitations, rejected; {nvalid} valid")
    print(f"best set   : |S| = {len(best)} of {inst['n_atoms']}  "
          f"(exact optimum {exact}, approx ratio {len(best)/exact:.2f})")
    print(f"coverage   : {'COVERAGE VERIFIED' if ok else 'FAILED'}")
    return best


def dry_run(shots):
    print("=== DRY RUN — nothing is submitted ===")
    _build_and_validate(shots)
    try:
        from qbraid.runtime import QbraidProvider
        dev = QbraidProvider().get_device(sc.AQUILA_DEVICE_ID)
        print(f"device     : {sc.AQUILA_DEVICE_ID}   status = {dev.status()}")
        print(f"pricing    : {dev.metadata().get('pricing')}")
    except Exception as e:
        print(f"device     : not resolvable here ({repr(e)[:70]}) — offline validation still passed")
    print("\nTo submit (this SPENDS credits), run yourself:")
    print(f"    .venv/bin/python scripts/run_headline_qpu.py --submit --shots {shots}")


def submit(shots):
    print("=== SUBMIT — this SPENDS credits ===")
    _, reg, _, _, ahs = _build_and_validate(shots)
    from qbraid.runtime import QbraidProvider
    dev = QbraidProvider().get_device(sc.AQUILA_DEVICE_ID)
    job = dev.run(ahs, shots=shots)  # <-- the ONLY line that submits to the QPU
    task_id = getattr(job, "id", None) or str(job)
    with open(TASK_FILE, "w") as f:
        json.dump({"task_id": task_id, "shots": shots,
                   "instance": os.path.basename(INSTANCE)}, f, indent=2)
    print(f"\nSubmitted.  task_id = {task_id}")
    print(f"saved -> {TASK_FILE}")
    print("\nWhen it reads COMPLETED, collect with:")
    print("    .venv/bin/python scripts/run_headline_qpu.py --collect")


def collect(task_id):
    print("=== COLLECT — read-only ===")
    inst, reg, G, exact = _load_instance()
    if not task_id:
        if not os.path.exists(TASK_FILE):
            raise SystemExit(f"no --task-id and no {TASK_FILE}: submit first or pass --task-id")
        task_id = json.load(open(TASK_FILE))["task_id"]
    from qbraid.runtime import load_job
    job = load_job(task_id, provider="qbraid")
    status = str(job.status())
    print(f"task {task_id}\nstatus: {status}")
    if "COMPLETED" not in status.upper() and "DONE" not in status.upper():
        raise SystemExit("job not completed yet — wait and re-run --collect.")
    r = job.result()
    measurements = [{"pre": [int(x) for x in m.pre_sequence],
                     "post": [int(x) for x in m.post_sequence]}
                    for m in r.data.measurements]  # qBraid Result -> AnalogResultData
    sc.save_results(
        OUT_RESULTS, instance_name="sukhumvit_90", n_atoms=inst["n_atoms"], source="QPU",
        tasks=[{"task_id": task_id, "shots": len(measurements), "measurements": measurements}],
        note="Real QuEra Aquila measurements for the 90-atom Sukhumvit headline.",
    )
    print(f"saved {len(measurements)} shots -> {OUT_RESULTS}\n")
    _summarise(inst, G, exact)
    print("\nRender the figure with:  .venv/bin/python scripts/run_headline_qpu.py --display")


def display():
    print("=== DISPLAY — offline, from saved shots ===")
    if not os.path.exists(OUT_RESULTS):
        raise SystemExit(f"no {OUT_RESULTS}: run --collect first")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import sleepviz as viz
    inst, reg, G, exact = _load_instance()
    best = _summarise(inst, G, exact)
    viz.apply_style()
    viz.payoff_map(inst, best)
    for n in plt.get_fignums():
        fig = plt.figure(n)
        fig.savefig(OUT_FIG, dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"\nfigure -> {OUT_FIG}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="validate + price only (default)")
    g.add_argument("--submit", action="store_true", help="SUBMIT the job (spends credits)")
    g.add_argument("--collect", action="store_true", help="collect a completed job (read-only)")
    g.add_argument("--display", action="store_true", help="render map + summary from saved shots")
    ap.add_argument("--shots", type=int, default=DEFAULT_SHOTS, help="1..1000 (Aquila limit)")
    ap.add_argument("--task-id", default=None, help="task id for --collect (default: saved file)")
    args = ap.parse_args()
    if not (1 <= args.shots <= 1000):
        raise SystemExit("shots must be 1..1000 (Aquila limit)")

    if args.submit:
        submit(args.shots)
    elif args.collect:
        collect(args.task_id)
    elif args.display:
        display()
    else:
        dry_run(args.shots)


if __name__ == "__main__":
    main()
