**DO NOT APPROVE BUILD — 76/100, up from 56.** Revision 2 closes several important paths, but “every point is addressed” overstates the result.

1. **Decision policy: round-1 findings**

   | Round-1 finding | Verdict on rev 2 |
   |---|---|
   | Selected rules imply overall permission | **Resolved for scoped shadow reporting.** Removing `allow` and displaying evaluated/unevaluated counts satisfies the subset-reporting alternative. |
   | Empty/invalid selection | **Mostly resolved.** Duplicate input IDs appear in tests but need an explicit rejection policy. |
   | Caller understates autonomy class | **Unresolved, P1.** A claimed Class 0–2 remains unverified yet can produce `no_objection_on_evaluated_rules`. Reporting uncertainty does not implement Waterline’s upward escalation. |
   | Malformed responses and partial batches | **Resolved in the plan.** Complete validation precedes policy; unavailable signals cannot become a positive recommendation. |
   | No qualifying threshold | **Resolved.** Explicit escalation is specified. |
   | Invalid/stale calibration | **Partially resolved, P1.** Missing bindings escalate, but corrupt artifacts and failed validation lack explicit states. A mutable model name such as `jev-latest` cannot detect a model change behind the same alias. |
   | Verdict precedence and unavailable output | **Resolved in principle.** Preserve the rule that response-validation failure terminates evaluation before verdict precedence. |

   There is **no literal `allow` path remaining**. However, these paths can still produce unjustified positive shadow output:

   - A rule passes despite unresolved autonomy classification.
   - Validation observes misses, but the record is nevertheless treated as “validated”: [PLAN.md:79](/tmp/jev-judge/PLAN.md:79) specifies reporting, not acceptance.
   - A frozen threshold of `0.5` may classify a near-0.5 score as passing despite the stated uncertainty rule. Define comparison boundaries and an explicit abstention interval.

2. **Calibration: improved, still provisional**

   Freezing before validation, retaining scores, reporting violation/compliant denominators, and testing the actual policy resolve much of round 1. Choosing the lowest qualifying threshold is reasonable as a **candidate-selection heuristic**, not proof of safety.

   Outstanding findings:

   - Splitting by case permits related scenarios across both sets. Disclosure does not establish independence.
   - Claude–Codex agreement remains a biased proxy, with correlated errors and difficult disagreements excluded.
   - Independently adjudicated violation/ambiguity cases and quantified uncertainty remain absent.
   - If the same 1,256 cases informed the earlier threshold analysis, splitting them now does not create an untouched holdout.
   - Case hashes and labels alone omit label-generation/adjudication provenance.

   **Minimum slice-1 change:** explicitly mark this calibration **provisional** unless supported by fresh, grouped validation and independent adjudication. Define acceptance/failure states, nonzero minimum denominators, and uncertainty reporting before using “validated.” Count a violation receiving `no_objection_on_evaluated_rules` as a miss; separately report rule-level performance so blanket class escalation cannot manufacture perfect detection.

   **New evidence ambiguity:** `first-result.json` reports 1,252 correct + 2 misses + 2 false alarms = 1,256, alongside 12 abstentions. Explain whether those counters overlap; the result does not establish complete-policy performance.

3. **Evidence ratings: partially fixed**

   Keeping inferred compliance at **A** resolves the principal overclaim. Two remaining problems:

   - [PLAN.md:100](/tmp/jev-judge/PLAN.md:100) awards artifact **AAA merely for commitment and SHA binding**. Require an actual verification check and receipt tied to the exact evaluated tree, dataset and configuration. Binding proves identity, not correctness.
   - Overall evidence takes only two components. Include classification and coverage evidence, with absent required evidence rated **FAIL**. Do not describe an unavailable compliance judgment as inference already performed.

4. **Scope, safeguards and exact remaining changes**

   Keep the library, CLI, offline tests, scoped output and execution separation. The smoke-test designation is correctly fixed.

   Before approval, revise the plan to require:

   - Escalation for unresolved class claims, invalid classes and duplicate selections; class inference can remain deferred.
   - Explicit threshold/abstention boundaries and invalid, provisional, failed-validation and stale calibration states; bind complete scoring configuration and immutable model identity where available.
   - The calibration and evidence corrections above.
   - Enforced token, monetary and elapsed-time limits, including retries. Printing an estimate is not a spend gate; rule/case counts do not bound request size sufficiently.
   - Removal or explicit gating of the **mandatory live finish line**. It conflicts with the plan’s own unapproved-metered-lane restriction; shadow requests still incur transport costs.
   - Redaction/minimisation for outbound actions, recorded results and errors, including `--record`; avoiding default disk writes alone does not resolve round-1 privacy concerns.
   - Tests with explicit expected outcomes for these gaps, including held-out validation failure, zero violation cases, corrupt artifacts, uncertainty boundaries, and semantic positive-output assertions rather than only searching for `allow`.

5. **Rescore**

   | Category | Score |
   |---|---:|
   | Evidence | 15/25 |
   | Problem | 19/20 |
   | Reuse | 12/15 |
   | Security | 11/15 |
   | UX | 9/10 |
   | Testability | 8/10 |
   | Cost | 2/5 |
   | **Total** | **76/100** |

Reviewed `BRIEF.md`, `PLAN.md`, `judge-r1.md`, and `first-result.json`. No files changed or executable tests run. This is a document review; repository assertions remain unverified. Next step: revise the explicit policy and finish-line requirements above, then resubmit.