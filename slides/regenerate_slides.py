from playwright.sync_api import sync_playwright
import pathlib, time

SRC = pathlib.Path("/home/claude/deck.html").resolve()
OUTDIR = pathlib.Path("/home/claude/slides_png")
OUTDIR.mkdir(exist_ok=True)

NAMES = [
    "title", "problem", "why-now", "the-blocker", "formulation",
    "mapping", "experiment", "result", "scoreboard", "the-gap",
    "value", "assumptions", "path-forward",
]

FONT_OVERRIDE = """
body, .slide, p, h1, h2, h3, li, td, th, div, span {
  font-family: 'Carlito', 'Liberation Sans', sans-serif !important;
}
.eyebrow, .pg, .num, .foot, th, td.r, svg text, [font-family] {
  font-family: 'Liberation Mono', 'DejaVu Sans Mono', monospace !important;
}
.bar { display: none !important; }
"""

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=2)
    pg.goto(SRC.as_uri(), wait_until="domcontentloaded", timeout=30000)
    time.sleep(2.0)
    pg.add_style_tag(content=FONT_OVERRIDE)
    # undo the auto-fit scaling so each slide renders at native 1280x800
    pg.evaluate("""() => {
        document.querySelectorAll('.page').forEach(p => {
            p.style.height = '800px'; p.style.width = '1280px';
            p.firstElementChild.style.transform = 'none';
        });
    }""")
    time.sleep(0.8)
    pages = pg.query_selector_all(".page")
    for i, el in enumerate(pages, start=1):
        name = NAMES[i-1] if i <= len(NAMES) else f"slide{i}"
        path = OUTDIR / f"slide-{i:02d}-{name}.png"
        el.screenshot(path=str(path))
        print("wrote", path.name)
    b.close()
