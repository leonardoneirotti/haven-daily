"""Haiku 5.5 vs Sonnet 5.5, side by side (spec §5.5, §10 step 6; issue #17).

`python -m haven.compare` runs collect → filter → summarise **once** on today's real items and
summarises the same kept items with both models, through the same code the morning job uses
(`haven.summarise.summarise`, standard API). It prints a side-by-side view for the owner, who
chooses the model (Haiku is the default unless Sonnet is clearly better).

`--dry-run` makes no API call: it collects, runs the free rules and prints the cost estimate,
so the owner can approve the cost before the real run.

**The re-run after the prompt fixes (issue #67):** `--models sonnet --batch` sends the kept items
through **one model** and **the batch**, exactly as the morning job does (`summarise_batch`);
`--skip-links-in docs/model-comparison.md` leaves out every item whose link is already in that
file, so only **fresh items** are compared. The view then also lists the PIN notices that had
ended: dropped by the 12 h rule, or kept and made Low by the code.

Nothing is written to data/: no brief, no items file. The view holds headlines, links and the
AI's own words only, never article text or teasers (hard rule 13), so it can go into
docs/model-comparison.md in the public repo. The facts check (`unsupported_terms`) reads the
article in memory and lists only the AI's words that the source doesn't contain.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from haven.collect import url_key
from haven.config import Place, Source, Tag, load_places, load_tag_list
from haven.feeds import Item
from haven.filter import notice_ended, pin_end
from haven.summarise import SummaryResult, summarise, summarise_batch

__all__ = ["HAIKU", "MODELS", "SONNET", "Comparison", "compare", "cost_usd", "ended_notices", "estimate",
           "format_markdown", "run_cost", "skip_links", "unsupported_terms"]

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
MODELS = (HAIKU, SONNET)
NAMES = {HAIKU: "Haiku 5.5", SONNET: "Sonnet 5.5"}
BY_NAME = {"haiku": HAIKU, "sonnet": SONNET}  # for --models
BATCH_DISCOUNT = 0.5  # the Batch API costs half on all tokens (spec §5.5)

# USD per million tokens, standard API, prompts up to 100K tokens (Anthropic list prices, spec §5.5).
PRICES = {HAIKU: (0.10, 0.50), SONNET: (2.00, 10.00)}

# Tokens per call for the estimate, from the real runs of 2 Nov 2026: the filter ~860 in / ~52 out
# (#13), the summariser ~3,000 in / ~1,100 out with Haiku (#15). Sonnet: same input, output assumed
# higher (more thinking), so the estimate errs on the high side.
FILTER_CALL = (860, 52)
SUMMARY_CALL = {HAIKU: (3000, 1100), SONNET: (3000, 1500)}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimated cost at list prices; the real bill is in the Anthropic Console."""
    price_in, price_out = PRICES[model]
    return input_tokens * price_in / 1e6 + output_tokens * price_out / 1e6


def run_cost(model: str, result: SummaryResult) -> float:
    """What one summary run cost at list prices: batch tokens at half price, the rest at full price."""
    standard_in = result.input_tokens - result.batch_input_tokens
    standard_out = result.output_tokens - result.batch_output_tokens
    return (cost_usd(model, standard_in, standard_out)
            + BATCH_DISCOUNT * cost_usd(model, result.batch_input_tokens, result.batch_output_tokens))


def estimate(ai_check_items: int, summary_items: int, models=MODELS, batch: bool = False) -> dict:
    """Expected cost of one comparison run: the relevance check plus one summary run per model."""
    est = {"filter": ai_check_items * cost_usd(HAIKU, *FILTER_CALL)}
    for model in models:
        est[model] = summary_items * cost_usd(model, *SUMMARY_CALL[model]) * (BATCH_DISCOUNT if batch else 1)
    est["total"] = sum(est.values())
    return est


# --- fresh items and ended notices (issue #67) ------------------------------------------------

_LINK = re.compile(r"https?://[^\s<>()|\]\[`\"']+")


def skip_links(items: list[Item], text: str) -> tuple[list[Item], list[Item]]:
    """(fresh, skipped): items whose link is already in `text` (an earlier write-up) are skipped.

    Links are compared like the duplicate check does (`collect.url_key`: no #fragment, no utm_*).
    """
    seen = {url_key(link.rstrip(".,;:")) for link in _LINK.findall(text)}
    fresh = [item for item in items if url_key(item.url) not in seen]
    skipped = [item for item in items if url_key(item.url) in seen]
    return fresh, skipped


