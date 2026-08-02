"""
deckwidgets.py — run the qBraid design-deck's live animations inside the notebook
=================================================================================

The deck's figures are self-registering custom elements (`graph-stage`,
`concept-figure`, `mapping-stage`). Jupyter sanitises `<script>` out of markdown and
HTML outputs, so we run each stage AS-IS inside a sandboxed `<iframe srcdoc>` — an
iframe executes its own scripts in an isolated document, exactly like the deck does.

    graph_stage("coloring")   # repeated-MIS graph colouring  (Canvas 2D — fully offline)
    graph_stage("mis")        # one MIS resolves to channel 1 (Canvas 2D — fully offline)
    concept_figure("power")   # 3D towers/phones             (three.js via CDN)
    mapping_stage()           # sites -> graph -> atoms       (three.js via CDN)

Each returns an IPython HTML object; make it the last expression in a cell to display.
graph-stage needs no network. concept-figure / mapping-stage import three.js from
unpkg (add three.module.js locally + point THREE_SRC at it for a fully offline demo).
"""

from __future__ import annotations

import base64
import html as _html
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # repo root; this module lives in src/
DECK = os.path.join(ROOT, "deck")
BASEMAP = os.path.join(ROOT, "data", "sukhumvit_basemap.png")

# three.js source used by concept-figure / mapping-stage. Swap for a local file
# (e.g. a data: URI or a served path) to run those two fully offline.
THREE_SRC = "https://unpkg.com/three@0.184.0/build/three.module.js"


def _read(name: str) -> str:
    with open(os.path.join(DECK, name), encoding="utf-8") as f:
        return f.read()


def _data_uri(path: str, mime: str) -> str:
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def _basemap_uri(maxw: int = 1200) -> str:
    """Basemap as a data URI, downscaled so the mapping-stage iframe stays light."""
    from io import BytesIO
    from PIL import Image
    im = Image.open(BASEMAP).convert("RGB")
    if im.width > maxw:
        im = im.resize((maxw, round(im.height * maxw / im.width)))
    buf = BytesIO(); im.save(buf, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _iframe(body: str, scripts: list[str], height: int, three: bool = False,
            radius: int = 12) -> "object":
    from IPython.display import HTML
    importmap = (f'<script type="importmap">{{"imports":{{"three":"{THREE_SRC}"}}}}</script>'
                 if three else "")
    script_tags = "\n".join(f"<script>{s}</script>" for s in scripts)
    doc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;height:100%;background:#0a0a0b;overflow:hidden}</style>"
        f"{importmap}</head><body>{body}{script_tags}</body></html>"
    )
    srcdoc = _html.escape(doc, quote=True)     # the browser HTML-decodes srcdoc back to the real doc
    return HTML(
        f'<iframe srcdoc="{srcdoc}" loading="lazy" '
        f'style="width:100%;height:{height}px;border:0;border-radius:{radius}px;'
        f'background:#0a0a0b;display:block" '
        f'sandbox="allow-scripts allow-same-origin"></iframe>'
    )


def graph_stage(mode: str = "coloring", height: int = 540):
    """Canvas-2D conflict-graph animation. mode='coloring' (repeated MIS painting the
    graph in channel colours) or 'mis' (one MIS resolves to channel 1). Fully offline."""
    body = (f'<graph-stage mode="{mode}" bare="1" '
            f'style="display:block;width:100%;height:100%"></graph-stage>')
    return _iframe(body, [_read("graph-stage.js")], height)


def concept_figure(kind: str = "power", height: int = 240):
    """3D 'why towers conflict' figure. kind = 'language' | 'power' | 'scheduling'."""
    body = (f'<concept-figure kind="{kind}" '
            f'style="display:block;width:100%;height:100%"></concept-figure>')
    return _iframe(body, [_read("concept-figure.js")], height, three=True)


DECK_HTML = os.path.join(DECK, "deck.dc.html")
DECK_ASSETS = os.path.join(DECK, "assets")
_STAGE_FILE = {"graph-stage": "graph-stage.js", "concept-figure": "concept-figure.js",
               "mapping-stage": "mapping-stage.js"}
FONTS = ("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;700;800"
         "&family=JetBrains+Mono&display=swap")


