# Build spec — "Which cells can sleep tonight?"

A single self-contained Jupyter notebook for a live 15-minute demonstration at
Quantum Club Thailand, Grand Hall, True Digital Park, 3 August 2026, 14:45 ICT.

Audience: Deputy PM / MHESI Minister Prof. Dr. Yodchanan Wongsawat, True
Corporation executives and network engineers, QTRiC researchers, press.
Mixed technical depth. Some attendees will run the notebook themselves.

---

## 0. What this notebook must do

Solve a real, current problem from True Corporation's Bangkok network —
**which cell sites can be put to sleep at 3 a.m. without opening a coverage
hole** — by mapping it to Maximum Independent Set on a unit-disk graph and
running it on QuEra's Aquila neutral-atom processor via the qBraid SDK.

Three audiences, three payoffs, all of which the notebook must deliver:

1. A minister sees Thai infrastructure optimised by a quantum computer.
2. A network engineer sees a number in baht and a coverage guarantee.
3. A physicist sees an honest benchmark that does not overclaim.

### Non-negotiable honesty constraints

These are hard requirements, not stylistic preferences. Violating them
destroys credibility with the QTRiC researchers in the room.

- **Do NOT claim quantum advantage.** Classical solvers beat Aquila on these
  instance sizes. The notebook must show the classical baseline winning on
  wall-clock time and say so plainly.
- **Every assumption gets a printed line** in the notebook output, not a
  buried comment.
- **The MIS formulation is a conservative relaxation.** The true optimum is
  the complement of a minimum dominating set; independent set guarantees
  feasibility but may leave savings unclaimed. State this.
- **Coverage is modelled as uniform-radius disks.** Real radii vary by band,
  tilt, and cell class. State this.
- **OpenCelliD gives crowdsourced estimated positions**, not surveyed tower
  locations. State this.
- Report the site-merge count explicitly: "N sites → M atoms".

---

## 1. Environment

```
python >= 3.10
qbraid >= 0.11.0          # API V2; earlier versions are incompatible
amazon-braket-sdk
networkx
numpy, scipy, pandas
matplotlib
```

Runs on qBraid Lab with pre-configured credentials. Do NOT ask the user for
AWS keys. Do NOT use `boto3` directly.

Device resolution — enumerate rather than hardcode ARNs:

```python
from qbraid.runtime import QbraidProvider
provider = QbraidProvider()
for d in provider.get_devices():
    print(d.id, d.metadata().get("status"))
```

Expected: `quera_aquila` for the QPU. For local simulation use the Braket
local AHS simulator (`LocalSimulator("braket_ahs")`). Verify the exact
simulator identifier available in the environment at build time and fall
back gracefully if the name differs.

---

## 2. Device facts — verified, use these

Source: AWS Braket developer guide, "Submit an analog program using QuEra
Aquila"; QuEra Aquila published specs; Sarkar et al. arXiv 2511.09633.

| Parameter | Value | Notes |
|---|---|---|
| Atoms | up to 256 | ⁸⁷Rb, 70S₁/₂ Rydberg state |
| `shotsRange` | **(1, 1000)** | hard per-task ceiling |
| Max program duration | **4 µs** | coherence-limited; performance metrics quoted at 4 µs |
| Ω_max | ~15.6–15.8 rad/µs (≈2.5 MHz) | must start and end at 0 rad/s |
| C₆ | 5,420,503 µm⁶·rad/µs | fixed, not user-controllable |
| Blockade radius R_b = (C₆/Ω)^(1/6) | **≈ 8.4 µm** at Ω_max | |
| Min atom separation | ~4 µm | |
| Field of view | ~75 × 76 µm | **verify from live device properties** |
| Cost | $0.01/shot | qBraid: 30 credits/task + 1 credit/shot |

### Critical API details — these cause silent wrong answers

**1. Coordinates are in METRES in the schema**, despite docs describing them
in µm. `Decimal('4e-6')` is 4 µm. Getting this wrong is a factor of 10⁶.

