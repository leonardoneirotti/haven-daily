# Build plan — prompts to give Claude Code, in order

Open this folder in Claude Code. It reads `CLAUDE.md` automatically. Then use these prompts one at a time, and check each result before moving on.

**The build phases now live in GitHub issues** (#3–#42, labels `v1`, `v2`, `later`, in build order with "blocked by" links). This list is the original outline; where it differs, the issues and `docs/SPEC.md` win.

## Version 1 — daily brief

1. "Read CLAUDE.md and SOURCES.md. Set up the Python project: folder structure, a config file listing sources, storage for items and status values, and a README. Explain the structure in a few lines."
2. "Test every source in SOURCES.md: does it have a feed or a readable page, how much text does it give, and what do its terms/robots.txt say? Write the results back into SOURCES.md as use / headline-only / drop."
3. "Write the collector: fetch the sources marked 'use' and 'headline-only', save new items (title, link, date, source, language, available text) without duplicates."
4. "Add a relevance filter for the Port of Rotterdam and its supply chains. Show me what it kept and dropped from today's items so I can tune it."
5. "For each kept item, generate the 2-line summary, planner impact and severity tag, following the rules in CLAUDE.md. Never invent facts. Before calling an API, tell me which model you suggest and the expected monthly cost."
6. "Run everything once on today's items and show me the output before building any page."
7. "Build the status line v1: weather warnings, Rhine water level, strike flag. Store values daily. No data = 'no data'."
8. "Render the static site: today's page (status line + max 5 items by severity), one page per day, an archive page, an About/Method page with severity rules and status thresholds, and the footer from CLAUDE.md. Clean, readable on mobile."
9. "Set up GitHub Pages and GitHub Actions: one scheduled job at ~06:45 Amsterdam time that runs the pipeline, commits `data/` to main and deploys the site (no PR). Keys only in secrets. Notify on failures."
10. "Let it run for a few days, then help me tune the filter and severity rules."

## Version 2 — ship map

11. "Add the daily AIS snapshot described in CLAUDE.md (aisstream.io, port bounding box, ~10–15 minutes, seagoing cargo ships only). The page must still build if it fails."
12. "Add the Leaflet map to each day's page: click a ship for its details and a point-to-point estimated route (searoute) to its cleaned destination, zooming out from Rotterdam. Highlight ships at terminals mentioned in today's news."

## Later

- Weekly digest of the top 3 items as a starting point for my LinkedIn post (I always rewrite it myself).
- Road and rail indicators; vessel and barge waiting times once a clean source is confirmed.
- Charts from stored history (e.g. Rhine level vs barge delays).
- Custom domain.
