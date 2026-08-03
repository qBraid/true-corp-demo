#!/usr/bin/env python3
"""
build_deck_notebook.py — assemble which_towers_can_share_a_channel.ipynb from the qBraid deck.

Each deck slide is a self-contained, fit-scaled iframe running the deck's real HTML +
animation JS as-is (via deckwidgets.deck_slide), interleaved with runnable "run it
yourself" code cells (mock MIS 2-colour, the measured channel plan, the assumptions).
"""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import nbformat as nbf  # noqa: E402

md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

SETUP = "import sys, os\nsys.path.insert(0, os.path.join(os.getcwd(), 'src'))\nfor _pkg in ('plotly', 'anywidget'):\n    try: __import__(_pkg)\n    except ImportError:\n        import subprocess; subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', _pkg])\nimport deckwidgets as dw          # deck slides as live iframes (graph-stage Canvas 2D; three.js for the rest)\nimport towers as tw, channels as ch, widgets as wg, networkx as nx"

MOCK = '# RUN IT YOURSELF: a random 12-tower conflict graph. Solve the largest co-channel\n# group (a Maximum Independent Set) as an Analog Hamiltonian Simulation on the local\n# braket_ahs simulator (no QPU), then finish the frequency plan by repeating the MIS.\nfrom IPython.display import display\n\nreg, G, xy = tw.random_conflict_graph(n=12)          # random unit-disk (blockade) graph\ndisplay(wg.graph_view(xy, list(G.edges())))          # 1. show the conflict graph\n\nmis = tw.mis_on_simulator(reg, G, shots=200)         # 2. the MIS, measured on the simulator\nchannels, channel_of, _ = ch.iterated_mis_coloring(G, first_set=mis, solver="exact")\ndisplay(wg.channel_graph_view(xy, list(G.edges()), channels))   # 3. live colouring (drag the slider)'

RESULT = """\
# THE MEASURED CHANNEL PLAN — the real Aquila runs (5 MIS rounds), validated.
import json
d = json.load(open('results/channel_assignment_90_qpu.json'))
print(f\"source        : {d['source']}\")
print(f\"channels      : {d['n_channels']}   (optimal {d['chromatic_number']}, greedy overspend {d['overspend']})\")
print(f\"round sizes   : {d['round_sizes']}   towers per channel\")
print(f\"valid colouring: {d['valid']}  ·  90/90 towers, complete & disjoint\")"""

MEASURED = '![QuEra Aquila on qBraid](resources/quera-device-image.png)\n\n**How this plan was measured on Aquila.** Every channel is one Maximum Independent Set, solved on the QPU and then repeated on the towers left over. \n\n```python\n# 1. EXTRACT: real OpenCelliD cells -> physical sites -> Aquila-legal atom register\ndf    = tw.load_cells("data/watthana_cells_real.csv")\ncells = tw.filter_cells(df, bbox=WATTHANA)              # True-group LTE / UMTS\nsites = tw.merge_close_sites(tw.cluster_cells_to_sites(cells, ref_lat, ref_lon))\nreg   = tw.affine_to_atoms(sites)                       # scale + snap to the 4 um lattice\nG     = tw.build_graph_from_register(reg)               # unit-disk = coverage-overlap graph\n\n# 2. ENCODE: the MIS as a quasi-adiabatic Rydberg sweep (Analog Hamiltonian Simulation)\nahs = tw.build_ahs_program(reg)                         # Omega and Delta ramps; blockade = interference\n\n# 3. SUBMIT: one AHS task to QuEra Aquila via qBraid (30 credits + 1 / shot)\nfrom qbraid.runtime import QbraidProvider\ndevice = QbraidProvider().get_device("aws:quera:qpu:aquila")\njob    = device.run(ahs, shots=1000)                    # the only line that talks to the QPU\n\n# 4. COLLECT + REPEAT: decode shots, reject blockade violations, keep the valid MIS,\n#    then repeat on the leftover towers until every tower has a channel.\nshots     = job.result().data.measurements\nmis, _, _ = tw.best_valid_set(tw.decode_shots(shots, reg.n)[0], G)\nchannels  = ch.iterated_mis_coloring(G, first_set=mis)[0]\n```'

ASSUME = "tw.print_assumptions()"


def build():
    cells = [
        md(
            "# Which towers can share a channel?\n\n"
            "The **qBraid × QTRiC** deck, running live in the notebook — every slide is the deck's "
            "own HTML and animations, embedded as-is — interleaved with the code you can run yourself. "
            "*Space Grotesk / JetBrains Mono load from Google Fonts; the three.js slides (3, 4, 8) fetch "
            "three.js from unpkg — point `deckwidgets.THREE_SRC` at a local copy for a fully-offline run.*"
        ),
        code(SETUP),
        code("dw.deck_slide(0)"),  # 01 Title (graph colouring animation)
        code("dw.deck_slide(1)"),  # 02 The problem
        code("dw.deck_slide(2)"),  # 03 Why towers conflict (3D)
        code("dw.deck_slide(3)"),  # 04 What we solve (3D mapping)
        code("dw.deck_slide(4)"),  # 05 Formulation — MIS (animation)
        md(
            "### Run it yourself: solve a random conflict graph on the AHS simulator, then colour it"
        ),
        code(MOCK),
        code("dw.deck_slide(5)"),  # 06 Colouring (animation)
        code("dw.deck_slide(6)"),  # 07 The experiment — 90 atoms
        code("dw.deck_slide(7)"),  # 08 The mapping (3D)
        code("dw.deck_slide(8)"),  # 09 Result
        md("### The measured channel plan on the quantum system `Aquila` "),
        md(MEASURED),
        code(RESULT),
        code("dw.deck_slide(9)"),  # 10 Path forward
        code("dw.deck_slide(10)"),  # 11 Assumptions
        code(ASSUME),
    ]
    nb = nbf.v4.new_notebook()
    nb["cells"] = cells
    nb.metadata.kernelspec = {
        "name": "truecorp-demo",
        "display_name": "truecorp-demo",
        "language": "python",
    }
    nbf.write(nb, os.path.join(HERE, "which_towers_can_share_a_channel.ipynb"))
    print(
        f"wrote which_towers_can_share_a_channel.ipynb — {len(cells)} cells "
        f"({sum(c.cell_type=='code' for c in cells)} code, {sum(c.cell_type=='markdown' for c in cells)} md)"
    )


if __name__ == "__main__":
    build()
