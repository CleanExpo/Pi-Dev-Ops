**83/100 — DO NOT APPROVE BUILD yet.** Rev 2 governs. The parent approval covers the restricted shadow-mode slice; arbitrary estate files introduce a new disclosure boundary.

1. **P0/P1 defects**

   - **P1 — Secrets and prohibited material can escape.** A harmlessly named `notes.md` can contain copied standards text or an unrecognised credential. Neither filename exclusions nor the expanded regexes establish safe content. Questions and true/false criteria are additional outbound text without an explicit admission check. Reporting `altered` after requesting a Noul does not resolve disclosure risk. See [input policy](/tmp/jev-judge-ask/PLAN.md:38) and [Rev 2 payload](/tmp/jev-judge-ask/PLAN.md:94).
   - **P1 — Path validation is not bound to the bytes sent.** `realpath` followed by a later open permits a file or ancestor directory to change between checking and reading. Require a confined, race-resistant read and send the exact admitted snapshot. See [path checks](/tmp/jev-judge-ask/PLAN.md:100).
   - **P1 specification gap — Concurrent budget enforcement.** The parent requires reservations before attempts and retention after uncertain failures. Rev 2 adds four concurrent workers without explicitly requiring atomic reservation against their shared cap. Separate check/debit operations can overspend. Require atomic reservation for initial attempts and retries. See [concurrency](/tmp/jev-judge-ask/PLAN.md:115).
   - **P1 specification gap — Batched failures.** Reused response validation must enforce exact question/result correspondence for the new multi-question call. Missing, duplicate, malformed or exhausted-retry results must produce `BLOCKED/unavailable`, with no substitute probability. “Each file shows only its Nouls” needs an explicit failure exception.

   **No direct answer-based authorization defect found.** The advisory restriction, absence of action fields and answer-independent exit behaviour are appropriate.

2. **Is the deny-list adequate?**

   **No.** Advisory status limits decision authority; it does not limit disclosure.

   The minimum change is a **positive outbound-content boundary**: accept only explicitly reviewed, non-sensitive, permitted inputs, bound to their exact bytes. Apply that boundary to content, transmitted paths, questions and criteria. Refuse unclassified inputs and anything triggering redaction **before any request**. Keep the deny-list as an additional check. Do not substitute another collection of regexes for provenance.

   For a small first version, restrict inputs to a curated export or synthetic fixture set.

3. **Cuts and required validation**

   - Cut arbitrary working-directory/glob access initially unless the admission boundary above exists.
   - Either cut concurrency initially or prove atomic shared reservations. Preserve the parent’s uncertain-cost accounting.
   - Specify deterministic question/criteria pairing, a concrete deadline, and explicit unavailable output.
   - Add offline and mutation tests for innocuously named prohibited content, sensitive question/criteria text, path replacement, concurrent near-cap attempts, retry exhaustion and incomplete multi-question responses. Disclosure refusals must assert **zero requests**.

   No second client, enforcement hooks or broader integration programme is needed.

4. **Score**

   | Evidence | Problem | Reuse | Security | UX | Testability | Cost | Total |
   |---:|---:|---:|---:|---:|---:|---:|---:|
   | 22/25 | 20/20 | 15/15 | 5/15 | 9/10 | 8/10 | 4/5 | **83/100** |

   **Exactly what must change:** establish the complete outbound-content boundary; bind validation to the bytes read; specify atomic capped accounting or remove concurrency; define batched failure semantics; add the corresponding acceptance and mutation tests.

Reviewed `BRIEF.md`, `PLAN.md` and `parent-approval.md`. No files changed, implementation tests or provider calls run. This is a specification review; inherited client behaviour remains unverified.