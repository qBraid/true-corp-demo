#!/usr/bin/env python3
"""
run_channel_qpu.py — iterated-MIS channel plan with EVERY channel measured on Aquila
====================================================================================

Grounds the whole frequency-reuse plan in real quantum execution. Each channel is a
Maximum Independent Set of the *residual* conflict graph; because removing atoms never
breaks min-spacing / rows / field-of-view, each residual is just a smaller sub-register
of the same 90-atom instance, submitted to QuEra Aquila.

    channel 1 : reuse the already-executed headline result (results/headline_qpu_90_results.json)
    channel 2 : submit the 56-atom residual -> Aquila -> MIS
    channel 3 : submit that residual -> Aquila -> MIS   ... until the residual is edgeless
    (edgeless residual: all remaining towers share the final channel; no QPU needed)

Sequential and data-dependent (round r+1 needs round r's measured MIS), so this is
STATEFUL and RESUMABLE: state is saved after every round in results/channel_qpu_state.json.

Phases
------
  --plan               : validate + show progress + next-round cost. NOTHING submitted.
  --run-all --shots N  : the full loop (submit -> poll -> collect -> iterate). SPENDS
                         credits; run it yourself. Re-run to resume after an interruption.
  --collect            : collect a pending job read-only (if you split submit/collect).
  --assemble           : build results/channel_assignment_90_qpu.json from the rounds.
  --display            : render the QPU channel map.

Only `dev.run(...)` (inside submit) talks to the QPU. Everything else is read-only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import sleepcells as sc          # noqa: E402
import channels as ch           # noqa: E402

INSTANCE = os.path.join(HERE, "results", "sukhumvit_90.json")
HEADLINE = os.path.join(HERE, "results", "headline_qpu_90_results.json")
STATE = os.path.join(HERE, "results", "channel_qpu_state.json")
OUT = os.path.join(HERE, "results", "channel_assignment_90_qpu.json")
OUT_FIG = os.path.join(HERE, "results", "channel_assignment_90_qpu.png")
POLL_S = 30


# ----------------------------------------------------------------------------- helpers
def _load():
    inst = sc.load_instance(INSTANCE)
    return inst, sc.register_from_instance(inst), inst["graph"]


def _subreg(reg, survivors):
    return sc.Register(coords_um=reg.coords_um[list(survivors)],
                       scale_m_per_um=reg.scale_m_per_um, rotation_rad=reg.rotation_rad)


def _induced_edges(reg, survivors):
    return sc.build_graph_from_register(_subreg(reg, survivors)).number_of_edges()


def _save_state(s):
    with open(STATE, "w") as f:
        json.dump(s, f, indent=1)


def _load_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else None


def _init_state(inst, G):
    """Channel 1 = the already-executed headline MIS (no resubmission)."""
    res = sc.load_results(HEADLINE)
    sel, _r, _t, _d = sc.decode_shots(res["shots"], inst["n_atoms"], policy="postselect")
    mis1, _v, _n = sc.best_valid_set(sel, G)
    mis1 = sorted(int(v) for v in mis1)
    survivors = [v for v in range(inst["n_atoms"]) if v not in set(mis1)]
    s = {"instance": "sukhumvit_90", "n_atoms": inst["n_atoms"],
         "rounds": [{"channel": 0, "source": "QPU (Aquila, measured)",
                     "task_id": res["tasks"][0]["task_id"], "shots": len(res["shots"]),
                     "size": len(mis1), "nodes": mis1}],
         "survivors": survivors, "pending": None}
    _save_state(s)
    print(f"channel 1 seeded from headline: {len(mis1)} towers -> {len(survivors)} survivors")
    return s


def _device():
    from qbraid.runtime import QbraidProvider
    return QbraidProvider().get_device(sc.AQUILA_DEVICE_ID)


# ----------------------------------------------------------------------------- submit / collect
def _submit_next(s, reg, shots):
    survivors = s["survivors"]
    sub = _subreg(reg, survivors)
    sc.assert_valid_register(sub)
    cost = sc.task_credits(shots)
    print(f"channel {len(s['rounds'])+1}: submitting {sub.n}-atom residual, {shots} shots "
          f"(cost {cost} credits) ...")
    job = _device().run(sc.build_ahs_program(sub), shots=shots)   # <-- the only QPU call
    tid = getattr(job, "id", None) or str(job)
    s["pending"] = {"task_id": tid, "shots": shots, "survivors": list(survivors)}
    _save_state(s)
    print(f"  submitted. task_id = {tid}")


def _collect_pending(s, reg, wait=True):
    """Poll the pending job. Returns 'collected' (round recorded), 'failed' (device
    failure — pending cleared so the caller can resubmit), 'pending' (not ready), or
    'none'. Neutral-atom runs fail transiently ('Issue encountered on device'), so a
    FAILED job is a retry signal, not a fatal error."""
    from qbraid.runtime import load_job
    p = s["pending"]
    if not p:
        return "none"
    tid, survivors = p["task_id"], p["survivors"]
    while True:
        st = str(load_job(tid, provider="qbraid").status())
        if "COMPLETED" in st.upper() or "DONE" in st.upper():
            break
        if any(b in st.upper() for b in ("FAIL", "CANCEL", "ERROR")):
            print(f"  channel {len(s['rounds'])+1} job ended {st} — transient device failure; "
                  f"clearing to resubmit.")
            s["pending"] = None
            _save_state(s)
            return "failed"
        if not wait:
            print(f"  channel {len(s['rounds'])+1} status: {st} (not ready)")
            return "pending"
        print(f"  [{time.strftime('%H:%M:%S')}] channel {len(s['rounds'])+1} status: {st}")
        time.sleep(POLL_S)
    meas = load_job(tid, provider="qbraid").result().data.measurements
    shots = [sc.Shot(m.pre_sequence, m.post_sequence) for m in meas]
    Gsub = sc.build_graph_from_register(_subreg(reg, survivors))
    sel, ret, tot, _d = sc.decode_shots(shots, len(survivors), policy="postselect")
    sub_mis, viol, nvalid = sc.best_valid_set(sel, Gsub)
    nodes = sorted(int(survivors[i]) for i in sub_mis)     # map sub-index -> original
    s["rounds"].append({"channel": len(s["rounds"]), "source": "QPU (Aquila, measured)",
                        "task_id": tid, "shots": len(shots), "size": len(nodes), "nodes": nodes,
                        "blockade_rejected": int(viol), "valid_shots": int(nvalid)})
    s["survivors"] = [v for v in survivors if v not in set(nodes)]
    s["pending"] = None
    _save_state(s)
    print(f"  channel {len(s['rounds'])}: {len(nodes)} towers "
          f"(rejected {viol} blockade-violating shots; {len(s['survivors'])} survivors left)")
    return "collected"


def _finish_edgeless(s, reg):
    """Edgeless residual: all remaining towers share the final channel (no QPU needed)."""
    survivors = s["survivors"]
    if survivors and _induced_edges(reg, survivors) == 0:
        s["rounds"].append({"channel": len(s["rounds"]), "source": "trivial (edgeless residual)",
                            "task_id": None, "shots": 0, "size": len(survivors),
                            "nodes": sorted(int(v) for v in survivors)})
        s["survivors"] = []
        s["pending"] = None
        _save_state(s)
        print(f"final channel {len(s['rounds'])}: {len(survivors)} towers "
              f"(edgeless residual — one shared channel, no QPU needed)")


# ----------------------------------------------------------------------------- top-level
def run_all(shots, max_retries=3):
    inst, reg, G = _load()
    s = _load_state() or _init_state(inst, G)
    if s["pending"]:
        _collect_pending(s, reg)                       # resume: collect, or clear if it failed
    while s["survivors"]:
        if _induced_edges(reg, s["survivors"]) == 0:
            _finish_edgeless(s, reg)
            break
        attempt = 0
        while True:                                    # retry this channel on transient device failure
            _submit_next(s, reg, shots)
            outcome = _collect_pending(s, reg)
            if outcome == "collected":
                break
            if outcome == "failed":
                attempt += 1
                if attempt > max_retries:
                    raise SystemExit(
                        f"channel {len(s['rounds'])+1} failed {attempt} times on the device; "
                        f"stopping. Re-run --run-all later to resume (nothing is lost).")
                print(f"  resubmitting channel {len(s['rounds'])+1} (attempt {attempt+1}/{max_retries+1}) ...")
                time.sleep(5)
    print("\nall channels grounded in real execution.")
    assemble()


def collect():
    inst, reg, G = _load()
    s = _load_state()
    if not s or not s["pending"]:
        print("no pending job to collect.")
        return
    outcome = _collect_pending(s, reg, wait=True)
    if outcome == "failed":
        print("pending job failed on the device and was cleared — re-run --run-all to resubmit.")


def _assemble_from_state(s):
    channels = [r["nodes"] for r in s["rounds"]]
    channel_of = {v: r["channel"] for r in s["rounds"] for v in r["nodes"]}
    return channels, channel_of


def assemble():
    inst, reg, G = _load()
    s = _load_state()
    if not s:
        raise SystemExit("no state — run --run-all first.")
    channels, channel_of = _assemble_from_state(s)
    ok, problems = ch.verify_coloring(G, channel_of)
    chi = ch.chromatic_number(G)
    covered = len(channel_of)
    print(f"\nQPU-grounded channel plan: {len(channels)} channels for {covered}/{inst['n_atoms']} towers")
    print(f"round sizes : {[len(c) for c in channels]}")
    for r in s["rounds"]:
        extra = "" if r["source"].startswith("trivial") else \
            f"  task {r['task_id'][-12:]}  ({r.get('valid_shots','-')} valid shots)"
        print(f"  channel {r['channel']+1}: {r['size']:2d} towers  [{r['source']}]{extra}")
    print(f"optimal (chi): {chi}   overspend: {len(channels)-chi}")
    print(f"valid colouring: {'YES' if ok else problems}")
    out = {"instance": "sukhumvit_90", "n_atoms": inst["n_atoms"], "source": "QPU_iterated",
           "n_channels": len(channels), "chromatic_number": chi,
           "overspend": len(channels) - chi, "round_sizes": [len(c) for c in channels],
           "channels": channels, "channel_of": {str(k): int(v) for k, v in channel_of.items()},
           "rounds": s["rounds"], "valid": bool(ok) and covered == inst["n_atoms"],
           "coords_lonlat": [[float(x), float(y)] for x, y in inst["coords_lonlat"]]}
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"saved -> {OUT}")


def display():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = json.load(open(OUT))
    inst = sc.load_instance(INSTANCE)
    lon = inst["coords_lonlat"][:, 0]; lat = inst["coords_lonlat"][:, 1]
    G = inst["graph"]
    palette = ["#e4002b", "#22e0a6", "#a06bff", "#ffb020", "#4aa3ff", "#ff6fae", "#8ce06a"]
    fig, ax = plt.subplots(figsize=(8, 7)); fig.patch.set_facecolor("#0b0f14"); ax.set_facecolor("#0b0f14")
    for u, v in G.edges():
        ax.plot([lon[u], lon[v]], [lat[u], lat[v]], color="#33404f", lw=0.5, zorder=1)
    for c, nodes in enumerate(d["channels"]):
        ax.scatter(lon[nodes], lat[nodes], s=70, c=palette[c % len(palette)],
                   edgecolors="white", linewidths=0.5, zorder=3, label=f"channel {c+1} ({len(nodes)})")
    ax.set_title(f"Aquila channel plan — {d['n_channels']} channels (all measured on QPU)",
                 color="white", loc="left", fontsize=12)
    ax.legend(facecolor="#11161d", edgecolor="none", labelcolor="white", fontsize=9, loc="upper right")
    ax.tick_params(colors="#8a94a3"); [sp.set_color("#33404f") for sp in ax.spines.values()]
    fig.tight_layout(); fig.savefig(OUT_FIG, dpi=120, facecolor=fig.get_facecolor())
    print(f"figure -> {OUT_FIG}")


def plan(shots):
    inst, reg, G = _load()
    s = _load_state() or _init_state(inst, G)
    done = len(s["rounds"])
    print(f"rounds completed: {done}   survivors: {len(s['survivors'])}   pending: {bool(s['pending'])}")
    if not s["survivors"]:
        print("all towers assigned — run --assemble."); return
    e = _induced_edges(reg, s["survivors"])
    if e == 0:
        print(f"next: edgeless residual ({len(s['survivors'])} towers) -> one final channel, NO QPU cost.")
    else:
        sub = _subreg(reg, s["survivors"]); sc.assert_valid_register(sub)
        print(f"next channel {done+1}: submit {sub.n}-atom residual ({e} conflict edges), "
              f"{shots} shots -> cost {sc.task_credits(shots)} credits. Register is Aquila-LEGAL.")
    print("\nTo run every remaining channel on the QPU (spends credits):")
    print(f"    .venv/bin/python scripts/run_channel_qpu.py --run-all --shots {shots}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--plan", action="store_true", help="validate + cost, no submission (default)")
    g.add_argument("--run-all", action="store_true", help="submit/collect every remaining channel (spends credits)")
    g.add_argument("--collect", action="store_true", help="collect a pending job (read-only)")
    g.add_argument("--assemble", action="store_true", help="build the QPU channel-assignment JSON")
    g.add_argument("--display", action="store_true", help="render the QPU channel map")
    ap.add_argument("--shots", type=int, default=500, help="shots per residual round (1..1000)")
    args = ap.parse_args()
    if not (1 <= args.shots <= 1000):
        raise SystemExit("shots must be 1..1000")
    if args.run_all:
        run_all(args.shots)
    elif args.collect:
        collect()
    elif args.assemble:
        assemble()
    elif args.display:
        display()
    else:
        plan(args.shots)


if __name__ == "__main__":
    main()
