#!/usr/bin/env python3
"""Assemble which_cells_can_sleep.ipynb from source cells (valid nbformat v4).

Slide images are base64-embedded so the notebook is a SINGLE self-contained file:
it renders the whole presentation with no dependency on the slides/ folder.
"""
import base64
import os
import nbformat as nbf

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "which_cells_can_sleep.ipynb")
SLIDES = os.path.join(HERE, "slides")

cells = []
def md(src): cells.append(nbf.v4.new_markdown_cell(src.strip("\n")))
def code(src): cells.append(nbf.v4.new_code_cell(src.strip("\n")))

def slide(fname, width=1000):
    """Return an <img> HTML string with the slide PNG base64-embedded inline."""
    with open(os.path.join(SLIDES, fname), "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return (f'<img src="data:image/png;base64,{b64}" width="{width}" '
            f'style="max-width:100%;height:auto;border:1px solid #ececec;'
            f'border-radius:8px;margin:0.4em 0;" alt="{fname}" />')

# ==========================================================================
# TITLE
# ==========================================================================
md(r"""
""" + slide("slide-01-title.png") + r"""

**Live · Quantum Club Thailand · True Digital Park · 3 August 2026 · QTRiC × qBraid**

We run this notebook top to bottom. Each section shows one slide we speak to, then the code
proves it live on real hardware. The whole thing fits the 15-minute slot.

> **We do not claim quantum advantage** — on these sizes a classical solver wins, and the
> notebook shows it winning. We run on quantum hardware to *measure the gap*, not beat the laptop.
""")

# ==========================================================================
# 0. SETUP
# ==========================================================================
md(r"""
## 0 · Setup — environment, parameters, device

Everything the demo needs ships in this folder (`sleepcells.py`, `data/`, `results/`). No
live download happens during the talk. The only network call is the optional live QPU
submission in Cell 1, and it is **off by default**.
""")

code(r"""
# --- imports & environment (self-contained; installs only if something is missing) ---
import sys, os, json, time, math, warnings, inspect
warnings.filterwarnings("ignore")

def _ensure(pkgs):
    import importlib
    missing = []
    for mod, pip in pkgs:
        try: importlib.import_module(mod)
        except Exception: missing.append(pip)
    if missing:
        print("installing:", missing)
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", *missing], check=False)

_ensure([("numpy","numpy"), ("scipy","scipy"), ("pandas","pandas"), ("networkx","networkx"),
         ("matplotlib","matplotlib"), ("braket","amazon-braket-sdk")])

sys.path.insert(0, os.getcwd())          # make the local modules importable on Lab
import numpy as np, pandas as pd, networkx as nx
import sleepcells as sc                   # tested pipeline + printed reports (single source of truth)
import sleepviz as viz                    # all matplotlib figures live here

try:
    import qbraid; QBRAID_VER = qbraid.__version__
except Exception:
    QBRAID_VER = "not importable"
print(f"qbraid {QBRAID_VER} · numpy {np.__version__} · networkx {nx.__version__}")
""")

code(r"""
# --- TOP-OF-NOTEBOOK PARAMETERS (the knobs) ---------------------------------
COVERAGE_OVERLAP_M = sc.COVERAGE_OVERLAP_M   # 500 m: two sites "mutually cover" within this distance
LIVE_ATOMS       = 16     # atoms in the live audience instance
SUBMIT_LIVE_JOB  = False  # True submits the live job to Aquila; False uses committed results
LIVE_SHOTS       = 100    # shots for the live job (maximum 1000)

DATA_CSV    = "data/watthana_cells.csv"
RESULTS_DIR = "results"
CENTER      = (13.731, 100.575)              # Watthana / Sukhumvit centre (WGS84)

viz.apply_style()                            # True red on white — all figure styling lives in sleepviz
print(f"COVERAGE_OVERLAP_M = {COVERAGE_OVERLAP_M:.0f} m   LIVE_ATOMS = {LIVE_ATOMS}   "
      f"SUBMIT_LIVE_JOB = {SUBMIT_LIVE_JOB}")
""")

md(r"""
### Assumptions
""" + slide("slide-12-assumptions.png") + r"""
""")

code(r"""
sc.print_assumptions()          # the consolidated block — printed, not buried
""")

