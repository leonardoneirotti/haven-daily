// Before and after, side by side, with the owner's targets (issue #104).
//   node tools/speed_compare.mjs before.json after.json [--profile phone]
// The two files come from tools/measure_speed.mjs --json, run on the same machine.
// Prints a Markdown table (for a GitHub Actions run summary).

import fs from "node:fs";

const args = process.argv.slice(2);
const [before, after] = args.slice(0, 2).map((f) => JSON.parse(fs.readFileSync(f, "utf8")));
const profile = args.includes("--profile") ? args[args.indexOf("--profile") + 1] : "phone";

// Targets on the throttled phone (owner, 18 Nov 2026); on the laptop, no task over 100 ms
// per zoom step (owner, #111, 21 Nov 2026).
const TARGETS = profile === "laptop" ? { zoom: 100 } : { text: 1500, map: 2500, move: 1000 };

const kb = (bytes) => (bytes == null ? "–" : `${Math.round(bytes / 1024)} KB`);
const ms = (value) => (value == null ? "–" : `${(value / 1000).toFixed(2)} s`);
const fonts = (entry) => entry.files.filter(([url]) => url.includes("fonts/")).reduce((a, [, sent]) => a + sent, 0);
const fontFiles = (entry) => entry.files.filter(([url]) => url.includes("fonts/")).length;
// A map move: the longest the page froze while dragging or zooming the chart.
const move = (entry) => entry.interactions
  ? Math.max(entry.interactions["drag the map"]?.longestTask ?? 0, entry.interactions["zoom in (button)"]?.longestTask ?? 0)
  : null;

// A zoom: the longest task of any zoom step, by button or by flying to an item (#111).
const ZOOMS = ["zoom in (button)", "zoom in again (button)", "zoom out (button)", "select an item (chart flies)"];
const zoom = (entry) => entry.interactions
  ? Math.max(...ZOOMS.map((name) => entry.interactions[name]?.longestTask ?? 0))
  : null;

const ROWS = [
  ["Sent", (e) => e.sent, kb],
  ["Fonts", (e) => fonts(e), (v, e) => `${kb(v)} (${fontFiles(e)} files)`],
  ["First text (FCP)", (e) => e.timing.fcp, ms],
  ["News and status visible", (e) => e.timing.text, ms, TARGETS.text],
  ["Map visible", (e) => e.timing.map, ms, TARGETS.map],
  ["Page ready (DOMContentLoaded)", (e) => e.timing.dcl, ms],
  ["Load event", (e) => e.timing.load, ms],
  ["Blocked (TBT)", (e) => e.timing.tbt, ms],
  ["Longest task while loading", (e) => e.timing.longest, ms],
  ["Map move: longest freeze", move, ms, TARGETS.move],
  ["Zoom step: longest task", zoom, ms, TARGETS.zoom],
];

const out = [];
out.push(`Before: ${before.machine}`, "", `Profile: ${profile}. Medians of ${after.runs} cold loads.`, "");
for (const page of Object.keys(after.pages)) {
  const b = before.pages[page]?.[profile], a = after.pages[page]?.[profile];
  if (!a) continue;
  out.push(`#### ${page}`, "", "| | Before | After | Target |", "|---|---|---|---|");
  for (const [name, get, fmt, target] of ROWS) {
    const bv = b ? get(b) : null, av = get(a);
    if (bv == null && av == null) continue;
    const verdict = target == null ? "" : av == null ? `${ms(target)}` : `${ms(target)} ${av <= target ? "✅" : "❌"}`;
    out.push(`| ${name} | ${b ? fmt(bv, b) : "–"} | ${fmt(av, a)} | ${verdict} |`);
  }
  if (a.errors?.length) out.push(`JavaScript errors after: ${a.errors.join(" | ")}`, "");
  out.push("");
}
console.log(out.join("\n"));
