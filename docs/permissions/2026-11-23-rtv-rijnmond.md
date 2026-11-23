# RTV Rijnmond: the impact line is allowed, on conditions (23 Nov 2026)

**Status: allowed, on three conditions (all met, spec §11; #115).** Rijnmond items get the "impact for planners" line from 23 Nov 2026. Follows the written permission for AI summaries of 19 Nov 2026 (`2026-11-19-rtv-rijnmond.md`), whose six conditions still apply.

- **From:** Daan Verberne, Sales, Marketing and Communications Manager, RTV Rijnmond
- **Date:** 23 November 2026
- **In reply to:** the owner's question of 19 Nov 2026 whether the impact line for planners is also okay for Rijnmond items
- Email address left out on purpose: this repo is public.

## His reply

> That's absolutely fine with us, as long as the additional line is clearly presented as Haven Daily's own interpretation and not as a statement or conclusion from Rijnmond. It's also important that any potential impact on logistics is based on the facts in the article and that possible consequences are not presented as confirmed facts.

## How each condition is met

| Condition | How |
|---|---|
| **Clearly Haven Daily's own interpretation**, not a statement or conclusion from Rijnmond | The card labels the line "Impact for planners · **Haven Daily's interpretation, not RTV Rijnmond's**" (also on "Not enough information"). The note under the summary stays ("…RTV Rijnmond is not responsible for it"). How it works: "The impact for planners on its items is Haven Daily's own interpretation, not RTV Rijnmond's." |
| **Based on the facts in the article** | The AI sees only the lead paragraph in the feed (no article page is opened, owner's choice of 19 Nov 2026), and the prompt says the impact must rest only on the facts in that text. As for every item: no facts, numbers, names, dates or quotes that are not in it, and "Not enough information" when the text doesn't support an impact. Code can't check meaning: a wrong impact found afterwards is fixed with a visible correction (hard rule 11), and RTV Rijnmond is told. |
| **Possible consequences not presented as confirmed facts** | The prompt asks for every consequence as possible, with "could" or "may", never as certain or confirmed. **Checked in code** (`summarise.sounds_confirmed`): an impact with a word such as "will", "won't", "going to", "confirmed", "certain" or "definitely", or with no "could", "may" or "might" at all, gets **one retry**; if the retry still sounds confirmed, the item keeps its summary and has **no impact line** (a failure line says why). |

The line `permission = { …, impact = true }` for RTV Rijnmond in `config/sources.toml` switches it on. Briefs published before this change keep no impact line for Rijnmond items: their `permission` record says `"impact": false`, and they are not changed.

## Follow-up

*(none)*
