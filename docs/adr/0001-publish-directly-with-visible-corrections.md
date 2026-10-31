---
status: accepted
date: 2026-10-31
---

# Publish directly, fix with visible corrections

The original plan put a human review between the AI and the public page: a 06:30 job opened a pull request, the owner could approve or edit it from their phone, and an 08:00 job auto-merged it if they hadn't. We dropped that. One scheduled job (~06:45 Amsterdam) now builds the brief, commits it straight to `main` and deploys it, **unreviewed**. Mistakes are fixed afterwards, and every fix to a published brief must add a dated correction note (`corrections: [{at, note}]`) that the page shows as "Corrected HH:MM" (hard rule 11). The page never changes silently.

**Why:** the owner is usually not awake before 08:00, so the review step would almost never have been used. It only added complexity: two jobs, a race between a late review and the 08:00 auto-merge, and summer/winter time handling for both.

## Considered options

- **PR review window + 08:00 auto-merge** (original plan): a human check before publishing, at the cost of two jobs and a daily PR.
- **Publish directly, fix silently**: simplest, but an AI-written page that changes without saying so loses trust.
- **Publish directly, fix with visible corrections** (chosen).

## Consequences

- Readers always see AI output that no human has checked. The page and the Method page say so, and hard rules 1, 9, 12 and 13 plus the fixed place and tag lists (spec §5.10) limit what the AI can get wrong.
- Corrections are a manual habit. `CLAUDE.md` makes Claude add the note itself and wait for the owner's OK before committing.
- The daily job needs write access to `main`; `main` is protected only against force-pushes and deletion (spec §5.1).
- If a review step is ever wanted back, it can't simply be re-enabled: the brief format no longer has `review` / `published_at`, and the templates and renderer would need the old states again.
