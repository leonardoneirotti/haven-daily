# Site speed: measurements and proposed fixes (issue #104)

*Measured 18 November 2026 on the sample site. Nothing in the site has been changed yet:
this page is the "measure first" step. The fixes below wait for the owner's OK.*

## How it was measured

`tools/measure_speed.mjs` builds nothing and changes nothing. It serves a built site
from `127.0.0.1` with gzip, like GitHub Pages, and drives a headless browser
(Edge on the laptop, Chrome on GitHub) through the DevTools protocol.

- **Two devices.**
  - **Laptop:** 1440×900, pixel density 2, 30 Mbit/s, 20 ms latency.
  - **Throttled phone:** 390×844, pixel density 3, 1.6 Mbit/s, 150 ms latency, CPU slowed 4×. This is Lighthouse's "slow 4G" phone.
- **Loads.** A warm-up load, then 3 cold loads per page and device with the cache off. The figures below are the medians. Then one more load with the profiler and a trace on, used only to see where the time goes.
- **Moving the map.** On pages with the chart, the same tab then:
  - drags the map;
  - zooms in;
  - selects an item, which makes the chart fly to it;
  - scrolls the page with the mouse wheel.

  Frame times and long tasks are recorded for each.
- **Memory.** Free memory is sampled throughout, and any load over 60 s is counted as stuck.

The same script ran in two places:
- the owner's laptop: i5-10210U, 8 GB, about 1 GB free, HP Sure Click running;
- a GitHub Actions runner: 4 cores, 16 GB, 14.5 GB free, no graphics chip.

The workflow is `.github/workflows/speed.yml`. To repeat a run:

```
python -m haven.render --briefs data/sample/briefs --out <dir>
node tools/measure_speed.mjs <dir> --runs 3 --json speed.json
```

## Page weight

Sizes are as sent, gzipped (the size on disk is in brackets).

| Page | Sent | Files | Fonts | Map files (basemap + Leaflet + map.js) |
|---|---|---|---|---|
| Today (`index.html`) | 508 KB (1341 KB) | 17 | 191 KB in 9 files | 291 KB |
| A day page | 502 KB (1292 KB) | 17 | 191 KB | 291 KB |
| A day page with ships | 461 KB (1275 KB) | 15 | 148 KB in 7 files | 291 KB |
| Archive | 95 KB (151 KB) | 6 | 79 KB in 3 files | — |
| How it works | 124 KB (187 KB) | 7 | 103 KB in 4 files | — |

The biggest files:

| File | Sent | On disk |
|---|---|---|
| `static/basemap.js` | 238 KB | 840 KB |
| `ibm-plex-sans-400-700-latin.woff2` | 45 KB | 45 KB |
| `vendor/leaflet/leaflet.js` | 43 KB | 147 KB |
| `ibm-plex-sans-400-700-latin-ext.woff2` | 31 KB | 31 KB |
| `ibm-plex-sans-italic-400-latin.woff2` | 24 KB | 24 KB |
| other fonts | 15–20 KB each | |
| `map.js` | 13 KB | |
| `style.css` | 12 KB | |
| `index.html` | 12 KB | |

There are no images apart from the small SVG icons.

`basemap.js` alone is **46 % of Today's weight**.

## Timings

All times are in milliseconds and are medians of 3 cold loads.
- **FCP:** when the first text appears.
- **Load:** when the browser's load event has run.
- **Blocked:** Total Blocking Time, the time the page could not respond to a tap.

| Page / device | Laptop | GitHub runner |
|---|---|---|
| Today / laptop | FCP 536, load 852, blocked 48 | FCP 140, load 4922, blocked 4591 |
| Today / phone | FCP 1844, load 4795, blocked 881 | FCP 624, load 6521, blocked 3448 |
| Day with ships / phone | FCP 1828, load 4016, blocked 769 | FCP 628, load 6150, blocked 3398 |
| Archive / phone | FCP 1132, load 1227, blocked 241 | FCP 468, load 985, blocked 0 |
| How it works / phone | FCP 1664, load 1927, blocked 518 | FCP 500, load 403, blocked 0 |

Moving the map. The figure given is the longest single task, which is how long the page freezes:

| | Laptop | GitHub runner |
|---|---|---|
| Drag, laptop profile | 0–1464 ms (varies from run to run) | 4364 ms |
| Drag, phone profile | 216–971 ms | 11323 ms |
| Zoom, phone profile | 50 ms | 11908 ms |
| Select an item (the chart flies) | 55–243 ms | 113–123 ms |
| Scroll the page | 0–150 ms | 0 ms (frames steady at 17 ms) |

When nobody touches the page it uses almost no CPU: 0–9 ms per 5 s on both machines. Nothing runs in the background.

## Which slowness is the laptop's, and which is the site's

### The laptop's

