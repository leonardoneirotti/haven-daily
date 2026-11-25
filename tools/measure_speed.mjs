// Site speed measurement (issue #104). Measures, changes nothing.
//
//   python -m haven.render --briefs data/sample/briefs --out <dir>
//   node tools/measure_speed.mjs <dir> [--runs 3] [--json out.json]
//
// Serves the built site locally the way GitHub Pages does (gzip for text files,
// Cache-Control: max-age=600; checked against the live site on 18 Nov 2026), then drives
// headless Edge through the Chrome DevTools Protocol (Node 22+ has WebSocket built in):
//
// - Cold load of each page, cache off, as a laptop (1440 x 900 at 2x, 30 Mbit/s, 20 ms)
//   and as a throttled phone (390 x 844 at 3x, "slow 4G" 1.6 Mbit/s and 150 ms like
//   Lighthouse, CPU slowed 4x). Weight per file as sent (compressed) and as stored;
//   first paint, largest paint, load event, main-thread busy time, long tasks, and the
//   JavaScript functions that took the most time.
// - On pages with a chart: drag the map, zoom in twice and out once, select an item (the chart flies to it)
//   and scroll the page, while counting frames and long tasks.
//
// Nothing leaves this computer: the server listens on 127.0.0.1 and the pages load
// nothing from other sites (hard rule 14).

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import zlib from "node:zlib";
import { spawn } from "node:child_process";

// The browser: headless Edge on the owner's laptop, Chrome on a GitHub Actions runner
// (HAVEN_BROWSER, plus HAVEN_BROWSER_ARGS such as --no-sandbox there).
const BROWSER = process.env.HAVEN_BROWSER ||
  (process.platform === "win32" ? "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" : "google-chrome");
const BROWSER_ARGS = (process.env.HAVEN_BROWSER_ARGS || "").split(" ").filter(Boolean);
// Node 22+ has WebSocket built in; older Node (some CI images) uses the "ws" package.
const WebSocketImpl = globalThis.WebSocket ?? (await import("ws")).default;
const LOAD_LIMIT_MS = 60000; // a load that takes longer is recorded as stuck, not waited for
const PAGES = {
  today: "index.html",
  day: "days/2026-10-27.html", // a day with nothing on the chart: the short strip (#81)
  "day-ships": "days/2026-10-28.html", // a quiet day with 34 ships on the chart
  archive: "archive.html",
  "how-it-works": "about.html",
  "control-nocss": "control-nocss.html", // experiments only: the archive without its stylesheet
};
const MAP_PAGES = new Set(["today", "day-ships"]);
const PROFILES = {
  laptop: { width: 1440, height: 900, dpr: 2, mobile: false, cpu: 1, latency: 20, down: 30e6, up: 10e6 },
  phone: { width: 390, height: 844, dpr: 3, mobile: true, cpu: 4, latency: 150, down: 1.6e6, up: 0.75e6 },
};
const TEXT = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml",
  ".json": "application/json", ".txt": "text/plain" };
const TYPES = { ...TEXT, ".woff2": "font/woff2", ".png": "image/png", ".jpg": "image/jpeg", ".ico": "image/x-icon" };

const args = process.argv.slice(2);
const site = path.resolve(args[0] ?? "");
const runs = Number(args[args.indexOf("--runs") + 1] || 3) || 3;
const jsonOut = args.includes("--json") ? args[args.indexOf("--json") + 1] : null;
const opt = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : null);
// Experiments: only some pages or devices; block files; add CSS before the page's first layout; another pixel density.
const onlyPages = opt("--pages")?.split(","), onlyProfiles = opt("--profiles")?.split(",");
const block = opt("--block")?.split(",") ?? [], extraCss = opt("--css"), dprOverride = Number(opt("--dpr")) || null;
// --preload a,b: <link rel=preload> for these files (paths in the site), added before the page is parsed.
const preload = opt("--preload")?.split(",") ?? [];
// --js "...": a script run before the page's own scripts (experiments only, e.g. to skip a drawing step).
const extraJs = opt("--js");
const interactions = !args.includes("--no-interact");
const reducedMotion = args.includes("--reduced-motion");
if (!args[0] || !fs.existsSync(path.join(site, "index.html"))) {
  console.error("usage: node tools/measure_speed.mjs <built site dir> [--runs 3] [--json out.json]");
  process.exit(2);
}