**2. Result bit semantics are INVERTED from intuition.** From the task
result schema:

- `preSequence[k]`: 0 = trap site empty, 1 = atom loaded
- `postSequence[k]`: 0 = atom in **Rydberg** state OR site empty,
  1 = atom in **ground** state

Therefore:

```python
# site k is IN the independent set (i.e. this cell sleeps) iff:
selected = (pre_sequence[k] == 1) and (post_sequence[k] == 0)
```

Write this as a named helper with a docstring. Do not inline it.

**3. Atom loading is probabilistic.** Some sites come up empty each shot.
Choose one policy, apply it consistently, and print which:
 - (a) post-select on fully-loaded shots only, or
 - (b) treat empty sites as not-selected and report defect rate.
Recommend (a) for the headline result, and report the retained-shot count.

**4. `amplitude` and `detuning` patterns must be the string `'uniform'`.**
Only local detuning carries a per-site pattern.

**5. Ω(t) must begin and end at exactly 0 rad/s.**

### Local detuning — optional path, default OFF

Local detuning is an **experimental capability available by request via
Braket Direct**, and would need to be enabled on **qBraid's AWS account**,
not the presenter's. Assume it is unavailable.

- Default: `local_detuning = None` → build the program with `localDetuning=[]`
- The `h_k` pattern is **static** (dimensionless, 0.0–1.0); only the overall
  magnitude Δ_local(t) is time-dependent. So per-site weights are fixed at
  submission — usable for static per-site energy draw, useless for anything
  traffic-dependent.
- Implement `build_ahs_program(..., weights=None)` so weighted MIS is a
  one-flag change if access lands, but **do not put it on the critical path**.

---

## 3. The scale mapping — Sukhumvit onto the chip

Derived by fixing the blockade radius to the coverage-overlap threshold.

```
COVERAGE_OVERLAP_M = 500.0     # two sites "mutually cover" within this
BLOCKADE_RADIUS_UM = 8.4       # R_b at Omega_max
SCALE_M_PER_UM     = COVERAGE_OVERLAP_M / BLOCKADE_RADIUS_UM   # ≈ 59.5 m/µm

MIN_SEPARATION_UM  = 4.0
MERGE_THRESHOLD_M  = MIN_SEPARATION_UM * SCALE_M_PER_UM        # ≈ 238 m
FIELD_UM           = 75.0
FIELD_M            = FIELD_UM * SCALE_M_PER_UM                 # ≈ 4.5 km
```

Print these as a table in the notebook. The line that lands with a
non-technical audience: **"4.5 km of Sukhumvit, rendered in an area narrower
than a human hair. We did not tune the blockade radius to match — that is
where rubidium happens to sit."**

Make `COVERAGE_OVERLAP_M` a top-of-notebook parameter. If the district
doesn't fit the field, this is the knob.

---

## 4. Data pipeline

**Source:** OpenCelliD, Bangkok extract, filtered to Watthana / Sukhumvit.
Ship a cached CSV in the repo — **the notebook must not depend on a live
download during the presentation.** Include the download script separately.

Pipeline:

1. Load cells; filter `mcc == 520` (Thailand), True Corp MNCs, bounding box
   for Sukhumvit.
2. **Cluster cells → sites.** Many cells (sector × band) share one physical
   site. Cluster on position with a small radius (~50 m). Report
   `n_cells → n_sites`.
3. **Merge sites closer than `MERGE_THRESHOLD_M`** (~238 m) — required by the
   4 µm floor. Report `n_sites → n_atoms`.
4. Select the target count (150 for the pre-run, 20 for the live demo) by
   taking the densest contiguous sub-district, not a random sample.
5. Build the graph: edge between sites within `COVERAGE_OVERLAP_M`.
6. Affine transform to atom coordinates: translate to origin, rotate to
   minimise bounding box, scale by `1/SCALE_M_PER_UM`, convert to metres.
7. **Assert** all pairwise distances ≥ 4 µm and the bounding box fits the
   field. Fail loudly with a clear message if not.

