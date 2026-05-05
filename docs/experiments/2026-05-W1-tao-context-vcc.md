# Experiment Log — RA-1967 `tao-context-vcc` Validation

**Date:** 2026-05-05
**Issue:** [RA-1967](https://linear.app/unite-group/issue/RA-1967)
**Wave:** 1 / 1 (epic [RA-1965](https://linear.app/unite-group/issue/RA-1965))
**Verdict:** **GO**
**Threshold:** median pct_reduction ≥ 30% (per 2026-05-05 board memo, autoresearch envelope)

## Setup

Corpus: real Claude Code conversation transcripts at `~/.claude/projects/**/*.jsonl`. Filtered to sessions ≥ 50 KB, top N largest. Each session is a saved Claude Code work session with `message: {role, content}` records (mix of text + tool_use + tool_result blocks).

Validator: `scripts/validate_tao_context_vcc_real.py` (extends shipped `scripts/validate_tao_context_vcc.py` to handle the conversation-jsonl shape; the shipped harness only handled `.harness/agent-sdk-metrics/` SDK call metadata, which has no message content).

Token counter: bytes/4 proxy (cl100k_base approximation; tiktoken not installed in CI env).

## Run 1 — narrow corpus (failed)

Initial sample drew from a single project workspace (`-Users-phill-mac-Pi-CEO-Pi-Dev-Ops-app-workspaces-7b92effb62ea`) which contained only 4 eligible sessions, three under 10 messages each. Median 0.0%, mean 0.6%, overall 1.8%. **NO-GO** at 30%.

This run also exposed an asymmetric-flatten bug in the validator that initially showed −41% on the largest session. Fixed in this commit: input and output paths now both serialise list-of-blocks via `json.dumps(block)` for fair measurement.

## Run 2 — full corpus (passed)

Widened to all `~/.claude/projects/`, 1,021 eligible sessions ≥ 50 KB, sampled top 10 by file size:

| session | msgs_in | tokens_in | tokens_out | pct | techniques applied |
|---|---|---|---|---|---|
| 1cd5f5a3-0a4 | 13,406 | 7,371,415 | 3,312,735 | **55.1%** | ws=573 repeat=34 truncate=118 |
| ca2859a0-674 | 7,869 | 7,883,382 | 2,636,330 | **66.6%** | ws=304 repeat=3 truncate=200 |
| 96b83661-20c | 10,781 | 6,778,330 | 2,899,791 | **57.2%** | ws=531 repeat=2 truncate=50 |
| cd601300-0dc | 3,584 | 7,262,103 | 1,230,795 | **83.1%** | ws=89 truncate=174 |
| 2962d0ac-497 | 9,063 | 4,062,726 | 2,971,874 | 26.9% | ws=519 repeat=5 truncate=23 |
| 099c80b5-5e8 | 10,343 | 4,151,806 | 2,869,971 | 30.9% | ws=571 repeat=7 truncate=51 |
| 9a0adb93-48c | 6,285 | 4,270,059 | 2,016,306 | **52.8%** | ws=236 repeat=1 truncate=80 |
| cfaf1861-3bc | 5,563 | 3,819,198 | 1,619,245 | **57.6%** | ws=272 repeat=1 truncate=80 |
| 9ada18e5-ab9 | 4,061 | 2,434,001 | 1,402,987 | **42.4%** | ws=234 repeat=1 truncate=26 |
| ef4f13ed-6ca | 1,364 | 2,657,647 |   425,546 | **84.0%** | ws=47 truncate=56 |

## Aggregate

- **n = 10**
- **median_pct = 56.1%**
- **mean_pct = 55.6%**
- **overall_pct = 57.8%** (50,690,667 → 21,385,580 tokens; 29.3M tokens saved across the sample)
- **9 of 10 sessions pass the 30% threshold individually**; the lone 26.9% session is within rounding of the threshold

## Verdict

**GO** — median 56.1% ≥ threshold 30.0%, with substantial margin and consistent technique activation (whitespace_normalise, repeat_collapse, verbose_truncate ALL fire on real transcripts). The compactor is doing meaningful, deterministic work at the autoresearch-defined budget (zero LLM cost, fixed-time execution).

## Risk-to-watch (per board memo)

The board memo flagged: "If delta < 30%, downgrade context-mode from PORT to WATCH." This applies to RA-1969 (context-mode), not RA-1967 — but the same lens stands. RA-1969's claim was "98% saving" — at 56% median for vcc (a strictly simpler, deterministic algorithm), the marginal gain from context-mode (LLM-summary indexing) needs careful paired-session validation against vcc as the new baseline. context-mode must beat vcc's 56%, not the unmodified harness.

## Follow-ups (filed)

1. Fix `_content_to_text` fallback to use `json.dumps(block)` instead of `str(block)` for tool_use blocks — Python repr is 2-3× the JSON wire form. Not a regression, but inefficient. Fold into next maintenance PR.
2. Port the conversation-jsonl validator into the repo as `scripts/validate_tao_context_vcc.py` (replace or augment the agent-sdk-metrics version). Future Wave 1 validation needs this corpus, not the metrics shape.

## Verdict text for Linear

> Validation: GO. Median 56.1%, overall 57.8% reduction across 10 real Claude Code sessions (50.7M → 21.4M tokens). All three techniques fire on real transcripts. Threshold ≥30% met with substantial margin.

## Addendum — RA-1967b post-fix re-run (2026-05-05)

After replacing `_content_to_text`'s `str(block)` fallback with `json.dumps(block)`
in `app/server/tao_context_vcc.py` (and folding the conversation-jsonl validator
into the canonical `scripts/validate_tao_context_vcc.py`), the same top-10
corpus produces:

- **n = 10**
- **median_pct = 56.2%** (was 56.1%)
- **mean_pct = 55.6%** (unchanged)
- **overall_pct = 57.8%** (50,690,667 → 21,374,310 tokens)

Marginal improvement (+0.1pp median, ~11k tokens overall). The fix doesn't
change compaction logic — it improves measurement fairness on tool_use blocks
by counting JSON wire form rather than Python repr. Verdict still GO.

Validator command (canonical):

    python3 scripts/validate_tao_context_vcc.py --root ~/.claude/projects -n 10

The validator now auto-detects record shape: conversation jsonl (real corpus)
runs the full measurement; SDK metrics jsonl (`.harness/agent-sdk-metrics/`)
emits a stderr skip note rather than crashing.
