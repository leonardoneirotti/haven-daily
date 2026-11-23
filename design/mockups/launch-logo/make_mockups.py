"""Mockups for two logo problems found at launch (#26): the favicon and explaining the flags.

    .venv\\Scripts\\python.exe design/mockups/launch-logo/make_mockups.py

Mockups only: nothing in templates/ or static/ changes. Sample data only. Pictures go next to this
script.

1. Favicon: three options built from the H·D hoist, next to today's Blue Peter tile, each in a
   browser-tab mockup (16 px on a normal screen, 32 px on a 2x screen, light and dark tabs) and as
   a phone home-screen icon (180 px). The options are drawn as SVG on a 32-unit grid; the browser
   draws them at each size, as it would a favicon.svg.
2. Explaining the flags: (a) small letters H and D next to the flags in the header logo;
   (b) one sentence in "About this project" on Today, linking to the flag key on How it works.
   Each is the sample site with the change pasted into the built page, shot on a phone and a laptop.
"""

from __future__ import annotations

import functools
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent.parent.parent
sys.path.insert(0, str(PROJECT_DIR))
from tools import style_pass_shots as shots  # noqa: E402
from tools.make_social_preview import css_tokens  # noqa: E402

T = {name: "#" + "".join(f"{c:02x}" for c in rgb) for name, rgb in css_tokens().items()}
WHITE, RED, YELLOW, BLUE, INK, WATER, BG = (T["flag-white"], T["flag-red"], T["flag-yellow"], T["flag-blue"],
                                           T["ink"], T["water"], T["bg"])


# --- 1. the icon options ----------------------------------------------------------------------


def flag_h(x: float, y: float, s: float, stroke: float) -> str:
    return (f'<rect x="{x}" y="{y}" width="{s}" height="{s}" fill="{WHITE}"/>'
            f'<rect x="{x + s / 2}" y="{y}" width="{s / 2}" height="{s}" fill="{RED}"/>'
            f'<rect x="{x + stroke / 2}" y="{y + stroke / 2}" width="{s - stroke}" height="{s - stroke}" '
            f'fill="none" stroke="{INK}" stroke-width="{stroke}"/>')


def flag_d(x: float, y: float, s: float, stroke: float) -> str:
    return (f'<rect x="{x}" y="{y}" width="{s}" height="{s}" fill="{YELLOW}"/>'
            f'<rect x="{x}" y="{y + s / 4}" width="{s}" height="{s / 2}" fill="{BLUE}"/>'
            f'<rect x="{x + stroke / 2}" y="{y + stroke / 2}" width="{s - stroke}" height="{s - stroke}" '
            f'fill="none" stroke="{INK}" stroke-width="{stroke}"/>')


def svg(title: str, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><title>{title}</title>'
            f'{body}</svg>\n')


ICONS = {
    "now": ("Now: Blue Peter tile",
            (PROJECT_DIR / "static" / "favicon.svg").read_text(encoding="utf-8")),
    "a": ("A · Flags only",
          svg("H over D, no pole", flag_h(8, 0, 16, 1) + flag_d(8, 16, 16, 1))),
    "b": ("B · Flags on a tile",
          svg("H over D on a light-blue tile",
              f'<rect width="32" height="32" rx="7" fill="{WATER}"/>' + flag_h(10, 4, 12, 1) + flag_d(10, 16, 12, 1))),
    "c": ("C · Hoist, simplified",
          svg("H over D on a halyard",
              f'<line x1="8" y1="1" x2="8" y2="31" stroke="{INK}" stroke-width="2" stroke-linecap="round"/>'
              f'<line x1="8" y1="4" x2="12" y2="4" stroke="{INK}" stroke-width="1.5"/>'
              f'<line x1="8" y1="28" x2="12" y2="28" stroke="{INK}" stroke-width="1.5"/>'
              + flag_h(12, 2, 13, 1) + flag_d(12, 17, 13, 1))),
}
# The home-screen tile behind an icon without its own (the phone needs an opaque square).
PHONE_TILE = {"now": None, "a": BG, "b": None, "c": BG}

FAVICON_PAGE = """<!doctype html><meta charset="utf-8"><title>favicon options</title>
<style>
body{margin:0;padding:20px;background:#fff;font:13px/1.3 "Segoe UI",system-ui,sans-serif;color:#202124}
table{border-collapse:collapse;table-layout:fixed}td,th{width:400px;padding:10px 14px;vertical-align:middle;text-align:left}
th{font-weight:600;font-size:13px}th.row{color:#5f6368;font-weight:400;width:150px}td{overflow:hidden}
.strip{display:inline-flex;align-items:flex-end;padding:6px 8px 0;border-radius:8px 8px 0 0}
.tab{display:flex;align-items:center;gap:8px;width:170px;height:30px;padding:0 10px;border-radius:8px 8px 0 0;font-size:12px;white-space:nowrap;overflow:hidden}
.tab.other{opacity:.75;width:120px}
.light{background:#dee1e6}.light .tab{background:#fff;color:#202124}.light .tab.other{background:transparent}
.dark{background:#202124}.dark .tab{background:#35363a;color:#e8eaed}.dark .tab.other{background:transparent}
.tab img{width:16px;height:16px;flex:none}.ph{width:16px;height:16px;border-radius:50%;background:#9aa0a6;flex:none}
.x2{zoom:2}
.phone{width:240px;padding:18px 0 14px;border-radius:24px;background:linear-gradient(160deg,#3b4f63,#1d2a38);text-align:center}
.home{width:180px;height:180px;margin:0 auto;border-radius:40px;overflow:hidden;display:flex;align-items:center;justify-content:center}
.home img{display:block}.label{margin-top:8px;color:#fff;font-size:15px}
</style>
<table>
<tr><th></th>HEADS</tr>
<tr><th class="row">Tab, normal screen<br>(16 px), light</th>ROW_LIGHT</tr>
<tr><th class="row">Tab, normal screen<br>(16 px), dark</th>ROW_DARK</tr>
<tr><th class="row">Tab, 2x screen<br>(32 px), light</th>ROW_LIGHT2</tr>
<tr><th class="row">Tab, 2x screen<br>(32 px), dark</th>ROW_DARK2</tr>
<tr><th class="row">Phone home screen<br>(180 px)</th>ROW_PHONE</tr>
</table>"""