def ended_notices(items: list[Item], read_at: datetime) -> list[str]:
    """One line per PIN notice that had ended by `read_at`: dropped by the 12 h rule, or kept (Low by the code)."""
    lines = []
    for item in items:
        end = pin_end(item)
        if end is None or not notice_ended(item, read_at):
            continue
        when = f"End Date {end:%Y-%m-%d %H:%M}"
        if item.filter and not item.filter["kept"] and item.filter["reason"].startswith("PIN notice ended"):
            lines.append(f"- dropped by the rules: {_cell(item.headline)} ({item.url}), {when}")
        elif item.filter is None or item.filter["kept"]:
            lines.append(f"- kept, Low by the code: {_cell(item.headline)} ({item.url}), {when}")
    return lines


# --- facts check ------------------------------------------------------------------------------

_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_][\w'’-]*")
_SENTENCE_END = re.compile(r"(^|[.!?:;]\s*)$")


def _norm(token: str) -> str:
    token = token.casefold()
    for suffix in ("'s", "’s"):
        if token.endswith(suffix):
            token = token[: -len(suffix)]
    return token


def unsupported_terms(text: str | None, source_text: str, vocabulary=()) -> list[str]:
    """Numbers and names in the AI's text that don't appear in the source.

    A pointer for the owner's facts check, not a verdict: a flagged word may be a fair paraphrase
    (an English word for a Dutch one, say). Names = capitalised words that don't start a sentence.
    Words of the fixed place and tag lists (`vocabulary`) are never flagged.
    """
    if not text:
        return []
    known = {_norm(t) for t in _TOKEN.findall(source_text or "")}
    for phrase in vocabulary:
        known.update(_norm(t) for t in _TOKEN.findall(phrase))
    flagged: list[str] = []
    for match in _TOKEN.finditer(text):
        token = match.group()
        if not token[0].isdigit():
            if not token[0].isupper() or _SENTENCE_END.search(text[: match.start()]):
                continue
        if _norm(token) not in known and token not in flagged:
            flagged.append(token)
    return flagged


# --- the comparison ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Comparison:
    items: list[Item]  # what was sent to both models, in order
    outputs: dict[str, SummaryResult]  # per model; outputs[m].items lines up with `items`
    checks: dict[str, list[list[str]]]  # per model, per item: words not found in the source
    left_out: list[Item]  # kept items not compared because of --max-items
    today: date
    read_at: datetime | None = None  # when the sources were read (ended PIN notices are Low from then)
    route: str = "standard"  # "standard" (#17) or "batch" (the re-run after the prompt fixes, #67)


def compare(items: list[Item], client, known: list[dict], today: date, models=MODELS,
            max_items: int | None = None, places: tuple[Place, ...] | None = None,
            tags: tuple[Tag, ...] | None = None, *, read_at: datetime, batch: bool = False,
            clock=None, sleep=None) -> Comparison:
    """The same items through the summariser once per model. Never raises for an API problem.

    `batch=False` (#17): the standard API (`summarise`). `batch=True` (#67): one batch per model,
    as the morning job sends it (`summarise_batch`; `clock` and `sleep` are for the tests).
    """
    places = load_places() if places is None else places
    tags = load_tag_list() if tags is None else tags
    chosen = list(items) if max_items is None else list(items[:max_items])
    left_out = [] if max_items is None else list(items[max_items:])
    vocabulary = tuple(p.label for p in places) + tuple(t.name for t in tags) + ("Rotterdam",)

    outputs: dict[str, SummaryResult] = {}
    checks: dict[str, list[list[str]]] = {}
    for model in models:
        if batch:
            result = summarise_batch(chosen, client, known, today, model=model, places=places, tags=tags,
                                     clock=clock, sleep=sleep, read_at=read_at)
        else:
            result = summarise(chosen, client, known, today, model=model, places=places, tags=tags,
                               read_at=read_at)
        outputs[model] = result
        per_item = []
        for sent, done in zip(chosen, result.items):
            ai = done.ai or {}
            source_text = f"{sent.headline} {sent.article_text or ''}"
            words = unsupported_terms(ai.get("summary"), source_text, vocabulary)
            words += [w for w in unsupported_terms(ai.get("impact"), source_text, vocabulary) if w not in words]
            per_item.append(words)
        checks[model] = per_item
    return Comparison(items=chosen, outputs=outputs, checks=checks, left_out=left_out, today=today,
                      read_at=read_at, route="batch" if batch else "standard")


# --- the side-by-side view --------------------------------------------------------------------


def _cell(value) -> str:
    return " ".join(str(value).split()).replace("|", "\\|")


def _strike(strike: dict | None) -> str:
    if not strike:
        return "none"
    when = (f"{strike.get('start') or '?'} to {strike.get('end') or '?'}"
            if strike.get("start") or strike.get("end") else "no dates")
    text = f"{strike['state']} · {strike['location']} · {when} · {strike['match']} {strike.get('strike_id') or ''}"
    if not strike.get("affects_rotterdam"):
        text += " · not Rotterdam"
    return text.strip()


def _unlisted(ai: dict) -> str:
    unlisted = ai.get("unlisted") or {}
    parts = []
    if unlisted.get("places"):
        parts.append("place " + ", ".join(map(str, unlisted["places"])))
    if unlisted.get("tags"):
        parts.append("tags " + ", ".join(map(str, unlisted["tags"])))
    return "; ".join(parts) or "none"


def _failures(result: SummaryResult, url: str) -> str:
    lines = [f["error"][len(url) + 2:] for f in result.failures if f["error"].startswith(url + ": ")]
    return "; ".join(lines) or "none"


def _row(name: str, values) -> str:
    return f"| {name} | " + " | ".join(_cell(v) for v in values) + " |"


def format_markdown(comparison: Comparison, sources: tuple[Source, ...]) -> str:
    """The side-by-side view: one table per item, then calls, tokens and cost per model."""
    models = list(comparison.outputs)
    names = {source.id: source.name for source in sources}
    route = ("through the batch, as the morning job sends it" if comparison.route == "batch"
             else "standard API, the same request")
    lines = [f"Run on {comparison.today.isoformat()}: {len(comparison.items)} kept items, each summarised by "
             + " and ".join(NAMES.get(m, m) for m in models) + f" ({route}).", ""]

    for n, sent in enumerate(comparison.items):
        outs = [(comparison.outputs[m].items[n].ai or {}) for m in models]
        headline_only = sent.access != "full" or not sent.article_text
        access = "headline only" if headline_only else "full article"
        lines += [f"### {n + 1}. {_cell(sent.headline)}", "",
                  f"{sent.url} · {names.get(sent.source, sent.source)} · {sent.published or 'no date'} · {access}", "",
                  "| | " + " | ".join(NAMES.get(m, m) for m in models) + " |",
                  "|---|" + "---|" * len(models)]
        lines.append(_row("Severity", [ai.get("severity") or "unrated" for ai in outs]))
        lines.append(_row("Place", [(ai.get("map") or {}).get("label", "none") for ai in outs]))
        lines.append(_row("Tags", [" · ".join(ai.get("affects") or []) or "none" for ai in outs]))
        if not headline_only:
            lines.append(_row("Summary", [ai.get("summary") or "—" for ai in outs]))
            lines.append(_row("Impact", [ai.get("impact") if ai.get("impact") else
                                         ("null (Not enough information)" if ai.get("severity") else "—")
                                         for ai in outs]))
        lines.append(_row("Strike", [_strike(ai.get("strike")) for ai in outs]))
        end = pin_end(sent)
        if end is not None and comparison.read_at is not None and notice_ended(sent, comparison.read_at):
            lines.append(_row("Notice ended", [f"{end:%Y-%m-%d %H:%M}: Low by the code"] * len(models)))
        lines.append(_row("Off the lists", [_unlisted(ai) for ai in outs]))
        lines.append(_row("Words not in the source", [", ".join(comparison.checks[m][n]) or "none" for m in models]))
        lines.append(_row("Failures", [_failures(comparison.outputs[m], sent.url) for m in models]))
        lines.append("")

    lines += ["### Calls, tokens and cost", "", "| Model | Calls | Tokens | Cost (list price) |", "|---|---|---|---|"]
    for m in models:
        r = comparison.outputs[m]
        cost = run_cost(m, r)
        lines.append(f"| {NAMES.get(m, m)} | {r.calls} | {r.input_tokens:,} in / {r.output_tokens:,} out | ${cost:.4f} |")
        if r.unavailable:
            lines.append(f"| | AI unavailable: {_cell(r.unavailable)} | | |")
    lines.append("")

    if comparison.left_out:
        lines += [f"### Not compared ({len(comparison.left_out)} kept items over the cap)", ""]
        lines += [f"- {_cell(i.headline)}: {i.url}" for i in comparison.left_out]
        lines.append("")
    return "\n".join(lines)


# --- the run by hand --------------------------------------------------------------------------


def main(argv=None) -> None:
    """`python -m haven.compare [--dry-run] [--models ...] [--batch] [--skip-links-in FILE] [--max-age-days N]
    [--max-items N] [--out FILE]`. Writes nothing to data/."""
    from haven import clock, storage
    from haven.collect import add_article_text, run_collect
    from haven.config import load_filter, load_sources
    from haven.env import load_env
    from haven.fetch import Fetcher
    from haven.filter import AI_CHECK, KEEP, MAX_AGE, TO_AI, ai_client, ai_cost_usd, apply_rules, run_filter
    from haven.summarise import known_strikes

    parser = argparse.ArgumentParser(prog="python -m haven.compare", description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="no API calls: counts and the cost estimate only")
    parser.add_argument("--max-age-days", type=int, default=None,
                        help="let items up to N days old through the age rule (comparison only; default 48 h)")
    parser.add_argument("--max-items", type=int, default=None, help="summarise at most this many kept items")
    parser.add_argument("--models", nargs="+", choices=sorted(BY_NAME), default=None,
                        help="which models to run (default: haiku sonnet)")
    parser.add_argument("--batch", action="store_true", help="send the items through the batch, as the morning job")
    parser.add_argument("--skip-links-in", type=Path, default=None,
                        help="leave out items whose link is already in this file (e.g. docs/model-comparison.md)")
    parser.add_argument("--out", type=Path, default=None, help="write the side-by-side view to this file")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # headlines and "·" on a Windows console

    max_age = MAX_AGE if args.max_age_days is None else timedelta(days=args.max_age_days)
    models = MODELS if args.models is None else tuple(BY_NAME[name] for name in args.models)
    load_env()
    sources = load_sources()
    fetcher = Fetcher()
    today = clock.today()
    collected = run_collect(sources, fetcher, today)
    now = datetime.fromisoformat(collected.feeds_read_at)
    print(f"Collected {len(collected.items)} new items from {collected.sources_checked} sources "
          f"at {collected.feeds_read_at}.")
    for failure in collected.failures:
        print(f"FAILURE  {failure['source']}: {failure['error']}")
    items, skipped = collected.items, []
    if args.skip_links_in is not None:
        items, skipped = skip_links(items, args.skip_links_in.read_text(encoding="utf-8"))
        print(f"Left out {len(skipped)} items whose link is in {args.skip_links_in}.")

    if args.dry_run:
        ruled = apply_rules(items, sources, load_filter(), now, max_age)
        kept = [r.item for r in ruled if r.decision.outcome == KEEP]
        to_ai = [r.item for r in ruled if r.decision.outcome == TO_AI]
        low, high = len(kept), len(kept) + len(to_ai)
        if args.max_items is not None:
            low, high = min(low, args.max_items), min(high, args.max_items)
        print(f"Rules: {len(kept)} kept (auto-keep), {len(to_ai)} to the AI check, "
              f"{len(ruled) - len(kept) - len(to_ai)} dropped.")
        for it in kept:
            print(f"  kept    {it.source:20} {it.headline}")
        for it in to_ai:
            print(f"  to AI   {it.source:20} {it.headline}")
        for line in ended_notices([r.item for r in ruled], now):
            print(f"  ended   {line[2:]}")
        route = "batch" if args.batch else "standard API"
        for label, n in (("if the AI check keeps none", low), ("if it keeps all", high)):
            est = estimate(len(to_ai), n, models, args.batch)
            parts = " + ".join(f"{NAMES[m]} ({route}) ${est[m]:.4f}" for m in models)
            print(f"Estimate {label} ({n} items summarised): filter ${est['filter']:.4f} + {parts} "
                  f"= ${est['total']:.4f}")
        return

    client = ai_client()
    if client is None:
        sys.exit("ANTHROPIC_API_KEY is not set (local .env): nothing was sent.")
    filtered = run_filter(items, sources, load_filter(), now, client, max_age)
    if filtered.ai_unavailable:
        sys.exit("The AI check was unavailable: nothing was summarised.")
    kept = [i for i in filtered.items if i.filter and i.filter["kept"]]
    filter_cost = ai_cost_usd(filtered.input_tokens, filtered.output_tokens)
    texts = add_article_text(kept, sources, fetcher)
    known = known_strikes(storage.read_recent("items", before=today, days=14))
    comparison = compare(texts.items, client, known, today, models=models, max_items=args.max_items,
                         read_at=now, batch=args.batch)

    window = "48 h (as the morning job)" if args.max_age_days is None else f"{args.max_age_days} days (comparison only)"
    header = [f"Age limit: {window}.", "", f"Filter: {len(kept)} kept of {len(filtered.items)} ({filtered.ai_calls} {AI_CHECK} calls, "
              f"{filtered.input_tokens:,} in / {filtered.output_tokens:,} out, ${filter_cost:.4f}).", ""]
    header += [f"- FAILURE {f['source']}: {f['error']}" for f in filtered.failures + texts.failures]
    if args.skip_links_in is not None:
        header += [f"Fresh items only: {len(skipped)} collected items left out because their link is in "
                   f"`{args.skip_links_in.as_posix()}`.", ""]
    ended = ended_notices(filtered.items, now)
    header += ["PIN notices that had ended when the sources were read:", ""] + (ended or ["- none"]) + [""]
    text = "\n".join(header) + "\n" + format_markdown(comparison, sources)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"Side-by-side view written to {args.out}")
    else:
        print(text)
    total = filter_cost + sum(run_cost(m, r) for m, r in comparison.outputs.items())
    print(f"Total for this run, at list prices: about ${total:.4f}.")


if __name__ == "__main__":
    main()
