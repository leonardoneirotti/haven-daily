# Barge low-water surcharge at Kaub: research (issue #19)

*Researched by Claude on 2 November 2026 for spec §2.2 and §11. All pages read that day by hand, once each, with the project user agent `HavenDaily-research/1.0` (no personal data sent). Only the water-level steps are recorded here; surcharge prices are not copied (hard rule 13: facts with a link, no third-party content in the repo).*

## Question

Does a barge operator serving Rotterdam publish a **Kaub-based low-water surcharge table**? If so, its first step could replace **GlW 77 cm** as the Rhine **Watch** level (spec §2.2), cited on the Method page.

## Answer in one line

**Yes.** Contargo publishes one, and its **first step is 150 cm or below at Kaub**. Maersk's own Rhine barge surcharge starts at the same level (below 1.51 m). Both also say that **at 80 cm or below** they no longer guarantee transport.

## What was checked

| Operator | Kind | Kaub table? | First step | "No guarantee" level | Source, read 2 Nov 2026 |
|---|---|---|---|---|---|
| **Contargo** | Barge/rail/truck operator, Rotterdam ⇄ Rhine terminals (also a Haven Daily source, §4) | **Yes**, 5 steps, full containers only, terminals **south of Koblenz** | **150–131 cm** (step 1) | **80 cm or below: by agreement**; an older Contargo notice says its *"transport obligation stops at water levels of less or equal 80 cm at Kaub"* | [Low water surcharge page](https://www.contargo.net/en/goodtoknow/lws) · [Kaub notice](https://www.contargo.net/en/business/business-news/detail-business/adjustment-of-low-water-surcharge-level-kaub/) (undated) |
| **Maersk** | Shipping line, carrier haulage by barge (inland from Rotterdam/Antwerp) | **Yes**, 10 steps, full containers only, effective 15 July 2026, "valid until further notice" | **below 1.51 m** (= 150 cm or below) | Kaub **below 81 cm**: *"a loading guarantee for your cargo cannot be granted"* | [Rate announcement, 14 Jul 2026](https://www.maersk.com/news/articles/2026/07/09/rhine-river-low-water-surcharge) |
| Hapag-Lloyd | Shipping line, carrier haulage | **Not read**: the site returned HTTP 403 to our request, so it wasn't read further (we don't get around blocks) | – | – | [Rhine low water surcharge update](https://www.hapag-lloyd.com/pt/services-information/news/2026/07/here-s-an-update-on-the-rhine-river-low-water-surcharge.html) |
| Danser | Barge operator, Rotterdam ⇄ Rhine/Neckar | **No table found.** A search result points to a notice saying there is no transport obligation under 0.81 m at Kaub, but the page returns 404, so it **couldn't be checked** | – | (unchecked) | danser.nl news (page gone) |
| HGK Shipping, Rhenus, BCTN, CTS | Barge operators | **No public Kaub surcharge table found** in a search of their sites | – | – | – |

Trade press (Container News, Tradlinx blog, The Loadstar) repeats these tables, but it isn't a primary source and wasn't used.

**How the steps are read (Contargo and Maersk alike):** the level measured at **05:00 CET** as published by ELWIS (the same WSV gauge we read through PEGELONLINE), on the barge's **timetabled departure day** (exports: from the inland terminal; imports: from the seaport). Contargo's bands are whole centimetres ("150 – 131 cm"), so **150 cm is already step 1 and 151 cm is not**. Maersk's "< 1,51 m" gives the same edge.

**Context from PEGELONLINE (Kaub, read 2 Nov 2026):** mean daily level **MW 208 cm** (2010–2020), GlW 77, MNW 65, lowest NW 25. The current reading was 21 cm.

## Terms

- **Contargo:** no robots.txt (HTTP 404, as in §4), footer "Copyright © 2026 CONTARGO. All rights reserved." We cite **one fact** (the level at which the surcharge starts) with a link; we don't reproduce the table or its prices. Citing a fact is not copying content.
- **Maersk:** robots.txt doesn't block `/news/articles/`. Same approach: cite the level, link the notice.
- Neither page is read by the daily job; this is a one-off citation on the Method page.

## Recommendation

1. **Watch: 150 cm or below at Kaub** (Contargo's step 1, matched by Maersk), instead of below GlW 77 cm. This is where a Rotterdam planner booking a barge to a terminal south of Koblenz **starts paying more per container**, which is the planner's own question. GlW 77 is a navigation reference: by the time Kaub is below 77, both operators have already stopped guaranteeing transport, so a Watch at 77 comes too late to warn anyone.
   - Cite on the Method page: *"Watch from 150 cm: first step of Contargo's Kaub low-water surcharge (terminals south of Koblenz), read 2 Nov 2026"* + link. Maersk can be named as a second source.
   - Effect: with a mean of 208 cm, Kaub will sit in Watch for longer stretches than with 77 cm. That is correct for a planner (costs are rising), but the owner should know the Rhine dial will be amber more often.
2. **Optional, outside #19's strict scope: Alert at 80 cm or below** instead of below MNW 65 cm. Both first-hand sources say transport is no longer guaranteed from that level (Contargo "by agreement" at ≤ 80 cm, Maersk "no loading guarantee" below 81 cm). MNW 65 is a statistical mean with no operational meaning for a planner. If not taken, keep MNW 65.
3. **High-water side unchanged:** Marke I 460 cm (Watch) and Marke II / HSW 640 cm (Alert) are official shipping limits; no operator table replaces them.
4. **Not in scope, worth knowing:** Contargo uses **Duisburg-Ruhrort**, **Cologne** and **Emmerich** for terminals further north (where most Rotterdam barge volume goes). The status line shows Kaub only (§2.2); adding another gauge would be a new decision, not part of #19.

**Decided by the owner (2 Nov 2026, PR #71): both recommendations accepted.** Watch at 150 cm or below, Alert at 80 cm or below (replaces MNW 65 cm). The spec §2.2 table is updated; #20 builds the thresholds from config and tests the edges 79/80/81 and 149/150/151 (plus 459/460/461 and 639/640/641 on the high side). A reading below the record low (NNW 25 cm; 21 cm on 2 Nov 2026) is a valid Alert, not an error.
