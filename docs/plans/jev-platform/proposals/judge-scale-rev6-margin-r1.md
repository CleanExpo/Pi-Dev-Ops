**95/100 — DO NOT APPROVE BUILD for the supplied file.** The brief requests rev 5, but [PLAN.md:3–8](/tmp/jev-judge-scale/PLAN.md:3) identifies the current plan as **rev 6**. Rev 5 resolves round 4; rev 6 reopens the hard-cost-cap blocker.

| Required change / earlier item | Verdict | Current PLAN.md evidence |
|---|---|---|
| Establish counting-call billing and bound attempts | **RESOLVED** | [206–217](/tmp/jev-judge-scale/PLAN.md:206): supplied zero-charge quotation, reservation rule and count-call cap |
| Make proposal handling consistent | **RESOLVED** | [90–97](/tmp/jev-judge-scale/PLAN.md:90), [292–295](/tmp/jev-judge-scale/PLAN.md:292): Jev prohibition and explicit Gemini echo exception |
| Match state keys to the tool shape; require template fields to be a subset | **RESOLVED** | [315–318](/tmp/jev-judge-scale/PLAN.md:315) |
| Cover content-only-with-prompt, mixed batches and incompatible selections | **RESOLVED** | [319–323](/tmp/jev-judge-scale/PLAN.md:319) |
| Hard-cap Gemini spending, including writer calls | **NOT RESOLVED — reopened** | [222–230](/tmp/jev-judge-scale/PLAN.md:222), [496–498](/tmp/jev-judge-scale/PLAN.md:496): empirical margin explicitly permits one-call excess |

Other previously closed requirements remain specified: positive admission, restricted Git environment, distinct failure outcomes, aggregate sizing, writer controls and failure mutations.

**New P0/P1 defects:** none identified in the rev-5 compatibility correction. **Rev 6 introduces a P1 cost-control regression:** `ceil(totalTokens × 1.25) + 256` is an observed safety margin, not a demonstrated upper bound. The plan itself acknowledges that counting underestimates input and that excess spending can occur. Stopping after receiving usage cannot prevent an already billed request from crossing the cap. This affects both the runner and the writer using `GeminiBudget`.

**Exactly what must change:**

1. Replace the empirical margin as the authorization-to-send bound with a provider-supported maximum covering all billable input, plus the documented output/thinking maximum. Reserve that amount before every attempt. If no such bound is established, keep metered Gemini runner/writer execution **BLOCKED**.
2. Require offline tests and bypass mutants proving that an unsupported bound or insufficient remaining budget produces **zero generation requests**, including retries. Retain uncertain-failure reservations and overrun reporting; neither substitutes for prevention.

Increasing the margin or collecting more observations does not establish a hard cap. No additional features are needed. Keep concurrency, command execution and bulk generation deferred.

| Category | Score |
|---|---:|
| Evidence | 24/25 |
| Problem | 20/20 |
| Reuse | 15/15 |
| Security | 15/15 |
| UX | 10/10 |
| Testability | 9/10 |
| Cost | 2/5 |
| **Total** | **95/100** |

Reviewed all 14 brief-required files: `BRIEF.md`, `PLAN.md`, verdicts r1–r4, both parent approvals, `PLAN-ask.md`, both Python files and three TypeScript references. **Files changed: none.** Static review only; no tests or network calls. Provider quotations were accepted as supplied evidence. Next step: correct the cost-bound contract before build approval.