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
and, about the run itself:
  timeout    the check didn't finish within CHECK_LIMIT_S; logged, the run goes on
  unfinished Edge stopped (or hit BLOCK_LIMIT_S) during this check; logged, the run goes on

Edge runs with reduced motion, so no animation keeps it busy, and a fresh Edge runs each
block of BLOCK checks. Progress is printed after every check.

Not run in CI (it needs Edge). Writes nothing to the repo: the page is built in a temporary
folder (or in --site, kept for screenshots). Items are invented ("Invented item 1").

    python tools/check_map_pins.py --only laptop --checks pairs   # 820 checks, ~1-2 s each
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
BLOCK = 20  # checks per Edge process
BLOCK_LIMIT_S = 180  # an Edge still running after this is stopped; the run goes on with the next check
CHECK_LIMIT_S = 30  # one check that takes longer is logged as "timeout"
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
const FROM = Number(params.get("from")), TO = Number(params.get("to"));
const CHECKS = __CHECKS__;
const PLACES = __PLACES__;
const CHECK_LIMIT_MS = __CHECK_LIMIT_MS__;

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
  return { name: check.name, problems: problems, reduced: win.matchMedia("(prefers-reduced-motion: reduce)").matches };
}

// One check; after CHECK_LIMIT_MS it gives up and reports "timeout", so one stuck page
// doesn't stop the run.
function run(base, check) {
  return new Promise((resolve) => {
    let done = false;
    const frame = document.createElement("iframe");
    const finish = (result) => {
      if (done) return;
      done = true;
      clearTimeout(limit);
      frame.remove();
      resolve(result);
    };
    const limit = setTimeout(() => finish({ name: check.name, problems: [{ kind: "timeout" }] }), CHECK_LIMIT_MS);
    frame.style.cssText = "position:absolute;left:0;top:0;border:0;width:" + W + "px;height:" + H + "px";
    frame.onload = async () => {
      const win = frame.contentWindow;
      await frame.contentDocument.fonts.ready;
      await new Promise((r) => win.requestAnimationFrame(() => win.requestAnimationFrame(r)));
      await new Promise((r) => setTimeout(r, 50));
      if (!done) finish(measure(check, frame));
    };
    frame.srcdoc = pageFor(base, check);
    document.body.appendChild(frame);
  });
}

// Each result goes to the tool as soon as it's ready, so a block stopped part-way keeps
// everything it finished.
(async () => {
  const base = await (await fetch("days/__DAY__.html")).text();
  for (let i = FROM; i < Math.min(TO, CHECKS.length); i++) {
    const result = await run(base, CHECKS[i]);
    await fetch("/check?run=__RUN__&n=" + (i + 1) + "&total=" + CHECKS.length, { method: "POST", body: JSON.stringify(result) });
  }
  await fetch("/done?run=__RUN__", { method: "POST" });
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
        if path == "/check":
            result = json.loads(body)
            self.server.results.setdefault(args["run"], []).append(result)
            kinds = sorted({problem["kind"] for problem in result["problems"]})
            size = args["run"].rsplit("-", 1)[0]
            print(f"  {size}: {args['n']}/{args['total']} {result['name']}" + (f"  [{', '.join(kinds)}]" if kinds else ""),
                  flush=True)
        elif path == "/done":
            self.server.event(args["run"]).set()
        self.send_response(204)
        self.end_headers()


def run_edge(url: str, profile: Path) -> bool:
    """Edge with the check page, reduced motion on. False if it hit BLOCK_LIMIT_S: then Edge
    and all its child processes are ended (a leftover Edge holding the same profile would
    take over the next launch)."""
    edge = subprocess.Popen(
        [str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
         "--window-size=1600,1000", "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
         "--disable-backgrounding-occluded-windows", "--force-prefers-reduced-motion", "--dump-dom", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        edge.wait(timeout=BLOCK_LIMIT_S)
        return True
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(edge.pid)], capture_output=True)
        edge.wait()
        return False


def run_size(name: str, site: Path, harness: str, server: Server, profile: Path, todo: list[dict]) -> list[dict]:
    """The checks in blocks of BLOCK, each in a fresh Edge (one Edge running hundreds of checks
    stopped part-way, #85; a new one per block also frees its memory). A block stopped part-way
    keeps the results it sent; the check it was on is logged as "unfinished" and the next block
    starts after it."""
    width, height = SIZES[name]
    total, results, start = len(todo), [], 0
    while start < total:
        end = min(start + BLOCK, total)
        run = f"{name}-{start}"
        (site / f"check-{run}.html").write_text(harness.replace("__RUN__", run), encoding="utf-8")
        url = (f"http://127.0.0.1:{server.server_address[1]}/check-{run}.html"
               f"?w={width}&h={height}&from={start}&to={end}")
        finished = run_edge(url, profile / run)
        server.event(run).set()  # lets the page's /hold request end, whatever happened
        got = server.results.pop(run, [])
        results += got
        start += len(got)
        if start < end:
            why = "Edge hit the block limit" if not finished else "Edge stopped"
            print(f"  {name}: {start + 1}/{total} {todo[start]['name']}  [unfinished: {why}; skipped]", flush=True)
            results.append({"name": todo[start]["name"], "problems": [{"kind": "unfinished", "why": why}]})
            start += 1
    return results


def report(name: str, results: list[dict]) -> int:
    width, height = SIZES[name]
    print(f"\n{name} ({width} x {height}): {len(results)} checks")
    failed = 0
    moving = sum(1 for r in results if r.get("reduced") is False)
    if moving:
        print(f"  warning: {moving} checks ran without reduced motion")
    for kind in ("no-map", "lost", "overlap", "hidden", "label-cut", "timeout", "unfinished"):
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

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        site = args.site or Path(tmp) / "site"
        day = build_site(site)
        todo = checks(set(args.checks.split(",")) if args.checks else set(),
                      args.places.split(",") if args.places else None)
        harness = (HARNESS.replace("__CHECKS__", json.dumps(todo))
                   .replace("__PLACES__", json.dumps({p.id: {"lat": p.lat, "lon": p.lon, "label": p.label,
                                                             "side": p.side} for p in load_places()}))
                   .replace("__DAY__", day)
                   .replace("__CHECK_LIMIT_MS__", str(CHECK_LIMIT_S * 1000)))
        server = Server(site)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            all_results = {}
            for name in [args.only] if args.only else list(SIZES):
                print(f"{name}: {len(todo)} checks", flush=True)
                all_results[name] = run_size(name, site, harness, server, Path(tmp) / f"edge-{name}", todo)
        finally:
            server.shutdown()

    failed = sum(report(name, results) for name, results in all_results.items())
    if args.json:
        args.json.write_text(json.dumps(all_results, indent=1), encoding="utf-8")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
