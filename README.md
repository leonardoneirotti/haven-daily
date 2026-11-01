# Haven Daily

A public web page, updated every morning, that tells a logistics planner what is affecting the Port of Rotterdam today and what it means for them. Personal, unofficial portfolio project. See `CLAUDE.md` for all decisions.

## What exists so far

The **site renderer**: Python turns one JSON "brief" per day into static HTML pages. Each page opens on a chart of the port with that morning's ships and the day's numbered items. The collector, filter, AI summaries and AIS snapshot (build plan steps 1–7 and 11) come later and only need to produce brief files in the same format.

```
haven/render.py           builds the site from brief files
haven/config.py           reads and checks the config files; a mistake stops the run with a clear message
haven/clock.py            "today" and "now" in Amsterdam time (a brief belongs to an Amsterdam date)
haven/env.py              loads API keys from a local .env file (names only in .env.example; never printed)
config/sources.toml       every source from SOURCES.md: verdict, URLs, RSS/HTML, language, auto-keep
config/filter.toml        off-topic word lists for the relevance filter (empty until tuning)
tests/                    pytest tests; tests/test_repo_config.py keeps sources.toml and SOURCES.md in step
templates/                Jinja2 page templates (base, day, archive, method page, shared macros)
static/style.css          the whole design: colour and type tokens, light + dark mode
static/map.js             draws the chart with Leaflet: land, ships, numbered items
static/basemap.js         port land shapes + place names (generated, see below)
static/vendor/leaflet/    Leaflet 1.9.4, self-hosted
tools/build_basemap.py    builds the basemap from OpenStreetMap (run once)
data/basemap/             basemap output as GeoJSON
data/sample/briefs/       three SAMPLE briefs (fake content, clearly marked on every page)
site/                     output, not committed (GitHub Actions will build it)
```

## Run it

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m haven.render
```

Then open `site/index.html` in a browser.

Run all tests:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

For local runs that need API keys: copy `.env.example` to `.env` and fill in the values. `.env` is git-ignored; online, the keys are GitHub Actions secrets.

The basemap is already built. To rebuild it (for example after changing the map area or place names in `tools/build_basemap.py`):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools\build_basemap.py
```

It downloads coastlines and water areas, and separately roads, railways, breakwaters and storage tanks, once from the Overpass API (cached in `data/basemap/osm-cache.json` and `osm-detail-cache.json`). It cuts the map rectangle along the coastline, keeps the land, and stores the detail compactly (about 650 KB for the whole `basemap.js`, roughly 200 KB as GitHub Pages sends it compressed).

## Brief format (one file per day)

| Field | Meaning |
|---|---|
| `date` | Day of the brief (Amsterdam date) |
| `built_at` | When the morning job wrote the brief (ISO timestamp with offset, Amsterdam time); shown as "Published HH:MM". The brief goes online straight away |
| `corrections[]` | `{at, note}` for every hand-made fix after publishing, `[]` if none. The page shows "Corrected HH:MM" (latest one) and lists every note under "How this brief was made" |
| `sample` | `true` shows the "Sample data" note |
| `status[]` | Status indicators: `key`, `label`, `icon`, `value` (number, text or `null` = no data), `unit`, `place`, `level` (`green`/`amber`/`red`/`null`), `observed_at`, `source_name`, `source_url`, optional `gauge_max`, `note` |
| `items[]` | `severity` (`high`/`medium`/`low`), `headline`, `url`, `source`, `language`, `published`, `summary`, `impact` (`null` = "Not enough information"), `affects[]`, optional `access: "headline-only"` for paywalled sources, optional `map: {lat, lon, label}` to pin the item on the chart |
| `ships` | AIS snapshot, or `null` when it failed: `snapshot_start`, `snapshot_end`, `source_name`, `vessels[]` with `name`, `type` (`container`/`tanker`/`bulk`), `flag`, `lat`, `lon`, `heading`, `status` (`underway`/`moored`/`anchored`), `speed_kn`, `length_m`, `area`, `destination_raw` (as typed on board), `destination` (cleaned, `null` = unknown), optional `news_item` (item number) |
| `build` | `sources_checked`, `items_collected`, `items_kept`, `failures[]` (`source`, `error`) |