Two instances, both saved to disk as JSON so results are reproducible:
- `sukhumvit_150.json` — the pre-run headline
- `sukhumvit_20.json` — the live audience run

---

## 5. The AHS program

Standard quasi-adiabatic MIS sweep, total 4 µs:

```
Ω(t):  0 → Ω_max over t_ramp (~0.3 µs), hold, → 0 over t_ramp
Δ(t):  Δ_start (negative) → Δ_end (positive), monotonic
φ(t):  0 throughout
```

Rationale to state in the notebook: at large negative detuning the ground
state is all-atoms-down (trivial); at large positive detuning the ground
state of the Rydberg Hamiltonian **is** the maximum independent set of the
unit-disk graph. The sweep carries the system from one to the other. No
penalty terms, no λ to tune — infeasible configurations are physically
forbidden by the blockade.

Sensible starting values (tune in the sweep): Δ_start ≈ −2π×5 MHz,
Δ_end ≈ +2π×5 MHz in rad/s. Follow the docs example's order of magnitude
(Ω ≈ 1.57e7 rad/s, Δ ≈ ±5.4e7 rad/s).

Provide `build_ahs_program(register, omega_max, delta_start, delta_end,
t_total, t_ramp, weights=None) -> AnalogHamiltonianSimulation`.

---

## 6. Classical baselines — both required

1. **Exact MIS** via max clique on the complement (`networkx.max_weight_clique`).
   Wrap in a timeout; at n=150 with high density this may not finish — that
   is itself a reportable result.
2. **Greedy** min-degree-first, and a randomised-restart greedy.

Record wall-clock for each. **Expect classical to win.** The notebook prints
a comparison table and a plain-English statement that it did.

Also compute the **approximation ratio**: best quantum result ÷ exact
classical optimum. This is the honest headline metric.

---

## 7. Results and the money model

For a returned sleep set S:

- `|S|` cells asleep, and |S|/n as a percentage
- **Coverage certificate**: assert S is a valid independent set, i.e. every
  sleeping cell has all neighbours awake. Print `COVERAGE VERIFIED` or fail.
- Energy and cost, using True's own published constants:

```
TARIFF_THB_PER_KWH   = 4.69   # from True: 42,000 MWh = THB 197M (2023)
GRID_TCO2E_PER_MWH   = 0.45   # from True: 64,000 MWh = 28,800 tCO2e
SITE_POWER_KW        = 4.0    # ASSUMPTION — flag prominently, biggest lever
RADIO_SHARE          = 0.60   # rest is cooling/baseband/transmission
DEEP_SLEEP_SAVING    = 0.70   # Vodafone UK + Ericsson, 2025
LOW_TRAFFIC_HOURS    = 6.0    # per night
```

Compute for the district, then extrapolate to True's ~17,000 national sites
with the extrapolation factor printed. Show a **sensitivity table** over the
incremental-sleep delta (+10 / +15 / +25 percentage points vs per-cell
rules), giving the ฿30–75M/year national range.

Print in bold: *"Every baht of this is reachable today with a classical
solver. Quantum's contribution to this number in 2026 is zero. The reason to
run it on quantum hardware is to measure the gap — see the benchmark
section."*

### Visualisations

1. Sukhumvit site map, plain.
2. Coverage graph over the map.
3. Atom register beside the map — same shape, with the scale annotation.
4. **The payoff plot**: the Bangkok map with the sleeping cells highlighted,
   derived from actual QPU measurement outcomes.
5. Shot-outcome histogram: independent-set size distribution across shots,
   with the classical optimum marked as a vertical line.
6. Classical vs quantum wall-clock, log scale.

---

## 8. Notebook structure — 15 minutes

Sections use markdown headers WHY / WHAT / HOW / RESULT / WHAT THIS MEANS.