code(r"""
# --- device resolution: ENUMERATE, do not hardcode ARNs (read-only; no job sent) ---
provider = None
DEVICE_ID = sc.AQUILA_DEVICE_ID          # 'aws:quera:qpu:aquila' (confirmed live on qBraid)
try:
    from qbraid.runtime import QbraidProvider
    provider = QbraidProvider()
    online = []
    for d in provider.get_devices():
        online.append(d.id)
    aq = provider.get_device(DEVICE_ID)
    md_aq = aq.metadata()
    print(f"Aquila resolved  : {DEVICE_ID}")
    print(f"  status         : {md_aq.get('status')}")
    print(f"  qubits         : {md_aq.get('num_qubits')}   (up to 256 ⁸⁷Rb atoms)")
    print(f"  program type   : braket_ahs   ·   shots ≤ {sc.AQUILA_SHOTS_MAX}")
    pr = md_aq.get('pricing', {})
    print(f"  pricing        : {pr.get('perTask')} credits/task + {pr.get('perShot')} credit/shot")
    print(f"  analog devices online: {[x for x in online if 'aquila' in x or 'fresnel' in x]}")
except Exception as e:
    print("qBraid provider unavailable — running FULLY OFFLINE from committed files.")
    print("  (this is fine: every result below loads from disk.)  reason:", repr(e)[:120])
""")

# ==========================================================================
# CELL 1 — SUBMIT LIVE JOB
# ==========================================================================
md(r"""
## 1 · Submit the live job to Boston

We send the live instance to **Aquila** — the same pipeline as the 150-atom headline, small
enough to finish while we talk. Nothing blocks: the result is collected in Cell 8.
""")

code(r"""
# Build the live instance (same pipeline as everything else) and the AHS program.
live_inst = sc.load_instance(f"{RESULTS_DIR}/sukhumvit_{LIVE_ATOMS}.json")
live_reg  = sc.register_from_instance(live_inst)
live_G    = live_inst["graph"]
live_ahs  = sc.build_ahs_program(live_reg)      # coordinates in METRES, Ω starts/ends at 0

live_job, live_task_id = None, None
cost = sc.task_credits(LIVE_SHOTS)
print(f"Live instance    : {LIVE_ATOMS} atoms, {live_G.number_of_edges()} coverage edges")
print(f"AHS program      : 4 µs quasi-adiabatic sweep, {LIVE_SHOTS} shots  (cost {cost} credits)")

if SUBMIT_LIVE_JOB:
    try:
        live_job = aq.run(live_ahs, shots=LIVE_SHOTS)          # <-- the only line that submits
        live_task_id = getattr(live_job, "id", None) or str(live_job)
        print(f"\nSubmitted. Task ID: {live_task_id}")
        print("Running in Boston now; collected in Cell 8.")
    except Exception as e:
        print("\nSubmission unavailable (device offline or queue closed):", repr(e)[:160])
        print("Cell 8 uses the committed result instead.")
else:
    print("\nSUBMIT_LIVE_JOB is False — running from committed results; no job submitted.")
""")

# ==========================================================================
# CELL 2 — WHY
# ==========================================================================
md(r"""
## 2 · WHY — at 3 a.m. the network is awake, almost nobody is
""" + slide("slide-02-problem.png") + "\n\n" + slide("slide-03-why-now.png") + "\n\n"
   + slide("slide-04-the-blocker.png") + r"""

*The joint decision — which cells can sleep **together** without opening a hole — is the
NP-hard part nobody solves. The network team does not need a better guess; it needs a
**coverage certificate** it can sign off on. That is what the rest of this notebook produces.*
""")

# ==========================================================================
# CELL 3 — WHAT (data + graph)
# ==========================================================================
md(r"""
## 3 · WHAT — the coverage problem is Maximum Independent Set
""" + slide("slide-05-formulation.png") + r"""

*Draw an edge between any two sites whose coverage overlaps (within 500 m); a safe sleep
pattern is then an **independent set**, and sleeping as many as possible is **Maximum
Independent Set**. Below we load real Watthana geometry, cluster cells → sites → atoms, and
build that graph. (Positions are representative estimated centroids, not surveyed towers.)*
""")