- **The 18-second loads.** In the first local run, 12 leftover headless browsers were still open and free memory was 0.78 GB. Today on the phone profile took 10.8 s to load, and some LCPs reached 18 s. With the leftovers closed, the same load took 4.8 s. On the runner, with 14.5 GB free, the page never took more than 6.5 s, and that was for a different reason (below). The 18 s came from memory: the laptop was paging to disk.
- **Slow layout.** On the laptop, laying out Today on the phone profile took 2336 ms; on the runner, 280 ms. A test page with no CSS at all still took 600 ms of layout on the laptop. That is the machine's floor, not the stylesheet.
- **Random freezes.** The same drag took 216 ms in one run and 1464 ms in another. Free memory was as low as 232 MB during the runs. Freezes that come and go with free memory are the laptop's.
- **The late "largest paint" figures on the laptop (9.7 s).** They come from the headless browser's graphics process being slow to answer under memory pressure. The page had painted at 0.5 s.

### The site's

1. **Moving the map is expensive when the browser draws the canvas without the graphics chip.**
   - Every pan or zoom repaints the whole chart.
   - Most of the cost is the "water lines": up to 20 wide strokes of the full coastline (`COAST_LINE_REACH`/`COAST_LINE_GAP` in `static/map.js`).
   - Laptop Edge draws the canvas on the graphics chip, so a drag costs about 0.2 s of work there.
   - The runner has no graphics chip, so the same repaint takes 4.4 s on the laptop profile and 12 s on the phone profile. During that time the page is frozen.
   - Browsers that draw the canvas without the graphics chip are common:
     - isolated or virtual browsers, possibly including HP Sure Click's (see the check below);
     - older or low-end phones;
     - remote desktops;
     - a laptop whose graphics driver Chrome has blocklisted.
   - The profiler puts the time under `drawImage` in `paint` (`static/map.js:325`). Chrome only runs the queued strokes when the off-screen water canvas is copied onto the chart.
2. **`basemap.js` is 238 KB gzipped (840 KB raw).**
   - On slow 4G it takes about 1.2 s to arrive, and parsing and running it takes about 0.4–0.5 s on the phone.
   - It is loaded by a normal `<script>` tag, so the page's "DOM ready" waits for it. On the phone profile, DOMContentLoaded and the load event both land at 4.8 s.
3. **Web fonts.**
   - Up to 9 font files (191 KB) load on a day page.
   - The browser only finds them after the CSS has been applied.
   - Each font that arrives makes the browser lay the long page out again, and `map.js` measures the callouts again.
4. **Small work on every map move.**
   - Leaflet's scale bar updates on every `move` event: about 30 extra layouts per drag.
   - `paint` reads 8 colours with `getComputedStyle` on each repaint. This forces a style check.
   - The callouts are measured again on every font `loadingdone`.
   - Each of these is small (under 50 ms) but adds up on a slow phone.

## Proposed fixes and expected gains

**Targets on the throttled phone** (owner, 18 Nov 2026):
- news and status visible within **1.5 s**;
- map visible within **2.5 s**.

**The budget.**
- The phone profile receives about 200 KB per second, and each round trip costs 150 ms. In 2.5 s it can receive roughly 400 KB.
- The page needs HTML and CSS (24 KB), the first-screen fonts (about 100 KB), Leaflet and `map.js` (56 KB), and the basemap. Parsing and drawing take about 0.5 s more.
- That leaves room for a basemap of about **80 KB**, against 238 KB today.