def tab(icon: str, theme: str, zoom: bool) -> str:
    other = "" if zoom else '<div class="tab other"><span class="ph"></span>Other site</div>'
    cell = (f'<div class="strip {theme}"><div class="tab"><img src="icons/{icon}.svg" alt="">Haven Daily · Today</div>'
            f'{other}</div>')
    return f'<td><div class="{"x2" if zoom else ""}">{cell}</div></td>'


def phone(icon: str) -> str:
    tile = PHONE_TILE[icon]
    if tile is None:  # the icon has its own tile: fill the square
        inner = f'<div class="home"><img src="icons/{icon}.svg" width="180" height="180" alt=""></div>'
    else:
        inner = f'<div class="home" style="background:{tile}"><img src="icons/{icon}.svg" width="126" height="126" alt=""></div>'
    return f'<td><div class="phone">{inner}<div class="label">Haven Daily</div></div></td>'


def favicon_mockups(work: Path) -> None:
    icons = HERE / "icons"
    icons.mkdir(exist_ok=True)
    for key, (_, text) in ICONS.items():
        (icons / f"{key}.svg").write_text(text, encoding="utf-8", newline="\n")
    keys = list(ICONS)
    page = (FAVICON_PAGE.replace("HEADS", "".join(f"<th>{ICONS[k][0]}</th>" for k in keys))
            .replace("ROW_LIGHT2", "".join(tab(k, "light", True) for k in keys))
            .replace("ROW_DARK2", "".join(tab(k, "dark", True) for k in keys))
            .replace("ROW_LIGHT", "".join(tab(k, "light", False) for k in keys))
            .replace("ROW_DARK", "".join(tab(k, "dark", False) for k in keys))
            .replace("ROW_PHONE", "".join(phone(k) for k in keys)))
    (work / "icons").mkdir(exist_ok=True)
    for f in icons.glob("*.svg"):
        shutil.copy(f, work / "icons" / f.name)
    (work / "favicon.html").write_text(page, encoding="utf-8")
    out = work / "favicon.png"
    shots.edge(["--window-size=1860,900", "--force-device-scale-factor=1", "--virtual-time-budget=2000",
                f"--screenshot={out}", (work / "favicon.html").as_uri()], work / "profile-favicon")
    with Image.open(out) as image:
        image.save(HERE / "favicon-options.png", optimize=True)
    print("  favicon-options.png")


# --- 2. explaining the flags -------------------------------------------------------------------

LETTERS_CSS = """<style>
/* Mockup (a): the letters next to the flags, centred on each flag */
.hoist-letters{display:flex;flex-direction:column;justify-content:space-between;height:2.75rem;
  padding-block:0.4rem;margin-left:-0.3rem;font-size:0.6875rem;font-weight:800;line-height:1;color:var(--ink-2)}
@media (max-width: 40rem){.hoist-letters{height:2.5rem;padding-block:0.36rem}}
</style>"""
LETTERS_HTML = '<span class="hoist-letters" aria-hidden="true"><span>H</span><span>D</span></span>'
SENTENCE = ('<p class="about-flags">Our logo spells H·D, Haven Daily, in '
            '<a href="about.html#flags">maritime signal flags</a>.</p>')


def option_a(html: str) -> str:
    html = html.replace("</head>", LETTERS_CSS + "</head>", 1)
    end = html.index("</svg>", html.index('<svg class="hoist"')) + len("</svg>")
    return html[:end] + LETTERS_HTML + html[end:]


def option_b(html: str) -> str:
    start = html.index('<div class="about-body">')
    end = html.index("</p>", start) + len("</p>")
    return html[:end] + SENTENCE + html[end:]


def legend_mockups(work: Path) -> None:
    built = work / "built"
    subprocess.run([sys.executable, "-m", "haven.render", "--briefs", "data/sample/briefs", "--out", str(built)],
                   cwd=PROJECT_DIR, check=True, capture_output=True)
    for name, change in (("letters", option_a), ("sentence", option_b)):
        site = work / name
        shutil.copytree(built, site)
        page = site / "index.html"
        page.write_text(change(page.read_text(encoding="utf-8")), encoding="utf-8")
    (work / "harness.html").write_text(shots.HARNESS, encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(shots.QuietHandler, directory=str(work)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        for name, src in (("letters", "letters/index.html"), ("sentence", "sentence/index.html#about-title")):
            for device in ("laptop", "phone"):
                out = HERE / f"{name}-{device}.jpg"
                shots.shoot(base, src, device, False, out, work)
    finally:
        server.shutdown()


if __name__ == "__main__":
    if not shots.EDGE.exists():
        raise SystemExit(f"Edge not found at {shots.EDGE}")
    with tempfile.TemporaryDirectory(prefix="logo-mockups-") as tmp:
        work = Path(tmp)
        favicon_mockups(work)
        legend_mockups(work)