code(r"""
# Load -> filter (True MNCs, MCC 520) -> cluster cells to sites -> merge to atoms
df = sc.load_cells(DATA_CSV)
fdf = sc.filter_cells(df)                              # True-group MNCs {0,4,5,18,25,99}
sites = sc.cluster_cells_to_sites(fdf, CENTER[0], CENTER[1], radius_m=50.0)
atoms = sc.merge_close_sites(sites)                    # enforces the 238 m (=4 µm) floor

sc.print_merge_counts(sites, atoms, df)               # cells -> sites -> atoms, printed explicitly
""")

code(r"""
# The full district + the coverage graph on the densest sub-district we will run.
# The graph is built from the ACTUAL atom register (snapped to Aquila's rows), so what
# we draw here is exactly what the QPU solves.
sub150 = sc.select_densest(atoms, 150)
reg150 = sc.affine_to_atoms(sub150)
edges150 = list(sc.build_graph_from_register(reg150).edges())
viz.district_and_graph(atoms, sub150, edges150)
""")

# ==========================================================================
# CELL 4 — AUDIENCE RUNS
# ==========================================================================
md(r"""
## 4 · AUDIENCE — run it yourself

**The cell to run on your own laptop.** The same pipeline at a size that finishes while we
talk: the quantum method on the **local Rydberg simulator** + the **exact classical** optimum,
with the coverage certificate. Under a minute. *(A blockade radius truncates the simulator to
the independent-set subspace; the full 2ᴺ statevector would hang.)*
""")

code(r"""
t0 = time.time()
try:
    from braket.devices import LocalSimulator
    res_live = LocalSimulator("braket_ahs").run(
        live_ahs, shots=200, blockade_radius=sc.BLOCKADE_RADIUS_UM * 1e-6, steps=100
    ).result()
    shots_live = [sc.Shot(m.pre_sequence, m.post_sequence) for m in res_live.measurements]
    live_source = "LOCAL SIMULATOR (run just now)"
except Exception as e:
    print("local simulator unavailable, loading committed result:", repr(e)[:80])
    rres = sc.load_results(f"{RESULTS_DIR}/localsim_{LIVE_ATOMS}_results.json")
    shots_live = rres["shots"]; live_source = "committed local-simulator result"

sel_live, ret, tot, defect = sc.decode_shots(shots_live, live_inst["n_atoms"])
sim_best = max(sel_live, key=len)
exact_live = live_inst["classical"]["exact_size"]
dt = time.time() - t0

print(f"quantum method   : {live_source}")
print(f"  best independent set over {ret}/{tot} shots : |S| = {len(sim_best)}")
print(f"exact classical  : max_weight_clique on complement -> optimum = {exact_live}")
print(f"coverage check   : {'COVERAGE VERIFIED' if sc.verify_independent_set(live_G, sim_best) else 'FAILED'}")
print(f"approximation    : {len(sim_best)}/{exact_live} = {len(sim_best)/exact_live:.2f}")
print(f"\nwall-clock       : {dt:.1f} s   (target < 60 s)")
""")

# ==========================================================================
# CELL 5 — HOW (mapping, scale table, three-panel)
# ==========================================================================
md(r"""
## 5 · HOW — that shape is also the shape of the machine
""" + slide("slide-06-mapping.png") + r"""

*Two atoms within the **Rydberg blockade radius** physically cannot both be excited — that
**is** the coverage constraint, enforced by rubidium, not a penalty term we added. Sweeping
detuning negative → positive over 4 µs carries the ground state to the maximum independent
set. Below: the scale table, the two demo-critical functions, and the "same shape" figure.*
""")

code(r"""
# The scale table — Sukhumvit rendered on the chip
sc.print_scale_table()

# The result-decoding rule. Aquila's bit semantics are inverted, and reading them backwards
# silently flips the answer — so this selection rule is stated explicitly:
print("\nSelection rule (Rydberg bit semantics are inverted):\n")
print(inspect.getsource(sc.rydberg_selected))
""")

code(r"""
# Three-panel "same shape" figure on the live instance: sites | graph | atom register
print("Same shape, three times: the map, the graph, and the atoms on the chip.")
viz.three_panel(live_inst, live_reg, live_G)      # returned figure is the cell's last expression -> displayed
""")