// ---------- A local copy of GitHub Pages ----------
const gzCache = new Map();
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  let file = path.join(site, decodeURIComponent(url.pathname));
  if (!file.startsWith(site)) { res.writeHead(403).end(); return; }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
  if (!fs.existsSync(file)) { res.writeHead(404).end(); return; }
  const ext = path.extname(file);
  const headers = { "Content-Type": TYPES[ext] ?? "application/octet-stream", "Cache-Control": "max-age=600" };
  let body = fs.readFileSync(file);
  if (TEXT[ext] && /gzip/.test(req.headers["accept-encoding"] ?? "")) {
    if (!gzCache.has(file)) gzCache.set(file, zlib.gzipSync(body, { level: 6 }));
    body = gzCache.get(file);
    headers["Content-Encoding"] = "gzip";
  }
  headers["Content-Length"] = body.length;
  res.writeHead(200, headers).end(body);
});
await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
const base = `http://127.0.0.1:${server.address().port}/`;

// ---------- Edge and a tiny CDP client ----------
const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), "speed-edge-"));
const edge = spawn(BROWSER, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profileDir}`,
  "--no-first-run", "--no-default-browser-check", ...BROWSER_ARGS, "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
process.on("exit", () => edge.kill()); // also when the run ends with an error
const wsUrl = await new Promise((ok, fail) => {
  let text = "";
  edge.stderr.on("data", (d) => {
    text += d;
    const m = text.match(/DevTools listening on (ws:\/\/\S+)/);
    if (m) ok(m[1]);
  });
  setTimeout(() => fail(new Error("the browser did not start")), 20000);
});
const ws = new WebSocketImpl(wsUrl);
await new Promise((ok) => ws.addEventListener("open", ok));
let nextId = 1;
const pending = new Map();
const listeners = new Set();
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const { ok, fail } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? fail(new Error(JSON.stringify(msg.error))) : ok(msg.result);
  } else if (msg.method) {
    for (const l of listeners) l(msg);
  }
});
function send(method, params = {}, sessionId) {
  const id = nextId++;
  ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  // A browser that stops answering ends the run with an error instead of hanging it.
  return new Promise((ok, fail) => {
    const timer = setTimeout(() => { pending.delete(id); fail(new Error(`${method}: no answer in 120 s`)); }, 120000);
    pending.set(id, { ok: (r) => { clearTimeout(timer); ok(r); }, fail: (e) => { clearTimeout(timer); fail(e); } });
  });
}
const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));

// Free memory, sampled twice a second: a laptop short of memory pages to disk and stalls,
// which looks like a slow site. Each result says how low free memory went while it ran.
let memLow = Infinity;
setInterval(() => { memLow = Math.min(memLow, os.freemem()); }, 500).unref();
const memMark = () => { const low = memLow; memLow = os.freemem(); return Math.round(low / 1048576); };

const PERF_SCRIPT = `
window.__perf = { lt: [], lcp: 0, fcp: 0, frames: [], text: 0, map: 0 };
// News and status visible: the first frame in which the first news item (or "Nothing significant")
// and the port status are laid out on screen. Frames only run once the page can be painted.
(function textProbe() {
  requestAnimationFrame(function (t) {
    var news = document.querySelector(".panel-title, .panel-quiet"), status = document.querySelector(".panel-status li");
    if (news && status && news.getBoundingClientRect().height && status.getBoundingClientRect().height) __perf.text = t;
    else if (document.readyState !== "complete" || !__perf.fcp) textProbe();
  });
})();
// Map visible: the frame after the first drawing on the basemap's canvas (the chart's water,
// land and lines). The drawing methods are watched until then, and put back after.
(function mapProbe() {
  var proto = CanvasRenderingContext2D.prototype, names = ["drawImage", "fill", "stroke"], originals = {};
  names.forEach(function (name) {
    originals[name] = proto[name];
    proto[name] = function () {
      if (!__perf.map && this.canvas.isConnected && this.canvas.closest && this.canvas.closest(".leaflet-basemap-pane")) {
        names.forEach(function (n) { proto[n] = originals[n]; });
        __perf.map = -1;
        requestAnimationFrame(function () { requestAnimationFrame(function (t) { __perf.map = t; }); });
      }
      return originals[name].apply(this, arguments);
    };
  });
})();
try { new PerformanceObserver(l => l.getEntries().forEach(e => __perf.lt.push([e.startTime, e.duration])))
  .observe({ type: "longtask", buffered: true }); } catch (e) {}
try { new PerformanceObserver(l => l.getEntries().forEach(e => { __perf.lcp = e.startTime; }))
  .observe({ type: "largest-contentful-paint", buffered: true }); } catch (e) {}
try { new PerformanceObserver(l => l.getEntries().forEach(e => { if (e.name === "first-contentful-paint") __perf.fcp = e.startTime; }))
  .observe({ type: "paint", buffered: true }); } catch (e) {}
