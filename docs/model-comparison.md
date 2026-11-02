# Summariser model: Haiku 5.5 vs Sonnet 5.5

*Issue #17 · spec §5.5, §10 step 6 · run on Monday 2 November 2026, 02:28 Amsterdam time.*

**Owner's decision: pending** (checklist #43). Haiku 5.5 is the default unless Sonnet 5.5 is clearly better (§5.5).

## How it was run

- `python -m haven.compare --max-age-days 7 --max-items 15` (`haven/compare.py`): collect → relevance filter (rules, then Haiku 5.5) → article text in memory → **the same 15 kept items summarised by both models**, through the summariser the morning job uses (`haven.summarise.summarise`: same prompt, same checks, effort `medium`, standard API). Nothing was written to `data/`.
- **A 7-day age limit instead of 48 h, for this comparison only** *(owner's choice, 2 Nov 2026)*. At 02:20 on a Monday the 48 h rule left 0 auto-kept items and 39 headline-only ones (mostly RTV Rijnmond city news): no summaries to compare. With 7 days, 23 items were kept; the first 15 in config order were compared (cap set before the run so the cost could be approved: estimate ≤ $0.34).
- **Facts were checked against the sources by Claude**, reading each article in memory (never saved, hard rule 13). The script's "Words not in the source" row helps: numbers and names in the AI's text that the article doesn't contain. Most hits are month names (PIN notices write dates as `30-10-2026`) and are fine.
- Severity was judged against §2.1 **as of the run date**: every PIN notice here had already ended by 2 November.

## Result

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Items rated | 15 of 15 | 14 of 15 (item 1 unrated: copied words even after the rephrase retry) |
| Fact errors | 2: items 2 and 7 read a notice's *end date* as the moment the measure was lifted | 2: item 6 the same misreading; item 10 spells Moerdijk "Moerijk" |
| Severity as §2.1 (my reading) | 7 of 15. Ended fog/pilot notices rated **High 3×, Medium 4×** | 13 of 14 rated. One ended notice rated Medium (item 10) |
| Impact on ended notices | Often still tells planners to "build in extra time" / "expect delays" (items 5, 8, 9) | Says the notice has ended and no action is needed (all 10) |
| Impact on live items (12–15) | Useful, specific | Useful, specific; about equal |
| Tag mistakes | 2: item 1 (energy-transition profile) tagged *Sea access · Hinterland*; item 2 *Hinterland* from the PIN area name. Earlier batch test (PR #65): *Sea access* on a terminal strike | 1 small: item 13 *Rhine*, which the article doesn't mention |
| Cost, this run (standard API) | **$0.0114** (15 calls, 48,474 in / 13,014 out) | **$0.1357** (16 calls, 53,249 in / 2,921 out) |
| Per item, standard / batch | $0.00076 / ~$0.00038 | $0.0090 / ~$0.0045 |
| Per month at 12 items/day, batch | ~$0.14 | **~$1.63** (spec estimate was $2.90: Sonnet used far fewer output tokens than assumed) |

Total cost of the comparison run, filter included: **about $0.155** at list prices (filter $0.0083: 73 calls).

### What the differences mean for the page

- **Severity is where they differ most, and it is what readers see first**: the brief sorts by severity and shows at most 5 items. With Haiku, three fog and pilot notices that had already ended would have been High, at the top of the page, above the 77-hour barge waiting time in Rotterdam. Sonnet rated all but one of them Low.
- **Facts: a draw.** Both misread the PIN notice layout once or twice ("End Date" is when the *notice* ends, not when the measure changed). That is a prompt problem as much as a model problem.
- **Tags: Haiku uses "Sea access" as a filler** (a profile article, and the terminal strike in PR #65). The tag list in the prompt gives names only, no meanings, so "Sea access" and "Hinterland" are guessed from the word.
- **Copy check:** Sonnet lost one quote-heavy profile to the own-words check (after its retry); Haiku none. The check is doing its job (hard rule 13); an unrated item is shown as headline + link.
- **Cost:** both fit the €5/month budget easily (filter ~$0.18 + Sonnet batch ~$1.63, before the Haiku fallback on slow-batch days, which is cheaper).

### Limits of this test

- One run, 15 items, **10 of them PIN notices** (the cap took items in config order). No Dutch items, no strike items and no headline-only items were compared (the 8 kept items over the cap were mostly headline-only: listed at the end).
- The items were 0–7 days old, so more of them had already ended than on a normal 06:45 morning, which makes the severity difference larger than a 48 h day would.
- Standard API, not the batch: the batch sends exactly the same request (§5.5), so the answers should be alike; the cost is half.

## Claude's recommendation (not a decision)

**Sonnet 5.5**, through the batch as built (#16), because its advantage is consistent where it matters most (severity and impact of time-limited items, 9 of 10 notices) and the measured cost (~$1.63/month in batch) is well inside the budget. Two prompt fixes help whichever model is chosen, and could be a small follow-up (proposed in the PR, not done here):

1. **A one-line meaning for each "affects" tag** in `config/tags.toml`, sent with the list (e.g. *Sea access: ships reaching or leaving the port by sea: fairways, pilots, tugs, anchorages, barriers, fog; not work on the quay*).
2. **Severity of something that has already ended by today is Low**, and PIN notices: "End Date" is when the notice ends, not when the measure changed.

If you prefer to keep Haiku, these two fixes plus a short re-run (~$0.02) would show whether Haiku closes the gap.

## Side by side

Run on 2026-11-02: 15 kept items, each summarised by Haiku 5.5 and Sonnet 5.5 (standard API, the same request).

### 1. “I’m in a hurry to leave a positive mark”

https://www.portofrotterdam.com/en/news-and-press-releases/im-hurry-leave-positive-mark · Port of Rotterdam Authority news & press releases · 2026-10-27T11:36:26+01:00 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | low | unrated |
| Place | none | none |
| Tags | Sea access · Hinterland | none |
| Summary | A profile of the Port of Rotterdam Authority's New Energies Manager, who works on making energy and product flows through the port more sustainable, with a focus on green ammonia and hydrogen. | — |
| Impact | Not enough information | — |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | none | none |
| Failures | none | summary copies the article (10+ words in a row) (after a retry) |

### 2. Visibility Arrangement - De-activate

https://pin.portofrotterdam.com/pin-16800 · PIN notices to shipping · 2026-10-31T03:45:02+01:00 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | low | low |
| Place | none | none |
| Tags | Hinterland · Sea access | Sea access |
| Summary | Port authorities have lifted a visibility-related traffic arrangement covering the city hinterland area. The lifting took effect on 1 November 2026 at 02:47, so it is already over as of today. | The Port of Rotterdam's Harbour Coordination Center reported that the Visibility Arrangement has been de-activated for the City Hinterland area. The notice carries an end date of 1 November 2026 at 02:47. |
| Impact | The arrangement's end time has already passed, so no action is needed for movements in the city hinterland area. Planners may still want to confirm current conditions with the Harbour Coordination Center if they expect any residual restrictions. | Visibility restrictions on shipping in the City Hinterland area have been lifted, so vessel movements there should no longer face fog-related limits. The notice is already past its end date, so no action is needed. |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | November | Port, November |
| Failures | none | none |

### 3. Visibility Arrangement - Activate

https://pin.portofrotterdam.com/pin-16799 · PIN notices to shipping · 2026-10-31T00:23:20+01:00 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | high | low |
| Place | none | none |
| Tags | Sea access | Sea access |
| Summary | The Port of Rotterdam put a low-visibility measure in place overnight on 31 October, covering a hinterland area where visibility was forecast below 500 metres. The window closed at about 03:43 that morning. | A visibility arrangement was activated for the Hinterland and City areas of the port because visibility is, or is expected to be, under 500 meters. The notice ran until 03:43 on 31 October 2026. |
| Impact | Vessels requiring towage were to be assessed case by case with the Port Authority, pilots and tug operators, and all movements were to be reviewed if visibility fell under 200 metres. Planners with arrivals or departures in that window should check schedules for delays, though the period has already passed. | The notice had already expired by today, 2 November, so it requires no action now. While it applied, vessels needing tugs were assessed case by case for safe manoeuvring, which could have delayed some movements. |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | October | October, 2, November |
| Failures | none | none |

### 4. Visibility Arrangement Hinterland - Activate

https://pin.portofrotterdam.com/pin-16798 · PIN notices to shipping · 2026-10-30T23:58:28+01:00 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | medium | low |
| Place | Oude Maas | Oude Maas |
| Tags | Sea access · Hinterland · Oude Maas | Barge · Hinterland · Sea access · Oude Maas |
| Summary | Fog-related measures were activated for the hinterland because visibility is under one kilometre. Vessels on the Oude Maas near Dordrecht and Moerdijk get heightened attention, and tug and pilot decisions are reviewed as visibility drops further. | A fog-related visibility arrangement was activated for the Hinterland area, with visibility under 1000 meters. The notice was posted late on 30 October and shows an end time of 31 October, 03:43. |
| Impact | The stated window ended on 31 October, so these restrictions should have lapsed by today. Planners using the Oude Maas should still check with the Harbour Coordination Center if fog returns, since tug and pilot reviews may then apply to vessels needing assistance. | The arrangement had ended by 31 October, so it no longer applies today. While it was active, vessels on the Oude Maas, Dordrecht and Moerdijk stretch could face extra caution, and manoeuvres of tug-assisted ships could be reviewed if visibility dropped further. |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | October | October |
| Failures | none | none |

### 5. Capacity Arrangement Pilots - Activate

https://pin.portofrotterdam.com/pin-16797 · PIN notices to shipping · 2026-10-30T21:15:33+01:00 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | high | low |
| Place | none | none |
| Tags | Sea access | Sea access |
| Summary | Pilot capacity arrangement was activated in Rotterdam after a surge in pilot demand, so ship boarding may take three hours or longer. The arrangement was scheduled to end in the early hours of 1 November. | A pilot capacity arrangement was switched on at the Port of Rotterdam on 30 October because pilot demand jumped. Boarding can take up to three hours or more, and agents are told if an earlier slot opens up. The notice ran until 1 November. |
| Impact | Vessel calls may face pilot boarding waits of three hours or more, so planners should build in extra time. Agents can request an earlier boarding, and the Harbour Coordination Center can confirm current status. | The notice has already expired, so no delays follow from it today. Planners can note that such demand surges can hold up vessel arrivals and departures, and should check with their agent or the Harbour Coordination Center if timing matters. |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | November | Port, October, November |
| Failures | none | none |

### 6. Capacity Arrangement Pilots - De-activate

https://pin.portofrotterdam.com/pin-16796 · PIN notices to shipping · 2026-10-30T14:41:43+01:00 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | low | low |
| Place | none | none |
| Tags | Sea access | Sea access |
| Summary | The port's temporary pilot capacity arrangement was switched off on 30 October, and pilotage for all vessels has returned to regular operation. | The temporary capacity arrangement for pilot services in the Port of Rotterdam was lifted on 30 October 2026 at 21:15. Pilotage for all vessels in all areas has returned to normal operation. |
| Impact | Planners can drop the extra pilotage allowances they built in for the temporary arrangement and plan vessel windows on standard pilot availability. The notice is past its end date, so no further action seems needed beyond checking with the Harbour Coordination Center if a specific call is still affected. | Pilot availability is back to normal, so vessels should no longer face restrictions from the capacity arrangement. Planners can resume standard scheduling; the Harbour Coordination Center can answer questions. |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | October | Port, October |
| Failures | none | none |

### 7. Visibility Arrangement - De-activate

https://pin.portofrotterdam.com/pin-16795 · PIN notices to shipping · 2026-10-30T10:42:28+01:00 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | medium | low |
| Place | none | none |
| Tags | Sea access | Sea access |
| Summary | The port authority reports that a low-visibility arrangement has been lifted in several Rotterdam zones, including Maasvlakte, Europoort, Botlek and the city hinterland, with the lifting in effect from the evening of 30 October. | The Harbour Coordination Center has switched off the Visibility Arrangement, which covers Maasvlakte 1 and 2, Europoort West and East, Botlek, City and Hinterland. The notice was posted on 30 October 2026 with an end time of 21:17. |
| Impact | Vessel and barge moves in the listed zones are no longer under this visibility restriction from the evening of 30 October. The item gives no detail on the wider traffic picture, so check with the Harbour Coordination Center for specifics. | Restrictions linked to reduced visibility no longer apply in these areas, so vessel movements should be back to normal. This notice is already a few days old, so it matters only for checking past delays. |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | October | October |
| Failures | none | none |

### 8. Visibility Arrangement - Activate

https://pin.portofrotterdam.com/pin-16794 · PIN notices to shipping · 2026-10-30T06:13:04+01:00 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | high | low |
| Place | Europoort | Europoort |
| Tags | Sea access · Europoort | Sea access · Europoort · Botlek |
| Summary | Port authorities activated a low-visibility regime covering Europoort West, Europoort East and Botlek City, with visibility below 500 metres expected. Vessels needing tugs will be reviewed case by case with pilots and tugs, and all ships reviewed if visibility drops under 200 metres. | A fog-related visibility arrangement was activated for Europoort West, Europoort East and Botlek City because visibility there is, or is expected to be, under 500 meters. The notice ran until the evening of 30 October 2026. |
| Impact | Expect possible delays to vessel movements in these three areas while visibility stays poor, especially for ships needing tugs. Contact the Harbour Coordination Center to confirm status and timing before planning moves. | Vessels needing tugs in these areas may face delays while safe manoeuvring is assessed. The notice dates from 30 October and its end time has passed, so it likely no longer applies today. |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | none | October |
| Failures | none | none |

### 9. Visibility Arrangement - Activate

https://pin.portofrotterdam.com/pin-16793 · PIN notices to shipping · 2026-10-30T05:34:27+01:00 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | medium | low |
| Place | none | none |
| Tags | Sea access | Sea access |
| Summary | The port authority put a low-visibility arrangement in force for the City area because visibility fell below 500 metres. It was scheduled to end at 06:14 on 30 October 2026, so it has already lapsed. | A fog-related Visibility Arrangement was activated for the City area of the port on 30 October, with visibility below 500 meters. Vessels needing tugs are assessed individually, and below 200 meters all vessels are assessed. The notice ended at 06:14 the same day. |
| Impact | Vessels needing tugs were to be reviewed case by case with the Port Authority, pilots and tugs, and all vessels were to be reassessed if visibility dropped under 200 metres. Planners should expect possible delays to sea-access movements during similar fog episodes and can contact the Harbour Coordination Center for current status. | The notice was only in force briefly on 30 October and has already ended, so no ongoing restrictions apply today. Any delays were limited to vessel movements in the City area that morning. |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | October | October |
| Failures | none | none |

### 10. Visibility Arrangement Hinterland - Activate

https://pin.portofrotterdam.com/pin-16792 · PIN notices to shipping · 2026-10-30T05:14:34+01:00 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | medium | medium |
| Place | none | Oude Maas |
| Tags | Sea access · Barge · Hinterland | Barge · Hinterland · Sea access · Oude Maas |
| Summary | Rotterdam's low-visibility arrangement was activated for the hinterland, where visibility is below 1,000 metres. It ended on 30 October at 21:16. | A fog-related visibility arrangement was activated for the Hinterland area on 30 October 2026, with visibility under 1000 meters. It was set to end that evening at 21:16. |
| Impact | Vessels near the Oude Maas, Dordrecht and Moerdijk need closer attention, and tug use is reviewed when visibility falls below 500 metres. The measure has already lapsed, so confirm current status with the Harbour Coordination Center before planning movements. | The notice was only valid on 30 October and has already lapsed, so there is no action now. While it lasted, vessels on the Oude Maas towards Dordrecht and Moerijk faced extra caution, and tug-assisted moves could need case-by-case approval. |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | 1,000, October | October, Moerijk |
| Failures | none | none |

### 11. Capacity Arrangement Pilots - Activate

https://pin.portofrotterdam.com/pin-16791 · PIN notices to shipping · 2026-10-29T22:58:53+01:00 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | medium | low |
| Place | none | none |
| Tags | Sea access | Sea access |
| Summary | Pilotage capacity measures were switched on because demand for pilots spiked, so ships may wait three hours or more for a pilot to come aboard. The measure was set to end on 30 October 2026. | Rotterdam activated its pilot services capacity arrangement because pilot demand surged. Boarding can take three hours or more, and agents are told if an earlier slot opens up. The notice ran until 30 October 2026, 21:17. |
| Impact | Vessels calling at Rotterdam could face long waits before pilot boarding, so arrival windows need extra buffer. Agents can ask the Harbour Coordination Center for an earlier boarding. The listed end date has passed, so confirm with the centre whether the delays still apply. | The notice has expired as of today, 2 November, so it likely no longer applies. It shows that vessels needing a pilot may wait hours, which can push back arrivals and downstream planning when such arrangements are active. |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | October | October, 2, November |
| Failures | none | none |

### 12. Current Low Water Levels – Important Information for Our Customers

https://www.contargo.net/en/business/business-news/detail-business/current-low-water-levels-important-information-for-our-customers-1/ · Contargo business news · 2026-10-30 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | medium | medium |
| Place | none | none |
| Tags | Rhine · Barge · Hinterland · Containers | Barge · Rhine · Containers · Hinterland |
| Summary | Contargo reports sharply falling river levels at several Rhine gauges and has introduced extra charges for barge container moves at its inland terminals, valid until further notice. It also states the level below which it will stop accepting transport on each stretch. | Contargo reports falling Rhine water levels at the Emmerich, Duisburg-Ruhrort, Cologne and Kaub gauges. It applies low-water surcharges at set thresholds and warns of short-notice operational measures. |
| Impact | Rotterdam container shipments routed by Rhine barge to German inland terminals may face higher costs and possible service cuts if levels keep dropping. Planners should check the surcharges and cut-off levels before booking Rhine legs. | Rhine container barge transport to and from Rotterdam's hinterland faces extra costs and possible disruption. Planners should check daily gauge updates and surcharges, and note that Contargo's transport obligation ends at the stated lowest gauge levels. |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | German | none |
| Failures | none | none |

### 13. UPDATE: Congestion in Antwerp and Rotterdam

https://www.contargo.net/en/business/business-news/detail-business/update-congestion-in-antwerp-and-rotterdam-4a4207cc50de17036f257d83b43d445a/ · Contargo business news · 2026-10-30 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | high | medium |
| Place | none | none |
| Tags | Barge · Hinterland | Barge · Containers · Rhine · Hinterland |
| Summary | Barge operator reports that waiting times for barge handling have risen at both ports, reaching about 77 hours in Rotterdam and 48 hours in Antwerp. | Contargo reports congestion at the seaports. Its barges currently wait about 48 hours for handling in Antwerp and about 77 hours in Rotterdam. |
| Impact | Barge schedules calling at Rotterdam should allow for much longer dwell times and build buffer into planning, as the wait there is considerably longer than in Antwerp. | Barge cargo through Rotterdam faces long handling waits, so planners should allow extra time for inland barge legs and consider this in schedules. The item gives no cause or expected end date. |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | none | none |
| Failures | none | none |

### 14. Impact of the Storm Systems on Rail Transport

https://www.contargo.net/en/business/business-news/detail-business/impact-of-the-storm-systems-on-rail-transport/ · Contargo business news · 2026-10-26 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | medium | medium |
| Place | none | none |
| Tags | Rail · Hinterland | Rail · Hinterland · Containers |
| Summary | Two storms, named Manja and Luise, hit train operations in Germany, the Netherlands and Belgium over the previous weekend. Trees brought down onto lines and terminal shutdowns from gusts caused the disruption. Winds have eased, but recovery is expected to take several more days. | Two storms hit rail services across Germany, the Netherlands and Belgium over the weekend, with trees on tracks and terminals shut by strong winds. Weather has calmed, but Contargo says rail operations need several more days to settle. |
| Impact | Rail freight to and from Rotterdam may face backlogs, delays and possibly cancellations over the coming days. Planners should build in buffer time and confirm rail slots with operators before dispatching cargo. | Expect delayed rail shipments and possible cancellations on Rotterdam hinterland routes while train and equipment rotations recover. Planners should allow extra transit time and check with Contargo about specific rail bookings. |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | none | Contargo |
| Failures | none | none |

### 15. Update (2) Mandatory Safety Test for Drivers

https://www.ect.nl/en/news/news-feed/update-2-mandatory-safety-test-drivers · ECT news · 2026-10-30 · full article

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Severity | medium | medium |
| Place | ECT Delta | none |
| Tags | Truck pickups · Containers · Hinterland · ECT Delta | Truck pickups · Containers · ECT Delta · Euromax |
| Summary | ECT has pushed back the driver safety test deadline to 5 January 2027 while it rolls out a new system called TCMS. The test is still required, and drivers without a valid result will be refused entry to ECT Delta and Euromax from that date. | ECT has pushed back the start of the compulsory driver safety test and its enforcement to 5 January 2027, after talks with the industry association. The requirement remains in force, and the recent TCMS rollout was also cited as a reason. |
| Impact | Truck drivers who serving ECT Delta or Euromax should book their safety test now rather than leave it late, since those without a valid result will be denied access in January 2027. Drivers who have already passed need no action yet, but their validity period will be adjusted later. | Truck drivers without a valid safety test will be refused entry to ECT Delta and Euromax from 5 January 2027. Hauliers should have drivers book tests soon to avoid last-minute scheduling bottlenecks; drivers who already passed need do nothing now. |
| Strike | none | none |
| Off the lists | none | none |
| Words not in the source | none | none |
| Failures | none | none |

### Calls, tokens and cost (this run)

| Model | Calls | Tokens | Cost (list price) |
|---|---|---|---|
| Haiku 5.5 | 15 | 48,474 in / 13,014 out | $0.0114 |
| Sonnet 5.5 | 16 | 53,249 in / 2,921 out | $0.1357 |

### Not compared (8 kept items over the cap)

- Port operational updates from around the world (21 Oct - 27 Oct 2026): https://mykn.kuehne-nagel.com/news/article/port-operational-updates-from-27-10-2026
- North Sea Port boekt hoogste kwartaaloverslag in vier jaar: https://www.nt.nl/havens/2026/10/28/north-sea-port-boekt-hoogste-kwartaaloverslag-in-vier-jaar/
- Rotterdam en Andalusië leggen waterstofsamenwerking vast tot 2029: https://www.nt.nl/havens/2026/10/27/rotterdam-en-andalusie-leggen-waterstofsamenwerking-vast-tot-2029/
- Havenwethouder Rotterdam: ‘Voor veel bedrijven is het bijna logisch om hier de tent op te doeken’: https://www.nt.nl/havens/2026/10/26/havenwethouder-rotterdam-voor-veel-bedrijven-is-het-bijna-logisch-om-hier-de-tent-op-te-doeken/
- News in Brief Podcast \| Week 43 \| Reliability, rates and port fee delay: https://theloadstar.com/news-in-brief-podcast-week-43-reliability-rates-and-port-fee-delay/
- EXCLUSIVE: CargoWise customs message delays leave forwarders waiting for clearance: https://theloadstar.com/exclusive-cargowise-customs-message-delays-leave-forwarders-waiting-for-clearance/
- A platform to challenge ‘death by a thousand [D&D] invoices’: https://theloadstar.com/a-platform-to-challenge-death-by-a-thousand-dd-invoices/
- Carriers’ November rate hikes ‘doomed’ say analysts, as demand goes flat: https://theloadstar.com/carriers-november-rate-hikes-doomed-say-analysts-as-demand-goes-flat/
