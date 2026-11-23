// How the chart takes the mouse, wheel, touchpad, keys and touch (issue #111), before and after.
//
//   python -m haven.render --briefs data/sample/briefs --out <dir>      (once per version)
//   node tools/check_map_input.mjs <before dir> <after dir>
//
// Opens Today of each built sample site in a headless browser (Edge here, Chrome on a GitHub
// runner: HAVEN_BROWSER, HAVEN_BROWSER_ARGS), sends real input through the DevTools protocol and
// reads what the chart and the page did: zoom (from the chart's own scale), how far the chart
// moved, how far the page scrolled, whether the browser's page zoom was stopped, the hint, the
// header. Laptop 1440 x 900 with a mouse; phone 390 x 844 with touch. Prints a Markdown table
// (for the speed run's summary). Changes nothing; the server listens on 127.0.0.1 and the pages
// load nothing from other sites (hard rule 14).

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawn } from "node:child_process";

const BROWSER = process.env.HAVEN_BROWSER ||
  (process.platform === "win32" ? "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" : "google-chrome");
const BROWSER_ARGS = (process.env.HAVEN_BROWSER_ARGS || "").split(" ").filter(Boolean);
const WebSocketImpl = globalThis.WebSocket ?? (await import("ws")).default;
const TYPES = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml",
  ".json": "application/json", ".txt": "text/plain", ".woff2": "font/woff2", ".png": "image/png" };

const sites = process.argv.slice(2, 4).map((d) => path.resolve(d));
if (sites.length !== 2 || !sites.every((d) => fs.existsSync(path.join(d, "index.html")))) {
  console.error("usage: node tools/check_map_input.mjs <before dir> <after dir>");
  process.exit(2);
}

// ---------- Both sites, side by side: /before/... and /after/... ----------
const server = http.createServer((req, res) => {
  const [, which, ...rest] = decodeURIComponent(new URL(req.url, "http://x").pathname).split("/");
  const root = { before: sites[0], after: sites[1] }[which];
  const file = root && path.join(root, ...rest);
  if (!file || !file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404).end(); return; }
  res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] ?? "application/octet-stream" }).end(fs.readFileSync(file));
});
await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
const base = `http://127.0.0.1:${server.address().port}/`;

