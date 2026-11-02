# Haven Daily — project context for Claude Code

*Owner: Leonardo Neirotti. Synced with `docs/SPEC.md` on 31 October 2026. Read this file before doing anything in this project.*

**`docs/SPEC.md` is the source of truth.** This file is a short summary. If the two disagree, the spec wins; tell me about the mismatch. Vocabulary: `GLOSSARY.md`. Source list: `SOURCES.md`.

## What this is

**Haven Daily** is a public web page, updated every morning, that tells a logistics planner what is affecting the Port of Rotterdam today and what it means for them. It is a **personal portfolio project** to show recruiters at Port of Rotterdam companies that I can build AI agents and apply them to a real operations problem.

## About me (for context only)

- 2nd-year BBA International Business (Supply Chain Management), Rotterdam University of Applied Sciences; looking for a 20-week internship from February 2027.
- I build with Claude Code step by step. **Explain decisions briefly**: I need to be able to talk about every part of it in an interview.

## Key decisions (details in the spec)

- **Publishing (§2, §5.1):** one GitHub Actions job at ~06:45 Amsterdam collects, builds, commits `data/` straight to `main` and deploys to GitHub Pages. No PR, no review window. Mistakes are fixed afterwards with a visible correction. The page never skips a day.
- **Schedule (§5.1.1):** triggers at 04:45, 05:45, 06:45 UTC + manual; a guard builds once, on the first run after 06:30 Amsterdam with no brief for today.
- **Pipeline (§5):** collect → filter (rules, then Claude Haiku 5.5) → summarise (Sonnet 5.5, chosen by the owner after the side-by-side test with Haiku 5.5, #17; Batch API with 20-min limit, fallback to Haiku standard) → status (MeteoAlarm/KNMI weather, Kaub Rhine gauge, strike flag) → brief → render → deploy.
- **AI budget:** all AI calls under €5/month; check real costs after week one.
- **AI never invents:** places and "affects" tags are picked from fixed lists (§5.10); severity can be `null` = unrated; strike dates only if stated.
- **Storage (§6.1):** plain JSON files per day in `data/`, written once; no article text ever.
- **Sources (§4, `SOURCES.md`):** final verdicts use / headline-only / drop.

## Hard rules (full text: spec §3)

1. Every item links to its original source. No invented facts, numbers or quotes.
2. Summaries short and in our own words. No full articles, long quotes or full translations.
3. Paywalled sources: headline + link only, or skip.
4. Respect each source's terms and robots.txt; if automated access isn't allowed, drop it.
5. Footer on every page: "Personal, unofficial project by Leonardo Neirotti. Not affiliated with the Port of Rotterdam Authority. AI-generated summaries — always check the original source."
6. Never use Port of Rotterdam branding or logos; the site must not look official.
7. **Never commit API keys.** GitHub Actions secrets only.
8. No company or confidential data.
9. If one source or step fails, the rest of the page still builds and the failure is shown.
10. Sample data is clearly marked on every page.
11. A published brief is never changed silently: every edit adds a correction.
12. Respect AI opt-outs: sources that block AI crawlers are headline-only; their text never goes to an AI.
13. No third-party article text or snippets in the repo; text is used in memory only.

## Editing a published brief

A brief in `data/briefs/` is public as soon as the morning job commits it. Whenever you edit one:

1. Add the correction note yourself: append `{"at": "<now, Amsterdam time, ISO 8601>", "note": "<one line: what changed and why>"}` to the brief's `corrections` list.
2. Show me the change and the note, and wait for my OK before committing.

## Secrets

- **Never ask me for API keys or tokens**, and never print, log or echo them. When reporting a possible leak, show only the file/commit and the first 6 characters.
- Code reads secrets **only from environment variables**: a local `.env` file (git-ignored; `.env.example` lists the variable names with no values) and **GitHub Actions secrets** online.
- Never write a key into code, config, tests, docs, output files or commit messages.

## Personal data

- **Never send the owner's email address or any other personal data to an outside service** (APIs, websites, user-agent strings, contact fields, search queries, …) **without asking me first.** This includes the email address the session knows about. Use a project name with no personal details in user agents (e.g. `HavenDaily-gazetteer/1.0`). *(Owner's rule, 2 Nov 2026.)*

## Open items

See spec §11 (permission emails, terms still to check, cost check after week one, and more).

## Agent skills

### Issue tracker

Issues live in GitHub Issues for leonardoneirotti/haven-daily, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
