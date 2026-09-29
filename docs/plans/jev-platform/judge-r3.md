**DO NOT APPROVE BUILD — 90/100, up from 76.** Rev 3 substantially improves the plan, but material budget, privacy and evidence gaps remain even for a shadow slice.

1. **Decision policy and round-2 conditions**

   No recommendation-level `allow` or `no_objection` path remains. Unverified classification forces escalation; classification evidence forces overall **FAIL**. Those are appropriate limits.

   | Round-2 condition | Rev 3 verdict |
   |---|---|
   | Unverified/invalid classes; duplicate selections | **Resolved.** Explicit escalation. |
   | Malformed responses, outages, partial batches | **Resolved in the plan.** Complete-response validation remains mandatory before policy. |
   | Threshold and abstention boundaries | **Resolved.** Inclusive `[0.40, 0.60]` abstention is explicit. |
   | Missing, corrupt, failed, stale calibration | **Mostly resolved.** States are explicit; rule-level positive-output gating needs clarification below. |
   | Calibration independence and proxy-label limitations | **Acceptably deferred through provisional-only status.** Fresh grouped validation and adjudication are not prerequisites for this restricted shadow slice. |
   | Minimum denominators, validation misses, counters | **Resolved.** Rule-level misses prevent blanket escalation from manufacturing detection success; old overlapping counters are excluded. |
   | Label provenance and quantified uncertainty | **Unresolved.** Neither is specified adequately. |
   | Verified artifact evidence; classification and coverage ratings | **Substantially resolved.** AAA now requires verification; overall FAIL is honest. Clarify AA below. |
   | Enforced resource limits | **Partially resolved, P1.** Estimates do not establish hard bounds. |
   | Mandatory live finish line | **Resolved as a plan requirement:** explicit scoped authorization assertion and `--live` gate. Actual authorization was not independently verified here. |
   | Outbound, recorded and error privacy | **Partially resolved, P1.** Error minimisation is sound; outbound protection remains incomplete. |
   | Tests with explicit expected outcomes | **Partially resolved.** Important assertions remain ambiguous. |

   **New positive-output ambiguity:** the [rule-pass predicate](/tmp/jev-judge/PLAN.md:163) requires a score and abstention check, while only the failure predicate explicitly requires `provisional`. The state table prevents a positive recommendation, but should also explicitly prevent a stale or failed record from displaying a positive **per-rule** finding. Require complete-response validity and `state == provisional` before either pass or fail classification.

2. **Calibration**

   “Lowest threshold with zero observed misses” is acceptable **candidate selection**, not demonstrated safety. Rev 3 correctly keeps results provisional because of proxy labels, related scenarios and a mutable model alias. Repartitioning previously inspected cases also does not create an untouched holdout.

   Two round-2 requirements remain:

   - Preserve label-generation provenance: producing models/prompts or their identifiers, agreement/exclusion procedure, and adjudication status. A dataset hash establishes identity, not how labels were obtained.
   - Specify uncertainty reporting. “0 of N” and a minimum of 50 cases do not quantify uncertainty. Any interval must state its assumptions and cannot establish true constitutional-violation risk from correlated model labels. Where those assumptions are unsupported, explicitly report that limitation.

   The revised disjoint counters are useful, but define their exhaustive allocation—including violations that abstain—and retain compliant-case escalation burden separately.

3. **Evidence ratings**

   Overall **FAIL**, classification **FAIL**, unavailable judgment **FAIL**, and inferred judgment at most **A** are honest.

   AAA is now defensible **for the artifact verification claim only**, provided “at the exact commit” means the checked files actually match that tree.

   Change “AA: valid but not bound” to **“the same verification checks passed, but without exact-SHA binding.”** Schema validity alone does not satisfy “proven.”

4. **Remaining material safeguards and exact changes**

   - **P1 — enforce actual resource bounds.** [Characters ÷ 3](/tmp/jev-judge/PLAN.md:207) is not a conservative token ceiling. Bound the complete serialized request using a supported tokenizer or a justified conservative upper bound; reserve worst-case billable usage before each attempt. Set each request timeout and retry wait from the remaining run deadline. A pre-send elapsed-time check alone cannot stop an in-flight request overrunning it.
   - **P1 — restrict live data and preserve meaning.** [The regex list](/tmp/jev-judge/PLAN.md:215) misses names, addresses, free-form customer information and other credential formats. It can also remove facts needed to judge an action. The smallest slice-1 fix is **synthetic, non-sensitive live inputs only**. Apply identical preprocessing during calibration and decisions, bind its version, and mark materially altered inputs uncertain.
   - **Make tests unambiguous.** Specify expected results at every boundary, including `0.10`; invalid calibration plus a high score must never yield a per-rule pass. Replace “every other positive output” with separate assertions for permitted provisional per-rule passes and prohibited positive recommendations. Add remaining-deadline, retry-budget and calibration-provenance checks.

   Keep the library, CLI, offline tests and isolated transport smoke test. No additional integration or class-inference work is needed for approval.

5. **Rescore**

   | Category | Score |
   |---|---:|
   | Evidence | 21/25 |
   | Problem | 20/20 |
   | Reuse | 15/15 |
   | Security | 12/15 |
   | UX | 10/10 |
   | Testability | 9/10 |
   | Cost | 3/5 |
   | **Total** | **90/100** |

   Approval requires the explicit state guard, calibration provenance/uncertainty and AA corrections, enforceable budgets, restricted live-data handling, and precise tests above.

Reviewed `BRIEF.md`, `PLAN.md`, `judge-r1.md`, `judge-r2.md`, and `first-result.json`. No files changed; no executable tests or live calls run. This is a pre-build document verdict, not implementation verification.