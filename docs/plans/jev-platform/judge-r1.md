**DO NOT APPROVE BUILD — 56/100.** The plan states fail-closed intentions, but rule selection, class assignment, malformed responses, and evidence ratings leave material gaps.

1. **P0/P1 decision-policy defects**

   - **P0: Caller-selected rules bypass coverage.** `--rules calibrated` excludes uncalibrated rules; explicit IDs can omit violated rules. Every selected rule could pass while an applicable, unscored rule is silently excluded. An empty selection could also reach “otherwise → allow.” Require a nonempty, validated coverage manifest. Incomplete applicability must escalate. A subset evaluation may report “selected rules passed,” never overall `allow`.
   - **P0: Caller-supplied class bypasses Waterline.** `--class 2` can describe an actual Class 3 action. The plan provides no mechanism to establish the highest applicable class or resolve ambiguity upward. Treat the supplied class as a claim requiring validation; unresolved classification must escalate.
   - **P1: Malformed scores can fall through.** Error handling does not specify finite numeric values within `[0,1]`, exact rule-ID matching, uniqueness, or response completeness across chunks. For example, NaN fails every ordered comparison and can reach `allow`. Validate the complete response before evaluating policy.
   - **P1: No fail-closed calibration failure state.** Specify escalation when no candidate threshold achieves zero misses, artifacts are invalid, or calibration no longer matches the rule, model, prompt, or scoring configuration.
   - **Outages:** Explicit errors, timeouts, and missing answers correctly escalate *as written*. Preserve `signal_unavailable` distinctly; do not substitute a score or imply compliance. A partially successful batch must never allow.

   These are policy defects; the stated absence of live integration limits their immediate operational impact.

2. **Calibration is not sound as proposed**

   Choosing `0.9` because it has zero misses on the same data used to select it measures fitting performance, not independent validation. Claude–Codex agreement is a proxy label with potentially correlated errors; filtering to agreement can remove difficult cases. The relevant safety denominator is the number of **violation cases**, which the supplied result omits—not all 1,256 cases.

   The result also reports 285 false alarms at `0.9`, versus 476 at `0.95`; neither can be interpreted as a false-alarm rate without the compliant-case count. Aggregate threshold counts do not demonstrate performance of the complete abstention and decision policy.

   **Minimum slice-1 fix:** Preserve case-level scores, labels, provenance, and denominators; separate calibration and untouched validation sets by scenario family; freeze the threshold before validation; evaluate the actual decision policy; report uncertainty and escalation burden. Include independently adjudicated violation and ambiguity cases. If this evidence is unavailable, keep calibration provisional and disable overall `allow`. Zero observed misses must never be described as zero risk.

3. **AA/AAA mapping overclaims**

   Scored agreement with two models does not prove constitutional compliance. SHA binding establishes provenance, not label truth or generalisation. Under the stated ladder, model-inferred compliance remains **A**, even when its artifacts have excellent provenance.

   Separate **artifact verification**, **empirical evaluation results**, and **decision evidence**. AAA can describe a genuinely verified, exact-SHA-bound artifact or check; it cannot automatically promote inferred compliance to AAA. Overall evidence must include classification and coverage, not merely the minimum rating among selected rules.

   `first-result.json` contains no eval SHA, Constitution revision, case-level provenance, or immutable model identity; it cannot establish AAA.

4. **Slice-1 scope and missing safeguards**

   - Cut automatic AA/AAA promotion and the successful-`allow` finish-line assumption until the preceding gaps are resolved.
   - Keep the library, CLI, registry, and offline tests. Label every output explicitly as a **shadow recommendation** and retain the structural separation from execution.
   - Add focused tests for omitted/empty/unknown rules, understated or ambiguous classes, invalid scores, duplicate IDs, partial chunks, stale calibration, and no qualifying threshold.
   - Define structured unavailable/error output, deterministic verdict precedence, bounded requests/retries, approved spend limits, and redaction of actions/results. Runtime key injection alone does not establish these protections.
   - Treat the two live examples as transport smoke tests only. They provide no meaningful calibration validation.

5. **Score and exact build conditions**

   | Category | Score |
   |---|---:|
   | Evidence | 7/25 |
   | Problem | 18/20 |
   | Reuse | 10/15 |
   | Security | 6/15 |
   | UX | 6/10 |
   | Testability | 7/10 |
   | Cost | 2/5 |
   | **Total** | **56/100** |

   Before approval, revise the plan to require validated coverage and Waterline classification; strict complete-response validation; explicit invalid/stale calibration states; independent validation of frozen thresholds; honest, separated evidence ratings; and the shadow, testing, privacy, and cost safeguards listed above.

Reviewed `BRIEF.md`, `PLAN.md`, and `first-result.json`. No files changed; document and result inspection only, with no executable checks run.