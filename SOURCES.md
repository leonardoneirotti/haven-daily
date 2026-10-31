# Candidate sources — to test before building

None of these are confirmed yet. For each one, check: is there an RSS feed or clean page? How much text do we get? What do the terms and robots.txt allow? Then mark it **use / headline-only / drop**.

## Official and operational (highest value)

| Source | What it gives | Notes |
|---|---|---|
| Port of Rotterdam Authority — news & press releases | Official news, filterable by theme (accessibility, safety, etc.) | portofrotterdam.com/en/news-and-press-releases. No RSS seen; check terms. Mixed content, needs filtering. |
| Port of Rotterdam — Port Performance | Anchorage waiting times (Rotterdam, Antwerp, Hamburg, Bremerhaven), Barge Performance Monitor | portofrotterdam.com/en/logistics/port-performance. Possibly charts only. Status line, later. |
| Port of Rotterdam — notices to shipping | Nautical notices | pin.portofrotterdam.com |
| Port of Rotterdam — weather, tide and water depth / arrivals & departures | Current info | Check what is machine-readable. |
| Contargo business news | Barge waiting times, terminal capacity limits, terminal system changes, Rhine low-water updates | contargo.net/en/business/business-news. Very planner-relevant. |
| Terminal operators' customer notices (ECT, APM Terminals, RWG, etc.) | Closures, restrictions | Check each site. |
| KNMI | Weather warnings | Look for an open data feed/API. Status line v1. |
| Rhine water levels (Kaub, Lobith) | Barge capacity | German and Dutch government water-level services; look for open APIs. Status line v1. |
| Rijkswaterstaat | Road works / closures (A15) | Later. |
| ProRail | Rail disruptions (Betuweroute) | Later. |

## News — summary + link

| Source | Notes |
|---|---|
| Google News RSS searches (EN + NL) | e.g. "Port of Rotterdam", "haven Rotterdam", "haven Rotterdam staking", "Maasvlakte", "ECT Rotterdam", "APM Terminals Rotterdam", "container congestion Rotterdam" |
| PortsEurope | Rotterdam category pages |
| NL Times | Rotterdam port tag |
| DutchNews.nl | English Dutch news |
| Tradlinx blog | Rotterdam tags |
| Kuehne+Nagel SeaNews | Weekly port operational updates (global) |

## Headline + link only, or skip (paywalled / restrictive)

Lloyd's List, The Loadstar (states reproduction or rewriting needs a licence), JOC, Nieuwsblad Transport, TradeWinds.

## Version 2 (ship map)

| Source | Notes |
|---|---|
| aisstream.io | Free AIS WebSocket API, subscribe by bounding box, API key via GitHub sign-in. Reported beta/instability and 1–3 min lag on free tier. Check terms for public display. |
| searoute (Python package) | Estimated sea routes for visualisation, not navigation. |