# ==========================================================================
# CELL 6 — RESULT 1
# ==========================================================================
md(r"""
## 6 · RESULT 1 — Sukhumvit on 150 atoms
""" + slide("slide-07-experiment.png") + "\n\n" + slide("slide-08-result.png") + r"""

*The slide is the claim; the cells below are the proof. We load the pre-run measurements, read
out which cells sleep, verify the coverage certificate live, and put a number in baht on it.*
""")

code(r"""
# Load the pre-run instance + results; the banner makes the data source unmistakable.
inst150 = sc.load_instance(f"{RESULTS_DIR}/sukhumvit_150.json")
res150 = sc.load_results(f"{RESULTS_DIR}/prerun_150_results.json")
G150 = inst150["graph"]
sc.print_standin_banner(res150)

# Decode: post-select on fully-loaded shots (headline policy), report retained count.
sel150, ret150, tot150, defect150 = sc.decode_shots(res150["shots"], 150, policy="postselect")
best150 = max(sel150, key=len)
sizes150 = [len(s) for s in sel150]
exact150 = inst150["classical"]["exact_size"]

print()
sc.print_result_summary(best150, 150, G150, exact150, ret150, tot150, defect150)
""")

code(r"""
# The payoff map: the district with the sleeping cells highlighted, from measurement outcomes.
viz.payoff_map(inst150, best150)
""")

md(r"""
### The value — ฿30–75M a year, on True's own constants
""" + slide("slide-11-value.png") + r"""

*Every baht below is built on True's own published numbers, so only the physical assumptions
are arguable — and reachable **today with a classical solver**. Quantum's contribution to this
number in 2026 is zero; we show the money to prove the problem is worth solving.*
""")

code(r"""
# The money model — True's own published constants; only the physics is arguable.
sc.print_money(len(best150), 150)
""")

# ==========================================================================
# CELL 7 — RESULT 2 (scoreboard)
# ==========================================================================
md(r"""
## 7 · RESULT 2 — the honest scoreboard
""" + slide("slide-09-scoreboard.png") + "\n\n" + slide("slide-10-the-gap.png") + r"""

*Classical won today — we show by how much: wall-clock, approximation ratio, and the shot
distribution Aquila returns. The real gap to advantage is not qubit count; it is **shot rate**.*
""")

code(r"""
# Classical exact-solve scaling on the densest sub-districts (grows fast with size).
print("CLASSICAL EXACT SOLVE (max_weight_clique on the complement, commodity CPU):")
print(f"  {'sites':>6s}{'avg deg':>9s}{'exact MIS':>11s}{'wall-clock':>13s}")
scale_pts = []
for k in [60, 120, 150, 180]:
    if k > atoms.n:
        continue
    subk = sc.select_densest(atoms, k)
    Gk = sc.build_graph_from_register(sc.affine_to_atoms(subk))   # same graph the QPU would solve
    s_k, dt_k, done = sc.exact_mis(Gk, timeout_s=30)
    scale_pts.append((k, dt_k, done))
    tag = "" if done else "  (did not finish — reportable!)"
    print(f"  {k:>6d}{2*Gk.number_of_edges()/k:>9.1f}{(len(s_k) if s_k else 0):>11d}{dt_k:>11.3f}s{tag}")
print(f"\n  Aquila, 150 atoms : one 4 µs sweep — but throughput is throttled by the shot rate.")
print(f"  approximation ratio (quantum {len(best150)} / classical optimum {exact150}) = "
      f"{len(best150)/exact150:.2f}   ← the honest headline metric")
""")

code(r"""
# Aquila's effective wall-clock is shot-rate limited, so its flat line sits ABOVE classical.
AQUILA_REP_HZ = 5.0                     # ASSUMPTION: Aquila effective rate ~few Hz (load+evolve+image)
aquila_today_s = 1000 / AQUILA_REP_HZ   # one 1000-shot task, shot-rate limited (queue excluded)
future_s = 1000 / 1000.0                # 1000 shots at 1 kHz — Cazals et al. advantage regime
print("The missing number is not qubits — it is SHOT RATE. The 4 µs sweep is flat in")
print("problem size, but a useful answer needs ~1000 shots; at Aquila's few-Hz effective")
print(f"rate that is ~{aquila_today_s:.0f} s (queue excluded), so the flat red line sits ABOVE")
print("classical for these sizes — classical wins. Going few-Hz -> kHz drops it ~100-1000x;")
print("THAT, not qubit count, is where advantage hides. The crossover is far to the right.")

# histogram + honest wall-clock (returned figure is the cell's last expression -> displayed)
viz.scoreboard(sizes150, exact150, len(best150), scale_pts, aquila_today_s, future_s, retained=ret150)
""")

