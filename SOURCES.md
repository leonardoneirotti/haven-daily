# Sources: final v1 list

Tested 31 Oct 2026. Verdicts and reasons: `docs/SPEC.md` §4. Full test evidence (quoted robots.txt and terms lines): `docs/source-tests-2026-10-31.md`.

- **use**: headline + link + own-words AI summary.
- **headline-only**: headline + link, shown like a paywalled item. The article text never goes to an AI (hard rule 12); the headline may go through the AI relevance filter.
- **auto-keep**: skips the AI relevance check (§5.4).

Tested from a desktop, not from GitHub Actions IPs. Some sites may still block the job.

## Use

| Source | URL | Notes |
|---|---|---|
| Port of Rotterdam Authority news & press releases | https://www.portofrotterdam.com/en/news-and-press-releases | HTML list. Auto-keep. `/en/rss.xml` is stale, don't use it. |
| PIN notices to shipping | https://pin.portofrotterdam.com/rss.xml | RSS, full notice text. 40–60/week, noisy: AI check. Feed keeps only ~10 items. |
| Contargo business news | https://www.contargo.net/en/business/business-news | HTML. AI check. |
| ECT news | https://www.ect.nl/en/news-feed | HTML. Auto-keep. `/en/rss.xml` is stale. |
| Kuehne+Nagel SeaNews | https://mykn.kuehne-nagel.com/news | HTML. Rotterdam paragraph of the weekly port update only. **Terms not found yet: check before launch.** |

## Headline-only

| Source | URL | Notes |
|---|---|---|
| NL Times | https://nltimes.nl/tags/port-rotterdam | Blocks AI crawlers. Use the port tag page (HTML), not the site-wide feed `rssfeed2`, which keeps only ~10 items. |
| Nieuwsblad Transport | https://www.nt.nl/havens/feed/ · https://www.nt.nl/tag/rotterdam/feed/ | Paywalled, blocks AI crawlers, `ai-train=no`. Ignore the body text in the feed. |
| PortsEurope | https://www.portseurope.com/category/rotterdam/feed/ | Subscription site, blocks AI crawlers. |
| The Loadstar | https://theloadstar.com/feed/ | Main feed only (robots disallows tag/category pages). Terms allow RSS for links back. |
| RTV Rijnmond | https://www.rijnmond.nl/rss/nieuws | Blocks ClaudeBot and ~130 other bots. **Terms not found yet: check before launch.** |

## Status line

| Source | URL | Notes |
|---|---|---|
| Weather warnings: MeteoAlarm (KNMI's warnings) | https://feeds.meteoalarm.org/api/v1/warnings/feeds-netherlands | No key. Use the Zuid-Holland warning. Terms §5 (read 31 Oct 2026): show "KNMI", time of issue, link to www.meteoalarm.org, their exact disclaimer, original level + hazard. Real-time (≤ 10 min) required for operational use: label "Warnings at 06:45 · not live" until MeteoAlarm answers. https://meteoalarm.org/en/live/page/terms-and-conditions |
| Weather warnings: KNMI (later) | https://developer.dataplatform.knmi.nl/open-data-api | Switch when `KNMI-public-weather-warnings` leaves TEST. Free registered key (`KNMI_API_KEY`). |
| Rhine, Kaub (PEGELONLINE): shown | https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations/KAUB/W.json?includeCurrentMeasurement=true&includeCharacteristicValues=true | No key. Thresholds from its official values (GlW, MNW, Marke I/II). |
| Rhine, Lobith (Rijkswaterstaat): stored only | https://ddapi20-waterwebservices.rijkswaterstaat.nl | No key. Use `OphalenWaarnemingen` over a recent window. |

## Dropped

| Source | Reason |
|---|---|
| Google News RSS | robots.txt disallows `/rss/`; feed terms: personal feed reader, non-commercial use only. |
| NOS | Terms art. 6.1 forbid automated access by bots without permission; art. 7 limits RSS to private personal use. |
| DutchNews.nl | robots.txt disallows `/feed/`. |
| Lloyd's List | robots.txt disallows `/rss/`. |
| RWG | Terms: no use without prior written permission. |
| JOC | No Rotterdam items. |
| APM Terminals Maasvlakte II | Private API only. |
| TradeWinds | No official feed; blocks AI crawlers. |
| Tradlinx | Korean only. |
| Port Performance | No public API or licence. |

## Version 2 (ship map)

| Source | Notes |
|---|---|
| aisstream.io | Free AIS WebSocket, bounding box, API key via GitHub sign-in. Beta, 1–3 min lag. **Check terms for public display.** |
| searoute (Python package) | Estimated sea routes for visualisation, not navigation. |
