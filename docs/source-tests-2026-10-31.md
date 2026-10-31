# Haven Daily – source test report

Tested 2026-10-31 (Sat), from a Windows desktop with curl (browser-like User-Agent) and WebFetch/WebSearch. Results from GitHub Actions IPs may differ, especially behind Cloudflare. "Uncertain" means not verified.

## Summary table

| Source | Access type | Text per item | robots / terms verdict | Recommendation |
|---|---|---|---|---|
| PoR news & press releases | HTML list (`/en/news-and-press-releases`). `/en/rss.xml` exists but is a stale Drupal front-page feed | List: headline + date + category. Article: full text | robots OK. Copyright page says "not permitted to reproduce content" | **Use**: headline + link + own-words summary, never copy text |
| PoR notices to shipping (PIN) | **RSS** `https://pin.portofrotterdam.com/rss.xml` | Full notice text + date, EN | robots OK. No terms on the PIN site | **Use**: best operational signal, needs filtering (very noisy) |
| PoR Port Performance | HTML + undocumented internal JSON (`/en/por_ppi/api/{type}`) | Numbers (anchorage, TEU, efficiency) | Not a public API. PoR copyright clause applies | **Drop** (at most a manual link; don't call the internal API) |
| Contargo business news | HTML only | Headline + 1–2 sentence teaser + date, EN | No robots.txt (404). Imprint has no reuse clause | **Use** (gentle HTML scrape, own-words summary) |
| ECT (Hutchison Ports) | HTML `/en/news-feed`; `/en/rss.xml` is stale | Headline + teaser + date | robots OK. Disclaimer: no reproduction without written consent | **Use, headline + link + short own summary** |
| APM Terminals Maasvlakte II | HTML shell; list loads via JS from `api.apmterminals.com` with an embedded key | Headline + date (via JS) | robots OK. T&C 10.2 bans hyperlinks, but only for registered users (uncertain if it covers the public) | **Drop** (low volume, private API) |
| Rotterdam World Gateway | HTML `/en/news` | Headline + day/month (no year in list) | robots OK. ToU: content "may not be used without prior written permission" | **Headline-only, low priority** (≈1 item/month) |
| KNMI warnings | Open Data API (key needed) | Warning files (TXT/XML; new: CAP XML + JSON) | CC-BY 4.0. Anonymous key was rate-limited all day | **Use, with your own free registered key**. Note dataset change (below) |
| PEGELONLINE Kaub | REST JSON, no key | Value + timestamp + low/normal state, every 15 min | DL-DE->Zero-2.0, no robots.txt | **Use** |
| RWS Lobith | REST JSON (POST), no key | Water level, 10-min values + forecast | CC0. Optional `X-API-KEY` header | **Use** |
| Google News RSS | RSS | Headline + publisher + date. Links are Google redirect URLs | robots.txt **disallows `/rss/`**. Feed copyright: "personal, non-commercial use … Any other use … expressly prohibited" | **Drop** |
| PortsEurope | **RSS** `/category/rotterdam/feed/` | Headline + ~450-char teaser + date | Paid subscription site. robots `Content-Signal: search=yes, ai-train=no, use=reference` | **Headline-only** |
| NL Times | RSS (site-wide only) `https://nltimes.nl/rssfeed2`. Tag pages are HTML | Headline + ~100–160-char snippet | robots blocks AI bots (anthropic-ai, GPTBot…), generic OK. Terms page is an empty placeholder | **Use, filtered** (low port volume) |
| DutchNews.nl | RSS `/feed/` exists | Headline + short teaser | **robots.txt `Disallow: /feed/` for all bots** | **Drop** |
| Tradlinx blog | RSS `/blog/feed/` | Korean headline + teaser | robots OK | **Drop** (Korean, ~0 Rotterdam items) |
| Kuehne+Nagel SeaNews | HTML only `mykn.kuehne-nagel.com/news` | Headline + teaser. Article full text public | robots `Allow: /news`. Terms not found (uncertain) | **Use, headline + link + own summary**. Weekly "Port operational updates" has a Rotterdam paragraph |
| Lloyd's List | RSS `/rss/lloyds-list` | Headlines | **robots `Disallow:/rss/`**. Feed page needs sign-in | **Drop** |
| The Loadstar | RSS `https://theloadstar.com/feed/` | Headline + ~550-char excerpt | Terms: "You may use our RSS feeds to create links back to our website" | **Headline-only** (allowed; low Rotterdam volume) |
| JOC | RSS `https://www.joc.com/rssfeed` (40 items) | Headline + ~150-char dek | robots OK. T&C has no RSS/linking clause, bans reproduction | **Headline-only, optional** (0 Rotterdam items in a week's sample) |
| Nieuwsblad Transport | RSS on **nt.nl**: `https://www.nt.nl/havens/feed/`, `/tag/rotterdam/feed/` (nieuwsbladtransport.nl is Cloudflare-blocked) | Feed carries excerpt **and** content:encoded body | robots: generic OK, AI bots blocked, `Content-signal: search=yes, ai-train=no`. No reuse clause found | **Headline-only**. Best Dutch volume (~5–6 Rotterdam items/week) |
| TradeWinds | No official feed found | – | robots: generic OK, AI bots blocked | **Drop** |

---

## 1. Port of Rotterdam Authority – news & press releases
- **Access:** HTML list at `https://www.portofrotterdam.com/en/news-and-press-releases`. It has 10 items with `datetime` attributes, headline, date and category. There is no snippet.
- **The feed is not usable:** `https://www.portofrotterdam.com/en/rss.xml` (and `/nl/rss.xml`) return valid RSS 2.0, but:
  - It is the Drupal front-page feed: 10 items, newest 23 Jul (EN) and 7 Sep (NL), while the HTML list has items up to 27 Oct 2026.
  - The `/en/` feed has Dutch titles linking to `/nl/` URLs.
  - The descriptions hold the whole rendered page HTML.
- **Text / date / language:** Article pages have full text. Date is in `<time datetime>`. EN and NL versions both exist.
- **robots.txt:** `User-agent: *` disallows only `/core/`, `/profiles/`, `/admin/`, `/search/`, `/user/*` and similar. The news paths are allowed. No AI-bot rules.
- **Terms:** <https://www.portofrotterdam.com/en/copyright>: "It is not permitted to reproduce content found on this website and our social media channels by printing it out, downloading and/or distributing it among third parties." The disclaimer (<https://www.portofrotterdam.com/en/disclaimer>) has nothing on scraping or RSS.
  - **Uncertain:** whether an own-words summary counts as "reproducing". Headline + link + a short original summary looks lowest-risk.
- **Volume:** 10 items from 17 Sep to 27 Oct, about 1.5–2 per week, all Rotterdam-relevant.
- **Recommendation: Use.** Scrape the HTML list for headline/date/link, then fetch the article only to write an original summary.

## 2. Port of Rotterdam – Port Information Notices (pin.portofrotterdam.com)
- **Access:** **RSS** at `https://pin.portofrotterdam.com/rss.xml` (application/rss+xml, `<language>en</language>`).
  - The homepage HTML lists both "PIN" and "BAS" (Dutch *Berichten aan de Scheepvaart*) messages with start/end dates and a filter. 83 active messages today.
  - The RSS seemed to carry only PIN items in today's sample.
  - **Uncertain:** whether BAS notices ever appear in the RSS.
- **Text:** Full notice text in `<description>` (HTML). Has `pubDate`. English.
  - Sample titles: "Visibility Arrangement - Activate/De-activate", "Capacity Arrangement Pilots - Activate".
- **robots.txt:** Standard Drupal file. Only `/core/`, `/profiles/`, `/admin/`, `/search/`, `/user/*` are disallowed, so `/rss.xml` is allowed.
- **Terms:** None on the PIN site. The site links to portofrotterdam.com, whose copyright clause (above) presumably applies (uncertain).
- **Volume:** 10 RSS items in ~29 hours (29 Oct 21:58 to 31 Oct 02:45 UTC), so roughly 40–60+ per week. Most are routine fog and pilot-capacity toggles. The feed shows only the last 10, so a once-a-day fetch will miss items on busy days.
- **Recommendation: Use.** Filter or aggregate: for example, collapse a day's "Visibility Arrangement" toggles into one "fog restrictions overnight" item. Consider polling more than once a day, or accept the gaps.

## 3. Port of Rotterdam – Port Performance page
- **Access:** `https://www.portofrotterdam.com/en/logistics/port-performance` is HTML with Highcharts. The script `/modules/custom/por_ppi/js/src/por_ppi.js` calls `https://www.portofrotterdam.com/{lang}/por_ppi/api/{anchorage|throughput|efficiency|fpoc_lpoc}?year=…&quarter=…` and gets back JSON. Tested: HTTP 200, `application/json`, for example `"response_type":"THROUGHPUT","total_teu":9599161…`.
- **Machine-readable?** Technically yes, but the endpoint is **undocumented and internal**. There is no API docs, licence or key. The page itself says it is "regularly updated", and the data looks monthly or quarterly. Other internal APIs (`ats-api.portofrotterdam.com/api/ship-visits`, `/positions`) appear in the page settings. I did not call those.
- **robots.txt:** `/en/por_ppi/api/` is not disallowed.
- **Terms:** The PoR copyright clause applies. Nothing grants reuse of the data.
- **Volume:** Not news. It changes monthly or quarterly.
- **Recommendation: Drop**, or at most link to the page manually. Don't build on an internal endpoint that could change or be withdrawn.

## 4. Contargo business news
- **Access:** HTML only. `https://www.contargo.net/en/business/business-news` redirects to `/en/business/business-news/current-customer-information/` (TYPO3, 46 pages). No RSS: `/en/rss.xml`, `/en/feed/` and `/rss` return 404, and `?type=100` / `?type=9818` return HTML.
- **Text:** Headline + 1–2 sentence teaser + date (MM/DD/YYYY), English (German site also exists). Examples:
  - 30 Oct: "UPDATE: Congestion in Antwerp and Rotterdam… Rotterdam: 77 hours"
  - 21 Oct: "Storm Warning in Rotterdam…"
  - 30 Oct: low-water item
  - The page header also shows Rhine gauge values (Emmerich, Ruhrort, Köln, Kaub) and BAF/TTFS surcharges.
- **robots.txt:** None (`https://www.contargo.net/robots.txt` returns 404). The page has meta `robots: INDEX, FOLLOW`.
- **Terms:** The imprint (<https://www.contargo.net/en/imprint/>) has only a liability disclaimer and trademark notice. No clause on scraping or reuse was found. A separate "T&Cs" link exists but was not read (uncertain).
- **Volume:** 5 items between 20 and 30 Oct, about 3 per week. Most are Rotterdam- or hinterland-relevant (barge waiting times, storms, low water).
- **Recommendation: Use.** Scrape page 1 once a day and write an own-words summary.

## 5. Terminal operators
### ECT (Hutchison Ports ECT Rotterdam)
- **Access:** HTML news list at `https://www.ect.nl/en/news-feed`. Service notifications are at `https://www.ect.nl/en/news/service-notifications`, which today said "There are currently no messages".
  - `https://www.ect.nl/en/rss.xml` exists but holds only 2 items (Apr and Dec 2025), Dutch titles: stale.
- **Text:** Headline + 1–2 sentence teaser + date, English. Recent items: "Update (2) Mandatory Safety Test for Drivers" (30 Oct), "Weekly update – week 43" (21 Oct), TCMS go-live (30 Sep).
- **robots.txt:** Standard Drupal. News paths allowed, no AI rules.
- **Terms:** <https://www.ect.nl/en/disclaimer-privacy-statement>: "The contents or information on this website may not be reproduced, distributed or published in any media for any purpose without prior express written consent from ECT."
- **Volume:** About 1 per week (8 items June to Oct).
- **Recommendation: Use, headline + link + a short own-words summary.** Don't copy teasers. The service-notifications page is worth checking daily.

### APM Terminals Maasvlakte II
- **Access:** `https://www.apmterminals.com/en/maasvlakte/about/news-and-updates` is a JS shell. The list loads from `https://api.apmterminals.com/content/articles` using a consumer key embedded in the HTML (`data-consumer-key`). I did **not** call that API: the key is not issued to us.
  - The terminal page itself linked 3 items: 26 Jun, 19 Aug and 10 Sep 2026.
  - `/en/rotterdam` and `/en/maasvlakte-ii` return 404. No RSS found.
- **robots.txt:** Only Sitecore and system paths are disallowed.
- **Terms:** <https://www.apmterminals.com/en/terms-conditions> are "Registered User Terms". Clause 10.2: "The Registered User or the Individual User may not place hyperlinks to any area of this Website." **Uncertain** whether this binds an unregistered public site. A separate developer API (developer.apmterminals.com) exists with its own licence; not evaluated.
- **Volume:** About 1 per month.
- **Recommendation: Drop**, given the low volume, the JS/private API and the odd linking clause. K+N's weekly update already covers APM operational news.

### Rotterdam World Gateway (rwg.nl)
- **Access:** HTML at `https://www.rwg.nl/en/news`. No RSS (`/rss.xml` and `/en/rss.xml` return 404). Customer portal `https://rwgservices.rwg.nl/` returns 403 behind a Cloudflare challenge.
- **Text:** Headline + day/month only in the list (no year). Six items, latest "Rotterdam World Gateway accelerates existing expansion" (6 Aug). Mostly maiden calls and PR.
- **robots.txt:** Standard Drupal, `/search` disallowed, news allowed.
- **Terms:** <https://www.rwg.nl/en/terms-use>: "Everything you see or read or that is contained in this website is protected by copyrights and may not be used without the prior written permission of RWG. The contents or information on this website may not be reproduced, distributed or published in any media…"
- **Volume:** About 1 per month.
- **Recommendation: Headline-only (low priority) or drop.**

## 6. KNMI weather warnings (Open Data API)
- **Important finding: the dataset is changing.**
  - The current dataset `waarschuwingen_nederland_48h` v1.0 (<https://dataplatform.knmi.nl/dataset/waarschuwingen-nederland-48h-1-0>) is marked **deprecated since 5 Oct 2026, with no updates from 2 Nov 2026**. It is TXT + XML, "continual", **CC-BY 4.0**, and covers ice/snow, rain, visibility, thunderstorm, gusts, heat and waterspouts, up to 48 h ahead.
  - Its successor is `KNMI-public-weather-warnings` v1.0 (<https://dataplatform.knmi.nl/dataset/knmi-public-weather-warnings-1-0>): **CAP (XML) and JSON**, "asNeeded", **CC-BY 4.0**. Warnings go up to 48 h ahead, plus "potentially dangerous weather" up to a week ahead.
  - The successor page is currently titled "[TEST]" and says "still in the testing phase and is subject to change", and the test data are "not real warnings".
  - The page mentions codes "yellow, amber or red", as summarised by WebFetch. **Uncertain** whether the files use "orange" or "amber".
  - Neither dataset page lists provinces. I could not download a file to confirm that Zuid-Holland (or the coastal/IJsselmeer areas) is a region field: **uncertain**.
- **Endpoints** (<https://developer.dataplatform.knmi.nl/open-data-api>):
  - List files: `GET https://api.dataplatform.knmi.nl/open-data/v1/datasets/{dataset}/versions/1.0/files` (params `maxKeys`, `orderBy`, `sorting`)
  - Download: `GET …/files/{filename}/url`, which returns a temporary download URL
- **Key needed:** Yes, sent in the `Authorization` header.
  - A shared anonymous key is published (valid until 1 Aug 2027; 50 req/min, 3000 req/h shared).
  - **In testing, every call with the anonymous key returned HTTP 429 "Rate Limit Exceeded" (three tries over ~1 h).** Register for a free personal key (200 req/s, 1000 req/h).
  - The docs say: "We consider excessive polling of the Open Data API to check for new files as abuse". Once a day is fine.
- **robots.txt:** `dataplatform.knmi.nl` disallows `/api/`, `/en/` and `/dataset?` (website search pages; one search returned HTTP 202). The API host `api.dataplatform.knmi.nl` has no robots.txt (404). Use the API, not the website.
- **Volume:** Event-driven, from 0 to several warnings per week (autumn/winter storms, fog).
- **Recommendation: Use** with a registered key. Code against `KNMI-public-weather-warnings`, keep the old dataset as a fallback until 2 Nov, and re-check once the successor leaves TEST. Attribution: "Source: KNMI (CC-BY 4.0)".

## 7. Rhine water levels
### Kaub – PEGELONLINE (WSV)
- **Endpoints** (tested, no key):
  - `https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations/KAUB.json?includeTimeseries=true&includeCurrentMeasurement=true`
  - `https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations/KAUB/W/currentmeasurement.json` returned `{"timestamp":"2026-10-31T16:15:00+01:00","value":31.0,"stateMnwMhw":"low","stateNswHsw":"normal"}`
  - Also available: `…/KAUB/W/measurements.json?start=P1D` (standard v2 API; not tested here)
- **Update frequency:** `equidistance: 15`, so a value every 15 minutes. Raw (unverified) data.
- **Key:** None needed.
- **Licence:** <https://www.pegelonline.wsv.de/webservice/ueberblick>: "Die Daten sind unter der Lizenz DL-DE->Zero-2.0 frei verfügbar." No attribution required. No rate limits stated.
- **robots.txt:** None (404).
- **Recommendation: Use.** Kaub 31 cm is notably low (state "low"), which makes this topical right now.

### Lobith – Rijkswaterstaat WaterWebservices (DDL)
- **Hosts:** The old `waterwebservices.rijkswaterstaat.nl` now redirects to a "switch-over" page that returns 404. The live host is `https://ddapi20-waterwebservices.rijkswaterstaat.nl`.
  - OpenAPI spec: `/webservices-api-docs`. Swagger UI: `/swagger-ui/index.html`.
  - Paths: `/ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen`, `/OphalenLaatsteWaarnemingen`, `/OphalenActueleWaarnemingen`, `/CheckWaarnemingenAanwezig`, `/METADATASERVICES/OphalenCatalogus`.
- **Working request** (tested 31 Oct):
  ```
  POST /ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen
  {"Locatie":{"Code":"lobith.bovenrijn.tolkamer"},
   "AquoPlusWaarnemingMetadata":{"AquoMetadata":{"Compartiment":{"Code":"OW"},"Grootheid":{"Code":"WATHTE"}}},
   "Periode":{"Begindatumtijd":"2026-10-31T06:00:00.000+01:00","Einddatumtijd":"2026-10-31T16:00:00.000+01:00"}}
  ```
  - It returned 10-minute measurements (`ProcesType: meting`, latest 14:50, 693 cm NAP) plus a `verwachting` (forecast) series.
  - `lobith.bovenrijn.haven` also works (680 cm).
  - Location codes are lowercase dotted (`lobith.bovenrijn.tolkamer`, `lobith.bovenrijn.haven`), not the old `LOBH`.
- **Caveat:** `OphalenLaatsteWaarnemingen` for Lobith returned **stale archive series** (2025-11-27, or even 1934). Use `OphalenWaarnemingen` with a recent `Periode` and take the last value. **Uncertain** why.
- **Key:** None. <https://rijkswaterstaatdata.nl/waterdata/>: "De WaterWebservices zijn openbaar toegankelijk en vereisen geen authenticatie. U kunt optioneel de header X-API-KEY meesturen…" Sending it is recommended.
- **Licence:** Same page: "Op de inhoud van de WaterWebservices is de Creative Commons zero verklaring (CC0) van toepassing." Fair use: excessive use may be throttled.
- **robots.txt:** The API host has none (JSON 404). The `waterinfo.rws.nl` website has `Disallow: /` with only a few `Allow` paths, so don't scrape Waterinfo; use the API.
- **Recommendation: Use.**

## 8. Google News RSS search
- **Format:** RSS 2.0, for example `https://news.google.com/rss/search?q=%22port%20of%20rotterdam%22%20when:7d&hl=en-US&gl=US&ceid=US:en`. It returned 100 items (EN). The NL query (`hl=nl&gl=NL&ceid=NL:nl`) returned 13.
  - Each item has: title ("Headline - Publisher"), `pubDate`, `<source url=…>`, and a description that is just an HTML link plus the publisher name. No snippet.
- **Links:** Google redirect URLs (`https://news.google.com/rss/articles/CBMi…?oc=5`), not publisher URLs.
- **robots.txt:** `User-agent: *` → `Disallow: /`, with Allow only for `/$`, `/home`, `/topics/`, `/publications/`, `/stories/`, `/swg/`, `/about`. **`/rss/` is not allowed.** CCBot, GPTBot, ClaudeBot and others get `Disallow: /`.
- **Terms (in the feed's `<copyright>`):** "This XML feed is made available solely for the purpose of rendering Google News results within a personal feed reader for personal, non-commercial use. Any other use of the feed is expressly prohibited."
- **Recommendation: Drop.** robots.txt and the feed's own terms both rule out use in a public website. At most, use it by hand as a discovery tool.

## 9. PortsEurope
- **Access:** **RSS** `https://www.portseurope.com/category/rotterdam/feed/` (200, `en-GB`). The site-wide feed is `https://www.portseurope.com/feed/`. `/tag/rotterdam/feed/` returns 404.
- **Text:** Headline + ~450–510-char teaser ending in "…" + `pubDate`. `content:encoded` is only a "The post … appeared first…" stub.
- **robots.txt:** Cloudflare-managed. `User-agent: *` → `Content-Signal: search=yes,ai-train=no,use=reference`, `Allow: /`. AI crawlers (ClaudeBot, GPTBot, CCBot, Google-Extended…) are fully disallowed. It reserves rights under EU DSM Art. 4.
  - **`ai-input` is not specified**, which the file says neither grants nor restricts. Feeding teasers to an LLM summariser is a grey zone (uncertain).
- **Terms:** <https://www.portseurope.com/terms-of-use/>: "Ports Europe is a paid subscription news service. Searches on the public internet will show headlines and a snippet… If you would like to include Ports Europe information in your website, or another product, please contact us directly". <https://www.portseurope.com/disclaimer/>: "Copying, disseminating and any other use of these materials is not permitted without the written permission of Infonicks, except… (such as the right to quote)".
- **Volume:** 10 items from 21 Sep to 29 Oct, about 2 per week.
- **Recommendation: Headline-only** (paywalled), with no AI summary of the teaser. Or ask them by email.

## 10. NL Times
- **Access:** RSS is site-wide only: `https://nltimes.nl/rssfeed2` (also `/rssfeedalt`; `/rss` redirects there), 10 items. Tag pages `https://nltimes.nl/tags/port-rotterdam` and `/tags/rotterdam` are HTML; `/tags/…/feed` returns 404.
- **Text:** Headline + 90–160-char snippet + date ("31 October 2026 - 15:55" format, not RFC 822), English. Articles are free.
- **robots.txt:** `User-agent: *` disallows only parameters, `/search/`, `/admin/` and similar. **Blocks** CCbot, anthropic-ai, Claude-Web, cohere-ai, GPTBot, ChatGPT-User and others with `Disallow: /`. A generic or own-named UA is allowed.
- **Terms:** <https://nltimes.nl/terms-and-conditions> contains only placeholder text ("text"). The footer says "© 2012-2026, NL Times, All rights reserved."
- **Volume:** The port tag had 12 items from 31 May to 17 Oct, about 0.5–1 per week. The site-wide RSS holds only ~10 hours of news, so a once-a-day fetch will miss port items.
- **Recommendation: Use with care**, filtered by keyword. Scraping the `/tags/port-rotterdam` HTML once a day may be more reliable than the 10-item RSS. Their AI-bot blocks signal a dislike of AI use. Keep to headline + link + own summary.

## 11. DutchNews.nl
- **Access:** RSS `https://www.dutchnews.nl/feed/` (200, `en-GB`). Headline + ~100–140-char teaser. Tag URLs redirect to a 404 page. Search is at `/search/<terms>/`. The WP REST API `/wp-json/wp/v2/posts` responds.
- **robots.txt:** `User-agent: *` → `Crawl-delay:10` and **`Disallow: /feed/`** (listed twice), plus `/news/rssfulltext.xml`. GPTBot gets `Disallow: /`.
  - Note: I fetched `/feed/` once while testing, before reading the rules closely. A production fetcher must not.
- **Volume:** Port-related stories appear roughly monthly (search results: 2025-03, 2025-09, 2025-10, 2026-08…).
- **Recommendation: Drop.** The feed is disallowed by robots.txt, and getting round that via wp-json would break the spirit of the rule.

## 12. Tradlinx blog
- **Access:** RSS `https://www.tradlinx.com/blog/feed/` (WordPress, `ko-KR`). `/blog/tag/rotterdam/feed/` and `/tag/port-of-rotterdam/feed/` return 200 but 0 items. `/blog/feed/?s=rotterdam` returned 4 items (2022 to 2026). `/en/blog/` redirects to the Korean blog.
- **Text:** Korean headline + teaser.
- **robots.txt:** `Allow: /`. Disallows `/_terms/` (the terms page itself) and HeadlessChrome.
- **Recommendation: Drop.** Korean-only, about 0 Rotterdam items per week.

## 13. Kuehne+Nagel SeaNews
- **Access:** HTML only at `https://mykn.kuehne-nagel.com/news` (Astro site). Articles at `/news/article/<slug>`. No RSS (`/news/rss`, `/feed`, `/rss.xml` return 404).
- **Text:** List: headline + teaser + date. Articles: full text public, with `datePublished` in JSON-LD. English.
  - The weekly article "Port operational updates from around the world (21 Oct - 27 Oct 2026)" has a Rotterdam paragraph: waiting time 1.36 days, yard occupancy ECT 85% / MVII 99%, closure 23–25 Oct.
- **robots.txt** (mykn.kuehne-nagel.com): `User-agent: *`, `Allow: /news`, `Disallow: /`. So `/news` and articles are allowed.
- **Terms:** Website terms of use not found (searched; WebFetch/WebSearch turned up only service T&Cs). **Uncertain.**
- **Volume:** 1 weekly roundup with a Rotterdam section, plus occasional Rotterdam mentions (e.g. 30 Oct, India–Rotterdam).
- **Recommendation: Use, headline + link + own-words summary** of the Rotterdam paragraph only. Check the terms before launch.

## 14. Paywalled publishers (headline feeds + linking)
- **Lloyd's List:** RSS `https://www.lloydslist.com/rss/lloyds-list`, listed on `/rss-feeds`, which asks you to sign in. robots: `User-agent: *` / **`Disallow:/rss/`**. **Drop.**
- **The Loadstar:** RSS `https://theloadstar.com/feed/` (10 items, ~550-char excerpts).
  - robots: `Disallow: /page/ /tag/ /category/ /wp-admin/`, so `/feed/` is allowed. Tag/category feeds are therefore off-limits; use the main feed and filter.
  - Terms (<https://theloadstar.com/licencing-and-copyright/>): "RSS feeds: You may use our RSS feeds to create links back to our website. This does not permit copying or republishing of full articles." Limited free use is also allowed: up to 2 articles/week, at most the first 3 paragraphs or 150 words, with source credit and link.
  - 0 Rotterdam items in today's 10-item sample, so volume is low (uncertain; maybe a few per month).
  - **Headline-only: explicitly allowed.**
- **JOC:** RSS `https://www.joc.com/rssfeed` (`/rss.xml` redirects there; 40 items, 22–30 Oct, ~150-char dek).
  - robots: `Allow: /`, disallows `/search` and `/subscription/subscribe`.
  - T&C (<https://www.joc.com/terms-conditions>): nothing on RSS or linking. Clause 5: "No part of the publication may be reproduced or transmitted…".
  - 0 Rotterdam items in 40.
  - **Headline-only, optional** (low yield).
- **Nieuwsblad Transport:** `www.nieuwsbladtransport.nl` returns HTTP 403 (Cloudflare "Just a moment…"). The live site is **`https://www.nt.nl/`**.
  - Feeds: `https://www.nt.nl/feed/`, `https://www.nt.nl/havens/feed/` (10 items/week, 6 about Rotterdam), `https://www.nt.nl/tag/rotterdam/feed/`, `https://www.nt.nl/tag/havenbedrijf-rotterdam/feed/`.
  - The feed's `content:encoded` carries article body text (up to ~7,000 chars). Don't use it: subscription site (<https://www.nt.nl/abonneren/>).
  - robots (nt.nl): `User-agent: *` disallows `/wp-json/`, `/?rest_route=`, `/ntlogin/` and similar. `Crawl-Delay: 1`. `Content-signal: search=yes, ai-train=no`. ClaudeBot, GPTBot, Google-Extended, CCBot and others are fully disallowed.
  - The colofon (<https://www.nt.nl/colofon/>) has no reuse clause. No general terms page found (`/algemene-voorwaarden/` and `/disclaimer/` return 404).
  - **Headline-only.** Dutch. The best volume of the paywalled group.
- **TradeWinds:** No official RSS found (`/rss` and `/rss.xml` return 404; only third-party rss.app wrappers exist).
  - robots: generic bots allowed apart from login/subscription/sponsor paths. GPTBot, ClaudeBot, anthropic-ai, Google-Extended, CCBot and others get `Disallow: /`. Terms not checked.
  - **Drop** (no feed; scraping a paywalled site's HTML isn't worth it).

## General notes for the fetcher
- Send an honest, descriptive User-Agent (e.g. `HavenDailyBot/1.0 (+https://<your-pages-url>)`). Re-check robots.txt for that UA at run time. Several sites block named AI crawlers; your bot isn't one of those UAs, but the content goes into an LLM, so the "ai-input" stance of PortsEurope and nt.nl is a grey area.
- Cloudflare-fronted sites (rwgservices, nieuwsbladtransport.nl, possibly portseurope/nt.nl) may challenge GitHub's cloud IPs even when they served curl here. **Untested from Actions.**
- Several 10-item feeds (PIN, NL Times site feed) roll over in under a day. A single 06:45 run will miss items unless you also scrape the list pages or poll more often.

---

## Added later on 31 Oct 2026: RTV Rijnmond and NOS (tested by Claude in the main session)

### RTV Rijnmond
- **Feed:** `https://www.rijnmond.nl/rss/nieuws`, HTTP 200, 50 items covering ~2.5 days (29–31 Oct). Description 119–433 characters (median 291). Dutch. `<copyright>Copyright © 2026 Rijnmond</copyright>`. (`/rss` returns 404.)
- **robots.txt:** `User-agent: *` → `Allow: /`, disallows `/content/`, `/embedded/`, `/data/`, `/inc/`, `/nos/`, search. Then ~130 named bots get `Disallow: /`, including `anthropic-ai`, `Claude-User`, `Claude-Web`, `ClaudeBot`, `CCBot`, `Applebot-Extended`, `Bytespider`.
- **Terms:** not found. The homepage footer links only `/privacystatement` and `/actievoorwaarden` (contest rules).
- **Port relevance:** a keyword scan of the 50 items found 0 real port items.
- **Verdict:** headline-only (hard rule 12); check terms before launch.

### NOS
- **Feeds:** `https://feeds.nos.nl/nosnieuwsalgemeen` (20 items, ~10 h) and `https://feeds.nos.nl/nosnieuwseconomie` (20 items, ~4 days). Descriptions contain the full article text (median ~2,500 characters). 0–2 port-related items per feed.
- **robots.txt (nos.nl):** `User-agent: *` disallows `/hybrid/`, `/widget-embed/`, `/special/`, `/api`, `/zoeken`. `Disallow: /` for CCBot, ChatGPT-User, GPTBot, Google-Extended, anthropic-ai, ClaudeBot, PerplexityBot, cohere-ai and others. `feeds.nos.nl/robots.txt`: 404.
- **Terms** (NOS Algemene Voorwaarden, last changed 1 Oct 2025, https://over.nos.nl/wp-content/uploads/2025/10/NOS-Algemene-Voorwaarden-2025.pdf):
  - Art. 6.1: "Automatische toegang tot de Websites en/of Diensten door bepaalde AI agents, bots of andere soortgelijke systemen, zonder toestemming van NOS, is strikt verboden; ongeacht het doel van de betreffende AI agent of bot."
  - Art. 6.2: exceptions only for search-engine bots and bots that only index metadata for a public search function.
  - Art. 7 (RSS): "Het gebruik is uitsluitend voor niet-commercieel gebruik door particuliere Gebruikers voor persoonlijke informatie, educatie of nieuwsgaring." Headlines may be used with clear attribution; the feeds may not be edited. Other use: contact juza@nos.nl.
- **Verdict:** drop.

### Google News (re-checked)
- robots.txt: `User-agent: *` → `Disallow: /`, then `Allow` only for `/$`, `/?`, `/home…`, `/nwshp$`, `/topics/`, `/publications/`, `/stories/`, `/swg/`, `/about…`. `/rss/` is not allowed.
- Feed `<copyright>`: "This XML feed is made available solely for the purpose of rendering Google News results within a personal feed reader for personal, non-commercial use. Any other use of the feed is expressly prohibited. By accessing this feed or using these results in any manner whatsoever, you agree to be bound by the foregoing restrictions."

### GDELT DOC 2.0 API (tested by Claude in the main session)
- **Endpoint:** `https://api.gdeltproject.org/api/v2/doc/doc?query=…&mode=artlist&format=json&maxrecords=75&timespan=7d&sort=datedesc`. Fields returned: domain, language, seendate, socialimage, sourcecountry, title, url, url_mobile.
- **robots.txt:** none on `api.gdeltproject.org` (404). `www.gdeltproject.org` disallows only `/data/`.
- **Licence** (gdeltproject.org/about.html): "available for unlimited and unrestricted use for any academic, commercial, or governmental use of any kind without fee"; "any use or redistribution of the data must include a citation to the GDELT Project and a link to this website".
- **Rate limit:** "Please limit requests to one every 5 seconds". The first 4 requests (including one via WebFetch from a different IP) all got 429. After a 16-minute cooldown, 6 of 9 requests still got 429 despite 10 s spacing.
- **Results (7 days):** `"port of rotterdam"` gave 1 article, and it was unrelated (business-standard.com, cybersecurity). `rotterdam (maasvlakte OR europoort OR botlek)` gave 0. `rotterdam (staking OR strike) (haven OR port)` gave 0. `sourcecountry:netherlands rotterdam haven` gave 0. `"haven van rotterdam" OR "rotterdamse haven"` was malformed (OR'd terms need parentheses), so it is not tested.
- **Verdict:** not useful for v1. Re-test the Dutch query, and re-test from GitHub Actions, only if news volume turns out too low.
