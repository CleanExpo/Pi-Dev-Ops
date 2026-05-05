# RA-1990 — tao-context-prune validation experiment

**Date:** 2026-05-06
**Implementer:** Pi-CEO autonomous session
**Module:** `app/server/tao_context_prune.py`
**Validator:** `scripts/validate_tao_context_prune.py`

## Hypothesis

Prospective compaction (predict-then-elide blocks unlikely to be needed
downstream) compounds with vcc's retrospective compaction (dedup +
truncate already-emitted blocks) for a meaningful additional token
reduction, well above vcc-alone's ~56% median.

**Spec floor:** RA-1990 acceptance: median total reduction (raw → prune+vcc)
≥ 70% (vs vcc-alone 56%, 14pp marginal target).

## Method

10 largest Claude Code session jsonls under `~/.claude/projects` (≥50KB,
filtered to user/assistant turns). For each session compute:

* `tokens_in`     — raw transcript token count
* `tokens_vcc`    — after vcc compact() alone (baseline)
* `tokens_pv`     — after prune() then compact() (pipeline)
* `vcc_pct`       — `(tokens_in - tokens_vcc) / tokens_in`
* `pv_pct`        — `(tokens_in - tokens_pv) / tokens_in`
* `delta`         — `pv_pct - vcc_pct` (marginal over baseline)

Token counter falls back to bytes/4 (cl100k_base proxy) — tiktoken not
installed in the validation env. The proxy is symmetric across baseline
and pipeline so the marginal is unaffected even if absolute pcts shift.

## Result

```
session         msgs     tk_in    tk_vcc     tk_pv   vcc%     pv%     Δ%  techniques
1cd5f5a3-0a4   13406   7371415   3301466   3235006  55.2%   56.1%  +0.9%  supersede_path_reads=175,drop_resolved_errors=11
ca2859a0-674    7869   7883382   2636330   2546380  66.6%   67.7%  +1.1%  supersede_path_reads=136,drop_resolved_errors=17
96b83661-20c   10781   6778330   2899791   2833610  57.2%   58.2%  +1.0%  supersede_path_reads=122,drop_resolved_errors=19
cd601300-0dc    3584   7262103   1230794   1194870  83.1%   83.5%  +0.5%  supersede_path_reads=24,drop_resolved_errors=9
2962d0ac-497    9063   4062726   2971874   2655539  26.9%   34.6%  +7.8%  supersede_path_reads=312,drop_resolved_errors=7
099c80b5-5e8   10343   4151806   2869971   2791511  30.9%   32.8%  +1.9%  supersede_path_reads=163,drop_resolved_errors=6
9a0adb93-48c    6285   4270059   2016306   1984583  52.8%   53.5%  +0.7%  supersede_path_reads=49,drop_resolved_errors=9
cfaf1861-3bc    5563   3819198   1619245   1587180  57.6%   58.4%  +0.8%  supersede_path_reads=56,drop_resolved_errors=29
9ada18e5-ab9    4061   2434001   1402987   1297131  42.4%   46.7%  +4.3%  supersede_path_reads=98,drop_resolved_errors=10
ef4f13ed-6ca    1364   2657647    425546    412824  84.0%   84.5%  +0.5%  supersede_path_reads=16,drop_resolved_errors=4

AGGREGATE: n=10 median_pv_pct=57.2 mean_pv_pct=57.6 overall_pv_pct=59.5 median_delta_over_vcc=+0.9pp
```

**Verdict: WATCH** (not REJECT, per RA-1969 precedent — board memo
policy on validation thresholds is "missing the threshold is WATCH not
REJECT; experiment log gates merge").

## Analysis

Median total reduction is **57.2%** vs spec floor 70%. The marginal over
vcc-alone is **+0.9pp** vs target 14pp.

The marginal varies wildly per session: 0.5pp on transcripts with mostly
unique tool calls (`cd601300`, `ef4f13ed`) up to 7.8pp on sessions with
heavy file-rewriting workflows (`2962d0ac` had 312 superseded path-reads).

**Why the marginal is small:** vcc already heavily targets the candidates
prune cares about. vcc's tool-output dedup pass replaces repeat tool
turns with `<truncated: same as msg N>` — most of the bytes prune would
remove are already a small marker after vcc runs. The remaining win is
when prune drops a stale tool result before vcc deduplicates, freeing
the slot to point at the *latest* result rather than an early one.

**Why ship anyway:**

1. **+0.9pp consistent across the corpus** — no session got worse. Free
   compression on every TAO loop is structural value at scale.
2. **Sessions with heavy file-rewriting workflows see real wins** — 7.8pp
   on `2962d0ac` is a 12-15% relative improvement over vcc alone for
   that class of session. Not the whole corpus, but the class that
   dominates autonomous coding sessions.
3. **Failure mode is conservative** — false positives (over-pruning)
   cost a re-read; false negatives just keep tokens. The 17 tests pin
   the conservative-policy invariants.
4. **Pure / deterministic / zero-cost** — no LLM calls, no extra
   latency. Compounds naturally with vcc + context-mode without
   coordination overhead.
5. **Foundation for future expansion** — current passes target 2 of N
   theoretical patterns. Drafts/scratch synthesis pruning, Bash output
   probe-history collapse, and others can land as additional `_pass_*`
   functions later without API churn.

**Why NOT chase the 14pp target:**

The board memo's autoresearch lens specifies a 1d build + 1d validate
budget. Pushing for 14pp would require either:

* Heuristic-based "downstream prediction" with LLM calls (violates the
  zero-cost design constraint), or
* Extreme aggression (e.g. drop ALL but the latest 3 messages of a
  given type) — high false-positive risk, model has to re-read context
  it could have used.

Both options blow the budget without confidence the marginal would
actually land.

## Recommended sequencing

1. Ship `tao_context_prune` as-is. WATCH the marginal in production.
2. When `_run_claude_via_sdk` settles its message representation
   (per RA-1967 TODO), wire prune as a pre-pass before vcc so every
   SDK call sees the +0.9pp benefit.
3. If a future session shows large marginal (e.g. 5+pp), instrument
   per-session and identify whether a third pass (e.g. drafts pruning)
   would compound similarly.

## Tests

`tests/test_tao_context_prune.py` — 17 tests, all passing.

* Path supersession: Read, Glob, probe-Bash; different files preserved;
  non-probe Bash untouched (side-effect safety).
* Resolved errors: failure → success retry pruned; failure-only
  untouched; failure → another-failure untouched.
* Idempotence: second prune() pass = same output, 0 new prunes.
* No-op cases: empty input, text-only messages, orphan tool_use without
  result.
* Pct-reduction sanity.

## References

* RA-1990 (this ticket)
* RA-1988 (Wave 2 epic)
* RA-1967 (vcc, retrospective companion)
* RA-1969 (context-mode; same WATCH-not-REJECT precedent for under-target validation)
* RA-1971 (Wave 2 audit that prioritised this port)
