// The chart at each of the 41 places, before and after a basemap change (issue #104).
//   node tools/basemap_shots.mjs <before site> <after site> <out dir> [--zoom 13.6]
// Two built sites (python -m haven.render ...). For every place in config/places.toml it
// centres the chart on the place at the zoom an item is shown at (13.6), and saves
// <out dir>/<place id>-before.png and -after.png; tools/basemap_sheet.py puts them side by side.
// Headless Edge (laptop) or Chrome (HAVEN_BROWSER, HAVEN_BROWSER_ARGS), like measure_speed.mjs.
// Nothing leaves this computer: the pages are served from 127.0.0.1 and load nothing from other sites.

import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const BROWSER = process.env.HAVEN_BROWSER ||
  (process.platform === "win32" ? "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" : "google-chrome");
const BROWSER_ARGS = (process.env.HAVEN_BROWSER_ARGS || "").split(" ").filter(Boolean);
const args = process.argv.slice(2);
const [beforeDir, afterDir, outDir] = args.slice(0, 3).map((p) => path.resolve(p));
const zoom = args.includes("--zoom") ? Number(args[args.indexOf("--zoom") + 1]) : 13.6;
const PAGE = "days/2026-10-28.html"; // a quiet day: few markers in the way, ships for scale
const TYPES = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml",
  ".woff2": "font/woff2", ".json": "application/json" };

// The places, read from config/places.toml (only the fields needed: id, label, lat, lon).
const places = fs.readFileSync(new URL("../config/places.toml", import.meta.url), "utf8")
  .split("[[place]]").slice(1).map((block) => Object.fromEntries(
    [...block.matchAll(/^(id|label|lat|lon)\s*=\s*"?([^"\n]+)"?/gm)].map(([, k, v]) => [k, k === "lat" || k === "lon" ? Number(v) : v])));

function serve(root) {
  const server = http.createServer((req, res) => {
    const file = path.join(root, decodeURIComponent(new URL(req.url, "http://x").pathname));
    if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) return res.writeHead(404).end();
    res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] ?? "application/octet-stream" }).end(fs.readFileSync(file));
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
}

const profile = fs.mkdtempSync(path.join(os.tmpdir(), "basemap-shots-"));
const browser = spawn(BROWSER, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profile}`,
  "--no-first-run", "--hide-scrollbars", ...BROWSER_ARGS, "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
process.on("exit", () => browser.kill());
const wsUrl = await new Promise((ok, fail) => {
  let text = "";
  browser.stderr.on("data", (d) => { text += d; const m = text.match(/ws:\/\/\S+/); if (m) ok(m[0]); });
  setTimeout(() => fail(new Error("the browser did not start")), 20000);
});
const ws = new WebSocket(wsUrl);
await new Promise((ok) => ws.addEventListener("open", ok));
let nextId = 0;
const pending = new Map();
ws.addEventListener("message", (e) => {
  const msg = JSON.parse(e.data);
  if (pending.has(msg.id)) { const { ok, fail } = pending.get(msg.id); pending.delete(msg.id); msg.error ? fail(new Error(msg.error.message)) : ok(msg.result); }
});
const send = (method, params = {}, sessionId) => new Promise((ok, fail) => {
  const id = ++nextId;
  pending.set(id, { ok, fail });
  ws.send(JSON.stringify({ id, method, params, sessionId }));
});
const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));

// The chart's Leaflet map is private to map.js; this keeps a handle on it when it is made.
const KEEP_MAP = `(function () {
  var kept;
  Object.defineProperty(window, "L", { configurable: true, get: function () { return kept; }, set: function (L) {
    kept = L;
    var make = L.map;
    L.map = function () { var m = make.apply(this, arguments); window.__chart = m; return m; };
  } });
})();`;

fs.mkdirSync(outDir, { recursive: true });
for (const [side, dir] of [["before", beforeDir], ["after", afterDir]]) {
  const server = await serve(dir);
  const { targetId } = await send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
  const s = (m, p) => send(m, p, sessionId);
  await s("Page.enable");
  await s("Runtime.enable");
  // Under 64rem the panel sits above the chart instead of over it: the whole chart is free.
  await s("Emulation.setDeviceMetricsOverride", { width: 820, height: 1000, deviceScaleFactor: 1, mobile: false });
  await s("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  await s("Page.addScriptToEvaluateOnNewDocument", { source: KEEP_MAP });
  await s("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/${PAGE}` });
  for (let i = 0; i < 100; i++) {
    const r = await s("Runtime.evaluate", { expression: "!!(window.__chart && document.fonts.status === 'loaded')", returnByValue: true });
    if (r.result.value) break;
    await sleep(200);
  }
  await sleep(1000);
  for (const place of places) {
    await s("Runtime.evaluate", { expression: `__chart.setView([${place.lat}, ${place.lon}], ${zoom}, { animate: false }); 1`, awaitPromise: true });
    await sleep(700); // the chart repaints when the move ends
    const box = (await s("Runtime.evaluate", { expression: `(() => { const r = document.getElementById("port-map").getBoundingClientRect();
      return { x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height, scale: 1 }; })()`, returnByValue: true })).result.value;
    const shot = await s("Page.captureScreenshot", { format: "png", clip: box, captureBeyondViewport: true });
    fs.writeFileSync(path.join(outDir, `${place.id}-${side}.png`), Buffer.from(shot.data, "base64"));
  }
  await send("Target.closeTarget", { targetId });
  server.close();
  console.log(`${side}: ${places.length} places`);
}
fs.writeFileSync(path.join(outDir, "places.json"), JSON.stringify(places, null, 1));
process.exit(0);