`;

// Experiments add CSS or preload links as soon as the document exists, before its first layout.
function injection() {
  const js = extraJs ? `
${extraJs}
` : "";
  if (!extraCss && !preload.length) return js;
  const html = (extraCss ? `<style>${extraCss}</style>` : "") + preload.map((f) =>
    `<link rel="preload" href="${base}${f}" as="${f.endsWith(".woff2") ? "font" : "script"}"${f.endsWith(".woff2") ? " type=\"font/woff2\" crossorigin" : ""}>`).join("");
  return `
(function () {
    function add() { document.documentElement.insertAdjacentHTML("afterbegin", ${JSON.stringify(html)}); }
    if (document.documentElement) add();
    else new MutationObserver(function (m, o) { if (document.documentElement) { o.disconnect(); add(); } })
      .observe(document, { childList: true });
  })();` + js;
}

async function openTab(profile) {
  const { targetId } = await send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
  const s = (m, p) => send(m, p, sessionId);
  for (const d of ["Page", "Network", "Performance", "Runtime", "Profiler"]) await s(`${d}.enable`);
  // A new tab in headless Edge counts as a background tab: timers and frames are throttled.
  await s("Page.bringToFront");
  await s("Emulation.setFocusEmulationEnabled", { enabled: true });
  await s("Network.setCacheDisabled", { cacheDisabled: true });
  await s("Emulation.setDeviceMetricsOverride", { width: profile.width, height: profile.height,
    deviceScaleFactor: dprOverride ?? profile.dpr, mobile: profile.mobile });
  if (block.length) await s("Network.setBlockedURLs", { urls: block });
  if (reducedMotion) await s("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  await s("Emulation.setCPUThrottlingRate", { rate: profile.cpu });
  await s("Network.emulateNetworkConditions", { offline: false, latency: profile.latency,
    downloadThroughput: profile.down / 8, uploadThroughput: profile.up / 8 });
  await s("Page.addScriptToEvaluateOnNewDocument", { source: PERF_SCRIPT + injection() });
  await s("Profiler.setSamplingInterval", { interval: 200 });
  return { targetId, sessionId, s };
}
async function evaluate(s, expression) {
  const r = await s("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  return r.result.value;
}
async function metrics(s) {
  const { metrics: list } = await s("Performance.getMetrics");
  return Object.fromEntries(list.map((m) => [m.name, m.value]));
}
function busy(before, after) {
  const d = (k) => Math.round(((after[k] ?? 0) - (before[k] ?? 0)) * 1000);
  const task = d("TaskDuration"), script = d("ScriptDuration"), layout = d("LayoutDuration"), style = d("RecalcStyleDuration");
  return { task, script, layout, style, other: task - script - layout - style };
}
function hotspots(profile, top = 8) {
  const byNode = new Map(profile.nodes.map((n) => [n.id, n]));
  const self = new Map();
  profile.samples.forEach((id, i) => {
    const n = byNode.get(id);
    const f = n.callFrame;
    if (f.functionName === "(idle)") return;
    const file = f.url ? f.url.split("/").pop() : "";
    const key = `${f.functionName || "(anonymous)"}${file ? ` ${file}:${f.lineNumber + 1}` : ""}`;
    self.set(key, (self.get(key) ?? 0) + (profile.timeDeltas[i] ?? 0) / 1000);
  });
  return [...self.entries()].sort((a, b) => b[1] - a[1]).slice(0, top).map(([k, ms]) => [k, Math.round(ms)]);
}
const median = (xs) => { const s = [...xs].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };

// ---------- A trace of the page's main thread, summed up ----------
// Self time per kind of work (layout, style, paint, script, parsing, GC...), and for layout
// the JavaScript function that forced it, if any (a "forced" layout blocks the script).
let tracing = null;
async function traceStart() {
  const events = [];
  const onData = (msg) => { if (msg.method === "Tracing.dataCollected") events.push(...msg.params.value); };
  listeners.add(onData);
  await send("Tracing.start", { transferMode: "ReportEvents",
    traceConfig: { includedCategories: ["devtools.timeline", "disabled-by-default-devtools.timeline", "v8.execute", "blink.user_timing"] } });
  tracing = { events, onData };
}
async function traceStop() {
  const { events, onData } = tracing;
  const done = new Promise((ok) => {
    const l = (msg) => { if (msg.method === "Tracing.tracingComplete") { listeners.delete(l); ok(); } };
    listeners.add(l);
  });
  await send("Tracing.end");
  await done;
  listeners.delete(onData);
  tracing = null;
  // The busiest renderer main thread is the page's.
  const mains = events.filter((e) => e.ph === "M" && e.name === "thread_name" && e.args.name === "CrRendererMain");
  let best = null, bestCount = -1;
  for (const m of mains) {
    const n = events.filter((e) => e.pid === m.pid && e.tid === m.tid && e.ph === "X").length;
    if (n > bestCount) { best = m; bestCount = n; }
  }
  if (!best) return null;
  const xs = events.filter((e) => e.pid === best.pid && e.tid === best.tid && e.ph === "X" && e.dur !== undefined)
    .sort((a, b) => a.ts - b.ts || b.dur - a.dur);
  const self = new Map(), forced = new Map();
  let layouts = 0, layoutMs = 0;
  const stack = [];
  for (const e of xs) {
    while (stack.length && stack[stack.length - 1].ts + stack[stack.length - 1].dur <= e.ts) stack.pop();
    const parent = stack[stack.length - 1];
    if (parent) parent.childDur = (parent.childDur ?? 0) + e.dur;
    stack.push(e);
  }
  for (const e of xs) {
    if (e.name === "RunTask" || e.name === "ThreadControllerImpl::RunTask") continue;
    const ms = (e.dur - (e.childDur ?? 0)) / 1000;
    self.set(e.name, (self.get(e.name) ?? 0) + ms);
    if (e.name === "Layout") {
      layouts++;
      layoutMs += e.dur / 1000;
      const st = e.args?.beginData?.stackTrace;
      const key = st && st.length ? `${st[0].functionName || "(anonymous)"} ${st[0].url.split("/").pop()}:${st[0].lineNumber}` : "(not forced by a script)";
      const f = forced.get(key) ?? { count: 0, ms: 0 };
      f.count++; f.ms += e.dur / 1000;
      forced.set(key, f);
    }
  }
  return {
    work: [...self.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10).map(([k, ms]) => [k, Math.round(ms)]),
    layouts, layoutMs: Math.round(layoutMs),
    layoutBy: [...forced.entries()].sort((a, b) => b[1].ms - a[1].ms).slice(0, 6)
      .map(([k, v]) => [k, v.count, Math.round(v.ms)]),
  };
}

// ---------- One cold load ----------
async function load(pageName, profileName, diag) {
  const profile = PROFILES[profileName];
  const { targetId, sessionId, s } = await openTab(profile);
  const files = new Map();
  let navStart = null;
  const errors = [];
  const onEvent = (msg) => {
    if (msg.sessionId !== sessionId) return;
    if (msg.method === "Runtime.exceptionThrown") {
      const d = msg.params.exceptionDetails;
      errors.push(`${d.exception?.description?.split("\n")[0] ?? d.text} (${(d.url ?? "").split("/").pop()}:${d.lineNumber + 1})`);
    } else if (msg.method === "Network.requestWillBeSent") {
      if (navStart === null) navStart = msg.params.timestamp;
      files.set(msg.params.requestId, { start: msg.params.timestamp });
    } else if (msg.method === "Network.responseReceived") {
      const r = msg.params.response;
      const f = files.get(msg.params.requestId) ?? {};
      files.set(msg.params.requestId, { ...f, url: r.url.replace(base, ""), type: r.mimeType, sent: 0, size: 0 });
    } else if (msg.method === "Network.dataReceived" && files.has(msg.params.requestId)) {
      files.get(msg.params.requestId).size += msg.params.dataLength;
    } else if (msg.method === "Network.loadingFinished" && files.has(msg.params.requestId)) {
      files.get(msg.params.requestId).sent = msg.params.encodedDataLength;
      files.get(msg.params.requestId).end = msg.params.timestamp;
    }
  };
  listeners.add(onEvent);
  const loaded = new Promise((ok) => {
    const l = (msg) => { if (msg.sessionId === sessionId && msg.method === "Page.loadEventFired") { listeners.delete(l); ok(); } };
    listeners.add(l);
  });
  const before = await metrics(s);
  if (diag) { await s("Profiler.start"); await traceStart(); }
  await s("Page.navigate", { url: base + PAGES[pageName] });
  const stuck = await Promise.race([loaded.then(() => false), sleep(LOAD_LIMIT_MS).then(() => true)]);
  // Settled: no new long task for 2.5 s (at most 40 s).
  let seen = -1, quietSince = Date.now();
  const deadline = Date.now() + 40000;
  while (Date.now() < deadline) {
    await sleep(250);
    const n = await evaluate(s, "__perf.lt.length + (document.getElementById('port-map') && !(__perf.map > 0) ? 0.5 : 0)");
    if (n !== seen) { seen = n; quietSince = Date.now(); }
    else if (Date.now() - quietSince > 2500) break;
  }
  const prof = diag ? (await s("Profiler.stop")).profile : null;
  const trace = diag ? await traceStop() : null;
  const after = await metrics(s);
  // Idle: the page just sits there for 5 s. How much of the main thread does it still use?
  if (diag) await traceStart();
  await sleep(5000);
  const idleTrace = diag ? await traceStop() : null;
  const idle = busy(after, await metrics(s));
  const t = await evaluate(s, `(() => {
    const n = performance.getEntriesByType("navigation")[0] || {};
    const lt = __perf.lt;
    const fcp = __perf.fcp;
    return { fcp: Math.round(fcp), lcp: Math.round(__perf.lcp), text: __perf.text ? Math.round(Math.max(__perf.text, fcp)) : null,
      map: __perf.map > 0 ? Math.round(__perf.map) : null, dcl: Math.round(n.domContentLoadedEventEnd),
      load: Math.round(n.loadEventEnd), longTasks: lt.length,
      longest: Math.round(Math.max(0, ...lt.map(x => x[1]))),
      tbt: Math.round(lt.filter(x => x[0] >= fcp).reduce((a, x) => a + Math.max(0, x[1] - 50), 0)),
      lastLongTaskEnd: Math.round(Math.max(0, ...lt.map(x => x[0] + x[1]))),
      canvasPx: [...document.querySelectorAll("canvas")].reduce((a, c) => a + c.width * c.height, 0),
      domNodes: document.getElementsByTagName("*").length };
  })()`);
  listeners.delete(onEvent);
  const list = [...files.values()].filter((f) => f.url !== undefined).map((f) => ({ ...f,
    startMs: Math.round((f.start - navStart) * 1000), endMs: f.end ? Math.round((f.end - navStart) * 1000) : null }));
  return { targetId, sessionId, s, timing: t, busy: busy(before, after), files: list,
    hot: prof ? hotspots(prof) : null, trace, idle, idleTrace, stuck, errors };
}

// ---------- Interactions on a page with a chart ----------
// ---------- A fly-to, frame by frame (#150) ----------
// Installed just before an item is clicked. Each frame it samples: the basemap canvas's scale (while
// the chart moves, Leaflet stretches the last drawing: scale 2 = one zoom level in; it goes back to 1
// when the chart is redrawn at the end), the map pane's position, the page's and the panel's scroll.
// It also notes every rebuild of the markers and when the pin card appears.
const FLIGHT_PROBE = `(() => {
  const p = window.__flight = { start: performance.now(), samples: [], mutations: [], card: null, stop: false };
  const canvas = document.querySelector(".leaflet-basemap-pane canvas");
  const mapPane = document.querySelector(".leaflet-map-pane");
  const markers = document.querySelector(".leaflet-marker-pane");
  const popups = document.querySelector(".leaflet-popup-pane");
  const panelList = document.querySelector(".panel-items");
  const matrix = (el) => { const t = el ? getComputedStyle(el).transform : "none"; return new DOMMatrixReadOnly(t === "none" ? undefined : t); };
  if (markers) new MutationObserver((records) => p.mutations.push([performance.now(), records.length])).observe(markers, { childList: true });
  if (popups) new MutationObserver(() => { if (!p.card && popups.querySelector(".leaflet-popup")) p.card = performance.now(); })
    .observe(popups, { childList: true, subtree: true });
  (function loop(t) {
    const c = matrix(canvas), m = matrix(mapPane);
    p.samples.push([t, c.a, c.e + m.e, c.f + m.f, window.scrollY, panelList ? panelList.scrollTop : 0]);
    if (!p.stop && t - p.start < 6000) requestAnimationFrame(loop);
  })(performance.now());
  return 1;
})()`;

// What the samples say about one flight. Moving = the canvas's scale or position changed since the
// frame before. The zoom path is log2(scale) until the redraw at the end puts the scale back to 1.
function flightSummary(raw) {
  const s = raw.samples, moving = [];
  for (let i = 1; i < s.length; i++) {
    if (Math.abs(s[i][1] - s[i - 1][1]) > 0.001 || Math.abs(s[i][2] - s[i - 1][2]) > 0.5 || Math.abs(s[i][3] - s[i - 1][3]) > 0.5) moving.push(i);
  }
  if (!moving.length) return { flightMs: 0, moved: false };
  const first = moving[0] - 1, last = moving[moving.length - 1], start = s[first][0], end = s[last][0];
  const path = s.slice(first, last + 1).filter((x, i, all) => i < all.length - 1 || Math.abs(x[1] - 1) > 0.001)
    .map((x) => Math.log2(x[1]));
  const final = path.length ? path[path.length - 1] : 0, lowest = Math.min(0, ...path), highest = Math.max(0, ...path);
  const gaps = [];
  for (let i = first + 1; i <= last; i++) gaps.push(s[i][0] - s[i - 1][0]);
  const during = (t) => t >= start && t < end, after = (t) => t >= end && t <= end + 1000;
  const scroll = (k) => Math.round(Math.max(...s.slice(first, last + 1).map((x) => x[k])) - Math.min(...s.slice(first, last + 1).map((x) => x[k])));
  return {
    moved: true,
    flightMs: Math.round(end - start),
    frames: gaps.length,
    longestFrame: Math.round(Math.max(0, ...gaps)),
    framesOver25: gaps.filter((g) => g > 25).length,
    framesOver50: gaps.filter((g) => g > 50).length,
    longTasks: raw.lt.filter((x) => x[0] >= start - 50 && x[0] <= end + 300).length,
    longestTask: Math.round(Math.max(0, ...raw.lt.filter((x) => x[0] >= start - 50 && x[0] <= end + 300).map((x) => x[1]))),
    zoomLevels: Math.round(final * 100) / 100,
    zoomsOutFirst: final > 0.05 && lowest < -0.05,
    lowestZoom: Math.round(lowest * 100) / 100,
    overshoot: highest > final + 0.05 && final > 0,
    markerRebuildsDuring: raw.mutations.filter((m) => during(m[0])).reduce((a, m) => a + m[1], 0),
    markerRebuildsAfter: raw.mutations.filter((m) => after(m[0])).reduce((a, m) => a + m[1], 0),
    cardAfterFlightMs: raw.card === null ? null : Math.round(raw.card - end),
    pageScrollPx: scroll(4),
    panelScrollPx: scroll(5),
  };
}

async function interact(tab, profileName, diag) {
  const { s } = tab;
  const profile = PROFILES[profileName];
  await evaluate(s, `(() => { const f = __perf.frames; f.length = 0;
    (function loop(t) { f.push(t); requestAnimationFrame(loop); })(performance.now()); return 1; })()`);
  const rect = await evaluate(s, `(() => { const r = document.getElementById("chart").getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height }; })()`);
  // On a phone the chart is below the panel: bring it on screen first.
  if (rect.y > profile.height - 200 || rect.y < 0) {
    await evaluate(s, `document.getElementById("chart").scrollIntoView({ block: "center" }); 1`);
    await sleep(800);
  }
  const r = await evaluate(s, `(() => { const r = document.getElementById("chart").getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height }; })()`);
  const cx = Math.round(r.x + r.w * 0.6), cy = Math.round(r.y + r.h / 2);
  const results = {};
  async function phase(name, action, settleMs) {
    const t0 = await evaluate(s, "performance.now()");
    const before = await metrics(s);
    if (diag) { await s("Profiler.start"); await traceStart(); }
    await action();
    await sleep(settleMs);
    const prof = diag ? (await s("Profiler.stop")).profile : null;
    const trace = diag ? await traceStop() : null;
    const after = await metrics(s);
    const t1 = await evaluate(s, "performance.now()");
    const f = await evaluate(s, `(() => { const f = __perf.frames.filter(t => t >= ${t0} && t <= ${t1});
      const gaps = f.slice(1).map((t, i) => t - f[i]).sort((a, b) => a - b);
      const lt = __perf.lt.filter(x => x[0] >= ${t0} && x[0] <= ${t1});
      return { frames: f.length, longestFrame: Math.round(gaps[gaps.length - 1] || 0),
        p95Frame: Math.round(gaps[Math.floor(gaps.length * 0.95)] || 0),
        slowFrames: gaps.filter(g => g > 50).length, longTasks: lt.length,
        longestTask: Math.round(Math.max(0, ...lt.map(x => x[1]))) }; })()`);
    results[name] = diag ? { busy: busy(before, after), hot: hotspots(prof, 6), trace } : { ...f, busy: busy(before, after) };
  }
  const mouse = (type, x, y, extra = {}) => s("Input.dispatchMouseEvent", { type, x, y, button: "left", ...extra });
  await phase("drag the map", async () => {
    await mouse("mousePressed", cx, cy, { clickCount: 1 });
    for (let i = 1; i <= 30; i++) { await mouse("mouseMoved", cx - i * 8, cy - i * 2, { buttons: 1 }); await sleep(16); }
    await mouse("mouseReleased", cx - 240, cy - 60, { clickCount: 1 });
  }, 2500);
  await phase("zoom in (button)", async () => {
    await evaluate(s, `document.querySelector(".leaflet-control-zoom-in").click(); 1`);
  }, 2500);
  // Two more zoom steps (#111): every new zoom level used to work out the water lines again.
  await phase("zoom in again (button)", async () => {
    await evaluate(s, `document.querySelector(".leaflet-control-zoom-in").click(); 1`);
  }, 2500);
  await phase("zoom out (button)", async () => {
    await evaluate(s, `document.querySelector(".leaflet-control-zoom-out").click(); 1`);
  }, 2500);
  // A fly-to, from the whole port each time, recorded frame by frame (#150): a number on the chart,
  // then an entry in the panel (an item with a place). The card that opens is closed after.
  async function flight(name, clickExpression) {
    await evaluate(s, `(() => { document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      const home = document.querySelector(".chart-home"); home && home.click(); return 1; })()`);
    await sleep(2000);
    await evaluate(s, FLIGHT_PROBE);
    await phase(name, async () => { await evaluate(s, clickExpression); }, 4000);
    const raw = await evaluate(s, `(() => { const p = window.__flight; p.stop = true;
      return { samples: p.samples, mutations: p.mutations, card: p.card, lt: __perf.lt.filter((x) => x[0] >= p.start) }; })()`);
    results[name].flight = flightSummary(raw);
  }
  await flight("select an item (chart flies)", `(() => { const b = document.querySelector('.callout-item[data-action="show-item"]');
    b && b.click(); return !!b; })()`);
  await flight("select an item in the panel (chart flies)", `(() => {
    const pinned = Array.from(document.querySelectorAll(".callout-item[data-rank]")).map((b) => b.getAttribute("data-rank"));
    const rank = pinned[pinned.length - 1], b = rank && document.querySelector('.panel-item[data-rank="' + rank + '"]');
    b && b.click(); return !!b; })()`);
  await evaluate(s, "window.scrollTo(0, 0); 1");
  await sleep(500);
  await phase("scroll the page", async () => {
    const x = Math.round(profile.width - 40), y = Math.round(profile.height / 2);
    for (let i = 0; i < 25; i++) {
      await s("Input.dispatchMouseEvent", { type: "mouseWheel", x, y, deltaX: 0, deltaY: 120 });
      await sleep(40);
    }
  }, 1500);
  return results;
}

// ---------- Run ----------
const cpu = os.cpus()[0]?.model ?? "unknown CPU";
const report = { measured: new Date().toISOString(), machine: `${cpu}, ${os.cpus().length} threads, ${(os.totalmem() / 1073741824).toFixed(1)} GB memory (${(os.freemem() / 1073741824).toFixed(1)} GB free at the start), ${process.platform}`, runs, pages: {} };
console.log(`Machine: ${report.machine}. ${runs} cold loads per page and device; medians.\n`);
// A first load warms Edge up (compiling, disk cache of the browser itself); not counted.
{ const w = await load("today", "laptop", false); await send("Target.closeTarget", { targetId: w.targetId }); }
for (const [pageName] of Object.entries(PAGES)) {
  if (onlyPages && !onlyPages.includes(pageName)) continue;
  if (!fs.existsSync(path.join(site, PAGES[pageName]))) continue;
  report.pages[pageName] = {};
  for (const profileName of Object.keys(PROFILES)) {
    if (onlyProfiles && !onlyProfiles.includes(profileName)) continue;
    memMark();
    const loads = [];
    for (let i = 0; i < runs; i++) {
      const tab = await load(pageName, profileName, false);
      loads.push(tab);
      if (i < runs - 1 || !MAP_PAGES.has(pageName) || !interactions) await send("Target.closeTarget", { targetId: tab.targetId });
    }
    const pick = (k) => median(loads.map((l) => l.timing[k]));
    const clean = loads[loads.length - 1];
    const files = clean.files.map((f) => ({ ...f, url: f.url.replace(/^.*?static\//, "static/") }))
      .sort((a, b) => b.sent - a.sent);
    const entry = {
      timing: { fcp: pick("fcp"), lcp: pick("lcp"), text: pick("text"), map: pick("map"), dcl: pick("dcl"), load: pick("load"),
        settled: pick("lastLongTaskEnd"), tbt: pick("tbt"), longest: pick("longest"), longTasks: pick("longTasks") },
      busy: Object.fromEntries(Object.keys(clean.busy).map((k) => [k, median(loads.map((l) => l.busy[k]))])),
      idlePer5s: median(loads.map((l) => l.idle.task)),
      stuckLoads: loads.filter((l) => l.stuck).length,
      errors: [...new Set(loads.flatMap((l) => l.errors))],
      canvasPx: clean.timing.canvasPx, domNodes: clean.timing.domNodes,
      sent: files.reduce((a, f) => a + f.sent, 0), size: files.reduce((a, f) => a + f.size, 0), requests: files.length,
      files: files.map((f) => [f.url, f.sent, f.size]),
    };
    entry.slowest = loads.map((l) => l.files.filter((f) => f.endMs !== null).sort((a, b) => b.endMs - a.endMs)[0])
      .map((f) => `${f.url.replace(/^.*?static\//, "static/")} ${f.startMs}->${f.endMs} ms`);
    if (MAP_PAGES.has(pageName) && interactions) {
      entry.interactions = await interact(clean, profileName, false);
      await send("Target.closeTarget", { targetId: clean.targetId });
    }
    // One more load with the profiler and a trace on, for where the time goes (not timed).
    const diag = await load(pageName, profileName, true);
    entry.hot = diag.hot;
    entry.trace = diag.trace;
    entry.idleTrace = diag.idleTrace;
    if (MAP_PAGES.has(pageName) && interactions) entry.diagInteractions = await interact(diag, profileName, true);
    await send("Target.closeTarget", { targetId: diag.targetId });
    entry.freeMemoryLowMB = memMark();
    report.pages[pageName][profileName] = entry;
    const t = entry.timing;
    console.log(`${pageName} / ${profileName}: ${(entry.sent / 1024).toFixed(0)} KB sent (${(entry.size / 1024).toFixed(0)} KB) in ${entry.requests} files; ` +
      `FCP ${t.fcp} ms, LCP ${t.lcp} ms, ` + (t.text ? `news+status visible ${t.text} ms, ` : "") +
      (t.map ? `map visible ${t.map} ms, ` : "") + `load ${t.load} ms, settled ${t.settled} ms, TBT ${t.tbt} ms, longest task ${t.longest} ms; ` +
      `main thread ${entry.busy.task} ms (script ${entry.busy.script}, layout ${entry.busy.layout}, style ${entry.busy.style}, other ${entry.busy.other}); ` +
      `free memory as low as ${entry.freeMemoryLowMB} MB` + (entry.errors.length ? `; JavaScript errors: ${entry.errors.join(" | ")}` : "") + (entry.stuckLoads ? `; ${entry.stuckLoads} load(s) stuck > ${LOAD_LIMIT_MS / 1000} s` : ""));
    if (entry.trace) console.log(`   load trace: ${entry.trace.work.map(([k, v]) => `${k} ${v}`).join(", ")}; ${entry.trace.layouts} layouts ${entry.trace.layoutMs} ms by ${entry.trace.layoutBy.map(([k, n, ms]) => `${k} x${n} ${ms}ms`).join("; ")}`);
    console.log(`   idle: main thread busy ${entry.idlePer5s} ms in 5 s` + (entry.idleTrace ? `; ${entry.idleTrace.work.slice(0, 6).map(([k, v]) => `${k} ${v}`).join(", ")}` : ""));
    console.log(`   last file per run: ${entry.slowest.join(" | ")}`);
    if (entry.hot) console.log(`   load JS: ${entry.hot.map(([k, v]) => `${k} ${v}`).join(", ")}`);
    if (entry.interactions) {
      for (const [name, r] of Object.entries(entry.interactions)) {
        const d = entry.diagInteractions[name];
        console.log(`   ${name}: ${r.frames} frames, longest frame ${r.longestFrame} ms, p95 ${r.p95Frame} ms, ${r.slowFrames} frames > 50 ms, ` +
          `longest task ${r.longestTask} ms; busy ${r.busy.task} ms`);
        if (d.trace) console.log(`      trace: ${d.trace.work.slice(0, 6).map(([k, v]) => `${k} ${v}`).join(", ")}; layouts ${d.trace.layouts} (${d.trace.layoutMs} ms) by ${d.trace.layoutBy.slice(0, 3).map(([k, n, ms]) => `${k} x${n} ${ms}ms`).join("; ")}`);
        console.log(`      JS: ${d.hot.slice(0, 5).map(([k, v]) => `${k} ${v}`).join(", ")}`);
        if (r.flight) console.log(`      flight: ${JSON.stringify(r.flight)}`);
      }
    }
  }
}
if (jsonOut) fs.writeFileSync(jsonOut, JSON.stringify(report, null, 1));
ws.close();
edge.kill();
server.close();
process.exit(0);
