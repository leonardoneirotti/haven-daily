"""Before/after screenshots for the visual style pass (issue #102), sample data only.

    python tools/style_pass_shots.py before --ref origin/main   # the site before the style pass
    python tools/style_pass_shots.py after                      # this checkout
    python tools/style_pass_shots.py before --out design/screenshots/issue-117 --pages today,how-it-works

Builds the sample site (data/sample/briefs), from this checkout or from a git ref (checked out
into a temporary worktree), and takes the pictures in headless Edge (spec §8.7), the same way as
the design review (#25): a small harness page holds the page in an iframe of the exact screen
size, because Edge won't make a window narrower than ~500 px; the phone shots are cropped
afterwards. Pictures go to design/style-pass/<name>/<page>-<device>-<first|full>.jpg.

- "first" = the first screen, exactly as a visitor sees it (laptop 1440 x 900 at 1x,
  phone 390 x 844 at 2x).
- "full"  = the whole page, trimmed so the design folder stays small (owner, 20 Nov 2026):
  at most the first FULL_MAX_HEIGHT pixels of the page, the laptop at half size. The chart's
  height is fixed at its first-screen value before the frame is stretched to the page's height,
  so the chart isn't drawn taller than on a real screen (its height follows the window, `vh`).

Nothing is fetched from the network; reduced motion is on, so the pictures don't depend on
where an animation happened to be.
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
from urllib.parse import quote
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

PROJECT_DIR = Path(__file__).resolve().parent.parent
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
OUT_DIR = PROJECT_DIR / "design" / "style-pass"
SAMPLE_BRIEFS = "data/sample/briefs"

PAGES = {  # name -> path in the built site
    "today": "index.html",
    "day": "days/2026-10-27.html",  # the sample day with a fog warning and an unrated item
    "archive": "archive.html",
    "how-it-works": "about.html",
    "not-found": "404.html",  # since #117
    "flag-key": "about.html#flags",  # How it works, scrolled to the flag key (#117)
    "about-block": "index.html#about-title",  # Today, scrolled to "About this project"
}
DEVICES = {  # name -> (width, height, scale for the first screen, scale for the whole page)
    "laptop": (1440, 900, 1, 0.5),
    "phone": (390, 844, 2, 1),
}
FULL_MAX_HEIGHT = 3000  # CSS pixels of a whole page kept in the "full" picture
EDGE_MIN_WIDTH = 600    # Edge's headless window is never narrower than ~500 px
SETTLE_MS = 2500        # fonts, the basemap and the map's first view
JPEG_QUALITY = 72
SITE_PATH = "haven-daily"  # the site's path on GitHub Pages (config/site.toml base_url)

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
      var height = Math.min(d.documentElement.scrollHeight, MAX);
      f.style.height = height + "px";
      document.body.setAttribute("data-h", height);
    } else {
      document.body.setAttribute("data-h", h);
    }
  }, SETTLE);
};
f.src = q.get("src");
</script></body></html>
""".replace("SETTLE", str(SETTLE_MS)).replace("MAX", str(FULL_MAX_HEIGHT))


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def edge(args: list[str], profile: Path) -> str:
    command = [str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               "--force-prefers-reduced-motion", f"--user-data-dir={profile}", *args]
    done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=180)
    return done.stdout


def shoot(base: str, src: str, device: str, full: bool, out: Path, work: Path) -> None:
    width, height, first_scale, full_scale = DEVICES[device]
    scale = 1 if full else first_scale
    url = f"{base}/harness.html?src={quote(src, safe='/')}&w={width}&h={height}&full={int(full)}"
    window_width = max(width, EDGE_MIN_WIDTH)
    page_height = height
    if full:  # first pass: how tall is the page (up to FULL_MAX_HEIGHT)?
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
        if full and full_scale != 1:
            image = image.resize((round(image.width * full_scale), round(image.height * full_scale)), Image.LANCZOS)
        out.parent.mkdir(parents=True, exist_ok=True)
        image.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    print(f"  {out.relative_to(PROJECT_DIR)}  ({image.width} x {image.height})", flush=True)


def build(work: Path, ref: str | None) -> None:
    """The sample site into work/site: from this checkout, or from `ref` in a temporary worktree."""
    out = work / "site"
    if ref is None:
        subprocess.run([sys.executable, "-m", "haven.render", "--briefs", SAMPLE_BRIEFS, "--out", str(out)],
                       cwd=PROJECT_DIR, check=True)
    else:
        tree = work / "ref"
        subprocess.run(["git", "worktree", "add", "--detach", str(tree), ref], cwd=PROJECT_DIR, check=True,
                       capture_output=True)
        try:
            subprocess.run([sys.executable, "-m", "haven.render", "--briefs", SAMPLE_BRIEFS, "--out", str(out)],
                           cwd=tree, check=True)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=PROJECT_DIR, check=True)
    # The 404 page links from the site's own path (/haven-daily/, #117): serve a copy there too.
    shutil.copytree(out, work / SITE_PATH)
    (work / "harness.html").write_text(HARNESS, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="folder in design/style-pass/ for the pictures, e.g. before or after")
    parser.add_argument("--ref", help="build the site from this git ref instead of the checkout")
    parser.add_argument("--pages", default="today,day,archive,how-it-works",
                        help="comma-separated: " + ", ".join(PAGES))
    parser.add_argument("--out", default=str(OUT_DIR.relative_to(PROJECT_DIR)),
                        help="folder for the pictures, relative to the project (default: design/style-pass)")
    args = parser.parse_args()
    out_dir = PROJECT_DIR / args.out
    if not EDGE.exists():
        raise SystemExit(f"Edge not found at {EDGE}")
    with tempfile.TemporaryDirectory(prefix="style-pass-") as tmp:
        work = Path(tmp)
        build(work, args.ref)
        handler = functools.partial(QuietHandler, directory=str(work))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            for page in args.pages.split(","):
                for device in DEVICES:
                    for full in (False, True):
                        out = out_dir / args.name / f"{page}-{device}-{'full' if full else 'first'}.jpg"
                        folder = SITE_PATH if page == "not-found" else "site"
                        shoot(base, f"{folder}/{PAGES[page]}", device, full, out, work)
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
