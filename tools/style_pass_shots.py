"""Screenshots for the visual style pass (issue #102), sample data only.

    python tools/style_pass_shots.py current            # the site as it is: 4 pages x phone/laptop
    python tools/style_pass_shots.py harbour editorial  # mockups: Today with a direction's stylesheet

Builds the sample site (data/sample/briefs) into a temporary folder and takes the pictures
in headless Edge (spec §8.7), the same way as the design review (#25): a small harness page
holds the page in an iframe of the exact screen size, because Edge won't make a window
narrower than ~500 px; the phone shots are cropped afterwards.

- "first" = the first screen, exactly as a visitor sees it (laptop 1440 x 900 at 1x,
  phone 390 x 844 at 2x).
- "full"  = the whole page at 1x. The chart's height is fixed at its first-screen value
  before the frame is stretched to the page's height, so the chart isn't drawn taller
  than on a real screen (its height follows the window height, `vh`).

A direction (design/style-pass/<name>/) is a mockup, not a change to the site: its
`style.css` is loaded *after* the site's own stylesheet in a copy of the built Today page,
so it can change only how things look (tokens, fonts, spacing, borders), never what the
page contains. Its fonts sit in its own `fonts/` folder and are loaded from there, like
the site's (hard rule 14). Nothing here is fetched from the network; templates and
static/style.css are not touched.
"""

from __future__ import annotations

import argparse
import functools
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from haven.render import render_site  # noqa: E402

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
OUT_DIR = PROJECT_DIR / "design" / "style-pass"
SAMPLE_BRIEFS = PROJECT_DIR / "data" / "sample" / "briefs"

PAGES = {  # name -> path in the built site
    "today": "index.html",
    "day": "days/2026-10-27.html",  # the sample day with a fog warning and an unrated item
    "archive": "archive.html",
    "how-it-works": "about.html",
}
DEVICES = {  # name -> (width, height, scale for the first screen)
    "laptop": (1440, 900, 1),
    "phone": (390, 844, 2),
}
EDGE_MIN_WIDTH = 600  # Edge's headless window is never narrower than ~500 px
SETTLE_MS = 2500      # fonts, the basemap and the map's first view

HARNESS = """<!doctype html>
<html><head><meta charset="utf-8"><title>shot</title>
<style>html,body{margin:0;background:#000}iframe{border:0;display:block}</style></head>
<body><iframe id="f" title="page"></iframe>
<script>
var q = new URLSearchParams(location.search);
var w = +q.get("w"), h = +q.get("h"), full = q.get("full") === "1";
var f = document.getElementById("f");
f.style.width = w + "px"; f.style.height = h + "px";
f.onload = function () {
  setTimeout(function () {
    var d = f.contentDocument;
    if (full) {
      // Keep the chart at its first-screen height, then show the whole page.
      [".stage", ".chart-map"].forEach(function (sel) {
        d.querySelectorAll(sel).forEach(function (el) {
          el.style.height = el.getBoundingClientRect().height + "px";
          el.style.minHeight = "0"; el.style.maxHeight = "none";
        });
      });
      var height = d.documentElement.scrollHeight;
      f.style.height = height + "px";
      document.body.setAttribute("data-h", height);
    } else {
      document.body.setAttribute("data-h", h);
    }
  }, SETTLE);
};
f.src = q.get("src");
</script></body></html>
""".replace("SETTLE", str(SETTLE_MS))


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def edge(args: list[str], profile: Path) -> str:
    command = [str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               "--force-prefers-reduced-motion", f"--user-data-dir={profile}", *args]
    done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=120)
    return done.stdout


def shoot(base: str, src: str, device: str, full: bool, out: Path, work: Path) -> None:
    width, height, scale = DEVICES[device]
    if full:
        scale = 1
    url = f"{base}/harness.html?src={src}&w={width}&h={height}&full={int(full)}"
    window_width = max(width, EDGE_MIN_WIDTH)
    page_height = height
    if full:  # first pass: how tall is the page?
        dom = edge([f"--window-size={window_width},{height}", f"--virtual-time-budget={SETTLE_MS + 3000}",
                    "--dump-dom", url], work / "profile-measure")
        match = re.search(r'data-h="(\d+)"', dom)
        if not match:
            raise SystemExit(f"could not measure {src} on {device}")
        page_height = int(match.group(1))
    shot = work / "shot.png"
    shot.unlink(missing_ok=True)
    edge([f"--window-size={window_width},{page_height}", f"--force-device-scale-factor={scale}",
          f"--virtual-time-budget={SETTLE_MS + 4000}", f"--screenshot={shot}", url], work / "profile-shot")
    with Image.open(shot) as image:
        image = image.convert("RGB").crop((0, 0, width * scale, page_height * scale))
        out.parent.mkdir(parents=True, exist_ok=True)
        image.save(out, "JPEG", quality=80, optimize=True, progressive=True)
    print(f"  {out.relative_to(PROJECT_DIR)}  ({image.width} x {image.height})", flush=True)


def build(work: Path) -> Path:
    site = work / "site"
    render_site(SAMPLE_BRIEFS, site)
    (work / "harness.html").write_text(HARNESS, encoding="utf-8")
    return site


def add_direction(site: Path, name: str) -> str:
    """A copy of the built Today page that loads the direction's stylesheet after the site's."""
    direction = OUT_DIR / name
    target = site / "style-pass" / name
    shutil.copytree(direction / "fonts", target / "fonts")
    shutil.copy(direction / "style.css", target / "style.css")
    page = (site / "index.html").read_text(encoding="utf-8")
    link = re.search(r'<link rel="stylesheet" href="([^"]*style\.css[^"]*)">', page)
    if not link:
        raise SystemExit("no stylesheet link in index.html")
    page = page.replace(link.group(0), link.group(0) + f'\n<link rel="stylesheet" href="style-pass/{name}/style.css">', 1)
    mockup = f"today-{name}.html"
    (site / mockup).write_text(page, encoding="utf-8")
    return mockup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("targets", nargs="+", help='"current", or the name of a folder in design/style-pass/')
    args = parser.parse_args()
    if not EDGE.exists():
        raise SystemExit(f"Edge not found at {EDGE}")
    with tempfile.TemporaryDirectory(prefix="style-pass-") as tmp:
        work = Path(tmp)
        site = build(work)
        handler = functools.partial(QuietHandler, directory=str(work))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            for target in args.targets:
                print(target, flush=True)
                if target == "current":
                    for page, path in PAGES.items():
                        for device in DEVICES:
                            for full in (False, True):
                                out = OUT_DIR / "current" / f"{page}-{device}-{'full' if full else 'first'}.jpg"
                                shoot(base, f"site/{path}", device, full, out, work)
                else:
                    mockup = add_direction(site, target)
                    for device in DEVICES:
                        for full in (False, True):
                            out = OUT_DIR / target / f"today-{device}-{'full' if full else 'first'}.jpg"
                            shoot(base, f"site/{mockup}", device, full, out, work)
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
