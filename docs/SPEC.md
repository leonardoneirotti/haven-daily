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
  - **Low**: background trend or long-term news, **or something already over when the brief is made** (a closure lifted, a measure ended, a delay cleared): it no longer affects today's plans. *(Owner's decision, 2 Nov 2026, issue #67.)* A PIN notice whose End Date has passed is made Low **by the code**, whatever the AI answered (§5.4, §5.5).
  - **Unrated**: the AI step failed for this item, so there is no summary, impact or severity: headline + link only (§5.6). Never a guess.
- "Affects" tags (e.g. Containers · Maasvlakte II · Truck pickups).
- For Dutch items: "Read in English" link.
- Optional map pin so the item appears on the chart: the AI picks a place from a fixed list, the code adds `lat`, `lon`, `label` (§5.10). "Affects" tags also come from a fixed list (§5.10).
- Paywalled sources: headline + link only ("Headline only: this source is paywalled or its terms don't allow a summary."). *(Wording changed from "This source is paywalled, so there is no summary." in #23, Claude's proposal, confirmed by the owner 2 Nov 2026, PR #75: NL Times, The Loadstar and RTV Rijnmond are headline-only for their AI or RSS terms, not a paywall, so the old sentence was untrue for them.)* *(Since #82, 3 Nov 2026: the card says "Headline only (paywalled, or the source's terms don't allow a summary) · severity rated from the headline": the design review's wording (PR #80) with the paywall added by the owner, 3 Nov 2026, PR #88, so the line still covers paywalled sources as this section says; §7.5.)*
- **Headline-only items** (paywalled or AI opt-out, §3 rule 12, §4) still get a **severity, rated by the AI from the headline alone**, shown as **"rated from headline only"** next to the severity tag *(since #82: as "severity rated from the headline" in the card's one grey line, §7.5)*. From the same headline the AI also picks the **place** and **"affects" tags** (same fixed lists, §5.10) and extracts **strike details** (same rules, §5.7: dates only if the headline states them; an `unsure` match never clears a strike), so a strike reported only by a headline-only source (e.g. NL Times, RTV Rijnmond) still raises the strike flag. No summary; impact stays `null` (the short card shows no impact block, #82). If that AI call fails, the item is unrated like any other. *(Decided by the owner, 1 Nov 2026.)*

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

**Rules:** no data = show "No data", never estimate. Thresholds documented on the Method page with their public source. **Each level is shown with a short meaning for a planner**, built from config or one constant, never written per day ("16 cm · Alert: barge transport no longer guaranteed"; No data shows only "No data"). *(Since #83, 3 Nov 2026, design review S6; §7.5 "Status meaning".)*

Thresholds (decided 31 Oct 2026; every number comes from a public source, cited on the Method page):

| Indicator | Normal | Watch | Alert | Source |
|---|---|---|---|---|
| Weather warnings | Highest level for Zuid-Holland valid at any time **during the rest of today** (from when the feed is read until midnight, Amsterdam date; a warning that already expired doesn't count, owner's decision 2 Nov 2026, #18) is green / none | … is **yellow** | … is **orange or red** | KNMI warnings via MeteoAlarm (later: KNMI directly) |
| Rhine water level, Kaub | 151–460 cm | **150 cm or below** (barge low-water surcharges start: first step of Contargo's Kaub table, terminals south of Koblenz; Maersk's Rhine barge surcharge starts at the same level; *owner's decision, 2 Nov 2026, PR #71*) or **above Marke I 460 cm** (high-water shipping restrictions) | **80 cm or below** (operators no longer guarantee transport: Contargo "by agreement", Maersk "no loading guarantee" below 81 cm; replaces MNW 65 cm; *owner's decision, 2 Nov 2026, PR #71*) or **above Marke II / HSW 640 cm** (shipping stops) | Low side: [Contargo low-water surcharge](https://www.contargo.net/en/goodtoknow/lws) and [Maersk Rhine low water surcharge](https://www.maersk.com/news/articles/2026/07/09/rhine-river-low-water-surcharge), both read 2 Nov 2026 (`docs/research/barge-surcharge.md`). High side: WSV official gauge values via PEGELONLINE (`characteristicValues`, read 31 Oct 2026) |
| Strike flag | No active Rotterdam strike (none found, all over, or cancelled) | Rotterdam strike announced for a later date, or with no stated dates | Rotterdam strike today (dates include today, or ongoing) | Kept items of the last 14 days (§5.7) |

### 2.3 Pages

1. **Today** (`index.html`) = latest day page.
2. **Day pages** (`days/YYYY-MM-DD.html`), each with its own chart, kept forever, with previous/next navigation.
3. **Archive**: grouped by month, newest first. Each row: date + edition number, a 5-slot severity strip (coloured numbered squares, empty slots for quiet days), top headline (or "Nothing significant"), status marks, ship count.
4. **How it works** (`about.html`; called **Method** until #86, and still "the Method page" in older sections of this spec): a contents list, then what this is, **who makes this** (second since #86: the owner's About text, §7.8, with the LinkedIn and code links), how a brief is made (~06:45 collect → filter → summarise → status → publish, all automatic and unreviewed; mistakes are corrected afterwards and the page republished), severity rules, status thresholds, sources and how they are used (incl. the GDELT credit "Headline discovery via the GDELT Project" + link to gdeltproject.org, if GDELT is adopted), the chart (data sources, "lines in the water are decoration, not depths", AIS limits, messy destinations), sources and copyright, privacy (#68), credits. *(Built 2 Nov 2026, issue #24: §5.3 "The Method page"; renamed and reordered 3 Nov 2026, #86.)*
5. **Footer on every page** (mandatory text): *"Personal, unofficial project by Leonardo Neirotti. Not affiliated with the Port of Rotterdam Authority. AI-generated summaries — always check the original source."* + "Map data © OpenStreetMap contributors." + **a privacy note**, its own line right after the disclaimer *(added 2 Nov 2026, issue #68; wording confirmed by the owner 2 Nov 2026, PR #79)*: *"Privacy: no cookies, no tracking, nothing loaded from other sites. The site is hosted on GitHub Pages, which logs visitors' IP addresses for security (GitHub Privacy Statement)."*, the last words linking the [GitHub Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement). The Method page repeats it in a "Privacy" section (§5.3). Then the footer links: How it works, Archive, LinkedIn and the source code (#86).
6. **Under the brand on every page** (#86): the owner's one-liner, §7.8.

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
14. **Privacy: no cookies, no tracking, nothing loaded from other sites.** No page sets a cookie or uses browser storage (local/session storage, IndexedDB, Cache API), there is no analytics or tracking of any kind (counters, pixels, embeds), and opening a page makes the browser contact no server but this site: fonts, styles, scripts, images and the map all come from the site itself. Links to other sites are fine (a link only contacts that site when clicked). `tests/test_privacy.py` keeps it this way (§5.3). *(Added 2 Nov 2026, issue #68; Claude's proposal to make it a hard rule, confirmed by the owner 2 Nov 2026, PR #79.)*

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
| Rhine, Kaub (PEGELONLINE, WSV) | **use**, shown | REST JSON, no key, DL-DE→Zero-2.0. Value every 15 min. Official characteristic values Marke I/II from the same API set the high-water thresholds; the low-water ones come from the barge operators' surcharge tables (§2.2, owner's decision 2 Nov 2026, PR #71). |
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
1. A **ruleset on `main` that only blocks force-pushes and branch deletion**. Normal pushes (owner and job) still work; history can't be rewritten by accident. **The test run (`tests.yml`) is not a required status check: decided by the owner 2 Nov 2026: not now, revisit at launch** (#26, PR #77). A required check on `main` would also apply to the job's direct push of `data/` and to the owner's correction pushes, neither of which has a check run; until then a PR is merged only when its tests are green.
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

### 5.1.2 The daily workflow as built (issue #26, 2 Nov 2026)

**`.github/workflows/daily.yml`**, two jobs:
1. **`brief`** (only on `main`; `contents: write`; at most 45 minutes): checkout of the latest `main` → **guard** (`python -m haven.guard`, standard library only, so it runs before anything is installed and a stopped run takes seconds) → install → **`python -m haven.run`**, with `--last-trigger` when the guard says so; only this step gets `ANTHROPIC_API_KEY` (`secrets.ANTHROPIC_API_KEY`) → **`python -m haven.publish`** (commit `data/` to `main`).
2. **`site`** (only when the guard said build): calls **`pages.yml`** (`workflow_call`), so a morning deploy uses exactly the steps of a normal one.

**`haven/guard.py`** holds the §5.1.1 rules and is tested on fixed clocks (winter and summer at each trigger, the 06:30 edge, both 2026 clock-change days and the days before, brief already there, manual runs, the Amsterdam date late in the evening): it prints its decision and writes `build`, `last_trigger` and `day` to `$GITHUB_OUTPUT`. A stop exits 0 (green). **`haven/publish.py`** does the commit: on `main` only; `git add --all -- data`; then refuses, before committing, anything but **new files under `data/` with exactly one new brief** (a file staged outside `data/`, a changed or removed earlier day, no brief, two briefs); commits as `github-actions[bot]`, `Brief YYYY-MM-DD (automatic)`; `git pull --rebase --autostash origin main`, `git push origin HEAD:main`, one retry. Tested with real git against a local "origin" (only `data/` committed while other files changed, a correction pushed at the same moment kept underneath, nothing committed on any refusal) and with a fake git for the retries.

**`pages.yml`** is now one job (render + deploy) that checks out the **latest `main`**, renders with `python -m haven.render --out site` and deploys; it runs on the owner's pushes, by hand, and from the daily job.

*Proposed by Claude, all eight confirmed by the owner 2 Nov 2026 (issue #26, PR #77):*
1. **The guard and the commit are Python modules, not shell in the YAML**, so the rules the issue asks to test (summer/winter, "only `data/` ever staged") are tested like the rest of the pipeline. `tests/test_workflows.py` checks the YAML calls them and keeps no copy of their logic (e.g. no `git add` in it, the crons equal `guard.SCHEDULE_CRONS`).
2. **The last trigger is recognised by its cron** (`github.event.schedule` = `45 6 * * *`). An unknown cron or event **fails the run red** instead of building without the reduced-brief fallback, so a cron edited in one place only shows up the same morning.
3. **A manual run has a tick box "last trigger", off by default**: §5.6 gives the reduced brief to the last scheduled trigger only. Tick it when running by hand after every scheduled run of the day failed, so an AI outage then gives a reduced brief instead of a skipped day.
4. **Two concurrency groups, not one** (the issue asked to share one with `pages.yml` or explain why not). GitHub keeps only one *waiting* run per group and cancels the older one, so in one shared group an owner's push arriving while a morning run waits would cancel the morning run. Instead: the whole daily workflow is in group `daily` (a retry waits for a slow run; a running one is never cancelled), and the **deploy job** is in group `pages` with every other deployment. A deploy that is replaced there loses nothing, because **every deploy renders the latest `main` at the moment it starts** (checkout `ref: main`), so the last one always includes both the brief and any correction.
5. **The site is built from `data/briefs/` as soon as it holds a brief, from the samples until then, never both** (`render.default_briefs_dir`; `--briefs` still overrides). So merging #26 doesn't break the live site before the first morning run, and the samples disappear with the first real brief (real briefs are never deleted, §5.9).
6. **`haven.publish` adds two checks beyond the spec**: only *new* files (the runner never edits an earlier day; corrections are the owner's pushes, not the job's), and exactly one new brief, whose date names the commit. Also `--autostash`, so a stray change outside `data/` can't block the rebase, and the bot's name is given to the rebase too (it rewrites our commit and the job's checkout has no git user: found by the tests).
7. **Timeouts:** 45 minutes for `brief` (the batch wait alone can take 22), 10 for the deploy. **Full history** in the checkout (`fetch-depth: 0`) so the rebase never misses a commit. **Runner exit 2** (today's files already there) fails the run red: after the guard it can't normally happen, so the owner should look.
8. **The ruleset is kept in the repo**, `.github/rulesets/main.json`: default branch, rules `non_fast_forward` (no force-push) and `deletion` only, **no bypass**, so neither the job nor the owner can rewrite `main`'s history by accident. Applied with `gh api --method POST repos/leonardoneirotti/haven-daily/rulesets --input .github/rulesets/main.json` after the owner's OK.

**Required status check:** decided by the owner 2 Nov 2026: not now, revisit at launch (§5.1).

**Daily publishing is off until launch** *(owner's decision, 2 Nov 2026, PR #77)*: the workflow is merged but **disabled** (`gh workflow disable "Daily brief"`) right after the merge, so no brief is built or published yet. It is enabled at launch, after #27 (fonts), #68 (privacy check), #25 (design review), **the six design-review changes #81–#86** (§7.8; native "blocked by" links on #26, owner 2 Nov 2026) and the MeteoAlarm permission (§11). Still open on #26 until then: enable the workflow, the manual test run (acceptance), and the required-check decision.

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
  places.py            the AI's place id + tags -> items[].map, affects, unlisted; nothing off the lists gets through (§5.10)
  summarise.py         summariser: one Claude call per kept item, structured output, checks; unrated on any bad answer (§5.5)
  compare.py           Haiku 5.5 vs Sonnet 5.5 on the same kept items, side by side, run by hand (§5.5, #17)
  weather.py           weather status: KNMI warnings for Zuid-Holland via MeteoAlarm -> one status reading (§5.11)
  rhine.py             Rhine status: Kaub reading shown (thresholds from config/rhine.toml), Lobith reading stored only (§5.12)
  strike.py            strike flag: worst level over the strikes in kept items (14 days, dated ones up to 60), deciding item(s) linked (§5.7)
  run.py               the morning pipeline: collect → filter → summarise → status → brief, today's three files written once; AI outage → nothing written, or a reduced brief on the last trigger (§5.13)
  guard.py             first step of the daily job: build today or stop (too early / brief already there), last trigger or not (§5.1.1, §5.1.2)
  publish.py           commits only new data/ files (one new brief) to main as github-actions[bot], pull --rebase, one retry (§5.1, §5.1.2)
  (ais.py — to build)
config/
  sources.toml         every source in SOURCES.md: verdict, URLs, access, language, auto-keep
  filter.toml          off-topic word lists per language (§5.4), small starter lists (football)
  places.toml          the fixed place list: 41 places, coordinates + OSM element id (§5.10)
  tags.toml            the fixed "affects" tags: 16 cargo/mode tags, each with a one-line meaning (§5.10)
  rhine.toml           the Kaub thresholds in cm, each with its public source in a comment, and what each level means ([kaub.meaning], #83) (§2.2, §5.12, §7.5)
tests/                 pytest; run with `python -m pytest` (settings in pytest.ini). conftest.py: no API keys, no internet in any test
.github/workflows/
  daily.yml            the morning job: guard → run → commit data/ to main → pages.yml (§5.1.2)
  pages.yml            render the latest main + deploy, on every push to main, by hand, and from daily.yml
  tests.yml            run all tests on every pull request and push to main; no secrets
.github/rulesets/
  main.json            the ruleset on main: no force-push, no deletion (§5.1, §5.1.2)
templates/             base.html, day.html, archive.html, about.html, _macros.html
static/
  style.css            the whole design (tokens at the top)
  map.js               the chart (Leaflet + custom canvas basemap)
  basemap.js           generated: land, detail, labels (window.HAVEN_BASEMAP)
  site.js              adds the "js" class to <html>
  favicon.svg
  fonts/               IBM Plex woff2 files + OFL.txt, self-hosted (§7.3, #27)
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
- `sources.toml` lists **news sources only**. The status-line endpoints (MeteoAlarm, PEGELONLINE, Rijkswaterstaat) are a different kind of source (no use/headline-only verdict, no items) and get their config when the status step is built. *(As built: their URLs are constants in `weather.py` / `rhine.py`; only the Rhine thresholds are config, `config/rhine.toml`, #20.)*
- **Dropped sources are listed** with a one-line `note` (why), for the record; they need no URL, access type or language and are never fetched.
- **`why`** *(added 2 Nov 2026, issue #24; Claude's proposal, confirmed by the owner 2 Nov 2026, PR #76)*: **one public line** shown on the Method page, saying why a source is headline-only or dropped, or how a `use` source is limited (K+N: Rotterdam paragraph only). The config check refuses an empty or multi-line `why`; `tests/test_repo_config.py` requires it for every headline-only and dropped source. **`note` stays for people reading the file and is never shown.**
- **`home`** *(owner's decision, 2 Nov 2026, PR #76)*: the source's **normal public page** (its website), which its name links to on the Method page; the first of its `urls` (what the job reads) follows as a small link, **"(feed)" for an RSS/Atom source and "(page)" for one read as a web page** (`access`, owner, 2 Nov 2026, PR #76). Required for every fetched source and never the same as a read URL (`tests/test_repo_config.py`); the config check refuses anything but one web address.
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
- **The unrated card says why it is empty**: *"Headline only. The AI step failed for this item, so there is no summary, impact or severity. Read the original for the details."* *(Since #82: the short card's line "Headline only (the AI step failed for this item) · no summary, impact or severity", §7.5.)* No impact block at all (so no "Not enough information", which is only for a rated item with `impact: null`).
- **A ship at the terminal of an unrated item still counts as linked**, but keeps its normal teal hull (like a low item); its popup button gets a grey edge.
- **A reduced brief with no items** says *"Without the AI step only items from the Rotterdam-specific sources can be shown, and they had nothing new"* instead of "nothing met the bar", which would be untrue when the filter never ran.
- The **Method page** lists Unrated under the severity rules and explains the reduced brief in two sentences.

*Real briefs on the day page (built 2 Nov 2026, issue #23).* The renderer now takes a brief written by the runner (§5.13) as it is: a status reading with `source_url: null` no longer crashes it (its source is shown as plain text). Tests in `tests/test_render_real.py`, including a brief written by `haven.run` (normal and reduced).
- **Weather dial** (MeteoAlarm requirements, §2.2): "KNMI: Code yellow · Wind → Watch" (`weather_mapping()`), "Issued 05:12" (`issue_time()`, Amsterdam time), "Read at", "KNMI via MeteoAlarm ↗" linking to www.meteoalarm.org, the note "Warnings at 06:46 · not live", and MeteoAlarm's disclaimer verbatim (test asserts the exact text).
- **Strike dial** (§5.7 point 6): the reading's value text as it is, then each linked item: role, headline linked to the original ↗, "NL Times · 2 Nov" (`strike_link()`).
- **Rhine**: the Kaub gauge as before, with the change since yesterday.
- **Headline-only items**: "rated from headline only" next to the severity tag; impact "Not enough information". *(Replaced by the short card in #82, §7.5: one grey line, no impact block.)*
- **Ships dial in v1**: "No data · Ship positions are not collected yet" (`AIS_SNAPSHOT_BUILT = False` in `render.py`; #31 sets it to `True`, and from then on a missing snapshot reads "The AIS snapshot failed" again).
- **"How this brief was made"**: sources checked, items collected, kept, shown, summaries in the batch / by the fallback (`build.summaries`), failures per source, correction notes.

*Proposed by Claude, all ten confirmed by the owner 2 Nov 2026 (issue #23, PR #75):*
1. **"Since yesterday" only against the brief of the day before.** After a missing day the dial says "No reading yesterday" instead of comparing with an older brief and calling it yesterday.
2. **An item from an earlier day links to its card on that day page** ("In the 30 Oct brief" → `days/2026-10-30.html#item-3`) **only if that day's page shows it** (among its 5 shown items, matched by URL). Otherwise only the original article is linked: a day page that doesn't show the item would confuse the reader. (Answers the "Note for #23" in §5.7 point 10.)
3. **Role labels on the strike line:** the deciding item has none; an `unsure` cancellation is "Possibly called off" (the §5.7 example); any other `unsure` item is "Possibly the same strike"; the named strike next to a higher unsure item is "Possibly the same as". The item's date is its `published` date (Amsterdam), else its collection day. The strike dial lists these items **instead of** one source link.
4. **"rated from headline only" is shown for every rated item with no summary**, not only `access: "headline-only"`: a `use` item whose article couldn't be read is rated from its headline too (§5.5 point 2). Its card says "Headline only: the article couldn't be read, so there is no summary." (was "No summary available."). *(Since #82: "Headline only (the article couldn't be read) · severity rated from the headline", the short card, §7.5.)*
5. **KNMI's level with no warnings** reads "KNMI: Code green → Normal"; on No data there is no mapping line, but the meteoalarm.org link and the disclaimer stay.
6. **An item's time is Amsterdam time, with the date when it isn't the brief's day** ("19 Nov 17:20"): real items can be up to 48 h old, and "17:20" alone would read as this morning. A date-only `published` shows the date ("19 Nov"); a zone-less one is read as Amsterdam time (as the filter does, §5.4); a missing or unreadable one shows nothing.
7. **Several failure lines from one source are grouped under its name**, sources in the order they first appear.
8. **The chart legend leaves out the ship symbols when a day has no ships**, and the chart says "No ship positions: ships are not collected yet." *(Since #81, 2 Nov 2026: no box on the chart in v1; the legend line under the chart says "Ship positions are not collected yet." in grey, §7.4.)*
9. **The four sample briefs use the real weather and strike reading shapes** (§5.11, §5.7), so the sample site shows the MeteoAlarm requirements and a linked strike item (29 Oct: "Strike today · Maasvlakte"; 27 Oct: KNMI yellow fog issued the evening before).

*The Method page (built 2 Nov 2026, issue #24).* `templates/about.html`, rewritten for the real pipeline: what this is; how a brief is made (collect → filter → summarise → status → publish, automatic, "Nobody checks a brief before it goes online", corrections afterwards); severity rules (Low incl. "already over" and the forced Low for ended PIN notices; "rated from headline only" (since #82 "severity rated from the headline"); Unrated; the reduced brief); the status thresholds with their sources; weather warnings (all MeteoAlarm requirements, disclaimer verbatim); how the strike flag works (§5.7, 14 days, not today's items); the AI models; sources; copyright and article text (hard rules 2, 3, 12, 13); the chart; credits (§12); who makes this. What lives in config or code comes from `render.method_page(sources, rhine)`, so the page can't drift: **the source list from `config/sources.toml`**, grouped by verdict, each name linking the source's public page (`home`) followed by a "(feed)" or "(page)" link to what the job reads, with a "how it's used" line built from verdict + `auto_keep` and the public `why` (§5.2.1); **the Kaub numbers from `config/rhine.toml`** (Normal = watch + 1 to watch_above); **the model names from `filter.AI_MODEL`, `summarise.SUMMARY_MODEL` / `FALLBACK_MODEL`** and the batch wait from `BATCH_WAIT`. Tests: `tests/test_method_page.py` (footer exact on every page, disclaimer verbatim, every use/headline-only source from config listed, a changed config changes the page, every threshold row links its source, nothing official or reviewed).

*Proposed by Claude; 1, 2 and 4–9 confirmed by the owner 2 Nov 2026 (PR #76), 3 changed by the owner:*
1. **A public `why` field in `sources.toml`** (§5.2.1) instead of showing `note`: the notes hold internal details ("the /en/rss.xml feed is stale"), and hand-writing the reasons in the template would be the hand-copied list the issue forbids.
2. **Dropped sources are listed too**, under "Not used", each with its `why`: it shows that sources were tested and turned down for their terms, which is part of the story. No link for them.
3. **Each source's name links to its normal public page** (`home`, §5.2.1), followed by a small link to **the feed or page the job actually reads** (its first URL): **"(feed)" for RSS/Atom sources, "(page)" for sources read as a web page**. *(Changed by the owner, 2 Nov 2026, PR #76: Claude had proposed linking only the address the job reads, so a reader clicking an RSS link would see XML. The ten home pages answered HTTP 200 on 2 Nov 2026.)*
4. **Threshold sources:** low water links Contargo's and Maersk's surcharge pages ("read 2 Nov 2026"); high water links PEGELONLINE's Kaub record with its characteristic values (Marke I 460, HSW/Marke II 640; link checked 2 Nov 2026). The links are constants in `render.py` (`RHINE_LOW_SOURCES`, `PEGELONLINE_KAUB_URL`), the numbers stay in `rhine.toml`. Weather links MeteoAlarm; the strike row says "Kept items of the last 14 days" and links the strike section on the same page.
5. **The AI models are named from the code**, through `render.MODEL_NAMES`; a model id missing from it **stops the build**, so switching a model can't leave the page naming the old one. The page also says the AI calls are kept under €5 a month.
6. **No ship positions in v1:** the "Collect" step no longer mentions them, and the chart section says "Ship positions are not collected yet" plus one line on what v2 will add. The full AIS text (seagoing cargo only, snapshot not live, messy destinations) returns when #31 sets `AIS_SNAPSHOT_BUILT`.
7. **"Nothing suggests it is official or reviewed" is tested** as: none of the words official, officially, reviewed, approved, verified, endorsed, partner on the page ("unofficial" is fine), the sentence "Nobody checks a brief before it goes online", "not affiliated with the Port of Rotterdam Authority", and no Port Authority image. (So the high-water source says "gauge marks of WSV", not "official values".)
8. **No GDELT credit**: GDELT is not used in v1 (§4); the credit is added only if it is adopted.
9. **New sections beyond the old page:** "Weather warnings" (moved out of the thresholds), "How the strike flag works", "The AI models" and "Credits". The issue asks for each; separate headings keep them findable.

*Privacy check (2 Nov 2026, issue #68, hard rule 14).* Checked on every page type (Today, day pages, archive, Method), rendered from the sample briefs and from a brief written by the runner: **no cookies, no browser storage, no analytics, no request to another server.** The one outside load there ever was, Google Fonts, was removed by #27 (§7.3); Leaflet is self-hosted, the map is our own canvas basemap (no tile server), and the scripts make no network requests. **Links are not loads:** sources, OpenStreetMap, MeteoAlarm, GitHub and the "Read in English" link through Google Translate only contact those sites when clicked (Google Translate then receives the article's address, which the Method page says). The host is the one thing the site can't switch off: **GitHub Pages logs every visitor's IP address for security** ([GitHub Pages: data collection](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages#data-collection)); the footer and the Method page say so rather than claim more than is true. The live site sets no cookie (response headers checked 2 Nov 2026).
- **Browser check (method):** both test sites served on 127.0.0.1, each page opened in headless Edge with a fresh profile, a Chromium NetLog recording every request, and every host except 127.0.0.1 blocked at the resolver (so Edge's own background traffic can't go out; a page's attempt to reach another server still shows up in the log). Result and numbers in PR #79.
- **The test (`tests/test_privacy.py`, no network):** every rendered page and every file the site ships (HTML, SVG, CSS, JS), plus `templates/` and `static/` themselves, is read and fails on: an outside address (`http(s)://`, `//host`, …) in `src`, `srcset`, `poster`, `data`, `action`, `ping` and the like, or in `href` on anything but `<a>`/`<area>` (stylesheets, preloads, preconnects, icons, `<base>`, SVG `<image>`/`<use>`); an outside `url(...)` or `@import` in CSS, inline styles and `<style>`; an embed (`<iframe>`, `<object>`, `<embed>`, …), even a local one; a `meta` refresh to another site or `set-cookie`; in JavaScript (files and inline scripts), the network and storage APIs (`fetch`, `XMLHttpRequest`, `sendBeacon`, `WebSocket`, `localStorage`, `sessionStorage`, `indexedDB`, `document.cookie`, …) or an outside address that isn't a link target; any known analytics name. The checker is tested on its own on bad and good snippets, so a check that finds nothing can't pass silently. The footer note is checked exactly on every page; the Method page's Privacy section links both GitHub pages.

*Claude's defaults (issue #68), all 7 confirmed by the owner (2 Nov 2026, PR #79):*
1. **Footer wording says GitHub Pages "logs visitors' IP addresses for security"**, not "may log" as in the issue: GitHub's own page says the IP address "is logged and stored for security purposes", so "may" would understate it.
2. **The note is its own line right after the disclaimer**, with one link (GitHub Privacy Statement); the disclaimer text (hard rule 5) is unchanged.
3. **Method page: a "Privacy" section after "Copyright and article text"**, linking GitHub's Pages data-collection note and the Privacy Statement, and saying Google Translate receives the article's address when "Read in English" is clicked.
4. **A new hard rule 14** rather than a line elsewhere, so the rule sits with the others in §3 and CLAUDE.md.
5. **JavaScript is checked by reading it**: banned network/storage APIs and hard-coded outside addresses. A script that builds an address from data at run time can't be caught that way; the HTML check (all data-driven addresses are rendered into the page) and the browser check cover that.
6. **Embeds are refused outright**, even from this site (no `<iframe>`, `<object>`, `<embed>`): none is used, and the issue asks for no embeds.
7. **A list of common analytics names** (Google Analytics/Tag Manager, Plausible, Matomo, Facebook pixel, Hotjar, Clarity, Cloudflare Insights, …) fails the test if any appears in a template, static file or built page, as a second line of defence besides the outside-load check.

### 5.4 Relevance filter (decided 31 Oct 2026)

Question it answers per item: *is this relevant to a logistics planner working with the Port of Rotterdam?* Two stages, cheapest first. Only kept items go on to the summariser.

**Stage 1: rules (free, predictable)**
- Drop duplicates of items already stored in the last ~14 days. **Done once, in the collect step** (`haven/collect.py`, issue #11, §5.8), not again here: the filter only ever sees new links. So the 14-day link check for undated items (below) is already done by the time they reach the filter; #12 needs no second check.
- Drop items published more than ~48 h before the run.
  - **The boundary:** an item exactly 48 h old is still kept; it is dropped only when it is *older* than 48 h. A test covers exactly 48 h. *(Decided by the owner, 1 Nov 2026, issue #12.)*
  - **Items with no readable date** (§5.8): kept only if their link wasn't seen in the last 14 days. *(Decided by the owner, 1 Nov 2026, issue #12.)* *Claude's reading, confirmed by the owner (1 Nov 2026):* "kept" means not dropped for age; the word lists and stage 2 still apply, and the 14-day link check is the same as the duplicate check above.
  - **Items with a date but no time** (Contargo, ECT, §5.8: `published` = `"2026-10-30"`): age counted from the **end of that day** (midnight at the start of the next day, Amsterdam time), so they are never dropped too early. *(Decided by the owner, 1 Nov 2026, issue #12.)*
- **Drop PIN notices that ended more than 12 hours before the run** *(owner's decision, 2 Nov 2026, issue #67)*. A PIN notice's **"End Date" is when the notice itself stops being valid**, not when the measure started or stopped; the Haiku vs Sonnet comparison (#17) showed both models misreading it and Haiku rating ended notices High or Medium. The End Date is read from the `End Date 1 Nov 2026 - 02:47` line of the notice text in memory (the PIN feed gives the whole notice, §5.8), **Amsterdam time**; only the date goes into the reason, never the notice text: `"PIN notice ended more than 12 h ago (End Date 2026-11-01 02:47)"`. A notice that **ended within the last 12 hours is kept** (it still goes to the AI check) **and made Low by the code** in the summariser (§5.5).
  - *Confirmed by the owner, 2 Nov 2026:* **"the run" is when the sources were read** (`feeds_read_at`, as for the 48 h rule); **exactly 12 h is kept**, dropped only when longer ago (a test covers it, as for 48 h); **no readable End Date = this rule doesn't apply** (the other rules and the AI still do); **the code forces Low** on a kept ended notice, not the prompt alone.
  - *Confirmed by the owner, 2 Nov 2026:* **De-activate notices follow the same rule** (their End Date is read the same way).
  - *Proposed by Claude, confirmed by the owner 2 Nov 2026* (`read_end_date` in `haven/filter.py`): the month is an English name or abbreviation ("Nov", "November", "Sep"/"Sept"), the year four digits; **an End Date without a time counts to the end of that day** (like a date-only published date above, so never dropped too early); **an impossible date or time** (31 Nov, 25:10) or a two-digit year is not readable; **two End Dates in one notice: the later one**; **an hour that happens twice or not at all at the clock change is read as the later moment** (tested on 25 Oct and 29 Mar 2026), again so a notice is never dropped too early. The rule only reads PIN notices (`pin-notices`); "End Date" in another source's text is ignored. The comparison's wider age limit (`--max-age-days`) doesn't change the 12 h.
- Drop items matching an off-topic word list (e.g. football, crime unrelated to port operations, housing). The word lists live in the config file so they can be tuned without touching code.
- **Auto-keep** items from the Rotterdam-specific sources listed in §4 (Port Authority news, ECT): they skip stage 2.

**Rules module (`haven/filter.py`, built 1 Nov 2026, issue #12).** `apply_rules(items, sources, config, now)` gives every item one outcome with a reason: **kept** (auto-keep source), **dropped**, or **to the AI check** (stage 2, #13). The rules run in this order and the first that hits gives the reason:
1. older than 48 h → dropped, `"older than 48 h"`;
2. a PIN notice that ended more than 12 h before the run → dropped, `"PIN notice ended more than 12 h ago (End Date <yyyy-mm-dd hh:mm>)"` *(added 2 Nov 2026, issue #67; placed right after the age rule, Claude's proposal confirmed by the owner 2 Nov 2026: PIN is not an auto-keep source, so the place only decides which reason a notice gets when a word would also hit)*;
3. auto-keep source → kept, `"Rotterdam-specific source (auto-keep)"` (the word lists don't apply to it);
4. a word from the off-topic list of the item's language in the headline → dropped, `off-topic word "<word>"`;
5. anything else → to the AI check, `"not decided by the rules: goes to the AI check"`.

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

**Chosen by test, not by guess.** On the first real run (build plan step 6), **Claude Haiku 5.5** (`claude-haiku-5-5`) and **Claude Sonnet 5.5** (`claude-sonnet-5-5`) summarise the same kept items. The owner compares them side by side on: facts match the source, impact is useful (or honestly "Not enough information"), severity follows §2.1. **Haiku 5.5 is the default unless Sonnet 5.5 is clearly better.** The comparison and the choice are written up in `docs/model-comparison.md`. **Chosen: Sonnet 5.5, through the batch** *(owner's decision, 2 Nov 2026, after the comparison below)*; the fallback for items the batch doesn't answer stays Haiku 5.5.

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

**Summariser module (`haven/summarise.py`, built 2 Nov 2026, issue #15).** `summarise(items, client, known, today, model)` makes **one standard-API call per kept item** with **structured output**, then checks the answer in code. The model is a parameter (default Sonnet 5.5 since #17; Haiku 5.5 before), so the side-by-side test (#17) ran the same code; `written_by` records it. The morning job calls it through the batch (next paragraph); `summarise` itself is the standard route.

**The batch (built 2 Nov 2026, issue #16).** `start_batch(...)` sends all kept items as one batch, one request per item (`custom_id` `item-<n>`), each **exactly the request the standard route would send**, and returns at once. `finish_batch(run)` waits until **20 minutes after the batch was sent**, so the runner can do other work in between (v2's AIS snapshot, #31) without adding time; `summarise_batch(...)` does both with nothing in between. The clock and the sleep are parameters, so the tests never really wait.
- **The Haiku fallback is not a refusal fallback.** An item the batch **gave no answer for** (not finished at 20 minutes and cancelled, or `expired` / `errored`) goes through the standard API with Haiku 5.5. An item the batch **did answer** is checked exactly like a standard answer: a refusal or bad answer makes it unrated and **no other model is asked** (point 8 below). *(Distinction written down 2 Nov 2026 at the owner's request.)*
- **Batch can't be created** (server error, connection, timeout, bad request): every item goes through the standard API with Haiku 5.5, one failure line `batch not created (<problem>); all items sent to the standard API`. A **rejected key** (401/403) = AI unavailable at once, as for the filter (§5.4). The standard-route outage rule then applies to the fallback calls: with no batch answer at all, the first 3 calls failing = AI unavailable; after at least one batch answer, 3 failures in a row = the rest unrated without calling again.
- **Results**: matched to items by `custom_id`, never by position (the API returns them in any order). Items come back in input order, and new strike ids are given in input order after all answers are in, whichever route each item took (so the ids don't depend on which items the batch finished).
- **Counts**: `build.summaries` counts **rated** items by `written_by.api`: `batch` vs `fallback` (= `standard`). Unrated items count in neither. `SummaryResult` also keeps the batch's tokens apart (`batch_input_tokens`, `batch_output_tokens`) from the total, for the week-one cost check.

*Proposed by Claude, all confirmed by the owner 2 Nov 2026 (issue #16, PR #65):*
1. **After cancelling, wait at most 2 more minutes** for the batch to end: results can only be read once a batch has ended. If it hasn't ended by then, **every** item goes to the Haiku fallback (failure line `batch did not end after cancelling; all items sent to the standard API`). Worst case the items it did finish are paid twice (a few cents on Haiku); the page is never held up. Latest page time: 20 + 2 minutes + the fallback calls.
2. **Check the batch every 30 seconds** (checking costs nothing); a check that fails is ignored and the next one tried, until the deadline.
3. **A slow batch is not a failure**: no failure line when items fall back because of the 20-minute limit or `expired` / `errored` results; `build.summaries` shows it. A failure line only when the batch couldn't be created, didn't end after cancelling, or its results couldn't be read (then every item falls back).
4. **A copied or too-long batch answer gets its one rephrase retry (point 4 below) through the standard API with the batch's own model**, not Haiku: the same model rephrases its own answer, so `written_by` still names the one model whose words are shown (point 8). The item is then `"api": "standard"` and counted under `fallback`. With Sonnet 5.5 as the batch model (chosen in #17), the retry is a Sonnet standard-API call at full price, a few tenths of a cent.
5. **`calls` counts standard-API calls only**; the batch request is one request for all items, not a call per item.
- **What the AI sees:** a `use` item's headline and article text (≤ 6,000 characters, in memory only), its source id, language and publication time, today's date **and the time the sources were read** (Amsterdam, #67), the place list (id, label, kind) and the tag list **with each tag's meaning** (§5.10, #67), and the strikes known from the last 14 days (§5.7). A **headline-only** item sends its **headline alone**, never any text, even if some were in memory (tested). The third-party text is wrapped in `<headline>` / `<article>` / `<known_strikes>` tags and the prompt says it is data, never instructions.
- **What it answers:** `summary` and `impact` (or `null` = "Not enough information") only when it had the article; always `severity`, `place` (one id or `"none"`), `tags` and `strike` (details or `null`; for dates, the **words as written**: `start_phrase`, `end_phrase`). Headline-only items use a schema without `summary` and `impact`.
- **Checks; any failure makes the item unrated** (`severity`, `summary`, `impact`, `written_by` = `null`, no tags, pin or strike) **with a failure line** under "AI summariser", as issue #15 says: unreadable or incomplete JSON; an unknown severity, strike state or match; summary or impact not text, an empty summary; summary or impact too long or copied from the article **even after one retry** (see 4 below); a `same` / `unsure` match that doesn't name a known strike id; a refusal or a cut-off answer. Failure lines name the kind of problem only, never what the AI or the article wrote. Place and tags go through `places.pick` (#14): anything off the lists is dropped and logged as `unlisted`, which doesn't make the item unrated. API outages are handled exactly like the relevance filter's (§5.4: no key, rejected key or the first 3 calls failing = AI unavailable; after one answer, 3 failures in a row = the rest unrated without calling again).
- **Strike dates** *(owner's decisions, 2 Nov 2026)*: the AI **copies the words** that say when a strike starts and ends, exactly as written ("on Thursday", "tomorrow", "5 November"); **the code works out the date** (`resolve_phrase`): "today", "tomorrow" and weekday names against the item's **published date** (Amsterdam), a written-out day and month from the words themselves. **A bad date is left out, never guessed: the strike stays (with no date it shows Watch, §5.7), the item stays rated, and a failure line says which date was left out** (words not in the source, not a short phrase, or the end before the start). **No published date, or vague words** ("next week", "soon"): no date, no failure line, so the strike stays Watch.
- **`known_strikes(days)`** builds the prompt's list from `storage.read_recent("items", before=today, days=14)`; **`brief_item(item, sources)`** gives the §6 item shape (`source` = the source's name, as shown on the page; `unlisted` stays in `data/items/` only).

*Proposed by Claude, all confirmed by the owner 2 Nov 2026, with the change marked (issue #15, PR #64):*
1. **Effort `medium`** (Haiku 5.5's default) for the summariser, `max_tokens` 8,192 (thinking counts toward it; only what is used is paid). The relevance check uses `low` because it is a yes/no question; a summary and a severity call need more care. The client's 30 s timeout and the SDK's 2 retries are shared with the filter.
2. **A `use` item whose article couldn't be read (#11) is rated from its headline alone**, like a headline-only item: severity, place, tags and strike; `summary` and `impact` `null`. The teaser is not sent either. The page (#23) can show "rated from headline only" for any item with a severity but no summary, so no extra field is needed.
3. **Length limits:** summary at most **320 characters**, impact at most **400** (the prompt asks for at most 45 and 50 words; the sample briefs' longest are 172 and 262). Longer = one retry (see 4), then unrated; never cut off mid-sentence. An empty impact counts as `null`.
4. **Own words, checked:** a summary or impact with **10 or more words in a row exactly as in the article** (case and punctuation ignored) is refused: it would put third-party text in the public repo (hard rules 2 and 13). The prompt asks for the summary and impact **entirely in its own words** and says copies are rejected. *(Changed by the owner, 2 Nov 2026: a copied or too long summary or impact (3, 4) gets **one retry**, the same item plus a note asking to rephrase in its own words within the limits; only if the retry also fails is the item unrated, with "(after a retry)" on the failure line. Other bad answers are not retried. Both calls count toward the tokens and the outage rule. Real test, 2 Nov 2026: the same invented item that the first prompt version copied passed on the first call with the stricter prompt.)*
5. **How date words are read** (`resolve_phrase`, `phrase_in`): the words must be in the headline or article word for word (upper/lower case and spacing ignored), at most 80 characters. A written-out date wins over a weekday ("Thursday 5 November" = 5 November). Forms read: "5 November", "5th of November", "November 5", Dutch "5 november", ranges "5 to 7 November" / "5 t/m 7 november" / "5, 6 and 7 November" (start = first day, end = last), "05-11-2026", "5/11" (numbers **day first**), "2026-11-05"; Dutch "vandaag", "vanavond", "morgen", "morgenochtend" too. A year in the words is taken as written; without one, **the year that puts the date nearest the published date** ("5 January" in a 30 December item = next year). A weekday is **the first one after the published date**; **the published day's own weekday is ambiguous** (today or a week later?) and gives no date. **"next Thursday", "last Monday", "volgende donderdag"** count as vague (people read "next" differently). An impossible date ("31 November") gives no date. **The words themselves are not stored**, only the dates (hard rule 13).
6. **New strike ids** are `strike-<run date>-<n>`, n counting from 1 and skipping ids already known; an id the AI sends with `"new"` is ignored. The known-strike list is fixed for the whole run (so it also works for the batch in #16): two items about the same *new* strike on the same morning get two ids, which can only make the flag stay up longer (safe side).
7. **Known strikes:** location and dates from the strike's **newest** item, "first headline" from its **oldest**, oldest strike first; strikes with `affects_rotterdam: false` are listed too, so the AI can match them.
8. **No refusal fallback to another model**: a refusal makes the item unrated (§5.6), and `written_by` always names the one model that wrote it. *(Confirmed by the owner, 2 Nov 2026.)*

**The comparison (issue #17, run 2 Nov 2026; write-up and side-by-side in `docs/model-comparison.md`).** `python -m haven.compare [--dry-run] [--max-age-days N] [--max-items N] [--out FILE]` collects, filters, reads article text in memory and sends **the same kept items** through `summarise` once per model; it writes nothing to `data/`, and its view holds headlines, links and the AI's own words only (hard rule 13). `--dry-run` makes no API call and prints the cost estimate, so the owner can approve it first.
- **Run:** 7-day age limit for the comparison only *(owner's choice, 2 Nov 2026: at 02:20 on a Monday the 48 h rule left only headline-only items, nothing to compare)*, 15 of 23 kept items (10 PIN notices, 3 Contargo, 1 ECT, 1 Port Authority). **Cost: ~$0.155** (filter $0.008, Haiku $0.011, Sonnet $0.136), estimate approved beforehand ≤ $0.34.
- **Result:** facts about equal (2 errors each; both misread a PIN notice's "End Date" at least once). **Severity: Sonnet followed §2.1 on 13 of 14 rated items, Haiku on 7 of 15**: Haiku rated fog and pilot notices that had already ended High 3× and Medium 4×. Tags: Haiku 2 mistakes (*Sea access* as a filler), Sonnet 1 small. Sonnet left 1 quote-heavy item unrated (copy check after the retry). Measured per item: Haiku $0.00076, Sonnet $0.0090 (standard API); **at 12 items/day in batch ≈ $0.14 vs ≈ $1.63 a month** (Sonnet used far fewer output tokens than the $2.90 estimate above assumed).
- **The owner's decision (2 Nov 2026): Sonnet 5.5, through the batch** (checklist #43), as Claude recommended. Set in `SUMMARY_MODEL` in `haven/summarise.py`; `FALLBACK_MODEL` stays Haiku 5.5 (§5.5 step 3). Two prompt fixes that the comparison showed (a meaning per tag; something already ended = Low, and what a PIN "End Date" means) are issue #67, right after #17 in build order, with a Sonnet re-run on **fresh items** (owner, 2 Nov 2026) and PIN notices that ended more than 12 h before the run dropped by the rules (§5.4).

**Prompt fixes after the comparison (built 2 Nov 2026, issue #67).**
- **A one-line meaning for every tag** in `config/tags.toml` (`[[tag]]` with `name` and `meaning`; the meanings written by Claude and confirmed by the owner 2 Nov 2026), sent in the prompt as `- <tag>: <meaning>`, with "each tag only for what its meaning says". *Sea access* says "not work on the quay"; *Hinterland* says it is not for an area named "Hinterland" (as in a PIN notice): the two mistakes of #17.
- **Severity Low also for something already over when the brief is made** (§2.1), in the prompt's Low rule.
- **What a PIN "End Date" means**, in the prompt: when the notice itself stops being valid, not when the measure started or stopped; an "Activate" notice starts the measure and a "De-activate" notice ends it, each at its publication time, so a measure a De-activate notice ended is already over.
- **A kept PIN notice whose End Date is at or before the time the sources were read is made Low by the code** after the answer passes the checks (both routes, batch and standard), whatever the AI rated it *(owner's confirmation, 2 Nov 2026)*. An unrated item stays unrated; nothing else in the answer changes.

*Proposed by Claude, all three confirmed by the owner 2 Nov 2026 (issue #67, PR #69):*
1. **The time the sources were read is a required argument** of `summarise`, `start_batch` and `summarise_batch` (`read_at`, timezone-aware): the runner (#22) passes the collect step's `feeds_read_at`, the same moment as the filter's 48 h and 12 h rules. No default ("now"), so it can't be forgotten, and two runs of the same items send the same request. It is also given to the AI ("The sources were read at 06:45 Amsterdam time on 2026-11-02."), so it can tell what is already over.
2. **The forced Low gives no failure line**: it is a rule, not a problem. The re-run write-up lists the notices it applied to.
3. **A tag's meaning is one line, at most 240 characters**; the config check refuses a tag without one (and the old `affects = [...]` list).

**The re-run (issue #67).** `python -m haven.compare --models sonnet --batch --max-age-days 7 --max-items 15 --skip-links-in docs/model-comparison.md`: one model, **through the batch** (`summarise_batch`, as the morning job), **fresh items only** (any item whose link is already in the #17 write-up is left out before the rules, compared like the duplicate check, `url_key`), and a list of the PIN notices that had ended (dropped by the 12 h rule, or kept and Low by the code). The cost shown counts batch tokens at half price. `--dry-run` prints the estimate first. **Run later** *(owner's decision, 2 Nov 2026)*: on 2 Nov all 10 notices in the PIN feed were already in #17 and no fresh full-text item was under 7 days old, so a re-run then couldn't test the fix. It waits until the PIN feed has new notices and is an item on checklist #43; the cost is stated and approved before it runs, and #67 doesn't wait for it.

*Proposed by Claude, all five confirmed by the owner 2 Nov 2026 (issue #17, PR #66):*
1. **Both models get exactly the same request** (tested), including effort `medium`, the summariser's setting (Sonnet 5.5's own default would be `high`): the comparison is of the models, not of their settings.
2. **Standard API, not the batch**: the batch sends the same request (§5.5), so the answers should be alike, and the result comes in minutes.
3. **A cap on items, taken in config order** (`--max-items`), so the cost has a ceiling before the run.
4. **The age limit is a parameter of the filter** (`max_age`, default 48 h, tested); only `haven.compare` passes another value. The morning job is unchanged.
5. **"Words not in the source"**: numbers and capitalised names in the summary or impact that the headline and article don't contain (words of the place and tag lists ignored). A pointer for the facts check, not a verdict.

### 5.6 When the AI fails (decided 31 Oct 2026)

**One item fails** (bad or unparseable response, refusal, timeout after the Haiku fallback): the item stays in the brief as **unrated**: headline + link, `severity: null`, no summary, no impact, and it is listed in `build.failures`. The other items continue normally. Unrated items sort after all rated ones and count toward the max of 5. *(Sorting rule confirmed by the owner, 31 Oct 2026.)*

**The AI is completely unavailable** (API down, key invalid; the filter or the summariser fails, either one is enough, §5.13; *changed from "both fail" by the owner, 2 Nov 2026, PR #74, so the spec matches the code*):
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
- `start` / `end`: only if the article states them, else `null`. **Never guessed.** *(Built in #15: the AI copies the words, the code works out the date from them and the published date; a bad date is left out, §5.5.)*

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

**Strike flag module (`haven/strike.py`, built 2 Nov 2026, issue #21).** No network, no AI: it reads back the strike details the summariser stored (§5.5) and applies the rules above. `flag_from_items(days, today, sources, ai_unavailable)` is the pure logic over (collection day, records) pairs; `read_strike_flag(today_records, today, observed_at, sources, ai_unavailable)` adds today's records (not stored yet when the runner calls it) to `storage.read_recent("items", before=today, days=60)` and **never raises** (hard rule 9); `reading(flag, observed_at)` gives the §6 `status[]` entry. The runner (#22) passes the collect step's `feeds_read_at` as `observed_at`. Every row of the table above has a test, plus "announced 18 days ahead is still Alert on its day".

- **The reading:** `key` `strike`, `label` "Strike flag", `icon` `megaphone`, `place` "Derived from kept items", `value` (short text, see 9 below), `level` (`green`/`amber`/`red`, `null` = No data), `items` (the linked item(s), see 10), `observed_at`, `source_name` / `source_url` (the first linked item's source name and URL; with nothing linked "Kept items of the last 14 days" and `null`), `note` ("Can't be judged without the AI step." when the AI was unavailable, else `null`).
- **No data** when the AI was unavailable (§5.6; nothing is read), or when the stored items can't be read (a broken file, or a bug of ours), then with one failure line under "Strike flag". Not Normal: Normal could hide a strike.

*Proposed by Claude, all ten and the No data rule above confirmed by the owner 2 Nov 2026 (issue #21, PR #73):*
1. **"The last 14 days" = today + the 14 days before**: the same 14 days the summariser's known-strike list covers (§5.5), so a `same` or `unsure` match always finds its strike in the window. "Up to 60 days back" = the 60 days before today.
2. **Once a strike counts, all its items of the 60 days count.** A strike counts when one of its confident (`new` / `same`) items is in the 14-day window or has a `start` or `end` today or later. Then its newest item is looked for among all its items of the 60 days, so a cancellation collected 16 days ago (no dates of its own, so outside the window by itself) still cancels a strike announced 20 days ago for today (tested). An `unsure` item never makes an old strike count again.
3. **"Newest item"** = latest collection day, then latest `published` time (read as in the filter, §5.4), then later in the day's file.
4. **An item's age for the 2-day rule** = days from its published date (Amsterdam) to today; the collection day when it has no readable date. Published 2 days ago = Alert, 3 days ago = Watch (both tested). "As of" shows that date.
5. **Cases the table doesn't name:**
   - `announced`, start today, no end → **Alert** ("Strike today").
   - `announced`, start **before** today, no end → **read as `ongoing` with no end date** (it has started by its own words; nothing says it has stopped): Alert while the newest item is ≤ 2 days old, then Watch ("Strike since 1 Nov, no newer report").
   - `announced`, only an **end** date, today or later → **Watch** ("Strike announced until 6 Nov"): with no start we can't say today is a strike day. End before today → over.
   - `ongoing` with a `start` after today (an odd answer) → Alert, as the table's "ongoing, end date not yet passed".
6. **"Never drops to Normal by itself" holds inside the 14-day window:** an undated `ongoing` strike with no newer item for 15 days leaves the window and the flag goes back to Normal (tested). Otherwise it could never clear.
7. **`unsure` items, compared with the strike they name** (its level from its confident items):
   - **higher** level → a strike of its own; the status line shows it and, as "possibly the same as", the named strike's newest item;
   - **same or lower** (e.g. a possible cancellation) → the strike stays as it was, and the unsure item is shown next to it ("unsure") **only if it is newer** than the strike's newest confident item: an older one has been overtaken by a confident report (tested);
   - naming a strike that **doesn't count** (outside the window, or not found) → judged on its own: it counts only if it would raise the flag by itself.
8. **Bad stored data never stops the flag:** an item with no `strike_id` counts as a strike of its own (safe side); unreadable `state`, `match` or `affects_rotterdam` → that item is skipped; an unreadable date → no date (so it can't hide a strike as "over"). Each with a failure line naming the item's number and day, never its headline.
9. **The value texts** (location from the deciding item, left out if missing): Alert "Strike today · Maasvlakte", "Strike ongoing · Maasvlakte", "Strike since 1 Nov · …"; Watch "Strike announced for 5 Nov · …", "Strike announced, no date given · …", "Strike announced until 6 Nov · …", "Strike ongoing as of 30 Oct, no newer report · …"; Normal "No active strike", or "Strike called off · …" when a cancellation is linked. Dates as "5 Nov" (no locale). The renderer (#23) can show them as they are.
10. **Linked items** (`items`): the deciding item first, then, for an unsure pair, the other one. Each: `headline`, `url`, `source` (the source's name; its id if unknown), `published`, `day` (collection day), `day_page` (`days/<day>.html`, `null` for today's items), `role` (`decides`, `unsure`, `possibly the same as`), `state`, `match`. **On Normal after a cancellation**, the newest confident cancellation of a Rotterdam strike that still counts is linked, so "called off" can show for up to 14 days after it (longer if the strike was dated further ahead). *Note for #23:* an item is linked to the day page of the day it was collected, but it may not have been among that day's 5 shown items; #23 decides how to link it then. *(#23: the day page is linked, to the item's card, only if it shows the item; §5.3.)*

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
- **POST** *(added 2 Nov 2026, issue #20; Claude's proposal, confirmed by the owner 2 Nov 2026, PR #72)*: `Fetcher.post_json(url, payload)` sends one JSON body, for Rijkswaterstaat's water-level API, which only answers POST queries. robots.txt, the host delay, the timeout and the one retry apply exactly as for a GET (the query only reads data, so sending it twice is harmless). **A redirect is not followed** for a POST but is a failure: whether to send the body again to another address would be a guess.
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
- **Duplicates, once, here:** an item whose link is in `data/items/` of the previous 14 days is not returned; the same link from two sources today counts once. **A stored line with no filter decision doesn't count** (a reduced day, §5.6, §5.13): the item comes back and is checked *(owner's decision, 2 Nov 2026, PR #74)*.
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
- **An article that can't be read** (fetch error, container missing = layout changed) is a failure line; **the item stays, without text**. What the summariser does with a `use` item without text is #15's decision *(#15: rated from its headline alone, §5.5)*.
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

#### 5.10.1 The lists as built (issue #14, 2 Nov 2026)

- **`config/places.toml`**: 41 places (12 terminals, 10 port areas, 5 North Sea anchorages, 1 lock, 2 storm surge barriers, 2 bridges, 9 fairways). Each has an `osm` field naming the OpenStreetMap element its coordinates were taken from (e.g. `way/145614140` = ECT Delta), so anyone can check it on openstreetmap.org. Coordinates were read **once** with an Overpass query on 2 Nov 2026: a node's own position, or the centre Overpass reports for a way or relation. **Exception (#85, 3 Nov 2026):** the Calandkanaal pin is `node/7306819468`, a point on the canal's own centre line (`way/41923863`, `waterway=canal`), between Europoort and the Calandbrug; the way's centre had been 0.12 km from the Europoort pin. A test checks every place lies inside the sheet bbox (§8.1); the loader refuses one outside it.
- **`config/tags.toml`**: 16 tags, each a `[[tag]]` with a `name` and a one-line `meaning` (≤ 240 characters, added 2 Nov 2026, issue #67; meanings confirmed by the owner 2 Nov 2026), sent with the tag in the summariser prompt (§5.5). Any place label is also a valid tag.
- **`haven/places.py` `pick(place, tags)`**: returns `map` (or `null`), `affects` and `unlisted` (left out of the item when nothing was discarded). `config.py` checks both files like the other config (unknown field, duplicate id/label/tag, bad OSM id, outside the sheet → stop with a message).

*Proposed by Claude; confirmed by the owner 2 Nov 2026 (issue #14, PR #59; the `delta-2` id and label on 2 Nov 2026 after the merge):*
1. **Two extra place kinds, `barrier` and `bridge`**, next to the five above: the Maeslantkering and Hartelkering (closed in storms: sea access) and the Botlekbrug and Calandbrug (rail/road bridges whose closures and openings delay trains and trucks) are not locks or fairways. Only one lock is listed (Rozenburgsesluis); the port's main waterways have no sea locks.
2. **The choice of places** and their short labels (e.g. "RWG", "APMT Maasvlakte II"). **Eurogeul** (the deep-water approach channel) has no named area in OSM: its pin is the Eurogeul E13 buoy (`node/1333828109`). **Uniport** stays out (owner). **Rozenburgsesluis** is the OSM lock way named after its canal ("Calandkanaal"): Claude's reading of which lock it is, kept by the owner and checked on the chart in the design review (#25). **Checked 2 Nov 2026 (#25):** the way's own tags say `lock_name=Rozenburgsesluis`, Wikipedia `nl:Rozenburgsesluis`, and link Rijkswaterstaat's chamber record; the pin lies between its lock gates, and the only other lock nearby (Keersluis) is 2.5 km away. The pin is on the right lock.
   - **APM Terminals Rotterdam (Maasvlakte I)** added at the owner's request (41st place). APM Terminals agreed in December 2019 to sell this terminal to Hutchison Ports and kept Maasvlakte II (Freightwaves, 19 Dec 2019); OSM now names its area **"Hutchison Delta 2 Terminal"** (`way/607016850`), and the coordinates are that area's centre. Id `delta-2`, label **"Delta II (ex-APMT Rotterdam)"**, so news using either name finds it *(Claude's proposal, confirmed by the owner 2 Nov 2026)*. Also checked: the address APM gives for Maasvlakte II (Europaweg 910) is the APMT Maasvlakte II area already on the list, so that pin is right.
3. **Label `side`**: `right` unless a neighbour sits close on the right (RWG, APMT Maasvlakte II, Maasvlakte II, Nieuwe Waterweg, Hartelkanaal, Hartelkering, Calandbrug, Rozenburgsesluis are `left`). To be checked on the real chart in the design review (#25). **Checked 2 Nov 2026 (#25, `docs/design-review.md`):** at the home view many pins are 1–30 px apart (a number square is 36 px), so no choice of side keeps neighbouring callouts apart; Europoort and Calandkanaal are on nearly the same point, and Delta II / ECT Delta still touch at the item zoom (11.8). **Decided by the owner (2 Nov 2026, PR #80, built in #85):** keep Europoort and move the **Calandkanaal** pin to a point on the canal itself, chosen from OpenStreetMap; and **merge close pins of the same day into one marker** in `map.js`, so no two visible markers overlap at the home view (checked for every pair of places). The `side` field stays, but matters less (§7.8). **Built 3 Nov 2026 (#85):** see §8.5 "Pins that share a marker"; no place's `side` was changed, because `map.js` now moves a label to the other side when it would run off the chart.
4. **Tags**: the spec's 12 plus **Shortsea**, **Ferries** and **Labour** (strikes and other labour news, the most common High item). **IT systems** added by the owner, 2 Nov 2026 (issue #67): outages or cyberattacks affecting Portbase, terminal or carrier IT systems, and booking or gate systems. A tag may not have the same name as a place.
5. **Matching ignores upper/lower case and spaces around the answer**; the item always gets the list's spelling. Repeated tags count once.
6. **More than 5 tags: the first 5 listed tags are kept**, in the AI's order; listed tags past the fifth are dropped without being logged (they are on the list, so nothing needs adding). Unlisted tags don't use up any of the 5.
7. **The pinned place's label is added as a location tag** at the end when the AI didn't include it and there is room (fewer than 5 tags): this is how "location tags taken automatically from the place list" is read.
8. An answer that is **not text** (a number, say) is logged as unlisted, never crashes the run. `"none"`, an empty answer or no answer = no pin, nothing logged.

### 5.11 Weather status (built 2 Nov 2026, issue #18)

**`haven/weather.py`.** `read_weather(fetcher, read_at)` makes one request (through the polite `Fetcher`, §5.8) to `feeds.meteoalarm.org/api/v1/warnings/feeds-netherlands` and returns one status reading in the §6 `status[]` shape, plus failure lines for `build.failures`. `reading_from_feed(data, read_at)` is the same without the network (tested on feeds we wrote ourselves in the real structure). `python -m haven.weather` reads the live feed once and prints the reading; it writes nothing.

**What the real feed looks like** (checked 2 Nov 2026): ~700 entries, one per warning **version**, per province **and per hazard**, including KNMI's daily **green** ("no warning") entries, published several days ahead. Each entry has an `alert` (`identifier`, `msgType` Alert/Update, `status`, `sent`, `references`) and two `info` blocks (nl-NL, en-GB) with the area (`areaDesc` + `EMMA_ID` geocode), `onset`/`expires` and the parameters `awareness_level` (`"2; yellow; Moderate"`) and `awareness_type` (`"1; Wind"`). **Old versions stay in the feed**: one fog warning appeared six times, each `Update` naming the one before it in `references`.

**Owner's decisions (2 Nov 2026):**
- **A warning that already expired when the feed is read doesn't count** ("valid at any time during the rest of today", §2.2), so a night fog warning that ended at 05:00 doesn't show Watch at 06:45; a warning starting later today does.
- **Zuid-Holland only, for now.** The feed also has KNMI **coastal** warnings for sea areas, among them **Hook of Holland** (`NL802`, the port's sea entrance), which had a yellow wind warning on 2 Nov while Zuid-Holland was green. Not counted; adding it later is one constant (`AREA_CODE`) plus the display naming the area. *Open item (§11).*

**The reading** (`key` `weather`, `label` "Weather warnings", `icon` `wind`, `place` "Zuid-Holland"): `value` (`"Code yellow · Wind"` or `"No warnings"`), `level` (`green`/`amber`/`red`), `knmi_level` (KNMI's own colour) and `hazards` (at the deciding level), `issued_at` (time of issue; `null` when there are no warnings, see 6), `warnings` (every yellow/orange/red warning that counts: level, hazard, onset, expires, issued_at, highest first), `observed_at` (when the feed was read), `source_name` "KNMI via MeteoAlarm", `source_url` www.meteoalarm.org, `note` "Warnings at 06:45 · not live". All times Amsterdam, ISO 8601. **Never the warning text** (headline, description, event name), tested.

**No data** (`value`, `level`, `knmi_level`, `issued_at`, `note` `null`, empty lists) with **one failure line** under "Weather warnings (MeteoAlarm)" when: the fetch fails or robots.txt blocks it, the answer is not JSON or not the warnings feed, **there is no Zuid-Holland entry for today at all**, or a Zuid-Holland warning has an unreadable level, colour, hazard or time.

*Proposed by Claude, confirmed by the owner 2 Nov 2026, with the change marked (issue #18, PR #70):*
1. **Only the newest version of each warning counts**: a version named in another message's `references` (an `Update` replaces it, a `Cancel` withdraws it) is ignored; a `Cancel` itself is never a warning. Only `status` "Actual" counts (not Test, Exercise, …).
2. **Zuid-Holland is matched by its code `NL009` or its name**, so a renamed area is still found.
3. **No Zuid-Holland entry for today = No data, not Normal.** KNMI always publishes green day entries, so an empty answer means the feed or the area changed; Normal would hide that forever (the same reason as the K+N 14-day check, §5.8).
4. **Any unreadable level, hazard or time in a Zuid-Holland entry = No data for the whole reading**, not "skip that entry": a skipped orange warning would show Normal.
5. **Valid during the rest of today** = onset before midnight tonight (Amsterdam) **and** expiry after the moment the feed was read; **expiring exactly at that moment = over**; no expiry = still valid; no onset = from when it became `effective` (else `sent`). A time without a timezone is unreadable.
   - A time without a timezone is unreadable here **on purpose** (MeteoAlarm always gives one), unlike the news filter, which reads such times as Amsterdam time (§5.4).
6. **Several hazards at the deciding level are all named** in the value, in onset order, once each ("Code yellow · Fog, Wind"); the time of issue is that of the **earliest-starting** one. *(Changed by the owner, 2 Nov 2026: **with no warnings there is no time of issue** (`issued_at` `null`); the reading shows only "No warnings" plus the read time. Claude had proposed the newest `sent` among today's green entries, but KNMI issues those days ahead, so it read as stale: "28 Oct" on 2 Nov. Tested.)*
7. **Hazard names as KNMI writes them, first letter capitalised** ("Wind", "Fog", "Snow-ice"), no translation table of our own.
8. **The note uses the real read time**, "Warnings at HH:MM · not live", not a fixed "06:45", so a late retry run says so.
9. **The module is `weather.py`**, one per indicator (Rhine #20 and strike flag #21 get their own); the runner (#22) puts the readings into `data/status/` and the brief.

Live run (2 Nov 2026, 12:47, from a desktop, nothing written): read with no failures; Zuid-Holland green → "No warnings" (before the owner's change to 6, the reading still gave the green entries' issue time, 28 Oct 03:08).

### 5.12 Rhine status (built 2 Nov 2026, issue #20)

**`haven/rhine.py`.** `read_rhine(fetcher, read_at, thresholds=None)` makes one request per gauge through the polite `Fetcher` (§5.8) and returns a `RhineResult`: the **Kaub** reading, the **Lobith** reading and failure lines for `build.failures`. `result.shown` = Kaub only (for the brief's status line), `result.stored` = Kaub and Lobith (for `data/status/`); the runner (#22) uses them. `kaub_from_answer` / `lobith_from_answer` are the same without the network (tested on answers we wrote ourselves in the real structure). `python -m haven.rhine` reads both once and prints the readings; it writes nothing.

- **Kaub thresholds** in `config/rhine.toml` (`[kaub]`: `alert_at_or_below = 80`, `watch_at_or_below = 150`, `watch_above = 460`, `alert_above = 640`, each with its source in a comment), checked by `config.load_rhine()`. **Not read from the API's characteristic values** (§2.2). `kaub_level`: Alert at 80 or below or above 640, Watch at 150 or below or above 460, Normal between (151–460). Every edge tested (79/80/81, 149/150/151, 459/460/461, 639/640/641). **A reading below the record low is a valid Alert** (owner, PR #71; 21 cm tested, 0 and negative too).
- **Kaub request:** GET `…/stations/KAUB/W/currentmeasurement.json` (latest value in cm on the gauge board + its time). **Lobith request:** POST to `OphalenWaarnemingen`, location `lobith.bovenrijn.tolkamer`, water height (`WATHTE`) in surface water (`OW`), `ProcesType` `meting`, period = **the 24 hours before the read time**.
- **The Kaub reading** (§6 shape, as in the sample briefs): `key` `rhine`, `label` "Rhine water level", `icon` `waves`, `value` (whole cm, see 6 below), `unit` `cm`, `place` "Kaub gauge", `level`, `gauge_max` (700, see 7 below), `observed_at` (**the time of the measurement**, Amsterdam; the page shows it as "Read at"), `source_name` "WSV via PEGELONLINE", `source_url` the gauge's PEGELONLINE page, `note` `null`.
- **The Lobith reading** (stored only): `key` `rhine-lobith`, `label` "Rhine water level, Lobith", `value` (cm), `unit` `cm NAP` (Rijkswaterstaat measures against NAP, not a gauge board, so the number is not comparable with Kaub's), `place` "Lobith gauge (Tolkamer)", `observed_at`, `source_name` "Rijkswaterstaat", `source_url` rijkswaterstaatdata.nl/waterdata/. **No `level`**: it has no thresholds and is not shown.
- **No data** (`value`, `observed_at` and Kaub's `level` `null`) **for that reading only**, with one failure line under "Rhine level, Kaub (PEGELONLINE)" or "Rhine level, Lobith (Rijkswaterstaat)", when: the request fails or robots.txt blocks it, the answer is empty or not JSON, or the value or time can't be read. The other reading is unaffected (tested both ways). A bug of ours in either is caught the same way (hard rule 9).

**What the real APIs look like** (checked 2 Nov 2026, ~13:20): Kaub `{"timestamp": "2026-11-02T13:00:00+01:00", "value": 21.0, "stateMnwMhw": "low", "stateNswHsw": "normal"}` (the two states are PEGELONLINE's own classification, not used). Lobith answers one series per `ProcesType`: `meting` (measurement) and `verwachting` (forecast). **Measurements arrive about 3 hours late** (newest 10:10 at 13:20), so a 2-hour window held **only the forecast**, and a window with no measurement at all answers **HTTP 204 with no body**. Neither host has a robots.txt (404 = everything allowed).

*Proposed by Claude, confirmed by the owner 2 Nov 2026, with the changes marked (issue #20, PR #72):*
1. **Kaub: the small `currentmeasurement.json` answer**, not the station answer with characteristic values that `SOURCES.md` listed: since PR #71 no threshold comes from the API, so there is nothing else to read each morning.
2. **A Kaub reading older than 6 hours is No data** (failure line "latest reading is from …, older than 6 h (gauge stuck?)"). The gauge reports every 15 minutes, so 6 hours without a new value means the gauge or the API is stuck; showing a stale number as today's level would be a guess. Exactly 6 h still counts (tested).
3. **Lobith: the newest measurement of the last 24 hours**, never a forecast value, even a newer one (tested). 24 h because of the ~3 h delay above; the stored `observed_at` shows how old it is. The request asks for `meting` only and the code checks it again, plus `WATHTE`, unit `cm` and `NAP`, so a changed answer can't slip in another quantity.
4. **Lobith: only values marked normal** (`Kwaliteitswaardecode` `"00"`, the only code in the live answer) count; anything else is skipped (e.g. RWS's missing-value marker 999999999). Lobith is stored only, so being strict costs little.
5. **Location `lobith.bovenrijn.tolkamer`**, the one tested on 31 Oct (`lobith.bovenrijn.haven` also answers, with slightly different values: 680 vs 693 cm in the 31 Oct test, not read at the same moment).
6. **Whole centimetres are stored as whole numbers** (21, not 21.0). *(Changed by the owner, 2 Nov 2026: **the Kaub value is rounded to whole cm first, half up, and then compared with the thresholds**, so the number shown always matches its level: 150.5 → 151 Normal, 80.5 → 81 Watch, 150.4 → 150 Watch (tested). Half up, not Python's `round()`, which rounds half to even (150.5 → 150). Claude had proposed comparing the unrounded value, which could show "150 cm" next to Normal. Lobith is stored as it comes.)*
7. *(Changed by the owner, 2 Nov 2026: **`gauge_max` = 700 cm**, above Alert 640, so high-water Watch (above 460) and Alert (above 640) are visible on the gauge instead of a full gauge from 300 up. Claude had proposed keeping the samples' 300. **Settled in the design review (owner, 2 Nov 2026, PR #80): `gauge_max` stays 700**, and the gauge gets lines at the Watch and Alert thresholds from `config/rhine.toml` so low readings are read against them (#83, §7.8). The four sample briefs use 700 too (owner, 2 Nov 2026, PR #72). *The lines are built (3 Nov 2026, #83, §7.5 "Status meaning").*)*
8. **A time without a timezone is unreadable**, as in the weather status (§5.11): both APIs always give one.
9. **Thresholds in config are checked**: four whole numbers, strictly in order (80 < 150 < 460 < 640), unknown or missing fields refused, so a typo or a swapped pair can't turn every reading Normal or Alert.
10. **The Lobith link on a reading is Rijkswaterstaat's water-data page**, not Waterinfo: it's only a link for the reader, and we never fetch Waterinfo (robots `Disallow: /`, §4).

Live run (2 Nov 2026, 13:31, from a desktop, nothing written): both read with no failures; Kaub **21 cm → Alert** (measured 13:15), Lobith **669 cm NAP** (measured 10:50).

### 5.13 Pipeline runner (built 2 Nov 2026, issue #22)

**`haven/run.py`.** `python -m haven.run [--last-trigger] [--data-dir DIR]` is what the morning job (#26) runs: steps 1–6 of §5.1, then today's three files (`data/items/`, `data/status/`, `data/briefs/`) **written once**. `run(...)` is the same as a function; every step can be replaced by a fake, so the tests never touch the network or the AI.

**Order:** collect (§5.8) → filter (§5.4, ages counted to `feeds_read_at`) → article text for the **kept** items only → the summariser batch is **sent** (§5.5) → **weather and Rhine are read while the batch runs** → the batch is **collected** (at most 20 minutes after it was sent, Haiku fallback) → strike flag from today's items and the stored days (§5.7) → the three files.

**Exit codes:** `0` brief written (normal or reduced), `1` AI unavailable and nothing written (the run fails, so GitHub notifies the owner and the next trigger retries, §5.6), `2` one of today's files already exists, nothing done.

*Proposed by Claude, all thirteen confirmed by the owner 2 Nov 2026 (issue #22, PR #74):*
1. **"The AI fully unavailable" = either AI step reports it** (relevance check or summariser: no key, key rejected, the first 3 calls failing, §5.4/§5.5). §5.6 says "either fails" (it said "both fail" until the owner changed it to match, 2 Nov 2026): if the relevance check is unavailable, the summariser isn't tried at all (nothing kept by the AI to send it, and the likely cause, the key or the API, is the same), and a summariser that is unavailable after a working filter is an outage too (every kept item would be unrated). **A relevance check that is unavailable stops the run at once**: no article pages, no batch, no status requests. With `--last-trigger` the run goes on to the reduced brief instead.
2. **Weather and Rhine are read during the batch wait**, so they add no time (the 20 minutes count from when the batch was sent, §5.5). Each is read at **its own time** (the weather note says the real read time, §5.11); the strike flag's `observed_at` is `feeds_read_at` (§5.7).
3. **The brief's `items` holds every kept item**, in collection order; the renderer sorts them and shows at most 5 (§5.3), so "kept" and "shown" can differ on the page. `build.items_kept` = how many are in the brief.
4. **`build.items_collected` = new items this morning** (the lines in `data/items/<today>.jsonl`), so the number can be checked against the file; **`build.duplicates`** (new field) = items left out because their link was seen in the last 14 days.
5. **`build.ai_usage`** (new field): calls and tokens per AI step, `{"relevance_check": {calls, input_tokens, output_tokens}, "summariser": {calls, input_tokens, output_tokens, batch_input_tokens, batch_output_tokens}}`, for the week-one cost check (§2), which otherwise only has the Console's total. Not shown on the page.
6. **`data/status/<today>.json` is a list of readings in the §6 `status[]` shape**: weather, Kaub (`rhine`), Lobith (`rhine-lobith`), strike flag. The brief's `status` has the same entries without Lobith.
7. **All or nothing, the brief last** (`storage.write_day`, §6.1): every file is checked before any is written; if writing fails half-way, the files this run created are removed again, so the next trigger can retry the whole day (a leftover items file would otherwise block it and the page would skip a day). Files that were there before are never touched. The brief goes last because its file is what the guard (#26) reads as "today is done".
8. **Any of today's three files already there = stop**, before any request or AI call, exit 2 (`test_second_run_on_the_same_day_fails_cleanly_and_changes_nothing`). The owner removes or fixes a leftover file by hand.
9. **A step that crashes** (a bug of ours) gives one failure line, `"<step>: unexpected error (<type>)"`, the kind of error only (the traceback goes to the job log, not the public page), and the run goes on with what the step gives on a bad day: collect → no items and **`feeds_read_at` `null`** (so the next PIN gap check doesn't trust a read that didn't happen); filter → nothing kept; article text → items without text (rated from the headline, §5.5); summariser → the kept items unrated, **not** an AI outage; weather / Rhine → No data. The step names: "Collect step", "Relevance filter", "Article text", "AI summariser", "Weather warnings (MeteoAlarm)", "Rhine level", "Strike flag".
10. **The reduced brief** keeps the AI step's own `"AI unavailable: …"` failure line (no extra line: the page already shows the §5.6 note). In `data/items/` the shown items are stored unrated; items the AI check never decided are stored without a `filter`, and come back the next morning (below).
11. **`ships: null`** in every v1 brief (the AIS snapshot is v2, #31; the page's Ships dial is #23's).
12. **The summariser's known strikes** are read day by day from the 14 stored days; a broken day is skipped (the duplicate check already reports it, §5.8).
13. **`--data-dir`** points the run at another folder, for a hand run that must not touch the repo's `data/`.

**Items the AI check never decided come back** *(owner's decision, 2 Nov 2026, PR #74)*: on a reduced day they are stored without a `filter`, so the **duplicate check (§5.8) doesn't count a stored line with no filter decision** as seen; the next run collects the item again and checks it, and the filter's 48 h rule still applies. *Claude's reading, confirmed by the owner 2 Nov 2026 (PR #74):* a `filter` that is `null` or not an object (a hand edit) is no decision either, so that item comes back once, visibly; a later day's decided line for the same link counts as seen as usual.

*Note for #23 (fixed in #23):* the renderer couldn't show a real brief: a strike reading with nothing linked has `source_url: null`, and `render.prepare_indicator` called `.startswith` on it. Now tested on briefs written by the runner (§5.3).

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
      "gauge_max": 700, "observed_at": "2026-10-29T06:15:00+01:00",
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
| `items[].access` | `"headline-only"` for paywalled and AI-opt-out sources: `summary` and `impact` are `null`, severity, place, `affects` and `strike` taken from the headline only, shown as "severity rated from the headline" on the short card (§2.1, §7.5) |
| `items[].strike` | strike details or `null` (§5.7): `state` `announced`/`ongoing`/`cancelled`, `location`, `affects_rotterdam`, `start`/`end` (dates or `null`, never guessed), `match` `same`/`new`/`unsure`, `strike_id` (assigned by code) |
| `items[].written_by` | which model wrote the summary and via which API: `{"model": "claude-…", "api": "batch" \| "standard"}` (§5.5); `null` for an unrated item |
| `build.items_collected` | new items this morning, the lines of `data/items/<date>.jsonl` (duplicates of the last 14 days not counted, §5.13 point 4) |
| `build.duplicates` | items left out because their link was already seen in the last 14 days (§5.13) |
| `build.items_kept` | items in the brief: every kept item (the page shows at most 5); on a reduced brief the auto-kept ones (§5.13) |
| `build.ai_usage` | calls and tokens per AI step (`relevance_check`, `summariser` with the batch part apart), for the week-one cost check; not shown (§5.13 point 5) |
| `build.feeds_read_at` | when this run started reading the sources (ISO 8601, Amsterdam time), from the collect step (§5.8). The next run passes it to the PIN gap check as `previous_run`. Not shown on the page. *(Issue #11.)* |
| `build.summaries` | how many **rated** items were written in the batch (`written_by.api` = `batch`) vs through the standard API (`fallback`: the Haiku fallback, or a rephrase retry, §5.5 #16); unrated items count in neither |
| `build.ai_unavailable` | `true` only on a **reduced brief** (§5.6): the AI was down until the last trigger, so all items are unrated and the page shows *"The AI step was unavailable this morning: headlines only, no summaries."* `false` otherwise; a missing field counts as `false`. *(Name proposed by Claude, confirmed by the owner 1 Nov 2026, PR #50.)* |
| `items[].map.side` | `"left"` puts the label left of the number where the right is crowded |
| `ships` | `null` when the AIS snapshot failed (page says so); always `null` in v1, where the page says ship positions are not collected yet (#23) |
| `vessels[].type` | `container` / `tanker` / `bulk` only |
| `vessels[].status` | `underway` / `moored` / `anchored` |
| `vessels[].destination_raw` | as typed on board (`"NL RTM"`, `"ANTWERP>HAMBURG"`, blank) |
| `vessels[].destination` | cleaned, `null` = Unknown |
| `vessels[].news_item` | rank of the item about this ship's terminal |

### 6.1 Stored raw data (decided 31 Oct 2026)

Next to the brief, the pipeline keeps the raw material, so nothing it saw is lost:

| File | Contents |
|---|---|
| `data/items/YYYY-MM-DD.jsonl` | **JSON Lines**: one line per item collected that morning, kept *and* dropped, with its filter decision (`"filter": {kept, stage, reason}`, §5.4). Collected fields (§5.8, issue #9; confirmed by the owner 1 Nov 2026, PR #53): `source` (id), `headline`, `url`, `published`, `language`, `access`. The HTML lists (issue #10) give the same fields; `published` is a timestamp, a date only (`"2026-10-30"`) when the page gives no time, or `null`. The collect step (issue #11) adds no further fields; the relevance filter adds `filter` (§5.4; `{kept, stage, reason}`, set by the rules for items they keep or drop, issue #12, and by the AI check for the rest, #13) and the summariser adds `severity`, `summary`, `impact`, `affects`, `map`, `strike`, `written_by`, and `unlisted` only when something was discarded (§5.5, §5.7, §5.10; issue #15; an unrated item has them as `null` / `[]`). Never `snippet` or `article_text` (in memory only, hard rule 13). |
| `data/status/YYYY-MM-DD.json` | Every status reading taken that morning (value, level, observed time, source), including failed readings as `null`. *As built (#22):* a list of readings in the §6 `status[]` shape: weather, Kaub, Lobith, strike flag (§5.13). |

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
- **`write_day(day, {kind: data})`** *(added 2 Nov 2026, issue #22)*: one day's files all or nothing, the brief last; nothing written if any of them exists; files created by a call that then fails are removed again (§5.13 point 7).

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

### 7.3 Typography — IBM Plex (self-hosted in `static/fonts/`, #27)

| Role | Font |
|---|---|
| Body text, UI, panel date ("Thursday"), section titles | IBM Plex Sans (400–700) |
| Headlines, big readings (94 cm, 40), callout labels, ship names, city label | IBM Plex Sans Condensed (500–700) |
| Kickers, severity tags, table headers, brand name, timestamps, AIS text, land place names on the map, the date line | IBM Plex Mono (400–600), uppercase + letter-spacing for labels |
| **Planner impact only** (+ water names in italic on the map) | IBM Plex Serif |

Principle: **fact vs interpretation in two typefaces** — the impact is the only serif text, with a rose label "IMPACT FOR PLANNERS *interpretation*". Max weight 700.

**Self-hosted, no Google Fonts** *(#27, 2 Nov 2026)*: the font files sit in `static/fonts/` and `style.css` loads them with `@font-face` rules, so a page never asks Google for a font and no visitor's IP address is sent to Google (EU privacy; checked again by #68). The pages look exactly as before: headless Edge screenshots before/after are pixel-identical outside the map (the map's texture differs between any two renders, also before the change). `tests/test_fonts.py` checks: no page, template or static file mentions `fonts.googleapis.com` / `fonts.gstatic.com`; every family, weight and style above has a rule pointing at a real woff2 file; no unused files; the licence ships with the site. *Claude's defaults, all 6 confirmed by the owner (2 Nov 2026, PR #78):*
1. **The exact files Google Fonts served** (downloaded 2 Nov 2026), not IBM's own release, so the letters render the same as before.
2. **Latin and Latin Extended only** (22 files, 452 KB in the repo; a visitor downloads only the files whose letters a page uses). Greek, Cyrillic and Vietnamese are left out: no page shows them today (checked), and such a letter would fall back to Helvetica/Arial.
3. **Plex Sans upright is one variable file** covering weights 400–700, as Google serves it; every other weight/style is its own file.
4. **`font-display: swap` kept** (as the old `&display=swap`): text shows at once in the fallback font and swaps when Plex has loaded.
5. **The SIL Open Font License is in `static/fonts/OFL.txt`** (IBM's licence file, copyright line included), published with the site; the Method page credit links it and says the fonts are served from this site.
6. **No download script:** the files are a one-off copy and don't change; updating them means downloading them again by hand. Where they came from is written in the comment above the rules in `style.css`.

### 7.4 Layout

**Wide screens (≥ 64rem): the "stage"**
- The chart fills the first screen: height `clamp(36rem, 100vh − 5.5rem, 62rem)`. **Except on a day with nothing on the chart** (see "First screen" below).
- **News panel floats over the chart's western side (open North Sea)**: `position:absolute; top/bottom/left: 1rem; width: 25rem`, background `rgba(21,19,17,.95)` (no backdrop blur — too slow), 1px rule border, big shadow.
  - Panel head: kicker "MORNING BRIEF · NO. 003" (mono), weekday huge (Plex Sans 700, ~2.9rem), date below (mono), publication line.
  - Panel items list (scrolls inside): numbered square + severity tag + headline (*no "affects" tag since #82*: the first of several tags read like a category). The selected item gets `--surface-2`, an ivory left bar, and **expands to show its 2-line summary** (or, for an item without one, the short card's grey line, #82).
  - Panel status: 2×2 mini grid (Weather, Rhine, Strike, Ships) with level icon + value. Severity words, status labels and kicker at 13 px (#82).
  - "↓ Full brief and port status" link.
- Ship filter (All / Container / Tanker / Bulk with counts) top-left of the free chart area; focus box ("1 Terminal strike · 6 ships at this terminal | Overview") top-right; legend bottom-left of free area; controls bottom-right.
- Vignette: `.chart-frame::after` with `box-shadow: inset 0 0 110px 16px rgba(0,0,0,.55)`, z-index 401 (above map, below panels).
- **Below the stage**: two columns — "The brief" (full items) and "Port status" (detailed dials, sticky), then ship table, build notes, day navigation.

**Phones/tablets (< 64rem)**: **panel first** (head, item list, mini status, link) → chart (62vh, 340–560px) → legend → full brief → status. *(Changed by #81, 2 Nov 2026: the chart used to come first and the panel's item list was hidden.)*

**First screen (built 2 Nov 2026, #81; design review M1, M2, S4, §7.8).** The brief comes before the chart, and the chart only takes the first screen when it has something to show.
- **The panel comes before the chart in the page itself** (HTML order), at every width. Phones show it in that order; on wide screens the panel is positioned over the chart, so they look as before. The panel's item list now shows on phones too.
- **Empty chart** = no shown item (of the 5) has a place and the day has no ships (`brief.chart_empty`, `render.prepare_briefs`). The stage gets the class `stage-empty` and the chart becomes a **strip**: phones `30vh` (min 15rem, max 20rem); wide screens: the panel stops floating and sits in a 25rem column **beside** the strip, the strip as tall as the panel (min 18rem), and the panel's item list is left out because the full brief starts right below. Days with pins or ships look as before.
- **Legend line under the chart**, grey: "No item has a place on the chart today." ("on this day" on an older day) on an empty day, and in v1 "Ship positions are not collected yet." on every day without ships. **No box over the port in v1.**
- **From v2 (#31, `AIS_SNAPSHOT_BUILT = True`)** a failed snapshot is still shown on the chart (hard rule 9): "No ship positions for this day. The AIS snapshot failed.", in the chart's **top-left corner** (where the ship filter would be; on wide screens right of the panel), amber edge, never over the Maasvlakte.
- `map.js` is unchanged: the strip opens on the same home views; with the panel not floating, `panelCover()` is 0, so no room is kept for it.
- Tests: `tests/test_first_screen.py`. Screenshots before/after (sample briefs only): `design/screenshots/issue-81/`.

*Claude's defaults (#81), all 7 confirmed by the owner (2 Nov 2026, PR #87):*
1. **An item cut from the 5 shown doesn't count** as a pin, and **a day with ships but no pins keeps the full chart** (the ships are something to show).
2. **Strip sizes**: phone `30vh`, min 15rem (240 px: room for the whole-port and zoom buttons, the scale and the credit), max 20rem; wide screens as tall as the panel beside it, min 18rem.
3. **Wide screens, empty day: panel beside the strip, without its item list.** With the list the panel is ~800 px tall and the chart beside it would be full height again; without it the strip is ~360 px and the first full card is on a 1440 × 900 laptop's first screen.
4. **The empty-chart line is shown on a day with no items too** (it stays true), next to "Nothing significant today" in the panel.
5. **The v1 line reads "Ship positions are not collected yet."**, the same words as the ships dial, instead of the review's "Ships: from v2": version names are internal words, which #84 removes from the public pages.
6. **The v2 note keeps its amber edge** (it is a real failure) but is smaller (13 px) and in the corner.
7. **The brief's intro now says "Show on chart" moves the chart "above the brief"** (was "at the top of the page", no longer true on phones); when the sentence shows at all is #82 (S10).

**Top bar**: signal-flag logo + "HAVEN DAILY" (mono) + "Thu 29 Oct · No. 003"; nav Today / Archive / Method (active = 3px underline). Sample-data note below in amber.

### 7.5 Components

- **Numbered square** (`.num`): same square in panel, full list, chart and archive strip → the chart works as the index of the brief. High = red with white number, medium = amber with dark number, low = slate, **unrated = outlined, no fill, grey `--nodata-ink` number** (§5.3).
- On the chart the high-severity square has a soft "ping" ring animation (transform/opacity only).
- **Severity tag**: mono uppercase, coloured ink; "UNRATED" in `--nodata-ink`.
- **Status dial**: label with icon, big condensed value + unit, place, level (icon+word) **followed by its meaning** ("Watch: low-water surcharges on barge transport", #83) + change, note, "Read at 06:20 · Source ↗". River gauge = striped board with water level **and lines at the Watch and Alert thresholds, labelled in cm** (#83).
- **Item card (full brief)**: num + severity + source · language · time; condensed headline (link); summary (sans, max 62ch); divider; impact label + serif impact text (max 62ch); Affects; actions: "Show on chart" (outlined button, needs JS; only for an item with a place, nothing in its stead without one, #82), "Read original (Dutch) ↗", "Read in English ↗".
- **Short card** (#82, below): an item with no summary shows the headline, one grey line saying why, the Affects line and the actions; no impact block.
- **Leaflet controls**: zoom = two separate ivory 32px squares with 6px gap and shadow; above them the **orange "whole port" button** (expand icon; on wide screens also the words **"Whole port"**, #82); scale bar and attribution in the same corner (bottom-right stack, bottom-up: attribution, scale, zoom, home).
- **Ship list header**: a small ▸ before "All N ships in the snapshot" that turns down when the list is open (#82).

**Cards and panel (built 3 Nov 2026, #82; design review S5, S10, S11, M3, §7.8).**
- **Short card (S5)** for every item without a summary, with one grey line (`render.HEADLINE_NOTES`, worked out once in `render.headline_note` and shown on the card and in the panel):
  - headline-only source: *"Headline only (paywalled, or the source's terms don't allow a summary) · severity rated from the headline"* (the owner's wording, PR #80; "paywalled, or" added by the owner, 3 Nov 2026, PR #88, to cover paywalled sources as §2.1 says);
  - `use` item whose article couldn't be read: *"Headline only (the article couldn't be read) · severity rated from the headline"*;
  - unrated (AI failed, §5.6): *"Headline only (the AI step failed for this item) · no summary, impact or severity"*.
  No impact block, no "No single place on the chart". **"Not enough information" stays for a rated item with a summary but no impact** (full card).
- **S10:** the brief's intro sentence *"Show on chart" moves the chart above the brief.* only when at least one **shown** item has a place (`brief.map.callouts`); the ▸ on the ship list; the "Whole port" label.
- **S11:** no "affects" tag in the panel (the card keeps all); panel severity words, status labels and kicker 13 px (were 11–12).
- **M3, one behaviour for every panel entry:** every entry is a `#item-N` link with `data-action="show-item"`. With JavaScript a click opens it in the panel (summary or grey line) and moves the chart **only if the item has a place**; without a place the chart stays where it is, the earlier item's focus box goes away, a screen reader hears "Item N has no place on the chart." and the address gets `#item-N` like any other item. Without JavaScript (or when the chart can't load) the entries stay plain links to the cards.
- Tests: `tests/test_cards_panel.py` (card variants, intro sentence, ship-list marker, label, panel sizes and markup). The click was checked in headless Edge (§8.7) at 1440 and 600 px: an entry with a place starts the chart moving; one without a place opens with its grey line and the chart doesn't change for 8 s afterwards (no map change at all), the page doesn't scroll. Screenshots before/after (sample briefs only): `design/screenshots/issue-82/`.

*Claude's defaults (#82), all 8 confirmed by the owner (3 Nov 2026, PR #88), with one change to the headline-only line above (paywall added):*
1. **The two lines the review didn't word** (article not read, unrated) follow the owner's headline-only line: "Headline only (why) · what that means". The unrated one drops "Read the original for the details": the "Read original" link is right below.
2. **The "rated from headline only" tag next to the severity is gone** where the line says "severity rated from the headline", so it isn't said twice. The Method page now quotes the new words.
3. **"No single place on the chart" is removed from every card**, not only short ones: an item without a place simply has no "Show on chart" button.
4. **The short card is decided by "no summary"**, not by `access`, so a `use` item whose article couldn't be read gets it too (it has nothing to interpret either).
5. **Selecting an item without a place leaves the chart where it is** (it doesn't fly back to the whole port), but takes away the earlier item's focus box, which would otherwise name the wrong item.
6. **"Whole port" shows from 64rem**, the width where the panel floats over the chart; 13 px bold; the button grows to the left. Phones keep the 32 px icon square; its spoken name stays "Show the whole port".
7. **The ▸ is a small SVG triangle**, not a text character, so it looks the same whatever font loads; it turns 90° when the list is open.
8. **All three panel sizes are 13 px** (0.8125rem), the lower end of the review's 13–14 px, so the panel keeps its rhythm; the status values (17 px) are unchanged.
- **Popup** (ship): dark surface, ship name (condensed 700), "Container ship · 350 m · Liberia", facts (Status, Area, Destination + raw AIS text in mono). If linked to news: full-width **peach button** "AT THE TERMINAL IN ITEM 1" with the severity colour as a 4px left border.
- **Accessibility**: skip link, `aria-live` announcer for chart changes, everything on the chart also listed as text, `needs-map` / `no-map` classes so buttons only appear when the chart works, reduced-motion support, focus outlines, 44px touch targets.

**Status meaning (built 3 Nov 2026, #83; design review S6, S7, §7.8).**
- **S6, each value with its meaning.** `render.status_meaning` gives one short line per level, **never written per day**: the **Rhine's from `config/rhine.toml`** (`[kaub.meaning]`, next to the thresholds it describes, checked by `config.load_rhine_meanings`: five one-line texts, none missing or extra), **weather and strike from one constant** (`render.STATUS_MEANINGS`; the strike text names `strike.WINDOW_DAYS`). Shown in the **full dial** after the level word ("Alert: barge transport no longer guaranteed", the meaning in plain ink) and as a **second small line in the panel's mini status** (13 px, grey). **No data shows only "No data"**, with no meaning line. The MeteoAlarm requirements on the weather dial are unchanged (mapping line, time of issue, link, note, disclaimer verbatim; tested).
- **S7, the gauge.** Lines at the four Kaub thresholds from `config/rhine.toml` (`render.gauge_marks`: 80 / 150 / 460 / 640 cm at 11.4 / 21.4 / 65.7 / 91.4 % of **`gauge_max` 700**), **Watch dashed amber, Alert solid red** (shape as well as colour, §2.2), each labelled in cm beside the board; the screen-reader label names the reading and the lines. A changed threshold in config changes both the text chosen and the lines (tested).
- Tests: `tests/test_status_meaning.py`. Screenshots before/after (sample briefs only): `design/screenshots/issue-83/`.

*Claude's defaults (#83), all 9 confirmed by the owner 3 Nov 2026 (PR #89), with the wording changes marked in 1:*
1. **The wording.** Rhine (in `config/rhine.toml`): Normal "no low-water surcharge or high-water restriction at Kaub"; Watch low "low-water surcharges on barge transport"; Alert low "barge transport no longer guaranteed" (the review's words); Watch high "high-water shipping restrictions"; Alert high "high water: shipping stops" (*kept by the owner, 3 Nov 2026, PR #89: 640 cm is Marke II = HSW, the highest navigable level, per PEGELONLINE's values for Kaub checked that day; Marke I is 460 cm*). Weather: Normal "no KNMI warning for Zuid-Holland for the rest of today" (*"for Zuid-Holland" added by the owner, 3 Nov 2026, PR #89*); Watch "weather may slow port operations and road transport today"; Alert "weather likely to disrupt port operations and road transport today". Strike: Normal "no Rotterdam strike today or coming up, in the news of the last 14 days" (*changed by the owner, 3 Nov 2026, PR #89, to say exactly what the window covers: kept news of today and the 14 days before, §5.7 point 1, read for strikes on today, ongoing, or announced for a later day; Claude's first text was "no active Rotterdam strike found in the last 14 days"*); Watch "no strike confirmed for today; check the dates"; Alert "a strike is on today".
2. **Where the texts live:** the Rhine's in `config/rhine.toml` under `[kaub.meaning]` (the issue: "next to the thresholds they describe"); weather and strike in one constant in `render.py`, because their rules are code, not config. The morning pipeline still reads only the numbers (`load_rhine`), so a text change can't break a morning run.
3. **Low or high side is read from the value** (below or above the middle of the Normal band), with the level as stored in the brief. A published level is never recomputed, and a reading stored under older thresholds still gets its side's text.
4. **Normal has a meaning too** (the issue lists Normal); **No data has none, also for the Rhine**.
5. **In the full dial the meaning follows the level word for all three dials, weather included**, on the level line just above "KNMI: Code yellow · Wind → Watch". The issue placed the weather meaning "after" that line; this keeps one place for every dial and leaves the MeteoAlarm mapping line exactly as it was.
6. **The panel shows the meaning without "Watch:"/"Alert:"**: the icon and colour already show the level (and screen readers hear it), and the cells are narrow.
7. **The strike meaning is one per level**, not the issue's "announced for a later date" for Watch: Watch also covers "announced, no date given" and "ongoing as of …, no newer report" (§5.7), where "later date" would be untrue. The value line already says which case it is.
8. **The gauge is taller (3.6 → 7.5 rem, 120 px)** so the 80 and 150 cm labels don't touch on a 0–700 cm scale; the board is a little wider (1.25 rem) with finer marks. A threshold above `gauge_max` would be left out.
9. **The Method page keeps its own threshold wording** (approved in #24, PR #76: longer, with "(Marke I)" / "(Marke II)" and the sources) instead of repeating the short config texts.

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


### 7.8 Design review decisions (#25, decided by the owner 2 Nov 2026, PR #80)

The review (`docs/design-review.md`) found why the site didn't feel user-friendly: on a typical v1 day the chart is empty but takes the first screen, most real items are headline-only shells, nothing says what the site is or who made it, status values have no meaning attached, and internal words show on the page. The owner approved 17 of its 19 proposals, built as six `v1` issues that block launch (in build order; #82 and #85 come after #81):

| Issue | Proposals | What changes |
|---|---|---|
| **#81** First screen | M1, M2, S4 | The chart shrinks to a strip on a day with no placed items and no ships; on phones the brief (head, item list, mini status) comes before the chart; in v1 no amber "No ship positions" box over the port (one grey line under the chart instead; from v2 a failed snapshot is shown off the port). **Built 2 Nov 2026 (§7.4 "First screen").** |
| **#82** Cards and panel | S5, S10, S11, M3 | Short headline-only card (no empty impact block, no "No single place on the chart"); the "Show on chart" sentence only when an item has a place; ▸ on the ship list; "Whole port" label on wide screens; panel text 13–14 px and no tag in the panel; every panel entry opens in the panel. **Built 3 Nov 2026 (§7.5 "Cards and panel").** |
| **#83** Status meaning | S6, S7 | Each status value with a short meaning built from config ("16 cm · Alert: barge transport no longer guaranteed"); Watch/Alert lines on the Rhine gauge; `gauge_max` stays 700 (§5.12). **Built 3 Nov 2026 (§7.5 "Status meaning").** |
| **#84** Plain words, archive legend | S8, S9 | Internal terms replaced on the public pages ("No AIS", batch/fallback, "Derived from kept items", the gap-check failure wording; the failure itself is still shown, hard rule 9); a legend line on the archive and text labels for its icons on phones. |
| **#85** Map pins | M4 (b), M5 | Calandkanaal moved to a point on the canal from OSM (Europoort stays); close pins of the same day merge into one marker so no two visible markers overlap at the home view; the home view always includes the day's pins (none under the panel or off the phone's view). **Built 3 Nov 2026 (§8.1 "Home view", §8.5 "Pins that share a marker").** |
| **#86** What, who, links | S1, S2, S3, L2 | The one-liner and About text below; LinkedIn and repository links; "Method" renamed "How it works", with a contents list and "Who makes this" second. **Built 3 Nov 2026 (below).** |

**The owner's texts, to be used exactly:**
- One line under the brand on every page: *"What affects the Port of Rotterdam today, and what it means for logistics planners. Updated every morning."*
- About text (Today page and "How it works"): *"Haven Daily is an independent portfolio project by Leonardo Neirotti, an International Business student at Rotterdam University of Applied Sciences. Every morning an automated pipeline reads public sources, uses AI to filter and summarise what matters for logistics planners, and publishes this brief. It is not affiliated with the Port of Rotterdam Authority or any company named here."*
- Links: LinkedIn `https://www.linkedin.com/in/leonardo-neirotti`, repository `https://github.com/leonardoneirotti/haven-daily` (#86 sets them; #28 later moves them into its site config with the base URL).

*Built 3 Nov 2026 (#86).* The two texts and the two links live once, in `SITE` in `haven/render.py` (`tagline`, `about`, `linkedin_url`, `repo_url`); `tests/test_who_and_links.py` checks the texts exactly on every page. The nav item, the page title and the footer link say "How it works"; the file stays `about.html`, so old links keep working. *Claude's defaults, not yet confirmed by the owner:*
1. **About block on the Today page only** (`index.html`), right below the brief (items and port status), before the ship list and "How this brief was made"; heading "About this project"; links "Leonardo Neirotti on LinkedIn", "Source code on GitHub", "How it works". Past day pages (`days/…`, including today's) don't repeat it: they have the one-liner, the footer links and "How it works" in the nav.
2. **The one-liner** is its own line under the brand row, above the sample-data note, in the secondary ink colour (`--ink-2`), 14 px. On a phone it takes two lines, so the brief starts ~48 px lower.
3. **"Who makes this" is the About text alone**, replacing the earlier text (which added "second-year BBA … (Supply Chain Management)" and "built with Python and GitHub Actions, with Claude models"; the models are named under "The AI models").
4. **The contents list** is numbered, two columns on wide screens, one entry per section in page order, worded like its heading (tested).
5. **Footer link words:** "How it works" (was "Method and sources") and "Source code on GitHub" (was "Source code").
6. The `<meta name="description">` is unchanged.

**Not in v1:** M6 (news labels on the chart styled apart from place names) → "Later" (§10); L1 (an English line under Dutch headline-only items) → v2 ideas (§9), because it needs a rule decision first.

**Screenshots for these issues:** only sample briefs or briefs with invented headlines are committed; screenshots of real headlines stay off the repo (owner, 2 Nov 2026, hard rule 13).

---

## 8. The chart (how it works — interview material)

### 8.1 Principles

- **No map service at runtime.** The basemap is a file in the repo, Leaflet is self-hosted. No tile server, no API key, no tracking.
- The chart is a fixed **"sheet"** (the basemap's bounding box): `maxBounds` = sheet (on wide screens extended west past the sheet by the panel's width, #85: see "Home view" below), `maxBoundsViscosity: 1`, min zoom = smallest zoom that stays inside the sheet. Max zoom 15. `zoomSnap: 0`, `zoomDelta: 0.5`. **Scroll-wheel zoom off** (page scrolls past the chart; zoom with buttons, pinch, double-click).
- **Sheet bbox** (south, west, north, east) = **(51.74, 3.40, 52.16, 4.62)**: from the North Sea anchorages to Rotterdam city, extended far west so the **news panel only ever covers open sea**.
- Home views: wide screens `view_home` = (51.845, 3.76, 52.07, 4.58) fitted into the space **right of the panel** (padding-left = panel width + 48px, top 72, right 72, bottom 64). Phones `view_compact` = (51.84, 3.74, 52.08, 4.26) (western port).
- **Home view with the day's pins (#85, M5, built 3 Nov 2026).** The normal home view is used when every pin is on the chart and right of the panel; a pin close to the chart's edge counts, because its marker is nudged inward so the whole number shows (§8.5 "Edges"; owner, 3 Nov 2026, PR #91). Otherwise the view is **moved, and zoomed out if needed, just enough** to bring the pins in (smallest move, so as much of the port as possible stays on screen). The chart never zooms out past the sheet, so this has limits, measured in headless Edge:
  - **Laptop:** at the smallest zoom the sheet fills the chart's width and the panel covers everything west of ~3.80° E, so the outer anchorages (3.50–3.76° E) could never sit right of the panel. West of the sheet there is only open sea, so on wide screens `maxBounds` reaches past the sheet's west edge by the panel's width (+ 48 px) at the smallest zoom; there the chart is plain water. Even so, an outer anchorage and the city end of the port (Botlekbrug to Waalhaven) can't sit right of the panel together; then the home view shows **as many pins as fit, most severe item first**, as on phones. *Limit accepted by the owner, 3 Nov 2026 (PR #91); measurements in §8.5 "Phone and laptop limit".*
  - **Phone:** the sheet's height sets the smallest zoom, at which a 390 px chart shows only ~0.51° of longitude, about the normal phone view. An anchorage and the city side (Botlek to Waalhaven) can't be on screen together. Then the home view shows **as many pins as fit, most severe item first** (item 1 always). *Limit accepted by the owner, 3 Nov 2026 (PR #91); measurements in §8.5 "Phone and laptop limit".*
  - The view is worked out before the chart moves, with Leaflet's own `_getBoundsCenterZoom` and `_limitCenter` (internal, stable in the self-hosted 1.9.4), so trying views never repaints the basemap. Decision 6 in §8.5, with its safeguard test.

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
- Panel entries are real links (`href="#item-N"`) → work without JavaScript; with JS, `preventDefault` and select. **Every entry, with or without a place** (#82): an item without a place opens in the panel and the chart doesn't move (§7.5 "Cards and panel").
- Ship filter buttons; "N at anchor" / "N under way" fly to those ships; ship names in the table find the ship and open its popup; orange button / "Overview" return home.
- Hovering an item (panel or brief) enlarges its number on the chart.

#### Pins that share a marker (#85, M4 option b, built 3 Nov 2026)

- After every move or zoom, `map.js` works out each item's marker box (number + label) from sizes measured once in a hidden copy (measured again when the fonts have loaded). **While two boxes overlap (4 px gap kept), they merge into one marker**, and the check runs again; zooming in splits them as soon as they have room. So no two visible markers overlap at any zoom.
- **A shared marker:** the numbers side by side, the first (lowest) item's number on its place, then the places on one line: "3 4 Delta II (ex-APMT Rotterdam) · ECT Delta". Two items at the same place: "2 4 Europoort". **Too wide for the chart** (phones): one row per place, "1 Europoort" / "2 Calandkanaal" …, running down from the first.
- **Label side:** the place's `side` from `config/places.toml`; the other side when the label would run off the chart or under the panel; for a shared marker then rows; if nothing fits, the narrowest.
- **Edges (owner, 3 Nov 2026, PR #91):** a marker whose place is on the chart but whose box sticks out of it moves inward just enough to stay 4 px from the edge, so no number is cut (e.g. 5 East Anchorage on a phone: 12 px below the top edge, the sheet can't move further north). A place off the chart or under the panel is not pulled into view. **The home view uses the same rule** (`onChart`): a pin counts as on screen when its place is on the chart and right of the panel, even closer than half a number to the edge. Before (an 18 px margin) the phone home view dropped 5 East Anchorage, 12 px below the top edge, from 10 pairs that fit on screen (owner, 3 Nov 2026, PR #91). The box geometry (`boxAt`, `overlaps`, `onChart`, `nudgeInside`) is in `static/pins.js`, pure and without Leaflet, so `tests/test_pins_geometry.py` runs it in Node (skipped where Node isn't installed).
- **Phone and laptop limit (accepted by the owner, 3 Nov 2026, PR #91).** On a phone the home view shows as many pins as fit, most severe first, because the sheet's height sets the smallest zoom (§8.1 "Home view"). Measured for every pair of places on the phone (390 × 844, with the `onChart` rule): no overlaps, lost items or cut labels; in **129 of 820 pairs** item 2 doesn't fit next to item 1 (item 1 is never left out), most often an outer anchorage, Eurogeul or Oude Maas with a place far from it. The item left out is one tap away: its entry is in the news list on the phone's first screen, above the chart, and tapping it (or "Show on chart" on its card) scrolls to the chart and flies to it. Not done: zooming out further (the view would run past the sheet's north and south edges, which are land, so either a larger basemap, about twice `basemap.js`, or empty bands) or a shorter phone chart (about 260 px to fix most pairs, a smaller chart every day). **Laptop** (1440 × 900, every pair, same rule, accepted the same day): no overlaps, lost items or cut labels; in **17 of 820 pairs** item 2 doesn't fit next to item 1 (item 1 is never left out). All 17 are an outer anchorage (3 East, 4 West or 5 East) with the city end of the port (RST, Vondelingenplaat, Pernis, Eemhaven, Waalhaven, Botlekbrug, Nieuwe Maas or Oude Maas): the chart right of the panel can't show both even past the sheet's west edge. On a laptop the item left out is in the news panel beside the chart, always visible; clicking it flies there. Results: PR #91 comments. A hint for an item off the chart is a later idea (#92, phones).
- **Picking and screen readers:** every number is its own `<button>` (`data-action="show-item"`, name "Item 4, ECT Delta: <headline>"), so each item in a shared marker can be picked by mouse, touch or keyboard; a shared marker is a `role="group"` named "Items 3 and 4 share this marker: Delta II (ex-APMT Rotterdam), ECT Delta". Tab order follows the item numbers. A marker rebuilt by a merge or split keeps the keyboard focus on the same item, and the selected and hovered items are re-applied.
- **Check (not in CI):** `python tools/check_map_pins.py` renders a page and measures the markers at the home view in headless Edge, laptop (1440 × 900) and phone (390 × 844): all 41 places at once, every place alone and every pair (820), for overlaps, numbers off the chart or under the panel, lost items and cut labels. `--places a,b,c` checks one set.

*Proposed by Claude; confirmed by the owner 3 Nov 2026 (PR #91):* (1) the Calandkanaal point (`node/7306819468`); (2) the shared-marker layout and the rows form for phones; (3) labels changing side at run time instead of edits to `side`; (4) the home view's "smallest move" rule and, on phones, "as many pins as fit, most severe first"; (5) letting wide screens pan past the sheet's west edge (open sea) by the panel's width; (6) working out the home view with Leaflet's internal map methods `_getBoundsCenterZoom` and `_limitCenter`, instead of moving the chart to try each view (which would repaint the basemap; §8.1 "Home view"). **Safeguard for (6):** `tests/test_leaflet_internals.py` fails if the bundled Leaflet (`static/vendor/leaflet/leaflet.js`) is not 1.9.4, if either method is missing, or if `map.js` starts calling another Leaflet internal; its message says to recheck decision 6 before updating Leaflet. *Claude's own, not part of that confirmation:* the place-list test's minimum distance of 1.5 km between the Calandkanaal pin and any other place.

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

**Phone screenshots anyway (used in #23 and #25):** open a small wrapper page that holds the real page in a 390 px wide `<iframe>`, in a 600 px window, then crop the image to 390 px (PowerShell `System.Drawing`; the venv has no Pillow). Add `--allow-file-access-from-files` and load pages as `file://` (screenshots over `http://` can hang). For a whole page, measure its height first (a script in the wrapper reads the footer's bottom through the iframe and `--dump-dom` prints it), make the iframe that tall and capture it in pieces of ≤ 4,000 px by shifting the iframe up (a capture is capped at ~8,200 device px). Note: in a tall iframe `vh` units read as the iframe height, so only the first-screen shots show the exact first screen.

---

## 9. Version 2: ship map with live data (after v1 has run reliably 1–2 weeks)

- **Own daily AIS snapshot** (no embedded MarineTraffic/VesselFinder widget): the morning job listens to the free **aisstream.io** WebSocket for ~10–15 min on a bounding box around the port and saves vessels present.
- **Seagoing cargo ships only** (container, tanker, bulk). No barges, tugs, pilot boats.
- Each day's map stays in the archive.
- Click a ship: name, type, flag, berth/terminal if known, declared AIS destination (cleaned + raw), and a **point-to-point estimated route** (now → next destination) drawn with `searoute`, labelled **"estimated"**; the map zooms out from Rotterdam to show the trip (the orange route line from the reference style fits here).
- Clean messy AIS destinations ("NL RTM", "ANTWERP>HAMBURG", blank) → show "Unknown" when unclear.
- Highlight ships at terminals mentioned in today's news (already designed).
- Optional "see it live" link to the ship on MarineTraffic (link only).
- **Idea, not decided: an English line under Dutch headline-only items** (design review #25, proposal L1). The summariser would add a short English "what the headline says" (≈ 12 words, labelled as an AI translation of the headline). **Not in v1 (owner, 2 Nov 2026, PR #80).** It needs a rule decision first: it sits close to hard rule 2 (no translations of third-party text) and to each source's terms (a new use of their headline), and it changes the summariser's prompt and checks. Until then, Dutch items rely on "Read in English".
- Check aisstream.io terms on public display before launch. aisstream is beta and sometimes unstable: **the page must still build if it fails** ("No ship positions for this day. The AIS snapshot failed.", in the chart's top-left corner, §7.4).

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
- **News labels on the chart that look different from place names** (design review #25, proposal M6: e.g. a dark label box with the severity colour as its edge; basemap names step back under a callout). **Not in v1 (owner, 2 Nov 2026, PR #80):** low-priority polish, to revisit with the new logo.
- **Phone chart: hint when an item is off-screen** (#92): at the phone home view nothing tells the user that an item didn't fit (§8.5 "Phone and laptop limit"). Not part of the launch path (owner, 3 Nov 2026, PR #91).
- **Map style switcher** ("tactical", "sunny satellite", "cartoon" — inspired by the moods of games like Call of Duty / GTA / Fortnite, not copies of their designs). Feasible because all chart colours and paint settings are tokens/constants.

---

## 11. Open items and before launch

- ~~Code still on the old review model~~ **Done 1 Nov 2026 (issue #5):** renderer, day and Method templates, README field table and the sample briefs now use `built_at` + `corrections` (the 29 Oct sample has one correction; sample build times moved after 06:45). `BUILD_PLAN.md` is now only a pointer to the GitHub issues and §10.
- Check `havendaily.nl` availability; buy once the first version works.
- Test every candidate source (§4) before building on it.
- Summariser model: ~~run the Haiku 5.5 vs Sonnet 5.5 comparison~~ **run 2 Nov 2026 (#17), written up in `docs/model-comparison.md`; the owner chose Sonnet 5.5 through the batch** (§5.5).
- **After the first week of daily runs: check real AI costs** in the Anthropic Console against the §5.4 estimates.
- **MeteoAlarm daily snapshot:** email **meteoalarm@geosphere.at** asking whether a daily, dated snapshot (06:45, labelled "not live", linking to meteoalarm.org) is allowed, given the ≤ 10 min real-time requirement for operational use. **The owner sends it.** Keep the reply in `docs/permissions/`. If refused: switch to KNMI directly sooner, or weather = "No data".
- **Weather: count the Hook of Holland coastal area too?** KNMI's coastal warning for Hook of Holland (`NL802`, the port's sea entrance) is in the same feed; v1 counts Zuid-Holland only (owner, 2 Nov 2026, §5.11). Decide after watching a few weeks of readings.
- **Switch weather warnings to KNMI directly** once `KNMI-public-weather-warnings` leaves TEST (check monthly); register a free KNMI key then.
- **Barge low-water surcharge table:** Claude researches (owner's decision, 31 Oct 2026): find whether a barge operator (e.g. Contargo) publishes a Kaub-based low-water surcharge table. If so, use its first step as the Rhine **Watch** level (instead of GlW 77 cm), citing that table on the Method page. **Researched 2 Nov 2026 (#19), `docs/research/barge-surcharge.md`:** Contargo publishes one (terminals south of Koblenz), **first step 150 cm or below**; Maersk's Rhine barge surcharge starts at the same level. Both stop guaranteeing transport at **80 cm or below**. **Decided by the owner (2 Nov 2026, PR #71): Watch at 150 cm or below, Alert at 80 cm or below** (replaces GlW 77 and MNW 65); §2.2 table updated. A reading below the record low (NNW 25 cm; Kaub read 21 cm on 2 Nov 2026) is a valid Alert, not an error.
- **Before launch, find and check the terms of Kuehne+Nagel SeaNews and RTV Rijnmond** (§4). Downgrade K+N to headline-only, or drop either, if their terms forbid our use.
- **Permission emails to NL Times and RTV Rijnmond:** Claude drafts one short email per publisher (what Haven Daily is, non-commercial portfolio project, what we'd do with their articles: a 2-line own-words AI summary + link, never the text itself, and that we respect their AI opt-out until they say yes). **The owner sends them.** Both stay headline-only (hard rule 12) unless a publisher replies yes in writing; keep the reply in `docs/permissions/`.
- ~~Design addition: the unrated item~~ **Done 1 Nov 2026 (issue #6):** outlined square, "UNRATED" tag, card without summary/impact, reduced-brief note driven by `build.ai_unavailable`, archive strip; samples: one unrated item on 27 Oct, a reduced brief on 26 Oct. Design choices confirmed by the owner (§5.3).
- Finalise Rhine thresholds and weather thresholds from public sources (Method page). *(Rhine numbers decided 2 Nov 2026, PR #71, and built into `config/rhine.toml`, #20; shown with their sources on the Method page since 2 Nov 2026, #24.)*
- **Design usability review before launch** (added 31 Oct 2026): the design looks good but doesn't feel user-friendly enough, and the owner can't yet say why. First find the concrete problems: review the pages as a first-time visitor (a planner and a recruiter, on a phone and on a laptop), list what they understand in 5 seconds and what confuses them, then propose changes. **Nothing is implemented until the owner approves the proposals.** The new logo and the social preview tags come after this review. **Review written 2 Nov 2026 (#25): `docs/design-review.md`, screenshots in `design/screenshots/issue-25/`** (20 problems, 19 proposals in three sizes, map checks). It used one real pipeline run (2 Nov, ≈ $0.043, written to a scratch folder; its screenshots show real headlines and stay off the repo, hard rule 13) and a copy of that brief with invented text. **Owner's decisions 2 Nov 2026 (PR #80), §7.8:** 17 proposals approved and split into six `v1` issues that block launch (**#81–#86**); M6 moved to "Later" (§10), L1 to v2 ideas (§9).
- ~~Self-host the IBM Plex font files (`static/fonts/`) instead of Google Fonts, to avoid sending EU visitors' IP addresses to Google.~~ **Done 2 Nov 2026 (#27), §7.3.**
- ~~Privacy check (EU/GDPR): no cookies, storage, analytics or outside loads; privacy note in the footer.~~ **Done 2 Nov 2026 (#68), hard rule 14, §5.3.** Footer wording and all 7 defaults confirmed by the owner (2 Nov 2026, PR #79).
- Check aisstream.io terms for public display.
- New logo (§7.6) and a social preview image (§7.7); add `og:image` / `og:title` / `og:description` meta tags.
- Fill in LinkedIn URL and repository URL in the site config (footer + Method page).
- First LinkedIn post: one concrete flagged item, what the tool said, and what the owner would do as a planner.

---

## 12. Credits

Status data: weather warnings by KNMI via MeteoAlarm (shown: "KNMI", time of issue, link to www.meteoalarm.org, MeteoAlarm's exact disclaimer), Rhine Kaub by WSV / PEGELONLINE (DL-DE→Zero-2.0), Rhine Lobith by Rijkswaterstaat (CC0). Map data © OpenStreetMap contributors (ODbL). Leaflet 1.9.4 (BSD-2). Icons: Lucide (ISC). Fonts: IBM Plex Sans, Sans Condensed, Mono, Serif (SIL Open Font License). Shapely (BSD) for the basemap tool. Jinja2 (BSD). Beautiful Soup and soupsieve (MIT). Anthropic Python SDK (MIT).
