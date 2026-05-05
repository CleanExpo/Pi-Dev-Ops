# RA-1969 — tao-context-mode validation experiment

**Week:** 2026-05-W3
**Linear:** RA-1969
**Sibling experiment:** RA-1967 (`tao-context-vcc`) — vcc baseline source.

## Hypothesis

Summary-index + on-demand expansion (the `context-mode` pattern) reduces working
context tokens by an additional ≥40% beyond what the deterministic `vcc`
compactor (RA-1967) already achieves.

## Method

- Repo: this sandbox (Pi-Dev-Ops).
- Scope dir for vcc baseline: `app/server/`.
- 10 hand-crafted questions in `scripts/_context_mode_questions.json`, each
  with `expected_files` listing the path(s) the question genuinely needs.
- Token counter: `tiktoken` cl100k_base.
- Baseline (vcc): flatten every source file in scope into a mega-prompt, run
  `tao_context_vcc.compact()`, count tokens.
- Treatment (context-mode): start with the index summaries, expand only the
  `expected_files` per question, count tokens.
- pct_reduction = (vcc_tokens − mode_tokens) / vcc_tokens × 100.

## Result

| Metric | Value |
|---|---|
| Files indexed | 582 |
| Bytes indexed | 4,404,851 |
| vcc baseline tokens | 228,754 |
| Questions | 10 |
| **Median reduction (mode vs vcc)** | **89.30%** |
| Mean reduction | 87.95% |
| Min / max | 79.06% / 90.01% |
| Threshold (per board memo) | ≥40% |
| Outcome | **PASS** |

The full per-question table is reproducible via:

```
python scripts/validate_tao_context_mode.py --repo-root .
```

## Interpretation

The Technical Architect's Round-2 challenge held: vcc already achieves a large
reduction out of the box (median 56.1% over raw harness, RA-1967 experiment
log). The threshold of "≥40% additional reduction over vcc" was deliberately
chosen to make context-mode prove its marginal value, not just its absolute
saving.

context-mode comfortably clears that bar at 89.30% median. The mechanism is
intuitive in retrospect: vcc operates after a transcript has accumulated, so
it can only compact what was already loaded; context-mode operates BEFORE
loading, so it never pays the cost of files the current task does not need.

The two primitives are complementary, not competing:
- `tao-context-mode` — pre-load filtering ("don't load what you don't need")
- `tao-context-vcc` — post-load compaction ("compact what you did load")

## Caveats

- This experiment uses hand-curated `expected_files`. In a live TAO loop the
  agent picks which files to expand, so realised reduction depends on agent
  precision. A follow-up experiment should measure expansion precision/recall
  on real TAO sessions once telemetry is in place.
- The default `TAO_MAX_ITERS=25` kill-switch trips during a real-repo index
  scan because it ticks once per file. The validator and CLI runner override
  to `100000`. Production callers building an index over a real repo must do
  the same — file the follow-up to either bump the default for non-LLM
  callers or expose a per-counter override.

## Recommendation

**GO.** Ship the skill + module + tests + validator. The 89.30% median is well
above the 40% threshold, and the build/expand pattern is composable with the
existing vcc compactor (use both: index-first, compact what survives).

Per the 2026-05-05 board memo, the disposition would have been WATCH (not
REJECT) on a borderline result; this is comfortably PASS.

## Artefacts

- Module: `app/server/tao_context_mode.py`
- Skill: `skills/tao-context-mode/SKILL.md`
- Tests: `tests/test_tao_context_mode.py` (12 tests, all green)
- Validator: `scripts/validate_tao_context_mode.py`
- CLI runner: `scripts/run_tao_context_mode.py`
- Questions: `scripts/_context_mode_questions.json`