| Cell | Time | Content |
|---|---|---|
| 1 | 0:00 | **Submit the live 20-atom QPU job immediately.** Non-blocking. Print the task ID. "That is now running in Boston." |
| 2 | 0:30 | WHY — the 3 a.m. question, RAN energy share, why nobody sleeps cells aggressively |
| 3 | 2:30 | WHAT — load Sukhumvit data, build the graph, print the merge counts |
| 4 | 4:00 | **Audience runs this** — 20-node instance on the local simulator + exact classical. Under 60 s on a laptop. |
| 5 | 6:00 | HOW — the Rydberg mapping, the scale table, the three-panel figure |
| 6 | 8:00 | RESULT 1 — load the pre-run 150-atom results from disk, show the payoff map, the coverage certificate, the money table |
| 7 | 11:00 | RESULT 2 — honest scoreboard: classical wall-clock, approximation ratio, the shot-rate gap |
| 8 | 13:00 | **Collect the live job** and compare to the simulator answer from cell 4 |
| 9 | 14:00 | WHAT THIS MEANS — runs in a browser, any Thai student, today |

Hard requirements:
- **Cell 4 must complete in under 60 seconds** on a default qBraid Lab
  instance. Pass a blockade radius to truncate the local simulator to the
  independent-set subspace — a full 2²⁰ statevector will hang. If 20 atoms is
  too slow, drop to 12–16; the story is unaffected.
- **Every pre-run result loads from committed JSON.** No QPU call is allowed
  to block the presentation except the cell-1 job, and its collection in
  cell 8 must degrade gracefully to "still queued — here is the rehearsal
  result" without an exception.
- Wrap every network call in try/except with a printed fallback.

---

## 9. Experiment budget

Pre-run before the event. Cost model: 30 credits/task + 1 credit/shot.

| Block | Tasks | Shots | Credits |
|---|---|---|---|
| 150-atom sweeps + refinement | 24 | 2,400 | 3,120 |
| 150-atom production (3 × 1000) | 3 | 3,000 | 3,090 |
| 20-atom sweeps + reference | 10 | 1,800 | 2,100 |
| 50-atom scaling point | 7 | 1,600 | 1,810 |
| Rehearsal in the real window | 3 | 900 | 990 |
| Live on stage | 3 | 900 | 990 |
| **Subtotal** | **50** | **10,600** | **12,100** |
| Contingency ~30% | ~15 | ~3,200 | ~3,630 |
| **Total** | **~65** | **~13,800** | **~15,700** |

Every task's parameters and results must be logged to a local JSON store so
the notebook can replay without a QPU.

---

## 10. Acceptance criteria

- [ ] Runs top to bottom on a fresh qBraid Lab instance with no edits
- [ ] Cell 4 completes in < 60 s
- [ ] Notebook does not raise if Aquila is offline or the job is still queued
- [ ] `COVERAGE VERIFIED` prints for every reported sleep set
- [ ] Rydberg selection uses `pre==1 and post==0`, in a documented helper
- [ ] Site-merge counts printed (`cells → sites → atoms`)
- [ ] All assumptions printed in one consolidated block
- [ ] Classical baseline shown winning on wall-clock, stated in words
- [ ] Approximation ratio reported
- [ ] Money model prints the sensitivity table and the "quantum contributes
      zero today" statement
- [ ] No claim of quantum advantage anywhere in the notebook
- [ ] Total runtime under 15 minutes including narration

## 11. References to cite inline

- Ebadi et al., *Quantum optimization of maximum independent set using
  Rydberg atom arrays*, Science 376, 1209 (2022)
- Andrist et al., *Hardness of the maximum independent set problem on
  unit-disk graphs and prospects for quantum speedups*, Phys. Rev. Research
  5, 043277 (2023) — the classical rebuttal; cite it, do not hide it
- Cazals et al., Phys. Rev. Applied (2026) — ~1000 atoms at 1 kHz needed for
  advantage; density and treewidth control instance hardness
- 3GPP TS 38.300 §15.4 — Network Energy Savings, cell DTX/DRX
- AWS Braket developer guide — Aquila analog program schema