# ==========================================================================
# CELL 8 — COLLECT LIVE JOB
# ==========================================================================
md(r"""
## 8 · Collect the live job

Back to Boston. If the job finished, we decode it and compare Aquila to the Cell-4 simulator.
If it is still queued, we **degrade gracefully** to the committed result — no exception.
""")

code(r"""
collected, coll_source = None, None
try:
    if SUBMIT_LIVE_JOB and live_job is not None:
        status = str(getattr(live_job, "status", lambda: "UNKNOWN")())
        print(f"live task {live_task_id} status: {status}")
        if "COMPLETED" in status.upper() or "DONE" in status.upper():
            r = live_job.result()
            collected = [sc.Shot(m.pre_sequence, m.post_sequence) for m in r.measurements]
            coll_source = "LIVE QPU (Aquila, Boston)"
        else:
            print("still queued — falling back to the committed result (no exception).")
    else:
        print("using the committed local-simulator result.")
except Exception as e:
    print("collection unavailable — falling back to the committed result:", repr(e)[:100])

if collected is None:
    rr = sc.load_results(f"{RESULTS_DIR}/localsim_{LIVE_ATOMS}_results.json")
    collected = rr["shots"]; coll_source = f"{rr['source']} (committed)"

sel_c, ret_c, tot_c, _ = sc.decode_shots(collected, live_inst["n_atoms"])
best_c = max(sel_c, key=len)
is_qpu = coll_source.startswith("LIVE QPU")
label = "Aquila (Boston)" if is_qpu else "the committed result"
print(f"\nsource           : {coll_source}")
print(f"best sleep set   : |S| = {len(best_c)}  (Cell-4 simulator got {len(sim_best)}, "
      f"exact optimum {exact_live})")
print(f"coverage check   : {'COVERAGE VERIFIED' if sc.verify_independent_set(live_G, best_c) else 'FAILED'}")
agree = "AGREE" if len(best_c) == len(sim_best) else f"differ by {abs(len(best_c)-len(sim_best))}"
print(f"agreement        : {label} and the live-cell simulator {agree} on the sleep-set size")
""")

# ==========================================================================
# CELL 9 — WHAT THIS MEANS
# ==========================================================================
md(r"""
## 9 · WHAT THIS MEANS
""" + slide("slide-13-path-forward.png") + r"""

*Apply, don't build. This notebook opens in a browser — **any Thai student can run tonight's
experiment tomorrow, on the same hardware.** One industry, one honest benchmark, and the
people who can read it. We proposed to start with the network under this building.*

---

### What this notebook proved, in one line each
- The coverage problem **is** the blockade constraint — same shape, no penalty terms.
- The machine returns a **valid, certified** sleep set: `COVERAGE VERIFIED`, printed, not asserted.
- The money is real (**฿30–75M/yr**) and reachable **today with a classical solver** — quantum's 2026 contribution is **zero**.
- The gap to advantage is a **shot-rate** number, and the only way to know when it closes is to measure it every year.

### References (cited inline)
- Ebadi et al., *Quantum optimization of maximum independent set using Rydberg atom arrays*, **Science 376, 1209 (2022)**
- Andrist et al., *Hardness of MIS on unit-disk graphs and prospects for quantum speedups*, **Phys. Rev. Research 5, 043277 (2023)** — the classical rebuttal; cited, not hidden
- Cazals et al., **Phys. Rev. Applied (2026)** — ~1000 atoms at 1 kHz needed for advantage
- Sarkar et al., **arXiv:2511.09633** — Aquila blockade / device parameters
- 3GPP **TS 38.300 §15.4** — Network Energy Savings, cell DTX/DRX
- AWS Braket developer guide — *Submit an analog program using QuEra Aquila*
""")

nb = nbf.v4.new_notebook()
nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}
with open(OUT, "w") as f:
    nbf.write(nb, f)
print(f"wrote {OUT}  ({len(cells)} cells)")
