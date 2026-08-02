# Which cells can sleep tonight?

A single self-contained Jupyter notebook for the live demonstration at **Quantum Club
Thailand**, Grand Hall, True Digital Park (West), Bangkok — **3 August 2026**.

It solves a real problem from True Corporation's Bangkok network — *which cell sites can be
put to sleep at 3 a.m. without opening a coverage hole* — by mapping it to **Maximum
Independent Set** on a unit-disk graph and running it on **QuEra's Aquila** neutral-atom
processor via the **qBraid SDK**.

> **We do not claim quantum advantage.** On these instance sizes a classical solver wins on
> wall-clock time; the notebook shows it and says so. The reason to run on quantum hardware
> in 2026 is to *measure the gap*.

---

## Run it

On **qBraid Lab** (recommended — credentials are pre-configured):

1. Upload this whole folder (the notebook needs `sleepcells.py`, `sleepviz.py`, `data/`,
   `results/`; the slides are embedded, so `slides/` is only needed to rebuild the notebook).
2. Open `which_cells_can_sleep.ipynb` and **Run All**. It executes top-to-bottom in well
   under a minute; no QPU job is submitted by default.
3. To submit the real live job on stage, set `SUBMIT_LIVE_JOB = True` in the Setup cell.

Locally: `pip install -r requirements.txt`, then run the notebook. Device enumeration and
the live job need qBraid credentials; every other cell runs fully offline from committed
files.

### The two knobs (top of the notebook)
| Parameter | Default | Meaning |
|---|---|---|
| `COVERAGE_OVERLAP_M` | `500` | Two sites "mutually cover" within this many metres. If a district does not fit the chip's field of view, this is the knob. |
| `LIVE_ATOMS` | `16` | Size of the audience live-simulation instance. **16** is the safe default (~2 s on Lab). The deck narrates *"the 20-atom instance"* — set `LIVE_ATOMS = 20` to match exactly (~30 s locally). `12` is bullet-proof. |
| `SUBMIT_LIVE_JOB` | `False` | Leave `False` to rehearse (no credits spent). Set `True` on stage to submit the real Aquila job. |

---

## What is real, what is a stand-in

This build was prepared with **read-only** access to the qBraid platform — **no QPU jobs were
submitted**. Two things are therefore stand-ins, and both are labelled loudly in the notebook:

- **Cell positions** — `data/watthana_cells.csv` is **representative** data generated on the
  real Watthana geography (real bounding box, real Sukhumvit BTS corridor, real True/dtac MNC
  codes under MCC 520), **not** real OpenCelliD records and **not** surveyed towers. See
  `data/DATA_PROVENANCE.md`. To use real data, run `scripts/download_opencellid.py` (needs a
  free OpenCelliD token) and point `DATA_CSV` at the output — nothing else changes.

- **QPU results** — the notebook is fully submit-ready, but the committed results are:
  - `results/localsim_{16,20}_results.json` — **real Braket local Rydberg (AHS) simulations**
    (`source="LOCAL_AHS_SIM"`), the most faithful stand-in that exists without submitting.
  - `results/prerun_150_results.json` — a **phenomenological** stand-in
    (`source="SIMULATED_STANDIN"`) for the 150-atom headline, which the local simulator cannot
    reach. It is a documented model (random-order greedy independent sets + loading defects),
    **not** a quantum simulation and **not** QPU data. The notebook prints a banner saying so.

  Before the event, run the real pre-runs (below) and overwrite `results/prerun_150_results.json`
  with `source="QPU"`; the banner turns off automatically.

---

## Files

```
which_cells_can_sleep.ipynb   the demo AND the deck in one file (slides base64-embedded)
sleepcells.py                 tested pipeline + printed reports: scale, graph, AHS, solvers, money
sleepviz.py                   all matplotlib figures (Style + low/high-level plot helpers)
requirements.txt
data/
  watthana_cells.csv          representative OpenCelliD-schema cells (generated)
  DATA_PROVENANCE.md          honest provenance statement
results/
  sukhumvit_{150,20,16}.json  instances (atoms, graph, classical optima)
  prerun_150_results.json     150-atom shots — SIMULATED_STANDIN (replace with QPU pre-run)
  localsim_{20,16}_results.json   live-cell shots — LOCAL_AHS_SIM
slides/
  slide-01..13-*.png          the 13 presentation slides (embedded into the notebook's markdown)
scripts/
  generate_representative_data.py   rebuilds data/watthana_cells.csv
  download_opencellid.py            fetch REAL OpenCelliD data (drop-in replacement)
  prerun_experiments.py             rebuild instances + stand-in results
  build_notebook.py                 assemble the .ipynb (embeds slides/ + wires the helpers)
```

**The notebook is the presentation.** There is no separate deck: each section shows the slide
it explains (base64-embedded, so the `.ipynb` renders the whole talk with no external files),
then the code proves it live. Presenter speaks to the slide; the cell output is the proof.
Architecture: `sleepcells` = logic + printed reports, `sleepviz` = figures, notebook = thin
orchestration + the slides.

Regenerate everything from scratch:
```
python scripts/generate_representative_data.py   # -> data/watthana_cells.csv
python scripts/prerun_experiments.py             # -> results/*.json
python scripts/build_notebook.py                 # -> which_cells_can_sleep.ipynb
```

---

## The real pre-runs (for the presenter, with submit access)

The notebook contains the exact submission code (`aq.run(build_ahs_program(reg), shots=...)`).
To produce real QPU data, in a submit-enabled qBraid environment:

1. Build the 150-atom program (`sleepcells.build_ahs_program`), submit `3 × 1000` shots to
   `aws:quera:qpu:aquila`, collect, and write the pre/post sequences into
   `results/prerun_150_results.json` with `source="QPU"` (schema: `sleepcells.save_results`).
2. Optionally sweep `Δ_start`, `Δ_end`, `t_ramp` to tune the approximation ratio first.

Cost model (matches the live device): **30 credits/task + 1 credit/shot**. The full
pre-run + rehearsal + stage budget is ~13,800 shots ≈ **15,700 credits** (see the spec).

---

## Honesty constraints (baked in and printed)

- MIS is a **conservative relaxation** of the true optimum (complement of a minimum dominating
  set): always feasible, may leave savings unclaimed.
- Coverage is modelled as **uniform-radius disks**; real radii vary by band, tilt, class.
- Positions are **crowdsourced estimated centroids**, not surveyed towers.
- Site-merge counts are printed explicitly (`cells → sites → atoms`).
- Every reported sleep set prints `COVERAGE VERIFIED`.
- **No quantum advantage is claimed anywhere.**

## References

Ebadi et al., *Science* **376**, 1209 (2022) · Andrist et al., *Phys. Rev. Research* **5**,
043277 (2023) · Cazals et al., *Phys. Rev. Applied* (2026) · Sarkar et al., arXiv:2511.09633 ·
3GPP TS 38.300 §15.4 · AWS Braket developer guide (Aquila AHS schema).
