# Haven Daily

A public morning page that tells a logistics planner what is affecting the Port of Rotterdam today and what it means for them.

## Language

**Brief**:
One day's published edition: the status line plus up to 5 items, as written by the morning job for one date.
_Avoid_: Report, digest, newsletter

**Source**:
A publisher (outlet) whose headlines or articles may appear in a brief, with one verdict: use, headline-only or drop.
_Avoid_: Feed, outlet, site, publisher

**Verdict**:
The decision on how a source may be used: **use** (headline, link and own-words summary), **headline-only** (headline and link), or **drop** (not collected).
_Avoid_: Status, permission level

**Discovery service**:
A service that only finds headlines and links from other sources (GDELT); it is never a source itself, and each result follows its own source's verdict.
_Avoid_: Aggregator, news API

**Item**:
One piece of news found in a source on a given morning. Every collected item is stored; only kept items can appear in a brief.
_Avoid_: Article, story, post

**Place**:
A named location in or near the port (terminal, area, anchorage, lock or fairway) from the fixed place list; the only locations an item can be pinned to.
_Avoid_: Location, site, POI

**Affects tag**:
A label from a fixed list naming what an item affects: a cargo type, transport mode or place.
_Avoid_: Category, keyword, topic

**Kept item / dropped item**:
An item the relevance filter judged relevant (kept) or not (dropped) to a Rotterdam logistics planner. Dropped items are still stored.
_Avoid_: Filtered, rejected, accepted

**Auto-keep source**:
A Rotterdam-specific source (Port Authority news, ECT) whose items the relevance filter keeps without the off-topic word lists or the AI check; only the 48 h age rule can drop them.
_Avoid_: Trusted source, whitelist

**Unrated item**:
A kept item that appears with headline and link only, because no severity, summary or impact could be produced for it.
_Avoid_: Unknown, unclassified, failed item

**Reduced brief**:
A brief published without any AI-written content because the AI was unavailable all morning: status line plus unrated items only.
_Avoid_: Fallback brief, degraded page, emergency edition

**Strike flag**:
The status indicator saying whether a strike affecting the Port of Rotterdam is happening today (Alert), coming up (Watch) or not active (Normal).
_Avoid_: Strike alert, strike status, industrial action indicator

**Deciding item**:
The item a status indicator's value is based on, linked from the status line.
_Avoid_: Trigger item, source item

**Correction**:
A dated one-line note recording a change made to a brief after it was published.
_Avoid_: Update, edit, erratum