The renderer sorts items by severity, keeps at most 5, works out "change since yesterday" from the previous brief, builds the "Read in English" link for non-English items and prepares the chart data.

## Design decisions (short version)

- **One dark palette, like a relief map under a lamp.** Warm charcoal page, ivory type, charcoal water with fine lines that follow the coast, textured land with roads, railways and storage tanks, teal ships, ivory controls and an orange "whole port" button. All colours are tokens at the top of `style.css`; `map.js` reads the chart colours from the same tokens, so map and page can never drift apart.
- **The basemap is painted by the browser.** `map.js` draws water, coast lines, land and detail on one canvas each time the map stops moving. The lines in the water cost no data: the browser strokes the coastline very wide in the line colour, then slightly narrower in the water colour, leaving a thin line at exactly that distance from the shore, and repeats this outwards. They are spaced 25, 50, 100… metres apart, whichever stays at least 5 pixels apart at the current zoom. They are decoration, not depths (said on the Method page).
- **The chart is the first screen; the news floats over the sea.** On wide screens the chart fills the first screen and today's items sit in a panel over its western side, with the port status in brief at the bottom of the panel. The basemap reaches far into the North Sea so the panel only ever covers open water, and the chart opens on the whole port to the right of the panel. The full brief and detailed port status follow below. On phones the panel sits under the chart. Place names are in the serif: water in italic, land in small capitals.
- **News and chart are linked.** Selecting an item (in the panel, the card or "Show on chart") flies the chart to where it happens and opens the item's summary in the panel. For the terminal strike it zooms in on the terminal, rings the ships moored there and fades the rest. Clicking a number on the chart highlights the item in the panel. There are also ship-type filters, "at anchor" and "under way" buttons that fly to those ships, and ship names in the table that find the ship. Without JavaScript, everything is still listed as text and the panel entries are links to the full items.
- **Ships as hulls seen from above.** Each ship is a small top-down hull turned to its heading; the deck shows the type (container stacks, a tanker's pipeline, a bulk carrier's hatch covers). Zoomed in, ships are drawn at their real length; zoomed out, a minimum size keeps them visible. Ships under way trail a wake that grows with speed, ships at anchor are hollow, and ships at a terminal named in the news take that item's colour. The shapes live once in `haven/render.py` and are used by both the legend and the chart.
- **One numbering system.** The numbered squares on the chart are the same squares as in the list, so the chart works as the index of the brief.
- **One type family, IBM Plex, used like an instrument panel.** Plex Sans for text, Plex Sans Condensed for headlines and big readings, Plex Mono for labels, times and AIS data. Fact vs interpretation stays visible: the planner impact is the only text in Plex Serif, labelled *interpretation*.
- **Fast on ordinary laptops.** The chart repaints only when it stops moving. The lines in the water (the slowest layer) are drawn at one pixel per screen point even on retina screens; the canvas covers the view plus a 10% margin; land gets a cheap offset shadow instead of a blurred one; detail coordinates are converted with a lookup table. No blur or shadow filters on anything that moves.
- **Colour only where it means something:** severity, status and linked ships. Status also uses shapes (octagon, triangle, circle), so it still works for colour-blind readers.
- **Logo:** the letters H and D in maritime signal flags. It looks maritime without any Port of Rotterdam branding.
- **No map service at runtime.** The basemap is a file in the repo and Leaflet is self-hosted. The page never depends on a tile server and stays fast.
- **Relative links** so the site works under GitHub Pages' `/<repo>/` address.

## Before launch

- Fonts load from Google Fonts. For an EU site, self-host the font files (`static/fonts/`) to avoid sending visitor IP addresses to Google.
- Check aisstream.io's terms for showing their data publicly (see `CLAUDE.md`).
- Fill in `SITE["linkedin_url"]` and `SITE["repo_url"]` in `haven/render.py`.
- Set the Rhine thresholds on the Method page (`templates/about.html`) from a public source.

Credits: map data © OpenStreetMap contributors (ODbL). [Leaflet](https://leafletjs.com) (BSD-2). Icons: [Lucide](https://lucide.dev) (ISC). Fonts: IBM Plex Sans, Sans Condensed, Mono and Serif (SIL Open Font License).
