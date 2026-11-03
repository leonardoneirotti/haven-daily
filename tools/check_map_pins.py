"""Map pin check in headless Edge (issue #85; method: docs/design-review.md, "Map checks").

Renders one day page, then loads its chart once per check, at the home view, with a
different set of numbered items each time:
  - all 41 places at once (the "all-places check page");
  - every place alone;
  - every pair of places (820 pairs).
Each check runs at laptop size (1440 x 900) and phone size (390 x 844, an iframe that wide,
as in spec §8.7), and measures the numbered markers on the chart:
  overlap    two visible markers (number + label) overlap
  hidden     an item's number is not fully on the chart, or is under the news panel
  lost       an item is on no marker (or on more than one)
  label-cut  a marker's label runs past the chart's edge or under the panel

Not run in CI (it needs Edge). Writes nothing to the repo: the page is built in a temporary
folder (or in --site, kept for screenshots). Items are invented ("Invented item 1").

    python tools/check_map_pins.py                  # everything, both sizes (~10-20 min)
    python tools/check_map_pins.py --only laptop --checks all,singles
"""

from __future__ import annotations

import argparse
import copy
import functools
import itertools
import json
import subprocess
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from haven import render  # noqa: E402
from haven.config import load_places  # noqa: E402

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
SIZES = {"laptop": (1440, 900), "phone": (390, 844)}
BASE_BRIEF = ROOT / "data" / "sample" / "briefs" / "2026-10-29.json"  # a sample day with pins

# The harness page: loads the day page into an iframe once per check, with that check's items
# written into the page's map data, waits for the chart and the fonts, and measures. It sends
# the results to this tool's local server. Until then the page keeps one image request open
# (/hold), so Edge's --dump-dom doesn't end the run before the checks are done.
HARNESS = """<!doctype html>
<meta charset="utf-8">
<title>Map pin check</title>
<body style="margin:0">
<img src="/hold?run=__RUN__" alt="" width="1" height="1">
<script>
"use strict";
const params = new URLSearchParams(location.search);
const W = Number(params.get("w")), H = Number(params.get("h"));
const CHECKS = __CHECKS__;
const PLACES = __PLACES__;
const results = [];

function pageFor(base, check) {
  const callouts = check.places.map((id, i) => Object.assign(
    { rank: i + 1, severity: i === 0 ? "high" : "medium", title: "Invented item " + (i + 1) }, PLACES[id]));
  return base
    .replace(/(<script type="application\\/json" id="map-data">)([\\s\\S]*?)(<\\/script>)/, (all, open, json, close) => {
      const data = JSON.parse(json);
      data.callouts = callouts;
      data.ships = null;
      return open + JSON.stringify(data).replace(/</g, "\\\\u003c") + close;
    })
    .replace("<head>", '<head><base href="' + new URL("days/", location.href) + '">');
}

function box(r) { return { left: r.left, top: r.top, right: r.right, bottom: r.bottom }; }
function overlap(a, b) {
  const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  return w > 0.5 && h > 0.5 ? Math.round(w) + "x" + Math.round(h) + " px" : null;
}
function inside(a, area) {
  return a.left >= area.left - 0.5 && a.right <= area.right + 0.5 && a.top >= area.top - 0.5 && a.bottom <= area.bottom + 0.5;
}

function measure(check, frame) {
  const doc = frame.contentDocument, win = frame.contentWindow;
  const mapEl = doc.getElementById("port-map");
  if (!mapEl || !doc.documentElement.classList.contains("has-map")) return { name: check.name, problems: [{ kind: "no-map" }] };
  const chart = box(mapEl.getBoundingClientRect());
  const panel = doc.querySelector(".panel");
  const panelRight = panel && win.getComputedStyle(panel).position === "absolute" ? panel.getBoundingClientRect().right : chart.left;
  const free = { left: Math.max(chart.left, panelRight), right: chart.right, top: chart.top, bottom: chart.bottom };
  const markers = Array.from(doc.querySelectorAll(".leaflet-marker-pane .callout")).map((m) => ({
    box: box((m.querySelector(".callout-inner") || m).getBoundingClientRect()),
    nums: Array.from(m.querySelectorAll(".num")).map((n) => ({ rank: Number(n.textContent.trim()), box: box(n.getBoundingClientRect()) })),
    text: m.textContent.replace(/\\s+/g, " ").trim(),
  }));
  const problems = [];
  const visible = markers.filter((m) => overlap(m.box, chart));
  for (let i = 0; i < visible.length; i++) {
    for (let j = i + 1; j < visible.length; j++) {
      const px = overlap(visible[i].box, visible[j].box);
      if (px) problems.push({ kind: "overlap", a: visible[i].text, b: visible[j].text, px: px });
    }
  }
  check.places.forEach((id, i) => {
    const found = markers.flatMap((m) => m.nums).filter((n) => n.rank === i + 1);
    if (found.length !== 1) problems.push({ kind: "lost", place: id, markers: found.length });
    else if (!inside(found[0].box, free)) problems.push({ kind: "hidden", place: id });
  });
  visible.forEach((m) => {
    const numsShown = m.nums.every((n) => inside(n.box, free));
    if (numsShown && !inside(m.box, free)) problems.push({ kind: "label-cut", marker: m.text });
  });
  return { name: check.name, problems: problems };
}

function run(base, check) {
  return new Promise((resolve) => {
    const frame = document.createElement("iframe");
    frame.style.cssText = "position:absolute;left:0;top:0;border:0;width:" + W + "px;height:" + H + "px";
    frame.onload = async () => {
      const win = frame.contentWindow;
      await frame.contentDocument.fonts.ready;
      await new Promise((r) => win.requestAnimationFrame(() => win.requestAnimationFrame(r)));
      await new Promise((r) => setTimeout(r, 50));
      const result = measure(check, frame);
      frame.remove();
      resolve(result);
    };
    frame.srcdoc = pageFor(base, check);
    document.body.appendChild(frame);
  });
}

(async () => {
  const base = await (await fetch("days/__DAY__.html")).text();
  for (let i = 0; i < CHECKS.length; i++) {
    results.push(await run(base, CHECKS[i]));
    if (results.length % 50 === 0) fetch("/progress?run=__RUN__&done=" + results.length, { method: "POST" });
  }
  await fetch("/result?run=__RUN__", { method: "POST", body: JSON.stringify(results) });
})();
</script>
"""


