---
name: improve-system
description: B.U.I.L.D. Loop — the improvement engine. Scans the 2nd Brain vault + session digests for fixable problems (broken wikilinks, orphan sources, near-duplicate pages, session signal) and emits GRADED proposals into 3 buckets (auto-apply / need-signoff / more-context) as a dated Obsidian review file with approve/reject checkboxes. Use when the user says "improve the system", "what should we fix in the brain", "run the improvement loop", or on the Tue/Fri improvement routine. Auto-apply is OFF by default (review-first).
---

# improve-system

Closes the self-improving loop. Turns the corpus + the session digests (from
`sync-claude-sessions`) into graded, human-reviewable improvement proposals.

## What it scans (deterministic, no LLM — free + fast)

- **Broken wikilinks** in `Wiki/` — aggregated by missing target. A page
  referenced by many others but never created is a strong "write this" signal
  (≥3 refs → need-signoff, else more-context). Sources/ and process/ are NOT
  link-checked (raw/derived, arbitrary refs).
- **Orphan sources** — `Sources/` files never cited by any Wiki page.
- **Near-duplicate pages** — Wiki pages sharing a normalized H1 title.
- **Session signal** — aggregate of `process/sessions/` digests (count + top
  projects) as candidate coverage; a future LLM pass will extract concrete
  learnings per digest.
- **.harness lessons** — delegated to `analyse_lessons.py --dry-run` (separate).

## CLAUDE.md hygiene (guided lint → need-signoff)

CLAUDE.md loads on every message, so bloat there silently degrades instruction-following
(signal-to-noise collapse), not just token cost. When reviewing the knowledge system, lint
each CLAUDE.md and emit fixes as need-signoff proposals:

- **Router, not a vault** — a lean file that points to detail by path, not one that holds it.
  Flag aspirational tone ("we value quality"), anything Claude can infer ("this is a React
  project"), stale/wrong rules, and emojis (Claude mirrors them into commits).
- **Per-folder split** — when a root CLAUDE.md crosses ~80 lines or the project passes ~10
  folders, propose splitting folder-specific rules into per-folder `CLAUDE.md` files (5–20
  lines each); the root keeps only cross-folder rules. Route every rule, lose none.

Enforces [[feedback-no-status-bloat]] and [[feedback-no-false-reporting]]: never propose a
status snapshot or an unverified claim into a CLAUDE.md.

## Buckets

- **auto-apply** — low-risk computable fixes. Applied + logged to
  `Wiki/_changelog.md`. **DEFAULT OFF** (review-first); enable with `--auto-apply`.
- **need-signoff** — higher-stakes (create missing page, merge dupes, cite/archive
  orphan). Written to `Outcomes/reviews/YYYY-MM-DD-improve-review.md` with
  `- [ ] Approve / Reject / Approve & don't ask again` per item.
- **more-context** — found but undecidable; same review file.

## How to run

```bash
cd ~/Pi-Dev-Ops
python3 scripts/improve_system.py --dry-run     # review → scratch (safe)
python3 scripts/improve_system.py               # review → vault, auto-apply OFF
python3 scripts/improve_system.py --auto-apply  # also apply the safe bucket
python3 scripts/test_improve_system.py          # 12 assertions, must be ALL PASS
```

## Operating rhythm (DRIVE)

Review-first for week 1: read the dated review file in Obsidian, tick boxes,
re-run. Only enable `--auto-apply` for categories you've watched produce clean
proposals. The human is the leader — you sign off, the system does the lifting.

- Spec: `~/Pi-Dev-Ops/docs/specs/2026-06-29-self-improving-system-build.md`.
- Upstream: `sync-claude-sessions` (produces the digests this reads).
- Orchestration: `/data-ingestion` runs the miner; this runs after.
