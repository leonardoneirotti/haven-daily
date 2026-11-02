# Design usability review (issue #25)

*Written 2 Nov 2026 by Claude for Leonardo Neirotti. Findings first, proposals after. **Nothing in this review is implemented.** Approved proposals become new `v1` issues that block launch (#25, spec §11).*

## Why the site doesn't feel user-friendly, in five points

The design looks good, but a first-time visitor has to work too hard to get the point. The concrete reasons:

1. **The first screen is a map that, in v1, usually shows nothing.** Ships come only in v2 (#31), and on the real 2 Nov run **none of the 10 kept items had a place on the chart**. So on a typical day the page opens on an empty chart with an amber box saying "No ship positions: ships are not collected yet". It looks like an error, and on a phone it fills the whole first screen (P1, P2, P3).
2. **On a real day most items are empty shells.** On 2 Nov, 4 of the 5 shown items were Dutch headline-only items: no summary and no impact, but the card still shows every block, with "Not enough information in the source to judge the impact" four times and "No single place on the chart" five times. The page looks like the AI failed, when it actually followed the rules (P4, P5, P6).
3. **Nothing on the page says what this is, who it's for, or who made it.** "Port of Rotterdam" isn't on the first screen. The only explanation is the Method page (13 sections), and the recruiter's main questions (who built this, how, where's the code) are answered last or not at all (P7, P8, P9).
4. **Status values come without their meaning.** The real day's strongest signal was the Rhine at 16 cm, **Alert**. The page shows a red "16 cm", but not what that means for a planner (barge operators no longer guarantee transport). That meaning is only on the Method page (P10, P11).
5. **Internal words leak onto the public page:** "No AIS", "Summaries in the batch / by the fallback", "gap check skipped", "Derived from kept items", "rated from headline only", "No. 001" (P12).

## How the review was done

- **Pages:** Today, a past day (27 Oct sample: no ships, one unrated item), the reduced brief (26 Oct sample), Archive and Method. Each was looked at as a first-time visitor, for two people (a **logistics planner** and a **recruiter**) on two screens (**phone 390 × 844**, **laptop 1440 × 900**).
- **Data:**
  - the four sample briefs;
  - **one real brief**: the full pipeline was run once on 2 Nov 2026 into a scratch folder (approved by the owner; cost ≈ $0.043). It collected 151 items, kept 10, showed 5, and summarised all 10 in the batch. Its screenshots show real headlines, so **they stay on the owner's machine and are not committed** (hard rule 13);
  - **a copy of that real brief with every headline, summary, impact, link and source name replaced by invented text** ("Invented headline: …", "Source A"). Structure, severities, languages, tags, status readings and build counts are unchanged. The committed screenshots of a "real" day use this copy;
  - the Method page, rendered from the real config.
- **Screenshots:** headless Edge. Edge won't make a window narrower than ~500 px (§8.7), so phone shots load the page in a 390 px iframe and are cropped afterwards. Long pages are captured in pieces. Map checks use a scratch page with all 41 places as numbered items, and the box of every callout is measured in the browser.
- **Limits:** this is an expert review, not a test with real people. The "5 seconds" findings are a careful guess at what a first-time visitor would see, not observations. A 5-second test with two or three real people (a classmate in supply chain, someone in HR) would confirm or correct them; see "Decisions for the owner".

Screenshots are in [`design/screenshots/issue-25/`](../design/screenshots/issue-25/) (folder set by the owner; the issue said `design/review/`):

| File | What it shows |
|---|---|
| `sample-today-phone-first.jpg`, `sample-today-laptop-first.jpg` | Today (29 Oct sample, with ships and pins), first screen |
| `sample-today-phone-full-1.jpg`, `-2.jpg`, `sample-today-laptop-full.jpg` | the same, whole page |
| `sample-past-phone-first.jpg`, `sample-past-laptop-first.jpg` | a past day with no ships and no pins (27 Oct sample) |
| `realshape-today-phone-first.jpg`, `realshape-today-phone-full-1.jpg`, `-2.jpg`, `realshape-today-laptop-first.jpg`, `realshape-today-laptop-full.jpg` | the real 2 Nov brief with invented text |
| `sample-archive-phone-first.jpg`, `sample-archive-laptop-first.jpg` | Archive |
| `sample-method-phone-first.jpg`, `sample-method-laptop-first.jpg` | Method page, first screen |
| `map-all-places-laptop.jpg`, `map-all-places-phone.jpg` | all 41 places pinned at once (check page, not a real day) |
| `map-maasvlakte-laptop.jpg`, `map-rozenburg-laptop.jpg` | only the neighbouring places of Delta II / ECT Delta and of Rozenburgsesluis |

## Five-second findings, per person and device

### Planner on a phone

**What they understand in 5 seconds:** the name "Haven Daily", a date ("Mon 2 Nov · No. 001"), and that there's a map of a port. On the sample day they also see a red "1 Terminal strike" on the chart. On a real day they see an empty chart with an amber box ([realshape-today-phone-first](../design/screenshots/issue-25/realshape-today-phone-first.jpg)).

**What's confusing:**
- **Where they look first:** the chart, because it fills the screen. On a real day nothing on it is today's news. The first item card starts about 1.5 screens down; the day's big heading ("Monday") is at the bottom edge of the first screen (P1, P3).
- **What they'd click:** the amber box (it looks like an alert, and it isn't clickable); the orange square button (its icon doesn't say "whole port"); "Full brief and port status" (it only scrolls a few pixels to what is already right below) (P2, P15).
- **What they'd miss:** the Rhine Alert. In the panel it's a red "16 cm" with no word for what it means; the full Rhine dial is ~3,000 px further down (P10).
- **Words they might not know:** "Kaub gauge", "No AIS" (archive), "Strike flag · Derived from kept items", "rated from headline only", "interpretation". Planners know "Shortsea" and "Hinterland".
- **Language:** 4 of the 5 real items are Dutch headlines with no English summary. A non-Dutch planner has to open "Read in English" (Google Translate) for each one (P5).

### Planner on a laptop

**What they understand in 5 seconds:** this is today's morning brief with up to 5 ranked items (numbered, coloured squares, severity word) and a 4-cell port status. This works well on the sample day ([sample-today-laptop-first](../design/screenshots/issue-25/sample-today-laptop-first.jpg)).

**What's confusing:**
- **On a real day the right two-thirds of the screen is an empty chart** with the amber "No ship positions" box over the Maasvlakte ([realshape-today-laptop-first](../design/screenshots/issue-25/realshape-today-laptop-first.jpg)) (P1, P2).
- **Clicking a panel entry behaves two ways.** An item with a place opens in the panel (summary appears) and the chart moves. An item without a place (all 5 on 2 Nov) is a plain link, so the page jumps down to the card. Nothing tells the two apart (P13).
- **The panel shows only headlines.** The summary appears only after a click, and only for items with a place. For a headline-only Dutch item the panel shows a Dutch title and nothing else (P5, P13).
- **"MEDIUM Containers"**: the first "affects" tag sits next to the severity and reads like a category, but it's one of several tags (P14).
- **The Rhine cell "16 cm" is red and bold, like a link, but isn't clickable;** the meaning ("Alert") is only a screen-reader text and the icon (P10).
- **Five items, all "Not enough information"** in the full brief below ([realshape-today-laptop-full](../design/screenshots/issue-25/realshape-today-laptop-full.jpg)): the planner can't tell "the AI wasn't allowed to read it" from "the AI couldn't make sense of it" (P4, P6).

### Recruiter on a phone (the most likely case: they arrive from a LinkedIn post)

**What they understand in 5 seconds:** a dark, polished map page called "Haven Daily". It looks like a professional tool. They don't know what it is, that AI made it, or who made it ([sample-today-phone-first](../design/screenshots/issue-25/sample-today-phone-first.jpg)).

**What's confusing:**
- **No sentence says what this is.** The meta description has one, but it's never shown. "Port of Rotterdam" appears only in the footer disclaimer, ~5,600 px down on the sample page (P7).
- **No link to the person or the code.** `site.linkedin_url` and `site.repo_url` are both `None` in `haven/render.py`, although the repository is public, so neither the footer nor the Method page shows them (P8).
- **"Method"** doesn't say "about this project" to a recruiter. The project story (what it does, the AI models, who makes it) is spread over 13 sections; "Who makes this" is the last one, ~11,900 px down on a phone ([sample-method-phone-first](../design/screenshots/issue-25/sample-method-phone-first.jpg)) (P9).
- **The best proof of skill is hidden:** "How this brief was made" (151 collected → 10 kept → 5 shown, 2 AI models, batch with fallback) is at the bottom, in internal words (P12).
- **The logo** (two signal flags) means nothing to most visitors. It's already planned to be redesigned after this review (§7.6).

### Recruiter on a laptop

**What they understand in 5 seconds:** "a dashboard for the port, nicely designed" (the strongest first impression of the four, thanks to the map and panel). They still don't know it's an AI project or whose it is.

**What's confusing:**
- Same missing "what / who / how" as on the phone (P7, P8, P9).
- **On a real day the page looks half-broken:** an empty map with an amber box, Dutch headlines, "Not enough information" repeated, and an amber failure line "PIN notices to shipping: gap check skipped: no brief of the last 14 days records when the feeds were last read" at the bottom (P1, P4, P12). A recruiter can't tell that this is the system being honest, not broken.
- **Archive:** coloured squares and three icons per day with no legend. The icons explain themselves only on mouse-over (`title`), and "No AIS" is jargon ([sample-archive-laptop-first](../design/screenshots/issue-25/sample-archive-laptop-first.jpg)) (P16).

## Problems

**How much it matters:** **High** = stops the 5-second understanding, or makes a real day look broken. **Medium** = slows the visitor down or misleads. **Low** = polish.

| # | Problem | Where | Screenshot | Matters |
|---|---|---|---|---|
| P1 | **The chart takes the first screen even when it shows nothing.** With no ships (v1) and no placed items (0 of 10 on 2 Nov), the phone's whole first screen and two-thirds of the laptop's are an empty chart. | Day pages, both devices | realshape-today-phone-first, realshape-today-laptop-first, sample-past-phone-first | **High** |
| P2 | **The "No ship positions" note looks like an error and hides the port.** An amber-bordered box in the middle of the chart, placed over the Maasvlakte, where most pins would be (on the all-places page it hides ECT Delta, APMT, RWG, Maasvlakte II, Euromax). On every v1 day it's expected, not a problem. | Chart | sample-past-laptop-first, map-all-places-laptop | **High** |
| P3 | **Phone: the brief starts below the chart.** The date heading is at the bottom of the first screen, the first item ~1.5 screens down. The panel's item list is hidden on phones, so the numbers on the chart have no list next to them. | Day page, phone | sample-today-phone-first, sample-today-phone-full-1 | **High** |
| P4 | **Headline-only cards repeat empty blocks.** Each card shows "Headline only: this source is paywalled or its terms don't allow a summary.", then the pink "IMPACT FOR PLANNERS interpretation" label, then "Not enough information in the source to judge the impact.", then "No single place on the chart". On 2 Nov that's 4 of 5 cards. | Full brief | realshape-today-laptop-full, realshape-today-phone-full-1 | **High** |
| P5 | **Dutch headline-only items have no English at all.** The headline is Dutch and there's no summary, so a non-Dutch reader gets nothing from the card or the panel without clicking out to Google Translate. | Panel, full brief, archive | realshape-today-laptop-first | **High** |
| P6 | **"Rated from headline only" is unclear and easy to miss.** Small grey mono text next to the severity. A reader doesn't know why a medium item has no summary, or how something can be rated without being read. | Item cards | realshape-today-laptop-full | Medium |
| P7 | **No line says what the site is or who it's for.** "Port of Rotterdam" isn't on the first screen of any page; the `<meta description>` sentence is never shown. | All pages | sample-today-laptop-first, realshape-today-phone-first | **High** |
| P8 | **No link to the maker or the code.** LinkedIn and repository URLs are empty in `render.py` (repo is public). | Footer, Method | sample-today-phone-full-2 | **High** (for the recruiter) |
| P9 | **The project story is at the end of a long Method page.** 13 sections, no contents list; "Who makes this" is last (~11,900 px on a phone). The nav word "Method" doesn't invite a recruiter in. | Method, nav | sample-method-phone-first, sample-method-laptop-first | Medium |
| P10 | **Status values come without their meaning.** "16 cm" in red; the dial says "Alert", but not what Alert means (operators no longer guarantee transport at ≤ 80 cm). Same for Watch (surcharges from ≤ 150 cm) and for the strike flag. The meaning is only on the Method page. | Panel mini status, Port status dials | realshape-today-laptop-first | **High** |
| P11 | **The Rhine gauge can't show the levels that matter.** On a 0–700 cm scale, 16 cm is a 2% sliver, and the Watch (150) and Alert (80) lines aren't drawn, so the gauge says "nearly empty" without saying how close to which line. (`gauge_max` 700 was left open for this review, §5.12 point 7.) | Rhine dial | realshape-today-laptop-full | Medium |
| P12 | **Internal words on the public page:** "No AIS", "Summaries in the batch / by the fallback", "PIN notices to shipping: gap check skipped: no brief of the last 14 days records when the feeds were last read", "Derived from kept items", "Kept items of the last 14 days", "No. 001". | Build notes, dials, archive, topbar | realshape-today-laptop-full, sample-archive-laptop-first | Medium |
| P13 | **Panel entries behave two ways.** With a place, a click opens the summary in the panel and moves the chart; without a place, the page jumps to the card. On 2 Nov all 5 jump. | Panel, laptop | realshape-today-laptop-first | Medium |
| P14 | **The first "affects" tag reads like a category** ("MEDIUM Containers", "MEDIUM Shortsea") although an item has several tags. | Panel | sample-today-laptop-first | Low |
| P15 | **Controls that don't say what they do:** the orange "whole port" button (icon only); "Full brief and port status" on a phone, which scrolls to what is already directly below; the ship-list header "All 40 ships in the snapshot" has no ▸ arrow showing it opens (`display: flex` on `<summary>` removes the marker). | Chart, panel, ship list | sample-today-phone-first, sample-today-phone-full-2 | Low |
| P16 | **Archive marks have no legend.** Five coloured squares and three status icons per row; the icons are explained only by a mouse-over `title` (nothing on a phone). "No AIS" on every v1 day. | Archive | sample-archive-phone-first, sample-archive-laptop-first | Medium |
| P17 | **The brief's intro says '"Show on chart" moves the chart at the top of the page'** even when no item has a "Show on chart" button (2 Nov). | Full brief | realshape-today-phone-full-1 | Low |
| P18 | **Small text where the 5-second reading happens.** On the laptop, the panel's severity words, tags and status labels are 11–12 px (`0.6875`–`0.75rem`) in mono or grey; the body text is 17 px. | Panel, item meta | sample-today-laptop-first | Low |
| P19 | **News labels and place names look the same on the chart.** A callout label ("Terminal strike") and the basemap's place names share colour and weight, and on the sample day "Terminal strike" covers "Maasvlakte 2". | Chart | sample-today-phone-first, sample-today-laptop-first | Low |
| P20 | **Map pins can stack or hide** (details in "Map checks" below): Europoort and Calandkanaal are 1–2 px apart; on the laptop the three outer anchorages and Eurogeul sit under the news panel; on the phone 14 of 41 places are outside the first view. | Chart | map-all-places-laptop, map-all-places-phone | Medium |

## Map checks asked for in the issue

- **Rozenburgsesluis: the pin is on the right lock. ✔** The OpenStreetMap way used (`way/455107064`) is named "Calandkanaal", but its own tags say `lock_name=Rozenburgsesluis`, `alt_name=Rozenburgse Sluis`, Wikipedia `nl:Rozenburgsesluis` (Wikidata Q2053067) and link Rijkswaterstaat's chamber record. The pin (51.8929, 4.2288) is the way's centre, between its lock gates and next to the Rozenburgsebrug. The only other lock nearby is the Keersluis, 2.5 km north-east. (Read from the OSM API and Overpass on 2 Nov 2026, user agent `HavenDaily-review/1.0`.) On our chart the pin sits on the Calandkanaal at the Rozenburg end, but the basemap doesn't draw locks, so "on the chart" can only mean the coordinates ([map-rozenburg-laptop](../design/screenshots/issue-25/map-rozenburg-laptop.jpg)).
- **Label sides: switching sides can't fix the overlaps.** Measured at the home view, many pins are only 1–30 px apart, closer than one number square (36 px), so the squares themselves overlap whichever side the labels are on. On the laptop 90 pairs of callout boxes overlap, on the phone 161, all inside the same clusters: Maasvlakte, Europoort/Hoek van Holland, Rozenburg/Calandbrug, Pernis/Eemhaven/Waalhaven. A real day shows at most 5 items, so a problem appears only when **two items of the same day** pick neighbouring places. Specific pairs:
  - **Europoort ↔ Calandkanaal: 1–2 px apart**: the two places have nearly the same coordinates, so they stack completely;
  - **RWG ↔ Maasvlakte II: 5 px; ECT Delta ↔ Maasvlakte: 12 px; EBS ↔ P&O Europoort: 13 px; Stena ↔ Hoek van Holland: 14 px;**
  - **Cobelfret, Rozenburgsesluis, Calandbrug and Rozenburg all within 16–30 px** ([map-rozenburg-laptop](../design/screenshots/issue-25/map-rozenburg-laptop.jpg)).
- **Delta II ↔ ECT Delta: not readable together.** They are 16 px apart on the laptop's home view and 11 px on the phone's. Selecting an item zooms in to at most 11.8 when there are no ships, which brings them to ~35 px apart: the two number squares just touch and the labels still overlap. In [map-maasvlakte-laptop](../design/screenshots/issue-25/map-maasvlakte-laptop.jpg) the four Maasvlakte pins are also half hidden under the "No ship positions" box (P2). Each one alone is fine.
- **Pins outside the view:** on the laptop, **3 East, 4 West and 5 East Anchorage and Eurogeul** sit under the news panel at the home view. On the phone, **14 of the 41 places** (Botlek, Pernis, Eemhaven, Waalhaven, RST, Vondelingenplaat, Botlekbrug, Hartelkering, Nieuwe Maas, Oude Maas, three anchorages, Eurogeul) are outside the first view, because the compact view covers only the western port. An item pinned there is invisible until "Show on chart" is pressed.

## Proposals

Each proposal names the problems it addresses. Sizes: **Small** = wording or CSS, no layout change; **Medium** = template or chart-code change; **Large** = layout change or new content.

### Small

| # | Proposal | Fixes |
|---|---|---|
| S1 | **One line under the brand on every page:** "What's affecting the Port of Rotterdam today, for logistics planners. A personal AI project by Leonardo Neirotti → How it works". Short, factual, and it doesn't make the site look official (hard rule 6). | P7 |
| S2 | **Fill in `repo_url`** (the repository is public) **and `linkedin_url`** (the owner gives the address). Both then show in the footer and on the Method page. | P8 |
| S3 | **Rename the nav item "Method" to "How it works"** and add a contents list at the top of that page. Move "Who makes this" to second place, right after "What this is". | P9 |
| S4 | **In v1, drop the amber "No ship positions" box from the chart.** Ships aren't built yet, so it isn't a failure: say it once, in grey, in the legend line under the chart ("Ships: from v2"). Keep the box for v2, for the day the AIS snapshot really fails (that is a failure, hard rule 9), but move it off the port, e.g. to the chart's top-left corner. | P1, P2 |
| S5 | **A shorter headline-only card:** the headline, then one grey line "Headline only (the source's terms don't allow a summary) · severity rated from the headline", the tags and the links. No impact block, and no "No single place on the chart" line (just no button). Keep "Not enough information" for items that have a summary but no impact. | P4, P6 |
| S6 | **Status values with their meaning**, built from the thresholds in config: Rhine "16 cm · Alert: barge transport no longer guaranteed", Watch "· low-water surcharges"; the strike flag says which strike. In the panel the meaning goes as a second small line under the value. | P10 |
| S7 | **Draw the Watch and Alert marks on the Rhine gauge** (150 / 80, and 460 / 640 on the high side) so a low reading is read against its lines. Keep `gauge_max` 700. | P11 |
| S8 | **Plain words for internal terms:** "No AIS" → nothing in v1 ("No ship data" from v2); "Summaries in the batch / by the fallback" → "Summaries: 10 by Claude Sonnet, 0 by the backup model"; "Derived from kept items" → "From the news of the last 14 days"; the PIN gap-check line in plain English ("Couldn't check whether port notices were missed since the last run: there's no earlier run yet"). The failure is still shown (hard rule 9); only its wording changes. | P12 |
| S9 | **Archive legend:** one line above the list ("Squares: today's items by severity · Icons: weather, Rhine, strike"), and on a phone the icons get their short labels as text. | P16 |
| S10 | **Show the brief's "Show on chart" sentence only when at least one item has a place;** add a ▸ arrow to the ship-list header; give the orange button a visible label "Whole port" on wide screens. | P15, P17 |
| S11 | **Panel text a step bigger** (severity, tags and status labels 13–14 px instead of 11–12) and the first tag only if it's a place or a cargo type, or no tag at all in the panel. | P14, P18 |

### Medium

| # | Proposal | Fixes |
|---|---|---|
| M1 | **The chart shrinks when it has nothing to show.** On a day with no placed items (and, in v1, no ships), the chart becomes a short strip (e.g. 30% of the screen on a phone, or the panel full width on a laptop with the chart beside it at half height), with one line "No item has a place on the chart today". Days with pins stay as they are. | P1, P3 |
| M2 | **Phone order: brief first, chart second.** On phones, put the panel head (date, publication line), the item list and the mini status above the chart. The chart then works as the index of a list the reader has already seen. | P3 |
| M3 | **One behaviour for every panel entry.** A click always opens the entry in the panel (summary, or the headline-only line for headline-only items) and moves the chart only if the item has a place. | P13 |
| M4 | **Pins never stack.** In `map.js`, when two of the day's callouts are closer than a number square at the current zoom, put them into one marker ("2 · 4", with both labels on one line), and split them again when zoomed in. Fix the Europoort / Calandkanaal coordinates in `config/places.toml` so they aren't the same point (e.g. Calandkanaal's pin further west along the canal; needs the owner's choice of point). With M4, the fixed `side` per place matters much less. | P20 |
| M5 | **The home view always includes the day's pins.** Fit the home view to the normal port area plus every callout of the day (outside the panel on the laptop), so an item at an anchorage or at Waalhaven is on screen from the start, also on a phone. | P20 |
| M6 | **Callout labels look different from place names** (e.g. a dark label box with the severity colour as its edge), and basemap names step back when a callout covers them. | P19 |

### Large

| # | Proposal | Fixes |
|---|---|---|
| L1 | **An English line for Dutch headline-only items.** These sources are headline-only because of their AI or RSS terms (hard rule 12), but the headline itself already goes to the AI for rating (§2.1). The summariser could add a short English **"what the headline says"** line (at most ~12 words, labelled "AI translation of the headline"), shown under the Dutch headline. **This needs the owner's decision and a spec change:** it is close to hard rule 2 ("no full translations") and to each source's terms (a translated headline is a new use of their headline), and it changes the summariser prompt and its checks. The alternative is to leave it as is and rely on "Read in English". | P5 |
| L2 | **A short "About this project" block for recruiters**, on the Today page below the brief (or as the first section of "How it works"): three sentences (what it does, how: the pipeline 151 → 10 → 5 with the two AI models, who made it and why), the LinkedIn and code links, and a small pipeline diagram. This is the text the LinkedIn post can link to. | P7, P8, P9, P12 |

## Decisions for the owner

Nothing above is built until you approve it. For each proposal, say **yes / no / changed**. The approved ones become new `v1` issues (blocking launch) linked here, grouped so that one issue = one PR. Points that need your own input:

1. **S2:** your LinkedIn URL (I won't look it up). The repo URL is `https://github.com/leonardoneirotti/haven-daily`.
2. **S1 / L2:** the exact wording of the one-line description and of the project text: it's your voice for recruiters.
3. **M1 + M2:** how far to go on the first screen. My recommendation: both, because together they fix the High problems P1 and P3 on the most common v1 day. When ships arrive in v2 (#31), the full-height chart comes back automatically on days with something on it.
4. **M4:** the new point for the Calandkanaal pin (or the Europoort pin), since both are on the same spot now.
5. **L1:** yes or no on an English line for Dutch headlines (a rule question more than a design one).
6. **Optional, your task:** a 5-second test with two or three people (show the Today page for 5 seconds on a phone, then ask "what is this, and who is it for?") before and after the changes. It would turn this review's guesses into observations.

After the approved changes: the new logo and the social preview tags (#28, #29) come next, as planned.
