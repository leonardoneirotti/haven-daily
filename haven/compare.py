"""Haiku 5.5 vs Sonnet 5.5, side by side (spec §5.5, §10 step 6; issue #17).

`python -m haven.compare` runs collect → filter → summarise **once** on today's real items and
summarises the same kept items with both models, through the same code the morning job uses
(`haven.summarise.summarise`, standard API). It prints a side-by-side view for the owner, who
chooses the model (Haiku is the default unless Sonnet is clearly better).

`--dry-run` makes no API call: it collects, runs the free rules and prints the cost estimate,
so the owner can approve the cost before the real run.

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

from haven.config import Place, Source, load_places, load_tags
from haven.feeds import Item
from haven.summarise import SummaryResult, summarise

__all__ = ["HAIKU", "MODELS", "SONNET", "Comparison", "compare", "cost_usd", "estimate", "format_markdown",
           "unsupported_terms"]

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
MODELS = (HAIKU, SONNET)
NAMES = {HAIKU: "Haiku 5.5", SONNET: "Sonnet 5.5"}

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


def estimate(ai_check_items: int, summary_items: int) -> dict:
    """Expected cost of one comparison run: the relevance check plus both summary runs."""
    est = {"filter": ai_check_items * cost_usd(HAIKU, *FILTER_CALL)}
    for model in MODELS:
        est[model] = summary_items * cost_usd(model, *SUMMARY_CALL[model])
    est["total"] = sum(est.values())
    return est


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


def compare(items: list[Item], client, known: list[dict], today: date, models=MODELS,
            max_items: int | None = None, places: tuple[Place, ...] | None = None,
            tags: tuple[str, ...] | None = None) -> Comparison:
    """The same items through `summarise` once per model. Never raises for an API problem."""
    places = load_places() if places is None else places
    tags = load_tags() if tags is None else tags
    chosen = list(items) if max_items is None else list(items[:max_items])
    left_out = [] if max_items is None else list(items[max_items:])
    vocabulary = tuple(p.label for p in places) + tuple(tags) + ("Rotterdam",)

    outputs: dict[str, SummaryResult] = {}
    checks: dict[str, list[list[str]]] = {}
    for model in models:
        result = summarise(chosen, client, known, today, model=model, places=places, tags=tags)
        outputs[model] = result
        per_item = []
        for sent, done in zip(chosen, result.items):
            ai = done.ai or {}
            source_text = f"{sent.headline} {sent.article_text or ''}"
            words = unsupported_terms(ai.get("summary"), source_text, vocabulary)
            words += [w for w in unsupported_terms(ai.get("impact"), source_text, vocabulary) if w not in words]
            per_item.append(words)
        checks[model] = per_item
    return Comparison(items=chosen, outputs=outputs, checks=checks, left_out=left_out, today=today)


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
    lines = [f"Run on {comparison.today.isoformat()}: {len(comparison.items)} kept items, each summarised by "
             + " and ".join(NAMES.get(m, m) for m in models) + " (standard API, the same request).", ""]

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
        lines.append(_row("Off the lists", [_unlisted(ai) for ai in outs]))
        lines.append(_row("Words not in the source", [", ".join(comparison.checks[m][n]) or "none" for m in models]))
        lines.append(_row("Failures", [_failures(comparison.outputs[m], sent.url) for m in models]))
        lines.append("")

    lines += ["### Calls, tokens and cost", "", "| Model | Calls | Tokens | Cost (list price) |", "|---|---|---|---|"]
    for m in models:
        r = comparison.outputs[m]
        cost = cost_usd(m, r.input_tokens, r.output_tokens)
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
    """`python -m haven.compare [--dry-run] [--max-age-days N] [--max-items N] [--out FILE]`. Writes nothing to data/."""
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
    parser.add_argument("--out", type=Path, default=None, help="write the side-by-side view to this file")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # headlines and "·" on a Windows console

    max_age = MAX_AGE if args.max_age_days is None else timedelta(days=args.max_age_days)
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

    if args.dry_run:
        ruled = apply_rules(collected.items, sources, load_filter(), now, max_age)
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
        for label, n in (("if the AI check keeps none", low), ("if it keeps all", high)):
            est = estimate(len(to_ai), n)
            print(f"Estimate {label} ({n} items summarised): filter ${est['filter']:.4f} + "
                  f"Haiku ${est[HAIKU]:.4f} + Sonnet ${est[SONNET]:.4f} = ${est['total']:.4f}")
        return

    client = ai_client()
    if client is None:
        sys.exit("ANTHROPIC_API_KEY is not set (local .env): nothing was sent.")
    filtered = run_filter(collected.items, sources, load_filter(), now, client, max_age)
    if filtered.ai_unavailable:
        sys.exit("The AI check was unavailable: nothing was summarised.")
    kept = [i for i in filtered.items if i.filter and i.filter["kept"]]
    filter_cost = ai_cost_usd(filtered.input_tokens, filtered.output_tokens)
    texts = add_article_text(kept, sources, fetcher)
    known = known_strikes(storage.read_recent("items", before=today, days=14))
    comparison = compare(texts.items, client, known, today, max_items=args.max_items)

    window = "48 h (as the morning job)" if args.max_age_days is None else f"{args.max_age_days} days (comparison only)"
    header = [f"Age limit: {window}.", "", f"Filter: {len(kept)} kept of {len(filtered.items)} ({filtered.ai_calls} {AI_CHECK} calls, "
              f"{filtered.input_tokens:,} in / {filtered.output_tokens:,} out, ${filter_cost:.4f}).", ""]
    header += [f"- FAILURE {f['source']}: {f['error']}" for f in filtered.failures + texts.failures]
    text = "\n".join(header) + "\n" + format_markdown(comparison, sources)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"Side-by-side view written to {args.out}")
    else:
        print(text)
    total = filter_cost + sum(cost_usd(m, r.input_tokens, r.output_tokens) for m, r in comparison.outputs.items())
    print(f"Total for this run, at list prices: about ${total:.4f}.")


if __name__ == "__main__":
    main()