def _asset_uri(name: str, maxw: int = 1200) -> str:
    """A deck asset as a data URI; large PNGs are downscaled to keep slides light."""
    import re as _re
    from io import BytesIO
    from PIL import Image
    path = os.path.join(DECK_ASSETS, name)
    im = Image.open(path)
    if im.width > maxw or im.mode not in ("RGB", "RGBA"):
        if im.width > maxw:
            im = im.resize((maxw, round(im.height * maxw / im.width)))
    if im.mode == "RGBA":  # keep logo transparency as PNG
        buf = BytesIO(); im.save(buf, "PNG"); return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    buf = BytesIO(); im.convert("RGB").save(buf, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _sections():
    import re
    html = open(DECK_HTML, encoding="utf-8").read()
    return re.findall(r"(<section\b.*?</section>)", html, flags=re.S)


def deck_slide(index: int, height: int = 560):
    """Render deck slide `index` (0-based) as a self-contained, fit-scaled iframe that
    runs the deck's actual HTML + animation JS as-is (Canvas 2D / three.js)."""
    import re
    from IPython.display import HTML
    section = _sections()[index]
    used: set = set()

    # <x-import component-from-global-scope="graph-stage" ... mode=.. bare=.. kind=.. style=..>
    def repl(m):
        attrs = m.group(1)
        get = lambda k: (re.search(k + r'="([^"]*)"', attrs) or [None, None])[1]
        comp = get("component-from-global-scope")
        used.add(comp)
        keep = " ".join(f'{k}="{get(k)}"' for k in ("mode", "bare", "kind") if get(k) is not None)
        style = get("style") or "width:100%;height:100%;display:block"
        return f'<{comp} {keep} style="{style}"></{comp}>'
    section = re.sub(r"<x-import\s+([^>]*)></x-import>", repl, section)

    # inline assets as data URIs (relative paths don't resolve inside srcdoc)
    for name in os.listdir(DECK_ASSETS):
        if name in section:
            section = section.replace(f"assets/{name}", _asset_uri(name))

    three = bool(used & {"concept-figure", "mapping-stage"})
    scripts = ""
    if "mapping-stage" in used:
        mjs = _read("mapping-stage.js").replace("assets/sukhumvit-basemap.png", _basemap_uri())
        scripts += f"<script>{mjs}</script>"
    for comp in used - {"mapping-stage"}:
        scripts += f"<script>{_read(_STAGE_FILE[comp])}</script>"

    importmap = (f'<script type="importmap">{{"imports":{{"three":"{THREE_SRC}"}}}}</script>'
                 if three else "")
    fit_js = ("<script>const s=document.getElementById('sl');"
              "function f(){const k=Math.min(innerWidth/1920,innerHeight/1080);"
              "s.style.transform='scale('+k+')';}"
              "new ResizeObserver(f).observe(document.documentElement);"
              "addEventListener('resize',f);f();</script>")
    doc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<link rel='stylesheet' href='{FONTS}'>"
        "<style>html,body{margin:0;height:100%;background:#0a0a0b;overflow:hidden}"
        "#sl{width:1920px;height:1080px;transform-origin:top left}</style>"
        f"{importmap}</head><body><div id='sl'>{section}</div>{scripts}{fit_js}</body></html>"
    )
    srcdoc = _html.escape(doc, quote=True)
    return HTML(
        f'<iframe srcdoc="{srcdoc}" loading="lazy" sandbox="allow-scripts allow-same-origin" '
        f'style="width:100%;aspect-ratio:16/9;border:0;border-radius:12px;background:#0a0a0b;'
        f'display:block;box-shadow:0 8px 34px rgba(0,0,0,.4)"></iframe>'
    )


def mapping_stage(height: int = 560, inline_basemap: bool = True):
    """3D cell-sites -> coverage graph -> atom-register animation. Uses three.js; the
    Sukhumvit basemap is inlined as a data URI so the ground plane renders offline."""
    js = _read("mapping-stage.js")
    if inline_basemap and os.path.exists(BASEMAP):
        js = js.replace("assets/sukhumvit-basemap.png", _basemap_uri())
    body = '<mapping-stage bare="1" style="display:block;width:100%;height:100%"></mapping-stage>'
    return _iframe(body, [js], height, three=True)
