# Which towers can share a channel?

A live demonstration for **Quantum Club Thailand**, Grand Hall, True Digital Park (West),
Bangkok — **3 August 2026**, delivered by **qBraid × QTRiC**.

It teaches **Maximum Independent Set** through a real telecom problem: *how many cell towers in
Sukhumvit can transmit on one slice of spectrum without interfering* — mapped onto **QuEra's
Aquila** neutral-atom processor via the **qBraid SDK**, and extended to a full **frequency-reuse
plan** by repeated MIS (graph colouring).

> **No quantum advantage is claimed.** A classical solver wins on wall-clock at these sizes; the
> notebooks show it and say so. The point is that the constraint is *physical* — the Rydberg
> blockade circles are the interference circles — measured against exact classical optima.

---

## The two notebooks

| Notebook | What it is |
|---|---|
| **`which_towers_can_share_a_channel.ipynb`** | The **qBraid × QTRiC deck**, running live in the notebook — every slide is the deck's own HTML + animations (`graph-stage` Canvas 2D; `concept-figure` / `mapping-stage` three.js), embedded as sandboxed iframes — interleaved with runnable "run it yourself" cells (mock MIS → 2 channels, the measured channel plan, the printed assumptions). |
| **`qpu_result_widgets.ipynb`** | Interactive dark, qBraid-themed widgets over the **real Aquila result**: district → towers → atoms + coverage graph, and a channel-stepper across the measured colouring. |

### Run it
On **qBraid Lab** (credentials pre-configured) or locally (`pip install -r requirements.txt`):
open a notebook, select the kernel, **Restart & Run All**. The deck's three.js slides fetch
three.js from unpkg and fonts from Google Fonts (network); `graph-stage` is fully offline.
Everything replays from committed files — **no QPU job is submitted by opening a notebook.**

---

## Layout

```
which_towers_can_share_a_channel.ipynb   the deck + runnable code (slides are live iframes)
qpu_result_widgets.ipynb                 interactive widgets over the real Aquila result
requirements.txt
src/                 importable modules (added to sys.path by each notebook)
  towers.py            pipeline: scale, unit-disk graph, AHS program, classical solvers, reports
  channels.py          iterated-MIS graph colouring + exact chromatic-number baseline
  viz.py               matplotlib figures
  widgets.py           Plotly + ipywidgets result widgets (dark qBraid theme)
  deckwidgets.py       renders each deck slide as a live sandboxed iframe (deck_slide)
  nbsetup.py           environment bootstrap
deck/                deck.dc.html + graph-stage.js / concept-figure.js / mapping-stage.js + assets/
data/                real OpenCelliD extract (Watthana, MCC 520, True-group LTE/UMTS) + basemap
results/             instances, real QPU shot stores, channel assignment, slide-map PNGs
scripts/             build + experiment scripts (see below)
resources/           QuEra Aquila device image
docs/    examples/   source deck PDFs / notes; the standalone deck-animations demo
```

Key scripts (all run from the repo root):
```
python scripts/build_deck_notebook.py     # assemble the deck notebook
python scripts/mock_mis_2colour.py         # the 2-colour teaching demo
python scripts/run_channel_qpu.py --plan   # price the iterated-MIS QPU run (submits nothing)
python scripts/export_channel_map.py        # the channel-plan slide image
```

---

## What is real

The frequency-reuse plan is grounded in **real quantum execution**. Every channel was measured
on **QuEra Aquila** (1,000 shots per round), collected read-only:

- **Data** — `data/watthana_cells_real.csv`, a real **OpenCelliD** extract (MCC 520, True-group
  LTE/UMTS), CC-BY-SA 4.0. Crowdsourced estimated positions, not surveyed towers. See
  `data/DATA_PROVENANCE.md`.
- **Result** — `results/channel_assignment_90_qpu.json` (`source="QPU_iterated"`): **90/90 towers
  coloured in 5 measured MIS runs**, sizes `34 | 26 | 20 | 8 | 2`, a complete, valid colouring
  (optimal is 4 — greedy overspent by one, the honest "greedy isn't optimal" moment). Round 1 hit
  0.97 of the exact optimum; rounds 2–5 hit the exact maximum. Raw shots in
  `results/headline_qpu_90_results.json` and `results/channel_qpu_round{2,3,4}_results.json`.

Jobs are submitted only by the presenter, from `scripts/run_channel_qpu.py --run-all` /
`run_headline_qpu.py --submit`. Cost model: **30 credits/task + 1 credit/shot**.

---

## Honesty constraints (printed by `towers.print_assumptions`)

- **Protocol (unit-disk) model, not physical** — conflicts are binary and pairwise; real
  interference aggregates and fails on a threshold ratio.
- Coverage is **uniform-radius disks**; a fixed 500 m interference radius, not OpenCelliD's range.
- Positions are **crowdsourced estimates**; colocated sectors collapse to one mast per site.
- **Greedy colouring is not optimal** — an exact ILP / chromatic-number baseline runs alongside.
- **No quantum advantage claimed** — CBC solves a 100-node MIS in milliseconds.

## References
Ebadi et al., *Science* **376**, 1209 (2022) · Andrist et al., *Phys. Rev. Research* **5**,
043277 (2023) · Cazals et al., *Phys. Rev. Applied* (2026) · Sarkar et al., arXiv:2511.09633 ·
3GPP TS 38.300 §15.4 · AWS Braket developer guide (Aquila AHS) · Cell data © OpenCelliD, CC-BY-SA 4.0.
