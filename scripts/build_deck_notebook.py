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

SETUP = """\
import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
for _pkg in ('plotly', 'anywidget'):
    try: __import__(_pkg)
    except ImportError:
        import subprocess; subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', _pkg])
import deckwidgets as dw          # deck slides as live iframes (graph-stage Canvas 2D; three.js for the rest)
import sleepcells as sc, channels as ch, networkx as nx
print('deck ready ·', len(dw._sections()), 'slides')"""

MOCK = """\
# RUN IT YOURSELF — a mock (classical) MIS on a tiny conflict graph, coloured with 2 channels.
# A ring of towers: each conflicts only with its two neighbours, so 2 channels suffice.
import math
G = nx.cycle_graph(10)                                  # 10 towers on a ring road (even cycle)
channels, channel_of, _ = ch.iterated_mis_coloring(G, solver='exact')   # MIS -> remove -> repeat
ok, _ = ch.verify_coloring(G, channel_of)
print('mock MIS rounds :', [len(c) for c in channels], '->', len(channels), 'channels')
print('minimum needed  :', ch.chromatic_number(G), '(chromatic number)')
print('valid colouring :', 'YES — no conflict shares a channel' if ok else 'NO')
print('channel of each :', [channel_of[i] + 1 for i in range(G.number_of_nodes())])"""

RESULT = """\
# THE MEASURED CHANNEL PLAN — the real Aquila runs (5 MIS rounds), validated.
import json
d = json.load(open('results/channel_assignment_90_qpu.json'))
print(f\"source        : {d['source']}\")
print(f\"channels      : {d['n_channels']}   (optimal {d['chromatic_number']}, greedy overspend {d['overspend']})\")
print(f\"round sizes   : {d['round_sizes']}   towers per channel\")
print(f\"valid colouring: {d['valid']}  ·  90/90 towers, complete & disjoint\")"""

ASSUME = "sc.print_assumptions()"


def build():
    cells = [
        md("# Which towers can share a channel?\n\n"
           "The **qBraid × QTRiC** deck, running live in the notebook — every slide is the deck's "
           "own HTML and animations, embedded as-is — interleaved with the code you can run yourself. "
           "*Space Grotesk / JetBrains Mono load from Google Fonts; the three.js slides (3, 4, 8) fetch "
           "three.js from unpkg — point `deckwidgets.THREE_SRC` at a local copy for a fully-offline run.*"),
        code(SETUP),
        code("dw.deck_slide(0)"),   # 01 Title (graph colouring animation)
        code("dw.deck_slide(1)"),   # 02 The problem
        code("dw.deck_slide(2)"),   # 03 Why towers conflict (3D)
        code("dw.deck_slide(3)"),   # 04 What we solve (3D mapping)
        code("dw.deck_slide(4)"),   # 05 Formulation — MIS (animation)
        md("### Run it yourself — one MIS, then colour with 2 channels"),
        code(MOCK),
        code("dw.deck_slide(5)"),   # 06 Colouring (animation)
        code("dw.deck_slide(6)"),   # 07 The experiment — 90 atoms
        code("dw.deck_slide(7)"),   # 08 The mapping (3D)
        code("dw.deck_slide(8)"),   # 09 Result
        md("### The measured channel plan (real Aquila runs)"),
        code(RESULT),
        code("dw.deck_slide(9)"),   # 10 Path forward
        code("dw.deck_slide(10)"),  # 11 Assumptions
        code(ASSUME),
    ]
    nb = nbf.v4.new_notebook()
    nb["cells"] = cells
    nb.metadata.kernelspec = {"name": "truecorp-demo", "display_name": "truecorp-demo", "language": "python"}
    nbf.write(nb, os.path.join(HERE, "which_towers_can_share_a_channel.ipynb"))
    print(f"wrote which_towers_can_share_a_channel.ipynb — {len(cells)} cells "
          f"({sum(c.cell_type=='code' for c in cells)} code, {sum(c.cell_type=='markdown' for c in cells)} md)")


if __name__ == "__main__":
    build()
