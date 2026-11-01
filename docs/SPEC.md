# Haven Daily — complete project blueprint

*One file with everything decided, designed and learned so far, so the project can be rebuilt from zero.
Owner: Leonardo Neirotti. Compiled 31 October 2026.*

---

## 1. What Haven Daily is

**Haven Daily** is a public web page, updated every morning, that tells a logistics planner what is affecting the **Port of Rotterdam** today and what it means for them.

- *"Haven"* means **port** in Dutch and **safe place** in English. The name works in both languages.
- It is a **personal portfolio project**, not a company tool. Goal: show recruiters at Port of Rotterdam companies that the owner can build AI agents and apply them to a real operations problem.
- It will be linked from LinkedIn, with a weekly post about it.

### About the owner (context only)

- 2nd-year BBA International Business (Supply Chain Management), Rotterdam University of Applied Sciences.
- Looking for a 20-week internship from **February 2027** at a Port of Rotterdam company (operations, process improvement, planning, logistics or data).
- Builds with Claude Code step by step. **Every decision must be explained briefly**: the owner must be able to talk about every part in an interview.

### Positioning (for README and interviews)

| Kind | Examples |
|---|---|
| Commercial, paid, B2B | Yusen Logistics "Supply Chain Disruption Radar" (2026), Sea Sentinel AI, GoComet, Portcast / SeaVantage / Beacon congestion trackers |
| Free but different | Port Authority news page and Port Performance page, PortsEurope (all of Europe), Kuehne+Nagel SeaNews (weekly, global) |
| **Haven Daily's niche** | **Free, public, Rotterdam-only, daily, with planner impact** |

---

## 2. Product decisions (settled)

| Topic | Decision |
|---|---|
| Name | **Haven Daily**. Domain not bought yet (check `havendaily.nl` first). Launch on the free GitHub Pages address. |
| Format | **Public static website** on GitHub Pages. Each day gets its own page; an archive lists all days; a Method page explains rules. |
| Language | Python (pipeline + renderer). Plain HTML/CSS/JS output, no front-end build step. |
| Scheduling | GitHub Actions. Three UTC triggers (04:45, 05:45, 06:45) + a manual trigger; a guard builds once, on the first run after 06:30 Amsterdam time that finds no brief for today. Handles summer/winter time and missed runs (§5.1.1). |
| Publishing | **Publish directly, fix afterwards.** ~06:45 Amsterdam: **one job** collects, builds, commits the day's data to `main` and publishes to GitHub Pages. No pull request, no review window, no 08:00 auto-merge. If something is wrong, the owner fixes it afterwards (edit the brief or the code, push to `main`) and the site republishes. **The page must never skip a day.** *(Changed 31 Oct 2026: replaces the 06:30 PR / 08:00 auto-merge plan. See `docs/adr/0001-publish-directly-with-visible-corrections.md`.)* |
| Alerts | **No email.** GitHub app notifications only (failed run). |
| Brief length | **Max 5 items** per day, sorted by severity. Quiet days: fewer items or "Nothing significant today". **Never pad.** |
| Dutch sources | Included. Each Dutch item: English summary + link to original + **"Read in English"** link (Google Translate URL of the original). **Never store or republish translated article text.** |
| Storage | Store every collected item (kept and dropped) and every status value from day one, so trends/charts are possible later. **Plain JSON files in the repo, one file per day per kind, written once and never edited by the pipeline** (see §6.1). Not SQLite: a binary database can't be read in a git diff and is re-stored whole every day. For charts later, a script loads the files into SQLite/pandas. |
| AI budget | **All AI calls together stay under €5/month.** Each AI step uses the cheapest model that does the job well enough. **After the first week of daily runs, check the real costs** (Anthropic Console usage) against the estimates in §5.4 and adjust. |
| Site colours | **Dark only.** No Day/Night switch. |
| Fonts | **IBM Plex** family (see §7.3). |

### 2.1 Each news item

- Headline + link to the original source (always).
- **What happened**: 2 lines, in the tool's own words (never copied text).
- **Impact for a Rotterdam planner**: delays, costs, which cargo, terminals or routes. Clearly labelled *interpretation*. If the article doesn't support an impact: **"Not enough information"**, never a guess.
- **Severity tag**:
  - **High**: directly affects Rotterdam operations **and** has a timeframe (e.g. strike at a terminal this week).
  - **Medium**: affects a European route, carrier or hinterland connection serving Rotterdam.
  - **Low**: background trend or long-term news.
  - **Unrated**: the AI step failed for this item, so there is no summary, impact or severity: headline + link only (§5.6). Never a guess.
- "Affects" tags (e.g. Containers · Maasvlakte II · Truck pickups).
- For Dutch items: "Read in English" link.
- Optional map pin so the item appears on the chart: the AI picks a place from a fixed list, the code adds `lat`, `lon`, `label` (§5.10). "Affects" tags also come from a fixed list (§5.10).
- Paywalled sources: headline + link only ("Headline only. This source is paywalled, so there is no summary.").
- **Headline-only items** (paywalled or AI opt-out, §3 rule 12, §4) still get a **severity, rated by the AI from the headline alone**, shown as **"rated from headline only"** next to the severity tag. From the same headline the AI also picks the **place** and **"affects" tags** (same fixed lists, §5.10) and extracts **strike details** (same rules, §5.7: dates only if the headline states them; an `unsure` match never clears a strike), so a strike reported only by a headline-only source (e.g. NL Times, RTV Rijnmond) still raises the strike flag. No summary; impact stays `null` = "Not enough information". If that AI call fails, the item is unrated like any other. *(Decided by the owner, 1 Nov 2026.)*

### 2.2 Port status line

Each indicator: **value, colour (green/amber/red), change vs yesterday, timestamp, source link**. Colour is always paired with a **shape** (circle-check = normal, triangle = watch, octagon = alert, circle-minus = no data) so it works for colour-blind readers.

**Version 1**
- Weather warnings (wind, storm, fog…) — KNMI's own warnings for **Zuid-Holland**, read via MeteoAlarm until KNMI's new dataset leaves TEST (§4). Shows only level + hazard, never the warning text. **MeteoAlarm display requirements** (owner read its Terms and Conditions §5, 31 Oct 2026), all mandatory on the weather dial and the Method page:
  - **"KNMI"** shown as the source of the warning;
  - the warning's **time of issue**;
  - a link to **www.meteoalarm.org**;
  - **MeteoAlarm's exact disclaimer**, verbatim: *"Time delays between this website and the www.meteoalarm.org website are possible. For the most up-to-date awareness information as published by the participating National Meteorological and Hydrological Services, please refer to www.meteoalarm.org."* (In the Method page template, `templates/about.html`; also shown with the weather dial.)
  - the **original level + hazard** next to our mapping, e.g. "KNMI: Code yellow · Wind → Watch".
  - **Real-time issue:** the terms require real-time redistribution (max 10 min delay) for "operational" use; we update once a day. **Until MeteoAlarm clarifies**, the weather status is labelled **"Warnings at 06:45 · not live"** with a link to meteoalarm.org for current warnings.
- Rhine water level — **Kaub** gauge (PEGELONLINE, WSV), shown with a small river-gauge graphic. **Lobith** (Rijkswaterstaat) is stored daily in `data/status/` for later trend charts, not shown.
- Active strike flag — derived from strike details in kept items of the last 14 days (§5.7), linked to the item that decided it.
- Ships in the port area — count from the AIS snapshot (v2), with "N at anchor / N under way".

**Later** (only once a clean, permitted automatic source exists): road (A15 closures, Rijkswaterstaat), rail (Betuweroute, ProRail), sea vessel waiting times (Port Authority "Port Performance"), barge waiting times (Barge Performance Monitor / operator notices).

**Rules:** no data = show "No data", never estimate. Thresholds documented on the Method page with their public source.

Thresholds (decided 31 Oct 2026; every number comes from a public source, cited on the Method page):

| Indicator | Normal | Watch | Alert | Source |
|---|---|---|---|---|
| Weather warnings | Highest level for Zuid-Holland valid at any time today (Amsterdam date) is green / none | … is **yellow** | … is **orange or red** | KNMI warnings via MeteoAlarm (later: KNMI directly) |
| Rhine water level, Kaub | 77–460 cm | **below GlW 77 cm** (official low-water reference for navigation) or **above Marke I 460 cm** (high-water shipping restrictions) | **below MNW 65 cm** (mean yearly low) or **above Marke II / HSW 640 cm** (shipping stops) | WSV official gauge values via PEGELONLINE (`characteristicValues`, read 31 Oct 2026) |
| Strike flag | No active Rotterdam strike (none found, all over, or cancelled) | Rotterdam strike announced for a later date, or with no stated dates | Rotterdam strike today (dates include today, or ongoing) | Kept items of the last 14 days (§5.7) |

### 2.3 Pages

1. **Today** (`index.html`) = latest day page.
2. **Day pages** (`days/YYYY-MM-DD.html`), each with its own chart, kept forever, with previous/next navigation.
3. **Archive**: grouped by month, newest first. Each row: date + edition number, a 5-slot severity strip (coloured numbered squares, empty slots for quiet days), top headline (or "Nothing significant"), status marks, ship count.
4. **Method** (`about.html`): what this is, how a brief is made (~06:45 collect → filter → summarise → status → publish, all automatic and unreviewed; mistakes are corrected afterwards and the page republished), severity rules, status thresholds, sources and how they are used (incl. the GDELT credit "Headline discovery via the GDELT Project" + link to gdeltproject.org, if GDELT is adopted), the chart (data sources, "lines in the water are decoration, not depths", AIS limits, messy destinations), sources and copyright, who makes this.
5. **Footer on every page** (mandatory text): *"Personal, unofficial project by Leonardo Neirotti. Not affiliated with the Port of Rotterdam Authority. AI-generated summaries — always check the original source."* + "Map data © OpenStreetMap contributors."

Each day page also shows: publication line ("Published 06:52 · Amsterdam time", taken from `built_at`; after a correction: "Published 06:52 · Corrected 09:14 · Amsterdam time", using the latest entry in `corrections`, with every correction note listed in "How this brief was made"), a collapsible table of all ships in the snapshot, and "How this brief was made" (sources checked, items collected, kept, shown, failures per source).

---

## 3. Hard rules

