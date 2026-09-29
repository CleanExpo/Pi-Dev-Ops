**DO NOT APPROVE BUILD — 96/100, up from 90.** Rev 4 resolves most round-3 conditions. Two corrections remain: the claimed hard spend bound is insufficiently justified, and the uncertainty formula is mislabeled.

1. **Decision policy and round-3 conditions**

   No recommendation-level path to `allow` or `no_objection` remains. Outages, unscored rules and invalid calibration cannot produce per-rule passes under Rev 4. No new P0/P1 clearance bypass identified.

   | Round-3 condition | Verdict |
   |---|---|
   | Complete-response validity and provisional-state guard | Resolved |
   | Label-generation provenance and adjudication status | Resolved |
   | Quantified uncertainty with explicit limitations | Partially resolved: incorrect “exact” formula |
   | Exhaustive counters, including uncertain violations | Resolved |
   | Compliant-case reviewer burden | Resolved |
   | AA verification and AAA exact-tree binding | Resolved as plan requirements |
   | Conservative request-size and monetary bounds | Partially resolved: provider assumptions remain unsupported |
   | Remaining-deadline timeout and retry handling | Resolved as plan requirements |
   | Synthetic-only live inputs, shared preprocessing, altered-input uncertainty | Resolved |
   | Explicit boundary, provenance and prohibited-output tests | Resolved; add checks for the two corrections below |

2. **Calibration**

   Lowest-threshold selection with zero observed misses is acceptable **provisional candidate selection**, not demonstrated safety. The case split, correlated agreement labels, excluded disagreements and previously inspected dataset prevent an independent safety claim. These limitations are acceptable for this restricted shadow slice.

   **New correctness defect:** [PLAN.md:268](/tmp/jev-judge/PLAN.md:268) says exact one-sided Clopper–Pearson equals `3/V` when there are zero misses. The exact bound is:

   `1 − 0.05^(1/V)`

   At `V = 50`, that is **5.8155%**, versus the approximate rule-of-three value of **6%**. The approximation is conservative here, so this is not a clearance bypass, but an artifact cannot honestly claim an exact calculation while prescribing an approximation. The formula follows by inverting the binomial zero-event probability using the [exact-binomial method](https://itl.nist.gov/div898/software/dataplot/refman2/auxillar/exacbino.htm).

   **Required change:** specify the exact calculation, handle `V = 0` as unavailable/failed validation, and test zero, intermediate and all-missed cases. Retain the existing limitations.

3. **Evidence ratings**

   The mapping is now honest **as specified**: AA requires verification; AAA additionally requires exact-tree binding; inferred compliance stays at most A; classification and overall recommendation remain FAIL.

   `first-result.json` still supplies only aggregate exploratory results. It does not establish these verification claims, and its overlapping counters remain correctly excluded.

4. **Remaining resource defect and scope**

   **P1 — the monetary cap remains conditional.** [PLAN.md:293](/tmp/jev-judge/PLAN.md:293) assumes byte-level tokenisation, then asserts that doubling serialized bytes covers overhead. Neither establishes that **all provider-billed input tokens** fit that reservation.

   Current [TypeSafe documentation](https://docs.typesafe.ai/models) confirms input-only billing and free output, so unbounded output charges are **not** the issue. The missing link is between serialized bytes and billable input, including provider formatting.

   **Required change:** substantiate that upper bound for the selected provider/model, or reserve a documented worst-case billable amount per attempt. If the bound cannot be established, refuse live requests. Test that retries and timed-out attempts retain their budget charge/reservation and cannot exceed the cap.

   Keep the current library, CLI, offline tests and synthetic transport smoke test. No additional integration, class inference or human-label programme is necessary for this slice.

5. **Rescore**

   | Category | Score |
   |---|---:|
   | Evidence | 24/25 |
   | Problem | 20/20 |
   | Reuse | 15/15 |
   | Security | 15/15 |
   | UX | 10/10 |
   | Testability | 9/10 |
   | Cost | 3/5 |
   | **Total** | **96/100** |

Reviewed `BRIEF.md`, `PLAN.md`, all three prior verdicts and `first-result.json`; checked official statistical and provider documentation and calculated the zero-miss example. No files changed, implementation tests or Jev calls run. Rev 4 was treated as governing; repository isolation and authorization assertions remain unverified. Next step: correct the uncertainty calculation and establish the billable-usage bound, with the specified tests.