def build_site(site: Path) -> str:
    """The day page every check starts from: a sample day with its pins, without ships (as in v1)."""
    brief = json.loads(BASE_BRIEF.read_text(encoding="utf-8"))
    brief = copy.deepcopy(brief)
    brief["ships"] = None
    briefs = site / "briefs"
    briefs.mkdir(parents=True, exist_ok=True)
    (briefs / f"{brief['date']}.json").write_text(json.dumps(brief), encoding="utf-8")
    render.render_site(briefs, site)
    return brief["date"]


def checks(which: set[str], custom: list[str] | None = None) -> list[dict]:
    ids = [place.id for place in load_places()]
    found = []
    if custom:
        unknown = set(custom) - set(ids)
        if unknown:
            raise SystemExit(f"Unknown place ids: {sorted(unknown)}")
        found.append({"name": " + ".join(custom), "places": custom})
    if "all" in which:
        found.append({"name": "all places", "places": ids})
    if "singles" in which:
        found += [{"name": place, "places": [place]} for place in ids]
    if "pairs" in which:
        found += [{"name": f"{a} + {b}", "places": [a, b]} for a, b in itertools.combinations(ids, 2)]
    return found


class Server(ThreadingHTTPServer):
    """Serves the check page and collects what the harness sends back."""

    def __init__(self, folder: Path):
        super().__init__(("127.0.0.1", 0), functools.partial(Handler, directory=str(folder)))
        self.results: dict[str, list] = {}
        self.finished: dict[str, threading.Event] = {}

    def event(self, run: str) -> threading.Event:
        return self.finished.setdefault(run, threading.Event())


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path != "/hold":
            return super().do_GET()
        self.server.event(query.split("run=")[1]).wait(timeout=3600)
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        path, _, query = self.path.partition("?")
        args = dict(part.split("=", 1) for part in query.split("&"))
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if path == "/progress":
            print(f"  {args['run']}: {args['done']} checks", flush=True)
        elif path == "/result":
            self.server.results[args["run"]] = json.loads(body)
            self.server.event(args["run"]).set()
        self.send_response(204)
        self.end_headers()


def run_size(name: str, site: Path, harness: str, server: Server, profile: Path) -> list[dict]:
    width, height = SIZES[name]
    (site / f"check-{name}.html").write_text(harness.replace("__RUN__", name), encoding="utf-8")
    url = f"http://127.0.0.1:{server.server_address[1]}/check-{name}.html?w={width}&h={height}"
    subprocess.run(
        [str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
         "--window-size=1600,1000", "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
         "--disable-backgrounding-occluded-windows", "--dump-dom", url],
        capture_output=True, timeout=3600,
    )
    if name not in server.results:
        raise SystemExit(f"{name}: Edge finished without sending results")
    return server.results[name]


def report(name: str, results: list[dict]) -> int:
    width, height = SIZES[name]
    print(f"\n{name} ({width} x {height}): {len(results)} checks")
    failed = 0
    for kind in ("no-map", "lost", "overlap", "hidden", "label-cut"):
        hits = [(r["name"], p) for r in results for p in r["problems"] if p["kind"] == kind]
        names = sorted({n for n, _ in hits})
        print(f"  {kind:10} {len(names):4} checks")
        for check_name, problem in hits[:12]:
            detail = {k: v for k, v in problem.items() if k != "kind"}
            print(f"             {check_name}: {detail}")
        if len(hits) > 12:
            print(f"             ... {len(hits) - 12} more")
        failed += len(names)
    return failed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", choices=sorted(SIZES), help="one screen size only")
    parser.add_argument("--checks", default="all,singles,pairs", help="any of all,singles,pairs")
    parser.add_argument("--places", help="one extra check with these place ids, in rank order (comma-separated)")
    parser.add_argument("--site", type=Path, help="build the check page here and keep it (for screenshots)")
    parser.add_argument("--json", type=Path, help="also write every result to this file")
    args = parser.parse_args()
    if not EDGE.exists():
        raise SystemExit(f"Edge not found at {EDGE}")

    with tempfile.TemporaryDirectory() as tmp:
        site = args.site or Path(tmp) / "site"
        day = build_site(site)
        todo = checks(set(args.checks.split(",")) if args.checks else set(),
                      args.places.split(",") if args.places else None)
        harness = (HARNESS.replace("__CHECKS__", json.dumps(todo))
                   .replace("__PLACES__", json.dumps({p.id: {"lat": p.lat, "lon": p.lon, "label": p.label,
                                                             "side": p.side} for p in load_places()}))
                   .replace("__DAY__", day))
        server = Server(site)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            all_results = {}
            for name in [args.only] if args.only else list(SIZES):
                print(f"{name}: {len(todo)} checks", flush=True)
                all_results[name] = run_size(name, site, harness, server, Path(tmp) / f"edge-{name}")
        finally:
            server.shutdown()

    failed = sum(report(name, results) for name, results in all_results.items())
    if args.json:
        args.json.write_text(json.dumps(all_results, indent=1), encoding="utf-8")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