1. Every item links to its original source. **No invented facts, numbers or quotes.**
2. Summaries are short and in our own words. No full articles, no long quotes, no full translations of third-party articles.
3. Paywalled sources (Lloyd's List, The Loadstar, JOC, Nieuwsblad Transport, TradeWinds): headline + link only, or skip.
4. Respect each source's terms and robots.txt. If a source doesn't allow automated access, drop it.
5. Footer disclaimer on every page (text above).
6. **Never use Port of Rotterdam branding or logos; the site must not look official.**
7. **Never commit API keys.** GitHub Actions secrets only.
8. No company or confidential data.
9. If one source or step fails, the rest of the page still builds and the failure is shown on the page.
10. Sample/fake data must be clearly marked on every page ("Sample data. The ships, news and readings on this page are invented to preview the design.").
11. **A published brief is never changed silently.** Any change to a published brief's content adds an entry to its `corrections` list (§6), shown on the page.
12. **Respect AI opt-outs.** If a source opts out of AI use (robots.txt blocks AI crawlers such as ClaudeBot/GPTBot, or signals like `ai-train=no`), only its **headline and link** are used, shown like a paywalled item. Its article text is never sent to an AI. The headline may still go to the AI, for the relevance filter and for what can be read from the headline alone: severity, place, "affects" tags and strike details (§2.1); nothing else from the source does. *(Added 31 Oct 2026; headline rating added 1 Nov 2026. Affects NL Times, Nieuwsblad Transport, PortsEurope, TradeWinds, RTV Rijnmond as tested. The Loadstar is headline-only because of its RSS terms, not an AI block (corrected 1 Nov 2026).)*
13. **No third-party article text in the repo.** No article text or feed snippets are ever committed (the repo is public, so committing them would republish them). Text is fetched and used **in memory only**, for summarising, then discarded. The stored item keeps the URL, so the original can always be reopened. *(Added 31 Oct 2026.)*

---

## 4. Sources (final v1 verdicts, decided 31 Oct 2026)

Every candidate was tested for: feed or clean page, how much text, robots.txt, terms, AI opt-out (hard rule 12). Full results with URLs and quoted robots.txt / terms lines: `docs/source-tests-2026-10-31.md` (RTV Rijnmond and NOS added the same day). Tested from a desktop, **not from GitHub Actions IPs**: sites behind Cloudflare may still block the job; the first real runs will show. The working list with URLs is `SOURCES.md`.

**Verdicts**
- **use** = headline + link + own-words AI summary.
- **headline-only** = headline + link, shown like a paywalled item, no article text to any AI (the headline may go to the AI for the relevance filter and for severity, place, tags and strike details "rated from headline only", §2.1).
- **drop** = not collected.

**News sources**

| Source | Verdict | Access | Why |
|---|---|---|---|
| Port of Rotterdam Authority news & press releases | **use** · auto-keep | HTML list (the `/en/rss.xml` feed is stale) | robots OK. Terms forbid *reproduction*; a short own-words summary + link is not reproduction. |
| PIN notices to shipping (Port Authority) | **use** · AI check | RSS `pin.portofrotterdam.com/rss.xml` | robots OK, no terms on site. 40–60 nautical notices/week, mostly noise: goes through the AI check, not auto-keep. |
| Contargo business news | **use** · AI check | HTML | No robots.txt, no reuse clause. Covers terminals across Europe, so not auto-keep. ~3/week. |
| ECT news | **use** · auto-keep | HTML `/en/news-feed` (its RSS is stale) | robots OK. Terms forbid reproduction without consent; summary + link is not reproduction. ~1/week. |
| Kuehne+Nagel SeaNews | **use** (Rotterdam paragraph only) · AI check | HTML | robots allows `/news`. **Terms not found: find and check before launch; headline-only if they forbid it.** |
| NL Times | **headline-only** | HTML port tag page `nltimes.nl/tags/port-rotterdam` (not the site-wide feed, which rolls over) | Blocks AI crawlers (hard rule 12). Optional: ask permission (§11). |
| Nieuwsblad Transport (nt.nl) | **headline-only** | RSS `nt.nl/havens/feed/` | Paywalled; blocks AI crawlers, `ai-train=no`. ~5–6 Rotterdam items/week. Don't use the body text in its feed. |
| PortsEurope | **headline-only** | RSS `/category/rotterdam/feed/` | Subscription site; blocks AI crawlers, `ai-train=no, use=reference`. ~2/week. |
| The Loadstar | **headline-only** | RSS `/feed/` (main feed only; robots disallows tag/category pages) | **Headline-only because of its RSS terms**: the feed may be used only "to create links back to our website", not to copy or republish articles. Not an AI opt-out: its robots.txt has no AI-crawler rules (checked 1 Nov 2026, corrected that day). Low Rotterdam volume. |
| RTV Rijnmond | **headline-only** | RSS `rijnmond.nl/rss/nieuws` (50 items ≈ 2.5 days) | robots allows generic bots but blocks ClaudeBot, anthropic-ai and ~130 other bots (hard rule 12). **Terms not found** (site footer has only privacy + contest rules): check before launch. Rotterdam regional broadcaster: few port items (0 of 50 in the test), but likely to cover local port strikes. |
| NOS | **drop** | RSS `feeds.nos.nl/…` | NOS terms (1 Oct 2025) **art. 6.1**: automated access by AI agents, bots or similar systems without NOS permission is "strictly forbidden, regardless of purpose" (only search-engine bots are exempt). **Art. 7**: RSS only for "non-commercial use by private users for personal information, education or news gathering". A public website built by a bot is outside both. Permission: juza@nos.nl. Also only 0–2 port-related items per 20. |
| Google News RSS | **drop** | RSS | Two independent reasons, both verified 31 Oct 2026: (1) robots.txt `User-agent: *` → `Disallow: /`, with `/rss/` not among the allowed paths; (2) the feed's own `<copyright>` says it is "made available solely for the purpose of rendering Google News results within a personal feed reader for personal, non-commercial use. Any other use of the feed is expressly prohibited." Hard rule 4. (Practical issue too: links are Google redirect URLs, not the original articles.) |
| DutchNews.nl | **drop** | RSS | robots.txt `Disallow: /feed/` for all bots. |
| Lloyd's List | **drop** | RSS | robots.txt `Disallow: /rss/`; feed page needs sign-in. |
| RWG (Rotterdam World Gateway) | **drop** | HTML | Terms: no use "without prior written permission" (hard rule 4). ~1/month. |
| JOC | **drop** | RSS | 0 Rotterdam items in 40; not worth the code. |
| APM Terminals Maasvlakte II | **drop** | Private API (key embedded in page) | Not a public interface; terms may ban linking. ~1/month. |
| TradeWinds | **drop** | No official feed | Blocks AI crawlers. |
| Tradlinx blog | **drop** | RSS | Korean only, no Rotterdam items. |
| Port Performance (Port Authority) | **drop** | Undocumented internal JSON | No public API or licence. |

**Auto-keep** (skips the AI relevance check, §5.4): Port Authority news and ECT only.

**Expected volume** without Google News: roughly **15–25 candidate items a week**, so quiet days with 0–2 items will be normal ("never pad"). The cost estimates in §5.4 / §5.5 (30 items/day to the AI check, 12 kept/day) are therefore **overestimates**.

**Status line sources**

| Source | Verdict | Notes |
|---|---|---|
| Weather: **MeteoAlarm** (EUMETNET) | **use**, with the display requirements in §2.2 and the label "Warnings at 06:45 · not live" until the daily-snapshot question is answered | JSON `feeds.meteoalarm.org/api/v1/warnings/feeds-netherlands`, no key, robots.txt allows bots. Republishes KNMI's own warnings (`contact: procesbewaker@knmi.nl`), one per province incl. Zuid-Holland, with awareness level green/yellow/orange/red, onset and expiry. Licence: "terms equivalent to CC BY 4.0, with additional requirements for redistributing" in its Terms and Conditions (§5, read by the owner 31 Oct 2026): https://meteoalarm.org/en/live/page/terms-and-conditions. Operational use requires real-time redistribution (≤ 10 min delay): daily snapshot being clarified (§11). |
| Weather: KNMI Open Data | **later** (switch when the successor leaves TEST) | Current dataset `waarschuwingen_nederland_48h` v1.0 is **deprecated, no updates from 2 Nov 2026**. Successor `KNMI-public-weather-warnings` v1.0 (CAP/JSON, CC-BY 4.0) is still "[TEST]" with "not real warnings". Needs a free registered key (secret `KNMI_API_KEY`). |
| Rhine, Kaub (PEGELONLINE, WSV) | **use**, shown | REST JSON, no key, DL-DE→Zero-2.0. Value every 15 min. Official characteristic values (GlW, MNW, Marke I/II) from the same API set the thresholds (§2.2). |
| Rhine, Lobith (Rijkswaterstaat) | **use**, stored only | REST JSON (POST), no key, CC0. Query a recent time window with `OphalenWaarnemingen`; the "latest observation" endpoint returned old archive values. Don't scrape the Waterinfo website (robots `Disallow: /`). |
| Port Authority weather, tide, depth, arrivals/departures | not tested | Later. |
| Rijkswaterstaat (A15 road works), ProRail (Betuweroute) | not tested | Later. |

**Feeds that roll over** (PIN and NL Times keep only ~10 items, less than a day): handled in §5.8.

**GDELT (tested, not used in v1; rule decided in advance 31 Oct 2026).** GDELT DOC 2.0 API (`api.gdeltproject.org/api/v2/doc/doc`) as a legal replacement for Google News, to **discover** Rotterdam port headlines + links. Licence: free for any use, "any use or redistribution of the data must include a citation to the GDELT Project" + a link to gdeltproject.org. Rate limit 1 request / 5 s per IP (429s seen in testing). **If adopted:**
- GDELT is only used to discover headlines and links. It never counts as a source itself; each result belongs to its **outlet** (the article's domain).
- Every result is checked against that outlet's verdict in `SOURCES.md`: **dropped** outlets are ignored, **headline-only** outlets stay headline-only, **use** outlets follow their normal rules.
- Outlets **not in our list are headline-only by default** until tested the same way and added to `SOURCES.md`.
- The Method page credits GDELT (§2.3).

**GDELT test result (31 Oct 2026, from a desktop):** `"port of rotterdam"` over 7 days returned **1 article, and it was unrelated** (a cybersecurity story). Three narrower queries (Maasvlakte/Europoort/Botlek, strike + port, Dutch "haven" with `sourcecountry:netherlands`) returned **0**. The Dutch-phrase query was malformed on Claude's side (GDELT needs `( … OR … )`), so Dutch coverage is untested. **6 of 9 requests got HTTP 429** despite 10 s spacing and 60 s back-off. **Decision (31 Oct 2026): GDELT is not used in v1** (near-zero useful results, unreliable access for a never-skip-a-day job). If news volume turns out too low: re-test the Dutch query once, and re-test from GitHub Actions. The discovery-only rule above stays for that case.

**Version 2 (ship map):** aisstream.io (free AIS WebSocket, subscribe by bounding box, API key via GitHub sign-in; beta, 1–3 min lag on free tier; **check terms for public display**), `searoute` Python package (estimated routes for visualisation, not navigation).

---

## 5. Architecture

### 5.1 Daily pipeline

```
~06:45 Amsterdam: one GitHub Actions job (cron in UTC)
  1. collect     fetch sources marked use / headline-only, drop duplicates of earlier days
  2. filter      keep / drop each item: rules first, then a cheap AI check (§5.4)
  3. summarise   AI: 2-line summary, planner impact, severity, affects tags, optional map pin
  4. status      KNMI warnings, Rhine level, strike flag
  5. ais         ~10-15 min aisstream.io snapshot, seagoing cargo ships only (v2)
  6. brief       write data/briefs/YYYY-MM-DD.json (+ data/items/, data/status/, see §6.1)
  7. commit      commit data/ straight to main (no pull request)
  8. render      python -m haven.render --briefs data/briefs --out site
  9. deploy      publish site/ to GitHub Pages

Corrections (any time later)
  owner edits data/briefs/YYYY-MM-DD.json or the code, pushes to main
  -> pages.yml re-renders and republishes the whole site
```

Each step catches its own errors and records them in `build.failures` so the page always builds.

The daily job renders and deploys **itself** (steps 8–9). It can't rely on `pages.yml` firing on its commit: pushes made with the built-in `GITHUB_TOKEN` don't trigger other workflows. `pages.yml` stays as the path for the owner's own pushes (corrections) and manual runs. The daily job needs `contents: write` to commit.

**Writing to `main` (decided 31 Oct 2026).** The repo is public; `main` has no PR requirement, so the job pushes directly with the built-in token (`permissions: contents: write` in the daily workflow; the repo default stays read-only). Safeguards:
1. A **ruleset on `main` that only blocks force-pushes and branch deletion**. Normal pushes (owner and job) still work; history can't be rewritten by accident.
2. The job **stages only `data/`**, so it can never commit code.
3. Before pushing: `git pull --rebase`, retry once (in case the owner pushed a correction at the same moment).
Commits come from `github-actions[bot]`, message `Brief YYYY-MM-DD (automatic)`.

### 5.1.1 Schedule, summer/winter time and retries (decided 31 Oct 2026)

GitHub cron runs in UTC only, often starts 5–30 min late, and occasionally drops a run. So the daily workflow has **three scheduled triggers plus a manual one**, and a guard at the start of the job decides whether to build.

| Trigger | UTC | Winter (CET, UTC+1) | Summer (CEST, UTC+2) |
|---|---|---|---|
| schedule | 04:45 | 05:45 → too early, stops | **06:45 → builds** |
| schedule | 05:45 | **06:45 → builds** | 07:45 → retry if needed |
| schedule | 06:45 | 07:45 → retry if needed | 08:45 → retry if needed |
| `workflow_dispatch` | any time | owner starts it by hand (GitHub mobile app) if all scheduled runs failed | same |

The guard, first step of the job ("today" = the **Amsterdam** date, via Python `zoneinfo("Europe/Amsterdam")`, so the clock change needs no code):
1. **Scheduled runs only:** if it is before 06:30 in Amsterdam, stop.
2. **All runs, manual included:** if `data/briefs/<today>.json` already exists on `main`, stop.
3. Otherwise run the pipeline.

Rules and limits:
- A `concurrency` group (one run at a time, never cancel a running one) stops a retry from overlapping a slow run.
- A run that writes the brief **with some failed sources counts as done**: it is not retried; the failures show on the page (hard rule 9). Retries only cover runs that were dropped or crashed before writing the brief.
- A stopped run (guard said no) ends green, so it doesn't send a failure notification.
- GitHub disables scheduled workflows in a repo with no activity for 60 days; the daily commit keeps it active.

### 5.2 Repository layout

```
haven/                 Python package
  render.py            brief JSON -> static HTML (Jinja2)
  config.py            reads and checks config/*.toml (§5.2.1)
  clock.py             "today"/"now" in Amsterdam time, clock injectable for tests
  env.py               loads a local .env (names only, never values)
  storage.py           daily files in data/: write once, read one day or the last N days (§6.1)
  fetch.py             polite HTTP layer every collector uses: user agent, robots.txt, AI opt-outs, delays (§5.8)
  feeds.py             RSS collectors: common item shape, headline-only text never read, PIN gap check (§5.8)
  pages.py             HTML list collectors: same item shape, K+N Rotterdam paragraph only (§5.8)
  collect.py           collect step: every source, duplicates, feed read time, K+N 14-day check, article text (§5.8)
  filter.py            relevance filter: stage 1 rules, stage 2 AI check (Haiku 5.5), kept/dropped report (§5.4)
  (summarise.py, status.py, ais.py — to build)
config/
  sources.toml         every source in SOURCES.md: verdict, URLs, access, language, auto-keep
  filter.toml          off-topic word lists per language (§5.4), small starter lists (football)
tests/                 pytest; run with `python -m pytest` (settings in pytest.ini)
templates/             base.html, day.html, archive.html, about.html, _macros.html
static/
  style.css            the whole design (tokens at the top)
  map.js               the chart (Leaflet + custom canvas basemap)
  basemap.js           generated: land, detail, labels (window.HAVEN_BASEMAP)
  site.js              adds the "js" class to <html>
  favicon.svg
  vendor/leaflet/      Leaflet 1.9.4, self-hosted
tools/build_basemap.py builds basemap.js from OpenStreetMap (run once)
data/basemap/          land.geojson + raw Overpass caches (caches git-ignored)
data/sample/briefs/    4 sample briefs (fake, marked as sample; 26 Oct is a reduced brief)
data/briefs/           real briefs, one per day (what the renderer reads)
data/items/            every collected item, one .jsonl file per day (§6.1)
data/status/           every status reading, one .json file per day (§6.1)
design/logo-concepts/  generated logo explorations
site/                  output, not committed (Actions builds it)
CLAUDE.md, SOURCES.md, README.md
BUILD_PLAN.md          pointer only: the plan is the GitHub issues + §10
requirements.txt       jinja2>=3.1,<4, tzdata (time zone rules; Windows has none built in), beautifulsoup4>=4.12,<5 (HTML lists, §5.8), anthropic>=2.3,<3 (Claude API, §5.4)
requirements-dev.txt   + pytest, + shapely>=2.0,<3 (only for the basemap tool)
.gitignore             .venv/, __pycache__/, *.pyc, osm caches, site/
```

Run locally:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m haven.render            # -> site/index.html
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest                  # all tests
.\.venv\Scripts\python.exe tools\build_basemap.py      # only to rebuild the map
```

**Relative links everywhere** (`root` = `""` or `"../"`) so the site works under GitHub Pages' `/<repo>/` path.

### 5.2.1 Config files and helpers (built 1 Nov 2026, issue #4)

- **Config is TOML in `config/`**, read with Python's built-in `tomllib` (no extra dependency). `haven/config.py` checks every file and stops with a message naming the file, the source and the problem (unknown verdict, missing URL, duplicate id, …), so a typo can't silently drop a source.
- **`tests/test_repo_config.py` keeps `config/sources.toml` and `SOURCES.md` in step**: same sources, verdicts and URLs, and only Port Authority news and ECT auto-keep (§4). Change both together.
- **"Today" is the Amsterdam date** (`haven/clock.py`, `zoneinfo("Europe/Amsterdam")`), as the guard in §5.1.1 needs. Tested around midnight UTC and on both 2026 clock-change days.

*Proposed by Claude, confirmed by the owner (1 Nov 2026, PR #47):*
- `sources.toml` lists **news sources only**. The status-line endpoints (MeteoAlarm, PEGELONLINE, Rijkswaterstaat) are a different kind of source (no use/headline-only verdict, no items) and get their config when the status step is built.
- **Dropped sources are listed** with a one-line `note` (why), for the record; they need no URL, access type or language and are never fetched.
- A source has a **list of `urls`**, because Nieuwsblad Transport has two feeds (`/havens/feed/` and `/tag/rotterdam/feed/`, `SOURCES.md`). The collector will merge them and drop duplicates.
- **Off-topic word lists are per language** (`en`, `nl`): Dutch headlines need Dutch words. An empty word is rejected (it would match every headline).
- **Unknown fields are an error**, not ignored, so `auto_kep = true` can't quietly turn auto-keep off.
- The clock helper **refuses a datetime without a timezone** instead of guessing which zone it is in.
- **`.env` is read by a small standard-library loader** (`haven/env.py`), not python-dotenv: the format is only `NAME=value` lines. Variables already set win (so GitHub Actions secrets are never replaced), an empty value counts as not set (a fresh copy of `.env.example` means "no key"), and errors give the line number, never the line.
- **Secret names** (the same in `.env`, `.env.example` and GitHub Actions secrets): **`ANTHROPIC_API_KEY`** for the Claude API (relevance filter, summariser), `AISSTREAM_API_KEY` for the AIS snapshot (v2), later `KNMI_API_KEY` (§4). The code reads the Claude key from `ANTHROPIC_API_KEY` only, never logs or prints it, and an unset or empty key means "AI unavailable" (§5.6). *(Name written into the spec 1 Nov 2026, issue #13.)*

*Technical necessity (not a choice):*
- **`tzdata` is a runtime dependency**: on Windows, `zoneinfo` has no time zone rules without it (found while building this; the Linux runner has them built in).

### 5.3 Renderer responsibilities (`haven/render.py`)

- Load all brief files, sort by date, number editions (No. 001, 002…).
- Sort items by severity (high → medium → low → unrated), keep max 5. Unrated items count toward the 5, so they are the first to be cut (§5.6).
- Compute "change since yesterday" for each status value ("+12 cm since yesterday", "Same as yesterday", "No reading yesterday", "First reading").
- Map status level `green/amber/red/null` → CSS key `ok/watch/alert/nodata` + label `Normal/Watch/Alert/No data` + icon.
- Build `translate_url` for non-English items: `https://translate.google.com/translate?sl=<lang>&tl=en&u=<url>`.
- Add ship labels/counts (type label, status label, flag name, linked item severity, counts by type, at anchor, under way, linked).
- Build the chart payload (`brief.map`, embedded as JSON in the page): `view_home`, `view_compact`, `ship_shapes`, `callouts`, `ships`, `ships_source`.
- Jinja2 with `StrictUndefined` (a template typo fails the build). Write `brief["items"]`, never `brief.items` (dict method clash).
- Icons: inline Lucide SVG paths (ISC licence) in a Python dict.
- Publication line (§2.3) from `built_at` + `corrections` (`publication_line()`, tested); a missing `corrections` field counts as `[]`. Correction notes are listed under "How this brief was made", oldest first. *(Built 1 Nov 2026, issue #5.)*

*Proposed by Claude, confirmed by the owner (1 Nov 2026, PR #49):*
- The "latest" correction is the one with the **latest `at` time**, not the last one in the list, so a hand edit that adds a note in the wrong place still shows the right time.
- Times are **converted to Amsterdam time** before showing HH:MM (the line says "Amsterdam time"); a timestamp **without a timezone is refused**, like the clock helper (§5.2.1).
- A correction made **on a later day** than the build shows its date too: "Corrected 30 Oct 10:02", so a fix a week later doesn't look like a same-morning one.
- With corrections, the publication line ends with a **"See corrections" link** to the notes under "How this brief was made".

*Unrated items and the reduced brief (built 1 Nov 2026, issue #6).* `severity: null` gets the CSS key `unrated` everywhere a severity is drawn (panel, full brief, chart callout, ship popup, archive strip, Method page). Items of the same severity keep the order they came in (stable sort). A reduced brief is marked by `build.ai_unavailable: true` (§6) and shows the §5.6 note under the publication line and above the brief.

*Proposed by Claude, confirmed by the owner (1 Nov 2026, PR #50):*
- **The unrated square is outlined, not filled**, in `--nodata-ink`: the same grey as "No data" on the status line, because both mean "no reading". Empty vs filled is the shape cue, so it doesn't rely on colour; the number inside keeps it distinct from the empty slots in the archive strip. On the chart it sits on the page colour so map lines don't show through.
- **The unrated card says why it is empty**: *"Headline only. The AI step failed for this item, so there is no summary, impact or severity. Read the original for the details."* No impact block at all (so no "Not enough information", which is only for a rated item with `impact: null`).
- **A ship at the terminal of an unrated item still counts as linked**, but keeps its normal teal hull (like a low item); its popup button gets a grey edge.
- **A reduced brief with no items** says *"Without the AI step only items from the Rotterdam-specific sources can be shown, and they had nothing new"* instead of "nothing met the bar", which would be untrue when the filter never ran.
- The **Method page** lists Unrated under the severity rules and explains the reduced brief in two sentences.

### 5.4 Relevance filter (decided 31 Oct 2026)

Question it answers per item: *is this relevant to a logistics planner working with the Port of Rotterdam?* Two stages, cheapest first. Only kept items go on to the summariser.

**Stage 1: rules (free, predictable)**
- Drop duplicates of items already stored in the last ~14 days. **Done once, in the collect step** (`haven/collect.py`, issue #11, §5.8), not again here: the filter only ever sees new links. So the 14-day link check for undated items (below) is already done by the time they reach the filter; #12 needs no second check.
- Drop items published more than ~48 h before the run.
  - **The boundary:** an item exactly 48 h old is still kept; it is dropped only when it is *older* than 48 h. A test covers exactly 48 h. *(Decided by the owner, 1 Nov 2026, issue #12.)*
  - **Items with no readable date** (§5.8): kept only if their link wasn't seen in the last 14 days. *(Decided by the owner, 1 Nov 2026, issue #12.)* *Claude's reading, confirmed by the owner (1 Nov 2026):* "kept" means not dropped for age; the word lists and stage 2 still apply, and the 14-day link check is the same as the duplicate check above.
  - **Items with a date but no time** (Contargo, ECT, §5.8: `published` = `"2026-10-30"`): age counted from the **end of that day** (midnight at the start of the next day, Amsterdam time), so they are never dropped too early. *(Decided by the owner, 1 Nov 2026, issue #12.)*
- Drop items matching an off-topic word list (e.g. football, crime unrelated to port operations, housing). The word lists live in the config file so they can be tuned without touching code.
- **Auto-keep** items from the Rotterdam-specific sources listed in §4 (Port Authority news, ECT): they skip stage 2.

**Rules module (`haven/filter.py`, built 1 Nov 2026, issue #12).** `apply_rules(items, sources, config, now)` gives every item one outcome with a reason: **kept** (auto-keep source), **dropped**, or **to the AI check** (stage 2, #13). The rules run in this order and the first that hits gives the reason:
1. older than 48 h → dropped, `"older than 48 h"`;
2. auto-keep source → kept, `"Rotterdam-specific source (auto-keep)"` (the word lists don't apply to it);
3. a word from the off-topic list of the item's language in the headline → dropped, `off-topic word "<word>"`;
4. anything else → to the AI check, `"not decided by the rules: goes to the AI check"`.

Kept and dropped items get `Item.filter` = `{"kept", "stage": "rules", "reason"}`, which `Item.record()` adds to the stored line; items for the AI check get theirs from stage 2. Ages are compared in UTC, so the clock change can't shift the 48 h by an hour (tested on 25 Oct 2026). Live smoke run (1 Nov 2026, 18:18, in memory, nothing written; before the starter words and the owner's changes): 151 items → 1 kept (auto-keep), 104 dropped as older than 48 h, 46 to the AI check (38 of them RTV Rijnmond, 7 of those football).

*Proposed by Claude, confirmed by the owner with the changes marked (1 Nov 2026, PR #57):*
- **Auto-keep sources skip the off-topic word lists; the 48 h age rule still applies to them.** So a three-day-old Port Authority story is dropped, but a badly chosen word can't drop a Rotterdam-specific item. *(Changed by the owner: Claude had proposed words before auto-keep. Tested: `test_an_auto_keep_source_skips_the_word_lists_but_not_the_age_rule`.)*
- **The age is counted to the moment the sources were read** (`feeds_read_at` from the collect step, passed by the runner #22), not to the end of the run: an earlier moment can only keep an item longer.
- **A timestamp without a timezone is read as Amsterdam time** and the 48 h rule applies (summer or winter time as on that date). *(Changed by the owner: Claude had proposed treating it as no readable date. Tested: `test_a_timestamp_without_a_timezone_is_read_as_amsterdam_time` and its summer-time twin.)* None of our collectors writes one today (feeds read a zone-less date as UTC when collecting, §5.8, so it reaches the filter with an offset). **An unreadable date or a date in the future** is not dropped for age (an unreadable date counts as "no readable date", §5.8; a future date is a feed or clock error, not an old item).
*Proposed by Claude, confirmed by the owner (1 Nov 2026, PR #57):*
- **Words are matched in the headline only** (not the snippet, which headline-only items don't have), ignoring case, as **whole words**, phrases allowed; a **`*` at the end** matches any ending ("voetbal*" → "voetbalclub"), because Dutch writes compounds as one word. `*` anywhere else is a config error. A `*` at the start ("*voetbal" for "profvoetballer") is not supported, to keep matching predictable.
- **Starter lists: football only** (`football`, `Eredivisie`, `Feyenoord`; Dutch also `voetbal*`, `Excelsior`, `Sparta`): the most frequent noise in the live RTV Rijnmond headlines, and words that can't be about the port (the Feijenoord district is spelled differently). **Crime and housing stay with the AI check**: a word can't tell "stabbing in the city centre" from "drugs found in a container". A repo test checks that no list word hits an invented port headline.
- **A source not in the config** is never auto-kept (its items go to the AI check).

**Stage 2: AI check (borderline items only)**
- Model: the cheapest suitable one, **Claude Haiku 5.5** (`claude-haiku-5-5`, $0.10 / $0.50 per million input/output tokens, Anthropic price list as of Oct 2026), low effort.
- Input: headline + snippet only, not the full article. Output: kept yes/no + one-line reason, as structured JSON.

**Every decision is recorded** on the item's line in `data/items/YYYY-MM-DD.jsonl`, so kept vs dropped can be reviewed and tuned (build plan step 4):
`"filter": {"kept": false, "stage": "rules", "reason": "older than 48 h"}` or `{"kept": true, "stage": "ai", "reason": "Strike at ECT Delta this week"}`.
When tuning: a wrong rule-stage decision means editing a word list; a wrong AI-stage decision means editing the prompt.

**AI check (`haven/filter.py`, built 1 Nov 2026, issue #13).** `check_with_ai(items, client)` sends each item the rules couldn't decide to **Claude Haiku 5.5** (`claude-haiku-5-5`), effort `low`, standard API, one call per item, with **structured output** forcing the answer into `{"kept": true/false, "reason": "<one sentence>"}`. Decisions are stored as `"filter": {"kept", "stage": "ai", "reason"}`. `run_filter(items, sources, config, now, client)` runs both stages (rules, then the AI for the rest) and returns the items in input order, the failure lines, whether the AI was unavailable, and the calls and tokens used. **`python -m haven.filter [--rules-only]`** collects once, runs both stages, writes nothing, and prints the report: kept, then dropped, then not checked, one line each with stage, source, headline and reason, plus the tokens used and their estimated cost.
- **What the AI sees** (hard rule 12): the headline, the source id and the language; plus the teaser (`snippet`, ≤ 1,000 characters) **only for `use` items**. A headline-only item sends its headline alone, even if a teaser were in memory (tested). The text is wrapped in `<headline>`/`<teaser>` tags and the prompt says it is third-party data, never instructions.
- **Key:** only from `ANTHROPIC_API_KEY` (§5.2.1). No key → AI unavailable, no call made.

*Proposed by Claude, all seven confirmed by the owner (1 Nov 2026, PR #58):*
- **One call per item**, not one call for all items: a bad answer costs one item, not the whole morning, and each decision is easy to trace. The cost difference is cents a month.
- **One item fails** (timeout, connection or server error after the SDK's 2 retries, refusal, answer cut off, unreadable answer, or a bug of ours): the item is **kept**, reason *"AI check failed (<problem>); kept to be safe"*, and a failure line `"<url>: <problem>"` goes to `build.failures` under "AI relevance check". Missing a real item is worse than one extra (the issue's suggestion).
- **The AI counts as unavailable** (§5.6), nothing is decided and the items for the AI keep no `filter` (the runner #22 then retries later or publishes a reduced brief) when: the key is not set; the key is rejected (HTTP 401/403, stops at once); or **the first 3 calls in a row fail**. If the AI answered at least once this morning and then 3 calls in a row fail, the AI is not "unavailable": the remaining items are kept as failed **without calling again**, so a mid-run outage can't hold the job up. Refusals and bad answers mean the API is up, so they never count toward the 3.
- **Timeout 30 s per request**, plus the SDK's own 2 retries: an outage is declared after at most about 5 minutes.
- **The prompt** (`SYSTEM_PROMPT` in `haven/filter.py`, in English): what counts as relevant (port and terminal operations, labour action, weather and water levels, hinterland barge/rail/truck, carriers serving Rotterdam, customs and fees, incidents and infrastructure in the port) and what doesn't (general city news, sport, culture, crime or politics with no link to freight through Rotterdam, other ports unless it affects Rotterdam). **PIN notices:** keep those that limit traffic for many ships (fog procedures, closures, pilot capacity), drop routine ones. **When unsure, keep.** The reason is one English sentence in the AI's own words, at most 15 words; stored at most 200 characters.
- **Thinking left at Haiku 5.5's default** (adaptive) at `low` effort, `max_tokens` 1,024 (thinking counts toward it). No temperature (rejected by Haiku 5.5), no prompt caching (the prompt is ~500 tokens; caching would save cents a month).
- **Failure lines and reasons name the kind of error only** (e.g. "HTTP 529", "timeout"), never the API's own message, so nothing it echoes can reach the public page.

**Cost (to check after week one, §2):** live run 1 Nov 2026: 41 items a morning reached the AI check after the rules. At ~700 input + ~150 output tokens per call (system prompt included; thinking counted as output), 41 × 30 ≈ 1,230 calls/month ≈ 0.86 M input + 0.18 M output ≈ **$0.18/month**, inside the $0.25 estimate above.

**Cost estimate (to check after week 1, see §2 AI budget):** ~30 items/day reach stage 2 × ~1,000 input + ~300 output tokens (thinking included) ≈ 0.9 M input + 0.27 M output per month ≈ **$0.25/month**. That leaves most of the €5 for the summariser.

### 5.5 Summariser model (decided 31 Oct 2026)

**Chosen by test, not by guess.** On the first real run (build plan step 6), **Claude Haiku 5.5** (`claude-haiku-5-5`) and **Claude Sonnet 5.5** (`claude-sonnet-5-5`) summarise the same kept items. The owner compares them side by side on: facts match the source, impact is useful (or honestly "Not enough information"), severity follows §2.1. **Haiku 5.5 is the default unless Sonnet 5.5 is clearly better.** The comparison and the choice are written up in `docs/model-comparison.md`.

Cost estimate per month (assumption: ~12 kept items/day, ~3,000 input + ~1,000 output tokens each, thinking included ≈ 1.08 M input + 0.36 M output). Prices: Anthropic list, Oct 2026.

| Model | Standard API | Batch API (50% off) |
|---|---|---|
| Haiku 5.5 ($0.10 / $0.50 per M) | ~$0.30 | ~$0.15 |
| Sonnet 5.5 ($2 / $10 per M) | ~$5.80 (over budget; needs a cap of ~8 items/day → ~$3.80) | **~$2.90, no cap needed** |
| Opus 5.5 ($4 / $20 per M), for reference | ~$11.50 | ~$5.80 |

**Batch API vs our schedule (facts, Anthropic docs):** batches run asynchronously at 50% of the standard price on all tokens; **most finish within 1 hour, but the maximum is 24 hours**. So a batch alone can't guarantee a 06:45 page, and the page must never skip a day.

**How the summariser calls the API (decided 31 Oct 2026):**
1. Send all kept items as **one batch** with the chosen summariser model.
2. Wait **at most 20 minutes**. (In v2 the AIS snapshot runs during this wait, so it costs no extra time. Waiting is free: public repos get unlimited Actions minutes.)
3. Items not finished by then: cancel them in the batch and send them through the **standard API with Haiku 5.5**, whichever model the batch used. That way a slow-batch day can't break the budget: worst case, a month where every item falls back costs ~$0.30 extra in summaries.
4. Page publishes around 07:05 at the latest.

The relevance filter (§5.4) uses the standard API: its output is needed before the summariser can start, and it costs ~$0.25/month anyway.

**Recorded for every item** (in the brief and in `data/items/`): which model wrote it and how: `"written_by": {"model": "claude-sonnet-5-5", "api": "batch"}` or `{"model": "claude-haiku-5-5", "api": "standard"}`. The brief's `build` block counts them, e.g. `"summaries": {"batch": 9, "fallback": 3}`. The week-one cost check (§2) uses these counts to see whether the 50% saving really happens.

### 5.6 When the AI fails (decided 31 Oct 2026)

**One item fails** (bad or unparseable response, refusal, timeout after the Haiku fallback): the item stays in the brief as **unrated**: headline + link, `severity: null`, no summary, no impact, and it is listed in `build.failures`. The other items continue normally. Unrated items sort after all rated ones and count toward the max of 5. *(Sorting rule confirmed by the owner, 31 Oct 2026.)*

**The AI is completely unavailable** (API down, key invalid; filter and summariser both fail):
1. Treated like a crash: **no brief is written** and the run ends **failed**, so the owner gets a GitHub notification.
2. The next scheduled trigger (§5.1.1) retries about an hour later.
3. Only the **last** scheduled trigger of the day (06:45 UTC) publishes a **reduced brief** instead of failing:
   - status line as normal (KNMI and Rhine don't use AI); **strike flag = No data**, since it can't be judged reliably without the AI;
   - only items auto-kept by the rules (Rotterdam-specific sources, §5.4), all **unrated**;
   - a note on the page: *"The AI step was unavailable this morning: headlines only, no summaries."*
4. The owner can fix it later with a correction (§6, hard rule 11).

So the page never skips a day. A full AI outage costs at most one hour's delay before the retry, and a reduced brief only if it lasts until the last trigger.

### 5.7 Strike flag (decided 31 Oct 2026)

**Why not just today's items:** strikes are announced days ahead. A strike announced Monday for Thursday has no new article on Thursday, and the Monday item is older than the filter's 48 h, so a flag built only from today's items would show Normal on the strike day.

**1. The summariser extracts strike details** for every item it writes (no extra AI call), or `null` if the item is not about a strike. For headline-only items it works from the headline alone (§2.1), so their strikes count too:

```json
"strike": {
  "state": "announced",
  "location": "Maasvlakte",
  "affects_rotterdam": true,
  "start": "2026-11-05",
  "end": "2026-11-05"
}
```

- `state`: `announced` (planned / called) · `ongoing` (happening now) · `cancelled` (called off, postponed indefinitely, or settled).
- `start` / `end`: only if the article states them, else `null`. **Never guessed.**

**2. The status step reads the strike details of kept items** (`data/items/`) from **the last 14 days, plus any strike whose `start` or `end` is today or later, up to 60 days back**. So a strike announced 18 days ahead is still seen on its day. *(Decided 31 Oct 2026.)*

**3. Same strike, several items: the newest item wins.** A cancellation article therefore brings the flag back to Normal; an "ongoing" article overrides an earlier "announced" one.

**Matching items to a strike (decided 31 Oct 2026).** The summariser's prompt includes the strikes already known from the last 14 days (id, location, dates, first headline). For each strike item it answers one of:
- `"same"` + the id of a known strike: a **confident** match;
- `"new"`: a different strike; **the code** (never the AI) gives it a new id, e.g. `strike-2026-11-02-1`;
- `"unsure"` + the id of the strike it might be.

Stored on the item as `strike.match` (`same` / `new` / `unsure`) and `strike.strike_id`. A wrong match is visible in the data and fixed with a correction.

**Safety rule: a false alarm is better than a missed strike.**
- Only a **confident** match can lower a strike's level. A cancellation clears a strike **only** on `"same"`.
- On `"unsure"`, the earlier strike stays active, and the status line shows **both items** so the reader can judge ("Strike at Maasvlakte on 5 Nov · NL Times, 2 Nov ↗ · Possibly called off: NT, 4 Nov ↗").
- An unsure item that would *raise* the level (e.g. `ongoing`) counts as a strike of its own. *(Confirmed by the owner, 31 Oct 2026.)*

**4. Each strike's level, from its newest item** (only strikes with `affects_rotterdam: true`):

| Newest item says | Level |
|---|---|
| `cancelled` | ignored |
| `end` is before today | ignored (over) |
| `announced`, dates include today | **Alert** |
| `ongoing`, end date not yet passed | **Alert** |
| `ongoing`, no end date, newest item ≤ 2 days old | **Alert** |
| `ongoing`, no end date, newest item > 2 days old | **Watch**, shown as "ongoing as of 3 Nov, no newer report". Never drops to Normal by itself (false alarm better than a missed strike). |
| `announced`, start after today | **Watch** |
| `announced`, no dates | **Watch** |

**5. The flag** = the worst level over all strikes, Normal if none. If the AI was unavailable (§5.6): **No data**.

**6. The status line links the item that decided it**: headline, source and date, linking to the original article, plus the day page where the item appeared if it isn't today's ("Strike at Maasvlakte today · NL Times, 2 Nov ↗"). With several strikes at the same level, the one with the newest deciding item is linked. On Normal after a cancellation, the cancellation item is linked ("Maasvlakte strike called off · NL Times, 4 Nov ↗").

### 5.8 Collector (decided 31 Oct 2026)

**Fetching politely**
- User agent: `HavenDaily/1.0 (+<Method page URL>)`.
- robots.txt is checked **on every run**: if a site adds a block, the collector stops fetching it automatically and records it in `build.failures`.
- A few seconds between requests to the same host (more if a `Crawl-delay` says so), timeouts on every request, at most one retry.

**Fetcher module (`haven/fetch.py`, built 1 Nov 2026, issue #8).** Every collector fetches through one `Fetcher`, made once per run, so robots.txt is read fresh each morning and once per host. A page that robots.txt disallows is never requested; the failure (one line, `"<url>: <problem>"`) goes to `build.failures`. Redirects are followed by the fetcher itself, so each hop is checked against robots.txt too. **AI opt-out (hard rule 12):** a `use` source whose robots.txt blocks a named AI crawler for the source's pages, or has a `Content-Signal` with `ai-train=no` or `ai-input=no`, is headline-only for that run, with a note naming the source and the reason so the owner updates `SOURCES.md`. The network, clock and sleep are injected: tests use fakes and never touch the internet or really wait.

*Proposed by Claude, confirmed by the owner (1 Nov 2026, PR #52):*
- **robots.txt is parsed by our own small parser (RFC 9309), not `urllib.robotparser`.** The standard-library parser takes the *first* matching rule instead of the *longest*, ignores `*` and `$`, and matches agent names as substrings. Tested 1 Nov 2026: with `Allow: /` before `Disallow: /feed/` it allows `/feed/`, and it allows `/user/42` under `Disallow: /user/*`, which would break hard rule 4.
- **HTTP through the standard library (`urllib.request`)**, no new dependency: we only need GET with headers and a timeout. `requests`/`httpx` would add packages for nothing the fetcher uses. The transport is one function, so it can be swapped later.
- **Numbers:** at least **3 s** between requests to one host (longer if `Crawl-delay` says so), **20 s** timeout per request. A `Crawl-delay` above **60 s** is not waited out: the host is not fetched and the failure is recorded, so one site can't stall the morning job.
- **robots.txt missing (4xx) = everything allowed; server error, 429 or no connection = nothing fetched from that host** (both as RFC 9309 says).
- **The one retry** is only for timeouts, network errors, 5xx and 429, after the normal host delay. A 403/404 is not retried (it won't change a few seconds later).
- **What counts as an AI opt-out:** a robots.txt group that **names** an AI crawler (ClaudeBot, Claude-User, Claude-SearchBot, Claude-Web, anthropic-ai, GPTBot, ChatGPT-User, CCBot, Google-Extended, Applebot-Extended, PerplexityBot, cohere-ai, Bytespider, meta-externalagent) and disallows the source's URL. A crawler only caught by the `*` group doesn't count: a site that blocks everyone except Haven Daily by name has given us permission, not opted out. `ai-input=no` counts as well as `ai-train=no`, because sending text to an AI for a summary is AI input. A `Content-Signal` line anywhere in the file counts (safe side).
- **The opt-out note goes into `build.failures`** (written there by the collector, issue #11), so it shows on the page and the owner sees it the same morning.
- **The Method page URL in the user agent** is a constant in `haven/fetch.py` (`https://leonardoneirotti.github.io/haven-daily/about.html`) until the site config exists (issue #28).

Checked once against the real robots.txt files (1 Nov 2026, robots.txt only): all five `use` sources are allowed for us and show no opt-out; NL Times (blocks Claude-Web), Nieuwsblad Transport and PortsEurope (`ai-train=no`) and RTV Rijnmond (blocks ClaudeBot) are detected as opt-outs; The Loadstar's robots.txt has no AI rules (it stays headline-only under its RSS terms, §4).

**Feed collectors (`haven/feeds.py`, built 1 Nov 2026, issue #9).** One function, `collect_feed(source, fetcher, previous_run)`, reads every feed URL of an RSS source (PIN notices, Nieuwsblad Transport, PortsEurope, The Loadstar, RTV Rijnmond) into the **common item shape**: source id, headline, url, published (Amsterdam time), language, access (`full` / `headline-only`). It returns the items plus failures (`{"source": <name>, "error": <one line>}`) for `build.failures`; a broken feed (HTTP error, timeout, robots block, not RSS, bad XML) is a failure, never an exception. **Headline-only:** only headline, link and date are read; the feed's body text is never parsed and no article page is fetched. **`use` (PIN):** the feed's `description` is kept as a plain-text snippet **in memory only** for the relevance filter; `Item.record()` (what goes to `data/items/`) never contains it and `repr()` doesn't show it. Nieuwsblad Transport's two feeds are merged, the same link counted once. Tested on feeds we wrote ourselves (invented headlines, hard rule 13). `python -m haven.feeds` reads the real feeds once and prints headlines and links only.

*Proposed by Claude, confirmed by the owner (1 Nov 2026, PR #53):*
- **PIN gap check = "oldest dated notice in today's feed is newer than `previous_run`"**, where `previous_run` is when the previous morning run read the feeds. Equal = no gap. No previous run known (first run) = no check. Undated notices are ignored; no dated notice at all = no check. The collect step supplies `previous_run`, so **each run stores the time it read the feeds** (owner's decision, 1 Nov 2026, added to issue #11); the previous brief's `built_at` would be a few minutes too late and could hide a gap.
- **The failure line reads "PIN notices to shipping: some notices may have been missed (feed rolled over)"** (source name + the spec's message), the same `{source, error}` shape as every other failure.
- **Dates:** `<pubDate>` (RFC 822), else `<dc:date>` (ISO 8601), stored as ISO 8601 in Amsterdam time, whole seconds. A date **without a timezone is read as UTC** (RFC 5322 does the same for "-0000"; an unknown zone name such as "CET" is treated that way too, so it can be an hour off). An unreadable or missing date = `null`; the item is **still collected**; the filter then keeps it only if its link wasn't seen in the last 14 days (§5.4, owner's decision 1 Nov 2026, issue #12).
- **Snippet:** HTML tags removed, entities decoded, whitespace collapsed, **at most 1,000 characters** (enough for the AI check, which reads headline + snippet only, §5.4, and keeps its cost low).
- **Headlines** are cleaned the same way (HTML tags and double-escaped entities like `&amp;#8217;` come out right).
- **Entries without a headline or an http(s) link are skipped**, with one failure line per feed saying how many, so a feed that changed format shows up the same morning. A `<guid>` is used as the link only if it is a permalink.
- **Links:** relative links made absolute, `#fragment` removed. No other clean-up of the stored link (no tracking-parameter stripping). *(Updated 1 Nov 2026, issue #11: duplicates are no longer found by exact link but by `url_key`, which also ignores `utm_*` parameters when comparing; see the collect step below.)*
- **RSS 2.0 only.** An Atom feed, an HTML page (e.g. a bot-check page) or RSS without `<channel>` is a failure naming what was found. All five feeds are RSS 2.0 (checked 1 Nov 2026).
- **XML with the standard library** (`xml.etree.ElementTree`), no new dependency; a feed that **declares its own XML entities is refused** (real feeds don't need them; it's how a small file is made to expand into a huge one).
- **An unexpected error in our own parsing is caught too** and recorded as `"<url>: unexpected error (<type>: <message>)"`, so a bug on one odd feed can't stop the morning run (hard rule 9). The message is visible on the page, so the bug isn't hidden.
- **The AI opt-out note** from the fetcher goes into that source's failures, without repeating the source name (the page already shows it).
- **Stored item fields** (`Item.record()`): `source` (id), `headline`, `url`, `published`, `language`, `access`. The collect step (issue #11) adds the filter decision and later steps the AI output (§6.1).

Live smoke run (1 Nov 2026, from a desktop): all five feeds read with no failures: PIN 10 items, Nieuwsblad Transport 19 (two feeds merged), PortsEurope 10, The Loadstar 10, RTV Rijnmond 50.

**Page collectors (`haven/pages.py`, built 1 Nov 2026, issue #10).** One function, `collect_page(source, fetcher)`, reads the HTML sources (Port Authority news, Contargo, ECT, Kuehne+Nagel SeaNews, NL Times) into the **same `Item` and result shape as the feeds**, so the collect step (#11) treats both alike. Each page has one small parser (a few CSS selectors), listed in `pages.PARSERS`; a test keeps that list and the `html` sources in `config/sources.toml` in step. Headline-only (NL Times, or a `use` source that opts out of AI this morning): only headline, link and date are read, no teaser, no article page. A layout change is a failure, never an exception (hard rule 9). Tested on pages we wrote ourselves with the real tags and classes and invented content (hard rule 13). `python -m haven.pages` reads the real pages once and prints headlines and links only.

**Kuehne+Nagel: the Rotterdam paragraph only.** Of all K+N articles only the weekly roundup ("Port operational updates from around the world …") is collected. Its article page is opened and only the section under the bold **"Rotterdam:"** label is kept, in memory, on the new `Item.article_text` field (and its first 1,000 characters as `snippet` for the relevance filter). Nothing else from the page is passed on, not the intro (which may also mention Rotterdam) and not the other ports. **The collect step (#11) must not replace an `article_text` that is already set**, or it would pass the whole K+N article on. If the terms check (#43) makes K+N headline-only, only `config/sources.toml` and `SOURCES.md` change.

*Proposed by Claude, confirmed by the owner (1 Nov 2026, PR #55):*
- **Parser library: BeautifulSoup (`beautifulsoup4`, MIT, pure Python, plus its `soupsieve` selector package) on Python's built-in `html.parser`.** Five different layouts are easiest to read and fix as CSS selectors (`div.news-item`, `time[datetime]`): when a site changes its layout, the fix is usually one line. Standard library only would mean writing our own HTML tree and matching code for five layouts. `lxml` (faster, C code) isn't needed for five small pages a day. This is the one new runtime dependency.
- **A date without a time stays a date**: Contargo (`datetime="2026-10-30"`) and ECT ("30 October 2026") give no time of day, so `published` is `"2026-10-30"`, not a made-up midnight. **The 48 h rule (#12) counts a date-only item's age from the end of that day** (midnight at the start of the next day, Amsterdam time), so it is never dropped too early; the 14-day duplicate check stops repeats. *(Owner's decision, 1 Nov 2026, added to issue #12; also in §5.4.)*
- **A page timestamp without a timezone is read as Amsterdam time** (HTML `<time>` without a zone means the publisher's local time; for feeds the rule stays UTC, §5.8 above). None of the five pages does this today.
- **List teasers are kept for `use` sources** as the in-memory `snippet` (Contargo, ECT; at most 1,000 characters), exactly like PIN's feed description; the Port Authority list has none.
- **Rotterdam paragraph boundaries:** from a bold label (`<strong>`/`<b>`) whose text ends in "Rotterdam" (e.g. "Netherlands Rotterdam:") to the next bold label, a heading, or the end of the label's block (`p`, `li`, `div`), whichever comes first; the label itself is left out; at most 6,000 characters (the article-text limit above). The K+N item's date comes from the article's JSON-LD `datePublished`.
- **No weekly roundup on the K+N list is not a failure**: it is on the first page only a few days a week. But if K+N renames the series, K+N would go quiet instead of failing, so **the collect step (#11) records a failure when K+N gave no item in 14 days** *(owner's decision, 1 Nov 2026, added to issue #11)*. Details, *confirmed by the owner (1 Nov 2026)*: "14 days" = today plus the 13 days before it, read from `data/items/`; any K+N item counts, headline-only too; **the check starts 14 days after the first collect run of any source** (first run 1 Dec → first check 15 Dec), not after 14 days of stored K+N items, so a K+N collector that is broken from day one is still caught; no check while K+N is dropped (never fetched).
- **A roundup without a Rotterdam paragraph is a failure and gives no item** ("no Rotterdam paragraph found in the weekly port update (layout changed?)"): nothing else from the page is ever used instead.
- **K+N headline-only** (by config or AI opt-out): the weekly roundup's headline and link only; the article is never opened, so the item has no date (the list shows none).
- **A page with no news cards at all is a failure** ("no news items found on the page (layout changed?)"); none of the five lists is ever empty. Cards without a headline or http(s) link are skipped and counted, as for feeds. Links are made absolute, `#fragment` removed, and the same link twice on a page (e.g. featured and listed) is one item.
- **Only the first page of each list is read.** It holds 5–24 items, more than a day's news for every source.
- **An `html` source without a parser** (added to the config, code not written yet) is a failure line, not a crash, and is not fetched.

Live smoke run (1 Nov 2026, from a desktop): all five pages read with no failures: Port Authority 10 items, Contargo 5, ECT 12, Kuehne+Nagel 1 (the 21–27 Oct roundup; Rotterdam paragraph 458 characters, in memory only), NL Times 24. The first run reported two K+N cards "without a headline": the small featured cards use an `h3` with another class; fixed and tested before this PR.

**Collect step (`haven/collect.py`, built 1 Nov 2026, issue #11).** `run_collect(sources, fetcher, today)` reads every `use` and `headline-only` source in config order with its collector (feeds or pages). One source failing never stops the others; even a crash inside a collector becomes a failure line (hard rule 9). It returns **today's new items in memory** plus the failures, `feeds_read_at`, and counts (sources read, items collected, duplicates); nothing is written here. The runner (#22) writes the day's items file once, after the filter and summariser have added their fields, and stores `feeds_read_at` in the brief (`build.feeds_read_at`, §6). `python -m haven.collect [--with-text]` runs it once and prints a table (source, access, published, headline; with `--with-text` only the number of characters of article text); it writes nothing.
- **Duplicates, once, here:** an item whose link is in `data/items/` of the previous 14 days is not returned; the same link from two sources today counts once.
- **K+N 14-day check** (owner's decision and details above): one failure line, *"no item collected in the last 14 days (weekly port update renamed, or the collector broken?)"*.
- **Article text:** `add_article_text(items, sources, fetcher)` opens each `use` item's article page and keeps up to 6,000 characters of its text **in memory** (`Item.article_text`); headline-only items are never opened, and text that is already set (K+N, PIN) is never replaced.

*Proposed by Claude, confirmed by the owner (1 Nov 2026, PR #56):*
- **Article pages are opened only for kept items**: the runner calls `add_article_text` after the relevance filter, which reads headline + snippet only (§5.4). Pages of items that are dropped anyway are never requested: fewer requests to publishers and less third-party text in memory.
- **PIN's article text comes from its feed**, no notice page is opened: the feed description is the whole notice (checked 1 Nov 2026: 340 characters on the page, 342 in the feed, the same text apart from title and date). `FULL_TEXT_FEEDS` in `haven/feeds.py` lists such feeds; the others' descriptions are teasers and are not used as article text.
- **Link normalisation for the duplicate check** (`url_key`): ignores `http`/`https`, upper/lower case in the host, a leading `www.`, the default port, a trailing `/`, **the `#fragment`** and **`utm_*` tracking parameters** (name in any case); keeps the path's case and **every other query parameter**, as written and in their order (`?id=123` can name the article). Only used for comparing: the stored link is never changed. *(Fragment and `utm_*` added by the owner, 1 Nov 2026; a test for each.)*

*Also proposed by Claude, confirmed by the owner with the changes marked (1 Nov 2026, PR #56):*
- **The same link from two sources today: the first source in config order wins.**
- **`feeds_read_at` = the moment the run started reading the sources** (before the first request), not the moment PIN was read: an earlier time can only make the next day's gap check warn more, never less. `previous_run` = the value in the latest brief of the previous 14 days that has a readable one (with timezone); a brief without it is skipped for an older one (same reason); none = no gap check. **When the gap check is skipped this way, a note says so** in `build.failures` (under PIN's name): *"gap check skipped: no brief of the last 14 days records when the feeds were last read"*, so a missed rollover is never silently unchecked (e.g. on the first run). *(Added by the owner, 1 Nov 2026; tested.)*
- **Where the article text is read** (checked 1 Nov 2026): Port Authority `div.news-page`, Contargo `main div.text`, ECT the main block's `.field--name-body`; inside it, the paragraphs, list points and headings, without the Port Authority's header block (headline and date) and "more news" box, menus, footers and forms. A test keeps this list and the `use` sources in config in step. **A container that matches but holds no readable text** (empty, whitespace only, or only parts that are left out) **counts as a failed read**, like a missing one (next point). *(Added by the owner, 1 Nov 2026; tested.)*
- **An article that can't be read** (fetch error, container missing = layout changed) is a failure line; **the item stays, without text**. What the summariser does with a `use` item without text is #15's decision.
- **An article on a site that opts out of AI** (checked per article, since an article can sit on another host than its list) makes that item headline-only for the run, with a note, like the source-level check (hard rule 12).
- **A broken stored items file** (hand edit) is a failure line, *"Duplicate check: …, line N: not valid JSON …; that day's links are not checked"*, and the run goes on: at worst an item comes back once, visibly. **The run never overwrites or deletes a broken stored file**: stored days are only read; the owner repairs them by hand. *(Added by the owner, 1 Nov 2026; tested.)*
- **Stored item fields:** the collect step adds none beyond the six collected fields (§6.1); the feed read time is stored once per run in the brief, not on every item line.

Live smoke run (1 Nov 2026, from a desktop, `--with-text`): 10 sources read, 151 items, 0 duplicates (no stored days yet), **no failures**, repo unchanged after the run. All 38 `use` items got text: Port Authority 10 (median 3,715 characters, longest capped at 6,000), PIN 10 (from the feed, median 684), Contargo 5 (median 539), ECT 12 (median 2,044), K+N 1 (Rotterdam paragraph, 458). All 113 headline-only items: no text.

**Article text (hard rule 13).** For **use** sources the collector opens the article page and passes up to ~6,000 characters to the summariser **in memory**; the text is then discarded. Headline-only sources: no article page is fetched at all. `data/items/` stores headline, URL, dates, source, language, filter decision and AI output, **never article text or feed snippets**.

**Feeds that roll over before 06:45**
- **NL Times:** collected from its port tag page (HTML, headline-only), which lists only port stories and goes back weeks, instead of the site-wide feed.
- **PIN notices:** feed kept, plus **gap detection**: if the oldest item in the feed is newer than the previous run, the brief records "PIN: some notices may have been missed (feed rolled over)" in `build.failures`. **After week one:** check how often this happens and whether a second daily collect is worth it.

### 5.9 Archive and site size (decided 31 Oct 2026)

**Every day page is kept forever**: no day is ever deleted, rotated or merged. `days/YYYY-MM-DD.html` URLs never change, so LinkedIn posts that link to a day keep working.

GitHub limits (GitHub Pages docs): **published site ≤ 1 GB**, source repo recommended ≤ 1 GB, soft bandwidth limit 100 GB/month.

Growth estimate, measured on the sample pages (31 Oct 2026): fixed assets (basemap, Leaflet, CSS, JS) ≈ **1.1 MB once**; a day page ≈ 22 KB base + ~1 KB per item + **~0.8 KB per ship**.

| | Per day | Per year | Years until 1 GB |
|---|---|---|---|
| Site, v1 (no ships) | ~30 KB | ~11 MB | ~90 |
| Site, v2 (100–250 ships/day, real count unknown until the AIS snapshot runs) | ~100–220 KB | ~36–80 MB | ~12–28 |
| Repo data (`data/briefs` + `data/items` + `data/status`, v2) | ~70–250 KB | ~25–90 MB | ~11–40 |

The archive page itself grows ~1 KB per day (one row), ~0.4 MB/year. Conclusion: no size problem for many years. **Re-check once a year, or once v2 shows the real ship count.** If it ever gets close, the first fix is to stop embedding the full ship table in old day pages (keep the data in `data/briefs/`), not to delete days.

### 5.10 Map pins and "affects" tags: fixed lists (decided 31 Oct 2026)

**Why:** a model asked for coordinates or free-form tags will invent them (coordinates a few hundred metres off, "Container" / "Containers" / "Container shipping" for one thing). So the AI only **picks from lists**; the code fills in the facts.

**Place list (gazetteer)**, a config file of ~30–40 known places, each with:
`id`, `label` (as shown on the chart), `lat`/`lon` (**taken once from OpenStreetMap**, never from the AI), label `side`, kind (`terminal` / `area` / `anchorage` / `lock` / `fairway`).
Examples: terminals (ECT Delta, Euromax, RWG, APMT Maasvlakte II…), areas (Maasvlakte, Europoort, Botlek, Waalhaven…), anchorages, locks, fairways.
- The summariser picks **one place id or "none"**. The code adds coordinates, label and side → `items[].map`.
- No known place → no pin: the item is still in the brief, just not on the chart.
- v2: ships at a terminal and items about that terminal share the same place id, so "ships at the terminal in the news" is a lookup, not a guess.

**Affects tags**, a config list of ~15 cargo/mode tags: Containers, Dry bulk, Liquid bulk, Breakbulk, RoRo, Barge, Rail, Truck pickups, Rhine, Hinterland, Sea access, Customs… **plus location tags taken automatically from the place list** (the item's place label, e.g. "Maasvlakte II"). The summariser picks **up to 5**.

**Log what's missing** (both lists): any place or tag the AI mentions that is **not** on its list is discarded from the item and recorded on the item's line in `data/items/` (`"unlisted": {"places": ["Calandkanaal"], "tags": ["Reefers"]}`). The owner reviews these to decide what to add; a list grows when the log shows the same request coming up often.

---

## 6. Data format: one brief per day

```json
{
  "date": "2026-10-29",
  "sample": true,
  "built_at": "2026-10-29T06:52:00+01:00",
  "corrections": [
    { "at": "2026-10-29T09:14:00+01:00", "note": "Item 2: wrong terminal, ECT Delta not APM 2." }
  ],
  "status": [
    {
      "key": "rhine", "label": "Rhine water level", "icon": "waves",
      "value": 94, "unit": "cm", "place": "Kaub gauge", "level": "amber",
      "gauge_max": 300, "observed_at": "2026-10-29T06:15:00+01:00",
      "source_name": "…", "source_url": "https://…", "note": null
    }
  ],
  "items": [
    {
      "severity": "medium",
      "headline": "Low Rhine water cuts barge loads to Mannheim and Basel",
      "url": "https://…", "source": "…", "language": "en",
      "published": "2026-10-28T17:20:00+01:00",
      "summary": "Barge operators have lowered maximum loads … into next week.",
      "impact": "Less barge capacity from Rotterdam to southern Germany … compare rail options now.",
      "affects": ["Barge", "Rhine", "Containers", "Dry bulk", "Hinterland"],
      "access": "full",
      "written_by": { "model": "claude-haiku-5-5", "api": "batch" },
      "map": { "lat": 51.906, "lon": 4.47, "label": "Low Rhine →", "side": "left" }
    }
  ],
  "build": { "sources_checked": 9, "items_collected": 41, "items_kept": 5,
             "summaries": { "batch": 5, "fallback": 0 },
             "ai_unavailable": false,
             "failures": [ { "source": "…", "error": "…" } ] },
  "ships": {
    "snapshot_start": "2026-10-29T06:28:00+01:00",
    "snapshot_end": "2026-10-29T06:40:00+01:00",
    "source_name": "aisstream.io",
    "vessels": [
      { "name": "Seline Express", "type": "container", "flag": "LR",
        "lat": 52.04604, "lon": 3.80571, "heading": 35,
        "status": "anchored", "speed_kn": 0.2, "length_m": 350,
        "area": "Maas anchorage", "destination_raw": "", "destination": null,
        "news_item": null }
    ]
  }
}
```

| Field | Meaning |
|---|---|
| `built_at` | when the morning job wrote the brief (Amsterdam time); shown as "Published HH:MM". *The old `review` and `published_at` fields are dropped: there is no review step any more.* |
| `corrections` | list of `{at, note}`, empty `[]` when the brief was never changed. Added by hand whenever a published brief's content is edited: `at` = time of the fix (Amsterdam), `note` = one line, what changed and why. The page shows "Corrected HH:MM" (latest entry) in the publication line and all notes under "How this brief was made". The morning job always writes `[]`. |
| `status[].value` | number, text, or `null` = No data |
| `items[].impact` | `null` → "Not enough information in the source to judge the impact." |
| `items[].severity` | `"high"` / `"medium"` / `"low"`, or `null` = **unrated** (AI step failed for this item; `summary` and `impact` are `null` too, §5.6). `null` means **only** "the AI failed". For a headline-only item a non-null severity was rated from the headline alone (§2.1). |
| `items[].access` | `"headline-only"` for paywalled and AI-opt-out sources: `summary` and `impact` are `null`, severity, place, `affects` and `strike` taken from the headline only, shown as "rated from headline only" (§2.1) |
| `items[].strike` | strike details or `null` (§5.7): `state` `announced`/`ongoing`/`cancelled`, `location`, `affects_rotterdam`, `start`/`end` (dates or `null`, never guessed), `match` `same`/`new`/`unsure`, `strike_id` (assigned by code) |
| `items[].written_by` | which model wrote the summary and via which API: `{"model": "claude-…", "api": "batch" \| "standard"}` (§5.5) |
| `build.feeds_read_at` | when this run started reading the sources (ISO 8601, Amsterdam time), from the collect step (§5.8). The next run passes it to the PIN gap check as `previous_run`. Not shown on the page. *(Issue #11.)* |
| `build.summaries` | how many items were summarised in the batch vs fell back to the standard API with Haiku 5.5 |
| `build.ai_unavailable` | `true` only on a **reduced brief** (§5.6): the AI was down until the last trigger, so all items are unrated and the page shows *"The AI step was unavailable this morning: headlines only, no summaries."* `false` otherwise; a missing field counts as `false`. *(Name proposed by Claude, confirmed by the owner 1 Nov 2026, PR #50.)* |
| `items[].map.side` | `"left"` puts the label left of the number where the right is crowded |
| `ships` | `null` when the AIS snapshot failed (page says so) |
| `vessels[].type` | `container` / `tanker` / `bulk` only |
| `vessels[].status` | `underway` / `moored` / `anchored` |
| `vessels[].destination_raw` | as typed on board (`"NL RTM"`, `"ANTWERP>HAMBURG"`, blank) |
| `vessels[].destination` | cleaned, `null` = Unknown |
| `vessels[].news_item` | rank of the item about this ship's terminal |

### 6.1 Stored raw data (decided 31 Oct 2026)

Next to the brief, the pipeline keeps the raw material, so nothing it saw is lost:

| File | Contents |
|---|---|
| `data/items/YYYY-MM-DD.jsonl` | **JSON Lines**: one line per item collected that morning, kept *and* dropped, with its filter decision (`"filter": {kept, stage, reason}`, §5.4). Collected fields (§5.8, issue #9; confirmed by the owner 1 Nov 2026, PR #53): `source` (id), `headline`, `url`, `published`, `language`, `access`. The HTML lists (issue #10) give the same fields; `published` is a timestamp, a date only (`"2026-10-30"`) when the page gives no time, or `null`. The collect step (issue #11) adds no further fields; the relevance filter adds `filter` (§5.4; `{kept, stage, reason}`, set by the rules for items they keep or drop, issue #12, and by the AI check for the rest, #13) and later steps the AI output (§5.5, §5.7, §5.10: e.g. `written_by`, `strike`, `unlisted`; exact names with the summariser, #15). Never `snippet` or `article_text` (in memory only, hard rule 13). |
| `data/status/YYYY-MM-DD.json` | Every status reading taken that morning (value, level, observed time, source), including failed readings as `null`. |

Rules:
- **One file per day per kind, written once by the morning job, never rewritten by the pipeline.** A day's file only changes when the owner edits it by hand.
- Duplicate check: the collect step reads the item files of the previous 14 days (§5.8, issue #11).
- Why not SQLite: a binary database can't be read in a git diff and gets stored whole again every day. Why not one big JSON file: it's rewritten every day, so diffs get noisy and it gets slower. Size estimate: ~50 KB/day, under 20 MB/year.
- Later charts: a small script loads all files into SQLite or pandas. The files stay the source of truth.

**Storage module (`haven/storage.py`, built 1 Nov 2026, issue #7).** One small module writes and reads all three daily files (`items`, `status`, `briefs`):
- **Write once:** the file is opened in "create only" mode, so writing a day that already exists fails (`AlreadyWrittenError`) and the file stays as it was. Everything is checked before the file is created, so a refused write leaves no half-written file that would block the retry.
- **Stable format:** UTF-8, LF line endings, a newline at the end. Same data → byte-identical file.
- **Hard rule 13 guard:** any field whose name contains the word `text`, `content`, `snippet` or `body` is refused, at any depth, and the error names the field but never repeats its value.
- **Read helpers:** one day (`None` if the day has no file) and the last N days (newest first, missing days skipped).

*Proposed by Claude, confirmed by the owner (1 Nov 2026, PR #51):*
- **Keys are sorted alphabetically** in every file. Fully deterministic whatever order the code builds a dict in; the cost is that a brief file starts with `"build"` instead of `"date"`. List order is never changed (collection order is information). `.json` files are indented 2 spaces; `.jsonl` has one object per line.
- **The last-N-days reader covers the N days *before* the given day, not that day itself**: the collector runs before today's file exists, so `read_recent("items", before=today, days=14)` = the 14 previous days.
- **`description` is on the guard's word list too**: it's the RSS field that carries feed snippets. Words are matched whole (`article_text`, `contentSnippet` are caught; `context` is not). The guard checks all three kinds, not only items.
- **A brief's `"date"` must match its file name**, so a brief can't be saved under the wrong day.
- **A day with no collected items still gets an (empty) items file**: "nothing collected" is recorded, and the day stays write-once.
- **NaN/Infinity are refused** (not valid JSON); "no data" is `null` (§2.2).
- Reading tolerates hand edits: CRLF line endings and blank lines in a `.jsonl` file; a broken line is reported with file name and line number.

---

## 7. Design system

### 7.1 Visual direction

Reference: Dribbble shot **"Pergamum University Map"** (dark warm map, contour lines hugging the coast, orange route/pins, teal markers, white square zoom buttons, peach call-to-action). Owner's reaction to our version: *"looks like Call of Duty, not bad"*.

**One dark palette for the whole site, like a printed relief map under a lamp**: warm charcoal, ivory type, charcoal water with fine lines following the coast, textured land, teal ships, one orange accent. **Colour carries meaning only**: severity, status, ships linked to the news.

### 7.2 Colour tokens (top of `style.css`; `map.js` reads the chart ones)

```css
:root {
  --bg: #151311;          /* page */
  --surface: #211e1a;     /* panels, popups, hovered rows */
  --surface-2: #2b2723;   /* selected item */
  --ink: #f2ebe0;  --ink-2: #aea294;  --rule: #352f29;
  --shadow: rgba(0,0,0,.55);
  --overprint: #f08ac6;   /* "Impact for planners" label = interpretation */
  --gauge-water: rgba(96,164,214,.45);  --gauge-line: #7cb8e4;

  /* chart */
  --water: #1b1917;  --water-line: #a8988a;  --land: #564c44;
  --land-shadow: rgba(0,0,0,.65);  --coast: #a29384;
  --road: #463d36;  --rail: #4b423a;  --tank: #827366;
  --water-label: #bdb1a3;  --land-label: #e6d8c6;  --label-halo: rgba(0,0,0,.85);
  --ship: #6fd6bc;        /* teal */

  /* controls */
  --button: #f6f1ea;  --on-button: #151311;   /* ivory zoom squares */
  --accent: #ff801d;  --on-accent: #151311;   /* orange "whole port" button */
  --cta: #fae8d9;     --on-cta: #151311;      /* peach popup button */

  /* severity (fills for numbered squares / inks for text) */
  --high: #d93a24;   --on-high: #fff;     --high-ink: #ff8b7b;
  --medium: #f2a51a; --on-medium: #1f1600; --medium-ink: #f5b84f;
  --low: #607286;    --on-low: #fff;      --low-ink: #a9b8c6;
  --ok-ink: #6bd49a; --nodata-ink: #9aa6b1;

  --panel-width: 25rem;  --gutter: 16px (28px from 40rem);  --page-width: 96rem;  --measure: 62ch;
  color-scheme: dark;
}
```

Reference colours sampled from the Dribbble shot: frame `#1a1816`, water `#2e2925`, land `#4a403a`, orange `#ff801d`, teal `#5a9f8e`, peach `#fae8d9`, ivory `#fdfbfc`.

### 7.3 Typography — IBM Plex (Google Fonts; self-host before launch for EU privacy)

| Role | Font |
|---|---|
| Body text, UI, panel date ("Thursday"), section titles | IBM Plex Sans (400–700) |
| Headlines, big readings (94 cm, 40), callout labels, ship names, city label | IBM Plex Sans Condensed (500–700) |
| Kickers, severity tags, table headers, brand name, timestamps, AIS text, land place names on the map, the date line | IBM Plex Mono (400–600), uppercase + letter-spacing for labels |
| **Planner impact only** (+ water names in italic on the map) | IBM Plex Serif |

Principle: **fact vs interpretation in two typefaces** — the impact is the only serif text, with a rose label "IMPACT FOR PLANNERS *interpretation*". Max weight 700.

### 7.4 Layout

**Wide screens (≥ 64rem): the "stage"**
- The chart fills the first screen: height `clamp(36rem, 100vh − 5.5rem, 62rem)`.
- **News panel floats over the chart's western side (open North Sea)**: `position:absolute; top/bottom/left: 1rem; width: 25rem`, background `rgba(21,19,17,.95)` (no backdrop blur — too slow), 1px rule border, big shadow.
  - Panel head: kicker "MORNING BRIEF · NO. 003" (mono), weekday huge (Plex Sans 700, ~2.9rem), date below (mono), publication line.
  - Panel items list (scrolls inside): numbered square + severity tag + first "affects" tag + headline. The selected item gets `--surface-2`, an ivory left bar, and **expands to show its 2-line summary**.
  - Panel status: 2×2 mini grid (Weather, Rhine, Strike, Ships) with level icon + value.
  - "↓ Full brief and port status" link.
- Ship filter (All / Container / Tanker / Bulk with counts) top-left of the free chart area; focus box ("1 Terminal strike · 6 ships at this terminal | Overview") top-right; legend bottom-left of free area; controls bottom-right.
- Vignette: `.chart-frame::after` with `box-shadow: inset 0 0 110px 16px rgba(0,0,0,.55)`, z-index 401 (above map, below panels).
- **Below the stage**: two columns — "The brief" (full items) and "Port status" (detailed dials, sticky), then ship table, build notes, day navigation.

**Phones/tablets (< 64rem)**: chart (62vh, 340–560px) → legend → panel in normal flow (head + mini status + link; the item list is hidden because the full brief follows) → full brief → status.

**Top bar**: signal-flag logo + "HAVEN DAILY" (mono) + "Thu 29 Oct · No. 003"; nav Today / Archive / Method (active = 3px underline). Sample-data note below in amber.

### 7.5 Components

- **Numbered square** (`.num`): same square in panel, full list, chart and archive strip → the chart works as the index of the brief. High = red with white number, medium = amber with dark number, low = slate, **unrated = outlined, no fill, grey `--nodata-ink` number** (§5.3).
- On the chart the high-severity square has a soft "ping" ring animation (transform/opacity only).
- **Severity tag**: mono uppercase, coloured ink; "UNRATED" in `--nodata-ink`.
- **Status dial**: label with icon, big condensed value + unit, place, level (icon+word) + change, note, "Read at 06:20 · Source ↗". River gauge = striped board with water level.
- **Item card (full brief)**: num + severity + source · language · time; condensed headline (link); summary (sans, max 62ch); divider; impact label + serif impact text (max 62ch); Affects; actions: "Show on chart" (outlined button, needs JS), "Read original (Dutch) ↗", "Read in English ↗".
- **Leaflet controls**: zoom = two separate ivory 32px squares with 6px gap and shadow; above them the **orange "whole port" button** (expand icon); scale bar and attribution in the same corner (bottom-right stack, bottom-up: attribution, scale, zoom, home).
- **Popup** (ship): dark surface, ship name (condensed 700), "Container ship · 350 m · Liberia", facts (Status, Area, Destination + raw AIS text in mono). If linked to news: full-width **peach button** "AT THE TERMINAL IN ITEM 1" with the severity colour as a 4px left border.
- **Accessibility**: skip link, `aria-live` announcer for chart changes, everything on the chart also listed as text, `needs-map` / `no-map` classes so buttons only appear when the chart works, reduced-motion support, focus outlines, 44px touch targets.

### 7.6 Logo

Current: the letters **H** and **D** in the International Code of Signals (H = white/red vertical halves, meaning "I have a pilot on board"; D = yellow/blue/yellow). The owner found it unclear → **redesign**. Process chosen: explore concepts with **Nano Banana Pro**, pick a direction, redraw as clean SVG in site colours. Never resemble Port of Rotterdam branding. Save concepts in `design/logo-concepts/`.

Prompts:

1. *Contour H* — "Minimal logo mark, the letter H formed by 6–8 concentric outline rings like coastline contour lines on a nautical chart, each ring evenly spaced, single colour warm ivory (#f2ebe0) on very dark charcoal (#151311), flat vector style, no gradients, no text, centred, must stay readable at 32 pixels, 4 variations in a 2×2 grid"
2. *Harbour from above* — "Minimal logo mark, abstract top-down view of a harbour: two parallel quay piers joined by a dock basin so the negative space reads as the letter H, a single small teal (#6fd6bc) ship hull moored inside, flat vector, warm ivory and teal on dark charcoal, no text, geometric, works as an app icon, 4 variations in a 2×2 grid"
3. *Navigation marker* — "Minimal monogram 'HD' inside a square tile inspired by maritime navigation markers and buoy day-marks, bold geometric letterforms, one orange accent (#ff801d) on dark charcoal with ivory letters, flat vector, no other text, no real company logos or port authority branding, 4 variations in a 2×2 grid"
4. *Lighthouse beam H* — "Minimal logo mark for 'Haven Daily', a daily port-news service. The letter H drawn as two lighthouse towers joined by a single horizontal beam of light. Flat vector, geometric, thick even strokes. Warm ivory (#f2ebe0) on very dark charcoal (#151311), with one small orange (#ff801d) light at the top of the left tower. No text, no gradients, no 3D. Readable at 32×32 pixels. 4 variations in a 2×2 grid."
5. *Compass sunrise* — "Minimal logo mark: a half compass rose rising over a flat horizon line, like a sun at dawn, symbolising a morning briefing for a seaport. Only 8 sharp compass points, the north point slightly longer and in orange (#ff801d), the rest warm ivory (#f2ebe0) on very dark charcoal (#151311). Flat vector, clean geometric lines, no text, no gradients. Works as a small app icon. 4 variations in a 2×2 grid."
6. *Mooring bollard monogram* — "Minimal monogram logo using the letters H and D. The H is built from two ship mooring bollards seen from the side, with a mooring rope forming the crossbar; the D is a simple rounded shape next to it, like a buoy. Bold flat vector, industrial and precise. Ivory (#f2ebe0) on very dark charcoal (#151311) with a teal (#6fd6bc) accent on the rope. No other text, no gradients, no real port or company branding. Readable at small sizes. 4 variations in a 2×2 grid."

### 7.7 Other images worth generating (Nano Banana Pro)

- **Social preview card (og:image, 1200×630)** — highest impact, LinkedIn shows it: "Wide 1200×630 banner, dark warm charcoal background (#151311), top-down stylised relief map of a large seaport at dusk with fine concentric contour lines in the water following the coastline, a few small teal ship silhouettes seen from above, one glowing orange accent, minimal and editorial, lots of empty dark space on the left for a title, no text, no logos, no real company branding"
- **Ship-type illustrations for popups** (one each, labelled "illustration" in the UI): "Top-down 3/4 view illustration of a large [container ship / oil tanker / bulk carrier] at sea, muted warm palette on a dark charcoal background, subtle teal highlights, clean editorial style, no text, no logos, no company markings, 800×500"

---

## 8. The chart (how it works — interview material)

### 8.1 Principles

- **No map service at runtime.** The basemap is a file in the repo, Leaflet is self-hosted. No tile server, no API key, no tracking.
- The chart is a fixed **"sheet"** (the basemap's bounding box): `maxBounds` = sheet, `maxBoundsViscosity: 1`, min zoom = smallest zoom that stays inside the sheet. Max zoom 15. `zoomSnap: 0`, `zoomDelta: 0.5`. **Scroll-wheel zoom off** (page scrolls past the chart; zoom with buttons, pinch, double-click).
- **Sheet bbox** (south, west, north, east) = **(51.74, 3.40, 52.16, 4.62)**: from the North Sea anchorages to Rotterdam city, extended far west so the **news panel only ever covers open sea**.
- Home views: wide screens `view_home` = (51.845, 3.76, 52.07, 4.58) fitted into the space **right of the panel** (padding-left = panel width + 48px, top 72, right 72, bottom 64). Phones `view_compact` = (51.84, 3.74, 52.08, 4.26) (western port).

### 8.2 Building the basemap (`tools/build_basemap.py`, run once)

1. **Water query** (Overpass API, mirrors: overpass-api.de, overpass.kumi.systems, overpass.private.coffee; cache raw JSON):
   `way[natural=coastline]`, `way/relation[natural=water]`, `way/relation[waterway=riverbank]` in the bbox, `out geom`.
2. **Land construction**: OSM has no "sea" polygon, only coastlines (land on the left). Cut the bbox rectangle along the coastlines (`polygonize` of bbox edge + coastline pieces), keep faces on the **sea side** (cross product with the nearest coastline segment), union with water areas (multipolygon relations joined from member ways), **land = bbox − all water**.
3. Clean: drop islets < 6e-6 deg² (~250×150 m), fill holes < 2.5e-5 deg² (~500×350 m), simplify 0.0002° (~15–20 m), round coords to 4 decimals.
4. **Detail query**: `highway ~ motorway|trunk|primary|secondary|tertiary` (major = first three) and `railway=rail`, **both with `tunnel!=yes`** (tunnels would draw roads across the water), `man_made ~ breakwater|groyne` (jetties), `man_made=storage_tank` (→ circles: centroid + radius = √(area/π) in metres, keep ≥ 4 m).
5. Lines: `linemerge` → clip to bbox → simplify 0.0001° → **compact encoding**: integer grid of 0.0001° (~10 m) counted from the south-west corner, first point absolute, then each point as the step from the previous one (`[x0, y0, dx1, dy1, …]`). Tanks: flat `[x, y, r_m, …]`.
6. Output `static/basemap.js`: `window.HAVEN_BASEMAP = {bbox, land (GeoJSON MultiPolygon), detail: {grid: 10000, major, minor, rail, jetty, tanks}, labels}`. Size ≈ **820 KB** (~250 KB gzipped by GitHub Pages). Last run: 205 land polygons, 2,078 major + 11,374 minor road lines, 2,977 rail, 773 jetty, 4,240 tanks.

Place labels (water = italic serif; land = mono caps; city = condensed caps):
North Sea (51.99, 3.84) · Nieuwe Waterweg (51.951, 4.163, 37°) · Nieuwe Maas (51.9, 4.4) · Oude Maas (51.846, 4.36, 30°) · Waalhaven (51.879, 4.452) · Maasvlakte 2 (51.976, 3.975) · Maasvlakte (51.946, 4.035) · Europoort (51.933, 4.13) · Botlek (51.868, 4.29) · Pernis (51.882, 4.385) · Hoek van Holland (51.984, 4.135) · Rozenburg (51.906, 4.245) · Rotterdam (51.925, 4.48).

### 8.3 Painting the basemap in the browser (`static/map.js`)

A custom Leaflet vector layer (`L.Path.extend`) on its own `L.canvas` renderer in a pane at z-index 250 (under labels and ships). Leaflet handles canvas size, retina, smooth CSS scaling during zoom, and asks for a repaint when the map stops moving.

> **Gotcha:** `L.Path` has no `initialize`, so give the subclass `initialize: function (o) { L.setOptions(this, o); }` — otherwise the `renderer` option is silently ignored and nothing is drawn.

Everything is converted once to **"world pixels"** (Web Mercator at zoom 0): `x = 256·(0.5 + lon/360)`, `y = 256·(0.5 − ln((1+sinφ)/(1−sinφ))/(4π))`. At zoom z: screen = world · 2^z − pixelOrigin. Detail points use a **lookup table per grid row** for the latitude formula (≈200,000 points decode in ~40 ms).

Paint order:
1. **Water + coast lines** (on a separate 1×-resolution canvas, then copied in — see §8.6).
   - **The trick:** for each line, stroke the coastline very wide in the line colour (`2d + 0.8 px`), then slightly narrower in the water colour (`2d − 0.8 px`). What remains is a thin line at exactly distance *d* from the nearest shore. Drawn from the outside in. No data needed.
   - Spacing: 25, 50, 100, 200… metres — the smallest that stays ≥ 6 px apart at the current zoom; lines out to 120 px. Zooming in one step halves the spacing, so existing lines stay put and new ones appear between.
   - Opacity fades with distance: `0.06 + 0.5·(1 − (i−1)/count)^1.8`.
   - Lines far from shore use a simplified coastline (tolerance = distance/15, buckets 10/5/2/0.75 px).
   - **They are decoration, not depth contours** (stated on the Method page).
2. **Land**: dark copy shifted 2.5 px down (cheap shadow), land fill (`evenodd`), a 128×128 random speckle pattern (grain), 0.8 px light coastline.
3. **Detail**: minor roads, major roads, rail in darker "cut" colours; jetties in land colour. Widths scale with zoom: `max(0.35, min(base·1.55^(z−11), base·4))`.
4. **Storage tanks** at real size (min 0.6 px), each with a small offset shadow.

Culling: only shapes whose box (plus a margin) touches the canvas are traced; points closer than the tolerance to the previous point are skipped.

### 8.4 Ships

Top-down hulls, bow up, 24 units long × 6 wide (shapes defined **once in `render.py`**, used by the legend macro and by `map.js`):

```
HULL       M0,-12C2.2,-9 3,-6 3,-2.5V10.5Q3,11.8 1.8,11.8H-1.8Q-3,11.8 -3,10.5V-2.5C-3,-6 -2.2,-9 0,-12Z
container  M-2.1,-8.6h4.2v2.3h-4.2zM-2.1,-5.8h4.2v2.3h-4.2zM-2.1,-3h4.2v2.3h-4.2zM-2.1,-0.2h4.2v2.3h-4.2zM-2.1,2.6h4.2v2.3h-4.2zM-2.6,6.4h5.2v2.6h-5.2z
tanker     M-0.4,-9h0.8v15h-0.8zM-2.2,-1.8h4.4v1h-4.4zM-2.6,7.2h5.2v2.8h-5.2z
bulk       M-1.7,-8h3.4v2.6h-3.4zM-1.7,-4.6h3.4v2.6h-3.4zM-1.7,-1.2h3.4v2.6h-3.4zM-1.7,2.2h3.4v2.6h-3.4zM-2.6,7.2h5.2v2.8h-5.2z
```

- SVG `viewBox="-6 -12 12 24"` in a `divIcon`, rotated by `--heading`. Deck = `rgba(0,0,0,.42)` over the teal hull (container stacks, tanker pipeline + manifold, bulk hatch covers; block near the stern = bridge).
- **Drawn to real length**: CSS `--len: max(var(--ship-min), calc(var(--length-m) * var(--px-per-m)))`; `map.js` sets `--px-per-m` on zoom end; `--ship-min` 26 px (19 px when zoomed far out, < z10.5).
- **Under way**: V-shaped wake behind the stern, length grows with speed. **At anchor**: hollow hull. **Linked to news**: hull in the item's severity colour. Selected: ring (`<circle r="15">`, scales with the ship). Dark 1.2 px outline instead of a drop-shadow filter.
- Legend: same symbols turned to point right (`rotate(90)`): Container · Tanker · Bulk · Under way · At anchor · At a terminal in the news · Item.

### 8.5 Interaction

- **Select an item** (panel entry, full-brief card, "Show on chart", number on the chart, popup button, or a `#item-N` link): highlight the panel entry (expanded summary) and the card, fade other ships/callouts, ring the ships at that terminal, focus box "Terminal strike · 6 ships at this terminal | Overview", **fly** to the item + its ships (max zoom 13.6 with ships, 11.8 without), keeping the panel area free.
- Clicking a number on the chart scrolls the **panel** entry into view (or the full card on phones).
- From the full brief, the chart scrolls back into view only if less than 60% of it is visible.
- Panel entries are real links (`href="#item-N"`) → work without JavaScript; with JS, `preventDefault` and select.
- Ship filter buttons; "N at anchor" / "N under way" fly to those ships; ship names in the table find the ship and open its popup; orange button / "Overview" return home.
- Hovering an item (panel or brief) enlarges its number on the chart.

### 8.6 Performance lessons (the site felt laggy — fixed)

Measured on a 2× screen: canvas was **13 Mpx**, repaint ~190 ms, setup ~180 ms. Fixes:
- Canvas renderer padding **0.3 → 0.1** (7.4 Mpx).
- Coast lines drawn on a separate canvas at **1 px per CSS pixel** (not retina) then `drawImage`d: 4× less work on retina; looks the same on dark water.
- Fewer lines: min gap 6 px, reach 120 px.
- Replaced canvas `shadowBlur` with an offset dark fill.
- **No `backdrop-filter`** on the panel and **no `filter: drop-shadow`** on 40 ship markers (both recomputed every frame while the map moves).
- Mercator lookup table for detail decoding.
- Repaint only on `moveend`; during zoom Leaflet scales the canvas with CSS.

### 8.7 Testing without the Chrome extension

Headless Edge works for screenshots and error checks:

```powershell
python -m http.server 8765 --directory site     # in the background
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --headless=new --hide-scrollbars `
  --window-size=1600,1000 --force-device-scale-factor=2 --virtual-time-budget=7000 `
  --screenshot="shot.png" http://localhost:8765/index.html
```

Use `--dump-dom` with a small injected script that writes errors/timings into a `data-` attribute. Headless windows have a minimum width (~500 px), so phone screenshots at 390 px are unreliable.

---

## 9. Version 2: ship map with live data (after v1 has run reliably 1–2 weeks)

- **Own daily AIS snapshot** (no embedded MarineTraffic/VesselFinder widget): the morning job listens to the free **aisstream.io** WebSocket for ~10–15 min on a bounding box around the port and saves vessels present.
- **Seagoing cargo ships only** (container, tanker, bulk). No barges, tugs, pilot boats.
- Each day's map stays in the archive.
- Click a ship: name, type, flag, berth/terminal if known, declared AIS destination (cleaned + raw), and a **point-to-point estimated route** (now → next destination) drawn with `searoute`, labelled **"estimated"**; the map zooms out from Rotterdam to show the trip (the orange route line from the reference style fits here).
- Clean messy AIS destinations ("NL RTM", "ANTWERP>HAMBURG", blank) → show "Unknown" when unclear.
- Highlight ships at terminals mentioned in today's news (already designed).
- Optional "see it live" link to the ship on MarineTraffic (link only).
- Check aisstream.io terms on public display before launch. aisstream is beta and sometimes unstable: **the page must still build if it fails** ("No ship positions for this day. The AIS snapshot failed.").

---

## 10. Build plan (prompts for Claude Code, in order)

**Version 1 — daily brief**
1. Set up the Python project: folder structure, a config file listing sources, storage for items and status values, README. Explain the structure in a few lines.
2. Test every source in SOURCES.md (feed or readable page? how much text? terms/robots.txt?) → mark use / headline-only / drop.
3. Collector: fetch "use" and "headline-only" sources, save new items (title, link, date, source, language) without duplicates. Article text in memory only, never saved (hard rule 13, §5.8).
4. Relevance filter for the Port of Rotterdam and its supply chains; show kept vs dropped so it can be tuned.
5. For each kept item: 2-line summary, planner impact, severity (rules in §2.1). Never invent facts. **Before calling an API: suggest a model and the expected monthly cost.**
6. Run everything once on today's items and show the output before building pages.
7. Status line v1: weather warnings, Rhine level, strike flag. Store values daily. No data = "No data".
8. Render the static site exactly as designed in §7–8 (already prototyped with sample briefs).
9. GitHub Pages + Actions: one scheduled job at ~06:45 Amsterdam that runs the pipeline, commits `data/` to main and deploys the site (no PR). Keys only in secrets. Notify on failures.
10. Let it run a few days, then tune the filter and severity rules.

**Version 2 — ship map**
11. Daily AIS snapshot (aisstream.io, port bbox, 10–15 min, seagoing cargo only); page builds if it fails.
12. Ship details + estimated `searoute` route, highlight ships at terminals in the news.

**Later**
- Weekly digest of the top 3 items as a starting point for the LinkedIn post (always rewritten by the owner).
- Road and rail indicators; vessel and barge waiting times once a clean source is confirmed.
- Charts from stored history (e.g. Rhine level vs barge delays).
- Custom domain.
- **Map style switcher** ("tactical", "sunny satellite", "cartoon" — inspired by the moods of games like Call of Duty / GTA / Fortnite, not copies of their designs). Feasible because all chart colours and paint settings are tokens/constants.

---

## 11. Open items and before launch

- ~~Code still on the old review model~~ **Done 1 Nov 2026 (issue #5):** renderer, day and Method templates, README field table and the sample briefs now use `built_at` + `corrections` (the 29 Oct sample has one correction; sample build times moved after 06:45). `BUILD_PLAN.md` is now only a pointer to the GitHub issues and §10.
- Check `havendaily.nl` availability; buy once the first version works.
- Test every candidate source (§4) before building on it.
- Summariser model: run the Haiku 5.5 vs Sonnet 5.5 comparison on the first real run, write `docs/model-comparison.md` (§5.5).
- **After the first week of daily runs: check real AI costs** in the Anthropic Console against the §5.4 estimates.
- **MeteoAlarm daily snapshot:** email **meteoalarm@geosphere.at** asking whether a daily, dated snapshot (06:45, labelled "not live", linking to meteoalarm.org) is allowed, given the ≤ 10 min real-time requirement for operational use. **The owner sends it.** Keep the reply in `docs/permissions/`. If refused: switch to KNMI directly sooner, or weather = "No data".
- **Switch weather warnings to KNMI directly** once `KNMI-public-weather-warnings` leaves TEST (check monthly); register a free KNMI key then.
- **Barge low-water surcharge table:** Claude researches (owner's decision, 31 Oct 2026): find whether a barge operator (e.g. Contargo) publishes a Kaub-based low-water surcharge table. If so, use its first step as the Rhine **Watch** level (instead of GlW 77 cm), citing that table on the Method page.
- **Before launch, find and check the terms of Kuehne+Nagel SeaNews and RTV Rijnmond** (§4). Downgrade K+N to headline-only, or drop either, if their terms forbid our use.
- **Permission emails to NL Times and RTV Rijnmond:** Claude drafts one short email per publisher (what Haven Daily is, non-commercial portfolio project, what we'd do with their articles: a 2-line own-words AI summary + link, never the text itself, and that we respect their AI opt-out until they say yes). **The owner sends them.** Both stay headline-only (hard rule 12) unless a publisher replies yes in writing; keep the reply in `docs/permissions/`.
- ~~Design addition: the unrated item~~ **Done 1 Nov 2026 (issue #6):** outlined square, "UNRATED" tag, card without summary/impact, reduced-brief note driven by `build.ai_unavailable`, archive strip; samples: one unrated item on 27 Oct, a reduced brief on 26 Oct. Design choices confirmed by the owner (§5.3).
- Finalise Rhine thresholds and weather thresholds from public sources (Method page).
- **Design usability review before launch** (added 31 Oct 2026): the design looks good but doesn't feel user-friendly enough, and the owner can't yet say why. First find the concrete problems: review the pages as a first-time visitor (a planner and a recruiter, on a phone and on a laptop), list what they understand in 5 seconds and what confuses them, then propose changes. **Nothing is implemented until the owner approves the proposals.** The new logo and the social preview tags come after this review.
- Self-host the IBM Plex font files (`static/fonts/`) instead of Google Fonts, to avoid sending EU visitors' IP addresses to Google.
- Check aisstream.io terms for public display.
- New logo (§7.6) and a social preview image (§7.7); add `og:image` / `og:title` / `og:description` meta tags.
- Fill in LinkedIn URL and repository URL in the site config (footer + Method page).
- First LinkedIn post: one concrete flagged item, what the tool said, and what the owner would do as a planner.

---

## 12. Credits

Status data: weather warnings by KNMI via MeteoAlarm (shown: "KNMI", time of issue, link to www.meteoalarm.org, MeteoAlarm's exact disclaimer), Rhine Kaub by WSV / PEGELONLINE (DL-DE→Zero-2.0), Rhine Lobith by Rijkswaterstaat (CC0). Map data © OpenStreetMap contributors (ODbL). Leaflet 1.9.4 (BSD-2). Icons: Lucide (ISC). Fonts: IBM Plex Sans, Sans Condensed, Mono, Serif (SIL Open Font License). Shapely (BSD) for the basemap tool. Jinja2 (BSD). Beautiful Soup and soupsieve (MIT). Anthropic Python SDK (MIT).
