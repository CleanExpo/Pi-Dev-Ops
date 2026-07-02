# ADR 006: Langfuse for LLM-native eval — CONDITIONAL GO (time-boxed PoV, eval slice only)

**Date:** 2026-07-01
**Status:** Conditional GO — 2-week proof-of-value, no standing adoption
**Decision body:** CEO Board (9-persona deliberation, research-grounded)

## Context

Pi ("2nd Brain") has **no LLM-native tracing/eval loop** — there is no way to know
whether a change to a classifier prompt (e.g. `feedback_loop._classify_with_claude`)
made results better or worse *before* shipping. The gap is real.

Langfuse was evaluated as the candidate tool (see `[[llm-stack-adoption-decision]]`).
Two things made this a **Board** call rather than an engineering one:

1. **Locked-constraint collision.** `[[feedback-no-sentry]]` bans third-party
   *production observability* SaaS — Pi-CEO projects use Vercel-native observability
   only. Langfuse markets itself as an observability platform, so at first glance it
   is a direct violation.
2. **Self-host footprint.** Self-hosted Langfuse v3 requires **four stateful backing
   services** — Postgres + ClickHouse + Redis/Valkey + S3-compatible blob store — plus
   two app containers (verified against langfuse.com self-hosting docs, 2026-07-01).

## Research findings (verified 2026-07-01, all cited to langfuse.com primary sources)

- **Q1 — Cloud Hobby (free):** free, no card; **50,000 units/month**, 30-day retention,
  2 seats; all features (tracing, prompt mgmt, evals, datasets, SDKs) within caps.
- **Q2 — Eval/datasets without prod traces:** **Yes, fully standalone.** Datasets
  populate via UI/SDK/API, **CSV upload**, or synthetic gen; experiments run with no
  live traces; `source_trace_id` is optional metadata. Upload → run-experiment →
  score works as an isolated eval harness with **zero production-trace ingestion.**
- **Q3 — Self-host:** 4 stateful services (Postgres, ClickHouse, Redis, S3) + 2 app
  containers. Materially heavier than v2's Postgres-only.
- **Q4 — Python SDK:** maintained OTEL-based SDK v3 (GA Jun 2025); one `@observe`
  decorator instruments a call — decorator-level, not a rewrite.
- **Q5 — Residency/training:** US / **EU (Ireland)** / Japan / HIPAA regions; **free
  tier available in EU**; customer traces/prompts **never used to train** any model;
  SOC 2 Type II + ISO 27001. (HIPAA/BAA gating is Med-confidence — enterprise, not
  inline-stated.)

## Decision

**CONDITIONAL GO — a 2-week proof-of-value using the Langfuse Cloud EU free tier as an
OFFLINE eval-dataset harness ONLY. Kill date enforced; no renewal without a measured win.**

Explicitly:
- ✅ **Cloud EU free tier**, eval-dataset + experiment features only.
- ✅ Datasets are **synthetic / redacted rows only** (no PII → the HIPAA/BAA open
  question never binds).
- ✅ Runs **offline** (local / CI), scored against `tao_judge`'s scalar metric, on the
  same classifier work as the DSPy PoV (`[[llm-stack-adoption-decision]]` item 4).
- ✅ The **golden eval dataset lives in-repo** (the durable asset); Langfuse is a
  disposable runner over it.
- ❌ **No self-host** (the 4-service v3 stack — excluded on sight).
- ❌ **No production traces** off-platform — that IS the `[[feedback-no-sentry]]` line.
- ❌ **No standing adoption** — the PoV competes head-to-head with a plain
  `tao_judge`-writes-CSV harness; whichever earns it is kept.

**Why this clears `feedback-no-sentry`:** an offline eval harness that never ingests
production traffic is a **test tool** (same category as pytest), not production
observability (Sentry's category). The ban is on the latter. The seam that keeps this
legal is Q2 — the eval slice is genuinely trace-free.

## The dissent that almost changed the decision

The **Contrarian** held that we may not need Langfuse at all: `tao_judge` already emits
a scalar score, and a 50-line pytest harness writing those scores to a CSV may equal or
beat Langfuse's dataset/experiment UI for our scale. This did not flip the decision — but
it *shaped* it: the GO is a **bake-off**, not an adoption. Langfuse must out-earn the
CSV baseline on the same work, or it's dropped at the kill date. The Contrarian withdrew
the block on that basis.

## What would change this decision

- If the eval slice turns out to require prod-trace ingestion in practice (contradicting
  Q2) → **NO-GO**, it becomes observability and hits `feedback-no-sentry`.
- If the `tao_judge`-CSV baseline matches Langfuse's value in the bake-off → drop Langfuse,
  keep the in-repo harness.
- If any real (non-synthetic) data is needed in datasets → re-open the Q5 residency/BAA
  question before proceeding.

## Next actions

1. **Eng (Pi-Dev-Ops, Python 3.11):** during the DSPy PoV, stand up a Langfuse Cloud EU
   free-tier project + a parallel `tao_judge`-CSV harness over the same `feedback_loop`
   classifier cases. Done = both produce a v1-vs-v2 score comparison on ≥30 synthetic
   cases. Kill date: **2026-07-15**.
2. **Eng:** keep the golden eval dataset committed under `docs/experiments/` (in-repo,
   tool-independent). Done = dataset file lands in the repo, not only in Langfuse.
3. **Board:** review the bake-off result at the kill date; adopt Langfuse-eval ONLY on a
   measured lift over the CSV baseline. Done = a follow-up status on this ADR (GO→adopt or
   drop).

## Risk to watch

The single most dangerous assumption: that "eval slice" stays trace-free in practice. The
moment convenience pulls a production trace into Langfuse "just to debug," this silently
becomes the observability SaaS `feedback-no-sentry` forbids. The synthetic-data-only +
offline-only guardrails exist to prevent exactly that drift.

## Cross-refs

- `[[llm-stack-adoption-decision]]` — parent eval (langfuse = ESCALATE-to-Board)
- `[[feedback-no-sentry]]` — the locked constraint this threads
- `[[feedback-anthropic-first]]` — classifiers run off-Anthropic (cheap tier); cost frame
- `[[adrs/004-implementation-conventions]]` · `[[feedback-secrets-handling]]` (Langfuse
  keys in `~/.hermes/.env`, never pasted)