// ---------- The browser and a tiny CDP client ----------
const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), "input-browser-"));
const browser = spawn(BROWSER, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profileDir}`,
  "--no-first-run", "--no-default-browser-check", ...BROWSER_ARGS, "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
process.on("exit", () => browser.kill());
const wsUrl = await new Promise((ok, fail) => {
  let text = "";
  browser.stderr.on("data", (d) => { text += d; const m = text.match(/DevTools listening on (ws:\/\/\S+)/); if (m) ok(m[1]); });
  setTimeout(() => fail(new Error("the browser did not start")), 20000);
});
const ws = new WebSocketImpl(wsUrl);
await new Promise((ok) => ws.addEventListener("open", ok));
let nextId = 1;
const pending = new Map();
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const { ok, fail } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? fail(new Error(JSON.stringify(msg.error))) : ok(msg.result);
  }
});
function send(method, params = {}, sessionId) {
  const id = nextId++;
  ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  return new Promise((ok, fail) => {
    const timer = setTimeout(() => { pending.delete(id); fail(new Error(`${method}: no answer in 60 s`)); }, 60000);
    pending.set(id, { ok: (r) => { clearTimeout(timer); ok(r); }, fail: (e) => { clearTimeout(timer); fail(e); } });
  });
}
const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));

// Recorded in the page: whether anything stopped the browser's own action for each wheel event.
const PROBE = `window.__wheel = []; addEventListener("wheel", (e) => __wheel.push(e.defaultPrevented), { passive: true });`;
const DEVICES = {
  laptop: { width: 1440, height: 900, dpr: 1, mobile: false },
  phone: { width: 390, height: 844, dpr: 3, mobile: true },
};

// A fresh tab on Today, the chart drawn and still.
async function open(which, device) {
  const d = DEVICES[device];
  const { targetId } = await send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
  const s = (m, a) => send(m, a, sessionId);
  const ev = async (expression) => (await s("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })).result.value;
  await s("Page.enable");
  await s("Runtime.enable");
  await s("Emulation.setFocusEmulationEnabled", { enabled: true });
  await s("Emulation.setDeviceMetricsOverride", { width: d.width, height: d.height, deviceScaleFactor: d.dpr, mobile: d.mobile });
  if (d.mobile) await s("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  await s("Page.addScriptToEvaluateOnNewDocument", { source: PROBE });
  await s("Page.navigate", { url: `${base}${which}/index.html` });
  for (let i = 0; i < 150; i++) {
    if (await ev(`!!document.querySelector(".leaflet-container") && !!document.getElementById("port-map").style.getPropertyValue("--px-per-m")`)) break;
    await sleep(100);
  }
  await sleep(1500);
  const tab = { s, ev, device, close: () => send("Target.closeTarget", { targetId }) };
  // Zoom (from the scale the chart gives its ships), the chart's offset, the page's scroll.
  tab.state = () => ev(`(() => { const c = document.getElementById("port-map"), r = c.getBoundingClientRect();
    const m = new DOMMatrix(getComputedStyle(document.querySelector(".leaflet-map-pane")).transform);
    const hint = document.getElementById("chart-hint");
    return { zoom: Math.log2(parseFloat(c.style.getPropertyValue("--px-per-m"))), x: m.e, y: m.f, scrollY: scrollY,
      top: r.top, left: r.left, width: r.width, height: r.height, wheel: __wheel.splice(0),
      hint: !!hint && getComputedStyle(hint).opacity > 0.5,
      header: document.querySelector(".topbar").classList.contains("is-hidden") ? "hidden" : "shown",
      picked: !!document.querySelector(".item.is-active") }; })()`);
  // A point on open chart (not on a marker, a label or a button), near `fx`, `fy` of the chart.
  tab.openPoint = (fx, fy) => ev(`(() => { const r = document.getElementById("port-map").getBoundingClientRect();
    const top = Math.max(r.top, 0), bottom = Math.min(r.bottom, innerHeight);
    for (let ring = 0; ring < 12; ring++) for (let a = 0; a < 8; a++) {
      const x = r.left + r.width * ${fx} + Math.cos(a * Math.PI / 4) * ring * 18, y = top + (bottom - top) * ${fy} + Math.sin(a * Math.PI / 4) * ring * 18;
      const e = document.elementFromPoint(x, y);
      if (e && e.tagName === "CANVAS") return { x: Math.round(x), y: Math.round(y) };
    }
    return null; })()`);
  return tab;
}

const mouse = (t, type, x, y, extra = {}) => t.s("Input.dispatchMouseEvent", { type, x, y, button: "left", ...extra });
async function drag(t, from, dx, dy) {
  const before = await t.state();
  await mouse(t, "mouseMoved", from.x, from.y, { buttons: 0 });
  await mouse(t, "mousePressed", from.x, from.y, { buttons: 1, clickCount: 1 });
  for (let i = 1; i <= 15; i++) { await mouse(t, "mouseMoved", from.x + (dx * i) / 15, from.y + (dy * i) / 15, { buttons: 1 }); await sleep(16); }
  const during = await t.state();
  await mouse(t, "mouseReleased", from.x + dx, from.y + dy, { buttons: 0, clickCount: 1 });
  await sleep(1500);
  const after = await t.state();
  return { during: Math.round(Math.hypot(during.x - before.x, during.y - before.y)), after: Math.round(Math.hypot(after.x - before.x, after.y - before.y)), picked: after.picked };
}
const touch = (t, type, points) => t.s("Input.dispatchTouchEvent", { type, touchPoints: points.map(([x, y], id) => ({ x, y, id })) });
async function swipe(t, from, dx, dy) {
  const before = await t.state();
  await touch(t, "touchStart", [[from.x, from.y]]);
  for (let i = 1; i <= 15; i++) { await touch(t, "touchMove", [[from.x + (dx * i) / 15, from.y + (dy * i) / 15]]); await sleep(16); }
  await touch(t, "touchEnd", []);
  await sleep(1500);
  const after = await t.state();
  return { chart: Math.round(Math.hypot(after.x - before.x, after.y - before.y)), page: Math.round(after.scrollY - before.scrollY) };
}
const zoomed = (a, b) => `${b.zoom - a.zoom >= 0 ? "+" : ""}${(b.zoom - a.zoom).toFixed(1)}`;
async function scrollChartToTop(t, extra = 0) {
  await t.ev(`document.getElementById("chart").scrollIntoView({ block: "start" }); window.scrollBy(0, ${extra}); new Promise((r) => setTimeout(r, 600))`);
}

// ---------- The checks: each returns one cell of the table ----------
const CHECKS = [
  ["Laptop: mouse wheel over the chart (3 notches down)", "laptop", async (t) => {
    const p = await t.openPoint(0.62, 0.5), a = await t.state();
    await mouse(t, "mouseMoved", p.x, p.y);
    for (let i = 0; i < 3; i++) { await mouse(t, "mouseWheel", p.x, p.y, { deltaX: 0, deltaY: 100 }); await sleep(60); }
    await sleep(200);
    const hint = (await t.state()).hint;
    await sleep(1000);
    const b = await t.state();
    return `page scrolls ${Math.round(b.scrollY - a.scrollY)} px, chart zoom ${zoomed(a, b)}, hint ${hint ? "shown" : "none"}`;
  }],
  ["Laptop: touchpad pinch (Ctrl + wheel)", "laptop", async (t) => {
    const p = await t.openPoint(0.62, 0.5), a = await t.state();
    await mouse(t, "mouseMoved", p.x, p.y);
    for (let i = 0; i < 10; i++) { await mouse(t, "mouseWheel", p.x, p.y, { deltaX: 0, deltaY: -15, modifiers: 2 }); await sleep(16); }
    await sleep(1200);
    const b = await t.state();
    const stopped = b.wheel.filter(Boolean).length;
    return `chart zoom ${zoomed(a, b)}; browser's page zoom ${stopped === b.wheel.length ? "stopped" : `not stopped (${b.wheel.length - stopped} of ${b.wheel.length} events)`}`;
  }],
  ["Laptop: drag at the opening view, 300 px east", "laptop", async (t) => {
    const r = await drag(t, await t.openPoint(0.7, 0.5), -300, 0);
    return `moves ${r.during} px while dragging, ${r.after} px after release`;
  }],
  ["Laptop: drag at the opening view, 200 px south", "laptop", async (t) => {
    const r = await drag(t, await t.openPoint(0.7, 0.4), 0, -200);
    return `moves ${r.during} px while dragging, ${r.after} px after release`;
  }],
  ["Laptop: double-click", "laptop", async (t) => {
    const p = await t.openPoint(0.7, 0.5), a = await t.state();
    await mouse(t, "mousePressed", p.x, p.y, { buttons: 1, clickCount: 1 });
    await mouse(t, "mouseReleased", p.x, p.y, { buttons: 0, clickCount: 1 });
    await mouse(t, "mousePressed", p.x, p.y, { buttons: 1, clickCount: 2 });
    await mouse(t, "mouseReleased", p.x, p.y, { buttons: 0, clickCount: 2 });
    await sleep(1500);
    return `chart zoom ${zoomed(a, await t.state())}`;
  }],
  ["Laptop: zoom-in button", "laptop", async (t) => {
    const a = await t.state();
    await t.ev(`document.querySelector(".leaflet-control-zoom-in").click(); 1`);
    await sleep(1500);
    return `chart zoom ${zoomed(a, await t.state())}`;
  }],
  ["Laptop: keyboard + on the chart", "laptop", async (t) => {
    const a = await t.state();
    await t.ev(`document.querySelector(".leaflet-container").focus(); 1`);
    for (const type of ["keyDown", "keyUp"]) await t.s("Input.dispatchKeyEvent", { type, key: "=", code: "Equal", windowsVirtualKeyCode: 187 });
    await sleep(1500);
    return `chart zoom ${zoomed(a, await t.state())}`;
  }],
  ["Laptop: drag that starts on item 1's number, 150 px west", "laptop", async (t) => {
    const n = await t.ev(`(() => { const b = document.querySelector('.leaflet-marker-pane .callout-item[data-action="show-item"]');
      if (!b) return null; const r = b.getBoundingClientRect(); return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) }; })()`);
    if (!n) return "no numbered marker on this page";
    const r = await drag(t, n, 150, 0); // west: open sea, room at the opening view
    return `chart moves ${r.after} px; item ${r.picked ? "picked" : "not picked"}`;
  }],
  ["Laptop: click on item 1's number", "laptop", async (t) => {
    const n = await t.ev(`(() => { const b = document.querySelector('.leaflet-marker-pane .callout-item[data-action="show-item"]');
      if (!b) return null; const r = b.getBoundingClientRect(); return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) }; })()`);
    if (!n) return "no numbered marker on this page";
    await mouse(t, "mouseMoved", n.x, n.y);
    await mouse(t, "mousePressed", n.x, n.y, { buttons: 1, clickCount: 1 });
    await mouse(t, "mouseReleased", n.x, n.y, { buttons: 0, clickCount: 1 });
    await sleep(1500);
    return `item ${(await t.state()).picked ? "picked" : "not picked"}`;
  }],
  ["Laptop: cursor at the window's top, over the chart (header hidden)", "laptop", async (t) => {
    await scrollChartToTop(t, 60);
    const a = await t.state();
    if (a.header !== "hidden") return `header was ${a.header} before the move`;
    const x = Math.round(a.left + a.width * 0.7);
    await mouse(t, "mouseMoved", x, 300);
    await mouse(t, "mouseMoved", x, 20);
    await sleep(600);
    return `header ${(await t.state()).header === "shown" ? "comes back over the chart" : "stays away"}`;
  }],
  ["Phone: vertical swipe on the chart, opening view (finger up 240 px)", "phone", async (t) => {
    await scrollChartToTop(t, -150);
    const r = await swipe(t, await t.openPoint(0.5, 0.6), 0, -240);
    return `page scrolls ${r.page} px, chart moves ${r.chart} px`;
  }],
  ["Phone: sideways drag, opening view (150 px)", "phone", async (t) => {
    await scrollChartToTop(t, -150);
    const r = await swipe(t, await t.openPoint(0.7, 0.5), -150, 0);
    return `chart moves ${r.chart} px, page scrolls ${r.page} px`;
  }],
  ["Phone: two-finger pinch out", "phone", async (t) => {
    await scrollChartToTop(t, -150);
    const p = await t.openPoint(0.5, 0.5), a = await t.state();
    await touch(t, "touchStart", [[p.x - 30, p.y], [p.x + 30, p.y]]);
    for (let i = 1; i <= 10; i++) { await touch(t, "touchMove", [[p.x - 30 - i * 8, p.y], [p.x + 30 + i * 8, p.y]]); await sleep(16); }
    await touch(t, "touchEnd", []);
    await sleep(1500);
    return `chart zoom ${zoomed(a, await t.state())}`;
  }],
  ["Phone: vertical swipe after two zoom-in taps (finger up 150 px)", "phone", async (t) => {
    await scrollChartToTop(t, -150);
    for (let i = 0; i < 2; i++) { await t.ev(`document.querySelector(".leaflet-control-zoom-in").click(); 1`); await sleep(1200); }
    const r = await swipe(t, await t.openPoint(0.5, 0.5), 0, -150);
    return `chart moves ${r.chart} px, page scrolls ${r.page} px`;
  }],
];

const rows = [];
for (const [name, device, check] of CHECKS) {
  const cells = [];
  for (const which of ["before", "after"]) {
    let tab = null;
    try {
      tab = await open(which, device);
      cells.push(await check(tab));
    } catch (error) {
      cells.push(`error: ${String(error.message).slice(0, 80)}`);
    } finally {
      if (tab) await tab.close().catch(() => {});
    }
  }
  rows.push(`| ${name} | ${cells[0]} | ${cells[1]} |`);
}
console.log(["### Map input (#111): Today, headless browser", "", "| Input | Before | After |", "|---|---|---|", ...rows, ""].join("\n"));
ws.close();
browser.kill();
server.close();
process.exit(0);