**The experiments.** The experiments for fixes 1, 4 and 5 were stopped before they finished (owner's call). Their gains below are estimates and are marked as such. Each fix will be measured with `tools/measure_speed.mjs` when it is built.

| # | Fix | What it changes | Expected gain (phone profile) |
|---|---|---|---|
| 1 | **Text, news and status first; the map after.** | `leaflet.js` and `map.js` get `defer`. `map.js` loads `basemap` only after the page has painted, and the chart frame shows a quiet "loading chart" until then. | The page is ready at about **1 s instead of 4.8 s**. News and status stop sharing the slow connection with 290 KB of map files. **Estimate: visible at 0.6–1.0 s**; FCP is 0.62 s already on the runner, and 1.8 s on this laptop. |
| 2 | **Simpler basemap.** | `tools/build_basemap.py` simplifies coastlines, waterways and the land detail (fewer points on straight and smooth stretches, with a tolerance of a few metres). It also stores each point as a small step from the previous one (delta encoding) instead of full coordinates. Port basins, jetties and the areas around the 41 places keep their shape; this is checked with side-by-side screenshots at every zoom level before merging. No 3D. | Delta encoding alone, already measured: **238 → 114 KB** gzipped, and half the parsing. With simplification: **estimate 60–80 KB**. On the phone that saves about 0.8 s of download and 0.2–0.3 s of parsing. |
| 3 | **Cheaper water lines.** | Water lines are drawn once per zoom level onto a cached canvas, not on every pan, and there are fewer of them far from the shore. | When the canvas is drawn without a graphics chip, the repaint drops from **4.4 s (laptop) and 12 s (phone)** to an **estimated 0.3–1 s**, since the lines are nearly all of the measured repaint time. With a graphics chip: little change, it is fast already. Without this fix, the 2.5 s map target can't be met in such browsers. |
| 4 | **Stop the endless ping** on the High marker. | It plays 3 times, then stops; with reduced motion, it doesn't play at all. | Measured idle CPU is already small (0–9 ms per 5 s), so the speed gain is small. The gains are a calmer page and less compositing and battery use, which matters most in a virtual browser like Sure Click. |
| 5 | **Fonts.** | The 4 first-screen fonts get `<link rel=preload>`. The page avoids the characters that pull in the `latin-ext` files (Today loads 9 font files). | **Estimate: 30–60 KB less** on Today, and fewer full-page relayouts while fonts arrive. |
| 6 | **Less work per map move.** | Leaflet's scale bar updates only when a move ends (`updateWhenIdle`). `paint` reads the 8 colours once, not on every repaint. Callouts are measured once on `document.fonts.ready`. | About 30 fewer layouts per drag. Tens of milliseconds per move on the phone: small, but it is the part of the lag that is there even with a graphics chip. |

**Expected result on the throttled phone:**
- news and status within 1.5 s with fix 1;
- the map within 2.5 s with fixes 1, 2 and 3 together.

Fixes 4 to 6 are small extras.

## What to check on the laptop

Open `chrome://gpu` (or `edge://gpu`) in the browser where the site feels slow, and look at **"Canvas: Hardware accelerated"**.
- **If it says "Software only":** fix 1 is the one that matters.
- **If the site opens in HP Sure Click's isolated browser:** that browser's own `chrome://gpu` page is the one to check.

## Results, part 1 (fixes 1, 4, 5, 6)

Measured on a GitHub runner, throttled phone profile, main against this branch in the same run
([run 44531754497](https://github.com/leonardoneirotti/haven-daily/actions/runs/44531754497)):

| Today | Before | After | Target |
|---|---|---|---|
| News and status visible | 0.67 s | 0.59 s | 1.5 s ✅ |
| Page ready (DOMContentLoaded) | 7.52 s | 1.34 s | |
| Map visible | 7.52 s | 7.49 s | 2.5 s: part 2 |
| Map move, longest freeze | 15.1 s | 15.3 s | 1 s: part 2 |

- **Fix 5 changed after measuring.** The font preloads made the first text *later*: 0.60 → 0.94 s on Today, and 0.46 → 0.73 s on the archive, where the preloads were the only change ([run 44407583387](https://github.com/leonardoneirotti/haven-daily/actions/runs/44407583387)). On a slow connection, about 80 KB of fonts held up the stylesheet. They are gone.
- **What stays from fix 5:**
  - a test that our own text pulls in no `latin-ext` font file (the sample pages never did: the 9 files are 9 typefaces and weights);
  - the **font budget**: 240 KB and 11 files.
- **Map visible and map moves** depend on the basemap and on drawing without a graphics chip. That is part 2 (fixes 2 and 3).

## Results, part 2 (fixes 2, 3, and the basemap fetched ahead of the fonts)

Measured on a GitHub runner with no graphics chip, throttled phone profile. "Before" is part 1's branch and "after" is this branch, in the same run
([run 44569539205](https://github.com/leonardoneirotti/haven-daily/actions/runs/44569539205)):

| | Today before | Today after | Day with ships after | Target |
|---|---|---|---|---|
| Sent | 509 KB | 367 KB | 320 KB | |
| `basemap.js`, sent (raw) | 238 KB (840 KB) | about 92 KB (158 KB) | about 92 KB (158 KB) | about 80 KB (the plan's room) |
| News and status visible | 0.56 s | 0.62 s | 0.59 s | 1.5 s ✅ |
| Map visible | 6.66 s | **2.85 s** | **2.53 s** | 2.5 s ❌ |
| Map move, longest freeze | 12.77 s | **0.29 s** | 0.28 s | 1 s ✅ |
| Blocked while loading (TBT) | 3.51 s | 0.51 s | 0.51 s | |

**Fetching the basemap ahead of the fonts** (owner's option 3) was measured on its own, against the run before it ([44534293643](https://github.com/leonardoneirotti/haven-daily/actions/runs/44534293643)):
- map visible: 2.93 → 2.85 s on Today, and 2.67 → 2.53 s on the day with ships;
- first text: 0.07 s later (0.56 → 0.62 s on Today, 0.52 → 0.59 s on the day with ships), still well within its 1.5 s target.

The test server speaks HTTP/1.1. GitHub Pages uses HTTP/2, where download priority can count for more, but that is not measured here.

**Map within 2.5 s: missed by 0.03–0.35 s, accepted** (owner, 19 Nov 2026). What's left is mostly the fonts: up to 192 KB in 9 files share the slow connection with the basemap. The style pass (#102) will replace the fonts. It must bring the map under 2.5 s on this profile within the font budget (240 KB, 11 files), measured with `.github/workflows/speed.yml`.
