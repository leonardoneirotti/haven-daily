# Haven Daily — project context for Claude Code

*Owner: Leonardo Neirotti. Decisions settled 29 October 2026. Read this file before doing anything in this project.*

## What this is

**Haven Daily** is a public web page, updated every morning, that tells a logistics planner what is affecting the Port of Rotterdam today and what it means for them.

*"Haven" means port in Dutch and safe place in English — the name works in both languages.*

It is a **personal portfolio project**, not a company tool. Its purpose is to show recruiters at Port of Rotterdam companies that I can build AI agents and apply them to a real operations problem. I will link it from my LinkedIn profile and post about it weekly.

## About me (for context only)

- 2nd-year BBA International Business (Supply Chain Management), Rotterdam University of Applied Sciences.
- Looking for a 20-week internship from February 2027 at a Port of Rotterdam company (operations, process improvement, planning, logistics or data).
- I build with Claude Code step by step. Explain decisions briefly so I understand what's being built; I need to be able to talk about every part of it in an interview.

## Decisions already made

| Topic | Decision |
|---|---|
| Name | **Haven Daily**. Domain not bought yet (check havendaily.nl first). Launch on the free GitHub Pages address. |
| Format | **Public static website** on GitHub Pages. Each day gets its own page; an archive lists all days. |
| Language | Python. |
| Scheduling | GitHub Actions. Note: GitHub cron runs in UTC and can start late. |
| Publishing | **Review window, then auto-publish.** ~06:30 Amsterdam time: a job builds today's page and opens it as a **pull request**. I get a GitHub mobile app notification and can approve or edit. ~08:00: if not merged, a second job merges and publishes automatically. The page must never skip a day. |
| Alerts | **No email.** GitHub app notifications only (new PR, failed run). |
| Brief length | **Max 5 items** per day, sorted by severity. On quiet days fewer items, or "nothing significant today". Never pad. |
| Dutch sources | Included. Each Dutch item gets an English summary + link to the original + a **"Read in English"** link that opens the original through a translation service (e.g. Google Translate URL). **Never republish or store full translated article text** on the page — that is a copy of someone else's work. |
| Storage | Store every collected item and every status value from day one (SQLite or JSON in the repo), so trends and charts are possible later. |

## Each news item on the page

- Headline + link to the original source (always).
- What happened, in 2 lines, in my tool's own words (never copied text).
- **Impact for a Rotterdam planner**: delays, costs, which cargo, terminals or routes. Clearly labelled as interpretation. If the article does not support an impact, say "Not enough information" rather than guessing.
- Severity tag with written rules (to refine):
  - **High**: directly affects Rotterdam operations and has a timeframe (e.g. strike at a terminal this week).
  - **Medium**: affects a European route, carrier or hinterland connection serving Rotterdam.
  - **Low**: background trend or long-term news.
- For Dutch items: the "Read in English" link.

## Port status line (top of each page)

A row of indicators, each with value, colour (green/amber/red), change vs yesterday, timestamp and source link.

**Version 1:**
- Weather warnings (wind, storm, fog) — KNMI.
- Rhine water level (Kaub and/or Lobith) — public government water-level data.
- Active strike flag — derived from today's news items.

**Later:** road (A15 closures, Rijkswaterstaat), rail (Betuweroute, ProRail), sea vessel waiting times (Port Authority "Port Performance" page), barge waiting times (Barge Performance Monitor / operator notices). Add only once a clean, permitted automatic source is confirmed.

**Rules:** no data = show "no data", never estimate. Colour thresholds are documented on an About/Method page with their public source.

## Version 2: ship map (after v1 has run reliably for 1–2 weeks)

- **Own daily AIS snapshot** (not an embedded MarineTraffic/VesselFinder widget). The morning job listens to the free aisstream.io WebSocket for ~10–15 minutes on a bounding box around the port and saves the vessels present.
- **Seagoing cargo ships only** (container, tanker, bulk). No barges, tugs, pilot boats.
- Map built with Leaflet into the day's page; each day's map stays in the archive.
- Click a ship: name, type, flag, berth/terminal if known, declared AIS destination, and a **point-to-point estimated route** (now → next destination) drawn with the `searoute` Python package, labelled "estimated". Map zooms out from Rotterdam to show the trip.
- AIS destination fields are messy ("NL RTM", "ANTWERP>HAMBURG", blank): clean them, show "unknown" when unclear.
- Highlight ships at terminals mentioned in today's news.
- Optional: a "see it live" link to the ship's page on MarineTraffic (a link only, no embedding).
- Check aisstream.io terms on publicly displaying their data before launch. aisstream is reported to be in beta and sometimes unstable: the page must still build if it fails.

## Hard rules

1. Every item links to its original source. No invented facts, numbers or quotes.
2. Summaries are short and in our own words. No full articles, no long quotes, no full translations of third-party articles.
3. Paywalled sources (Lloyd's List, The Loadstar, JOC, Nieuwsblad Transport): headline + link only, or skip.
4. Respect each source's terms and robots.txt. If a source doesn't allow automated access, drop it.
5. Footer on every page: "Personal, unofficial project by Leonardo Neirotti. Not affiliated with the Port of Rotterdam Authority. AI-generated summaries — always check the original source."
6. Never use "Port of Rotterdam" branding or logos; the site must not look official.
7. **Never commit API keys.** Use GitHub Actions secrets.
8. No company or confidential data.
9. If one source or step fails, the rest of the page still builds and the failure is noted.

## Secrets

- **Never ask me for API keys or tokens**, and never print, log or echo them. When reporting a possible leak, show only the file/commit and the first 6 characters.
- Code reads secrets **only from environment variables**: a local `.env` file (git-ignored; `.env.example` lists the variable names with no values) and **GitHub Actions secrets** online.
- Never write a key into code, config, tests, docs, output files or commit messages.

## Known competitors (useful for my README and interviews)

Commercial, paid, B2B: Yusen Logistics "Supply Chain Disruption Radar" (2026), Sea Sentinel AI, GoComet, Portcast/SeaVantage/Beacon congestion trackers. Free but different: Port Authority news page and Port Performance page, PortsEurope (all of Europe), Kuehne+Nagel SeaNews (weekly, global). Haven Daily's niche: free, public, Rotterdam-only, daily, with planner impact.

## Open items

- Check havendaily.nl availability; buy once the first version works.
- Test every candidate source in `SOURCES.md` before building on it.
- Choose the AI model/API for summaries and check monthly cost (expected to be low for a daily run; verify current pricing).
- First LinkedIn post: one concrete flagged item, what the tool said, and what I'd do as a planner.
