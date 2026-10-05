**90/100 — DO NOT APPROVE BUILD.** Rev 3 governs. The principal round-1 disclosure condition remains unresolved.

### 1. Round-1 conditions

| Condition | Verdict |
|---|---|
| Positive admission boundary covering all outbound content | **Unresolved.** Committed globs authorize filenames, not reviewed contents. Questions and criteria remain regex-screened free text. |
| Refuse sensitive input before sending; remove `altered` scoring | **Resolved in specification.** Checks cover bytes, paths, questions and criteria before requests. |
| Bind validation and transmission to the same bytes | **Resolved for reading/transmission.** Descriptor-relative traversal, regular-file checking and reuse of the same buffer address the race. This does not establish that those bytes were approved. |
| Atomic capped accounting or remove concurrency | **Resolved.** Serial processing and a fixed attempt cap, together with inherited reservation retention, satisfy this condition. |
| Explicit batched failure semantics | **Resolved.** Missing, duplicate, malformed and unavailable responses produce no Nouls. |
| Deterministic question/criteria pairing | **Partial.** Question IDs are ordered; matching repeated `--true`/`--false` arguments and rejecting mismatched counts remain unspecified. |
| Concrete deadline | **Resolved.** 120-second default and bounded request timeout. |
| Corresponding acceptance and mutation tests | **Partial.** Added tests leave admission gaps and contain potentially vacuous refusal checks. |

### 2. Remaining P1 disclosure defects

**A committed allow-glob is not approval of exact content.** Under [Rev 3’s manifest rules](/tmp/jev-judge-ask/PLAN.md:127), an agent can add or modify a matching Python, Markdown or JSONL file containing an unrecognised credential or unlabelled standards excerpt. The committed manifest still admits it. Computing its SHA-256 merely records what leaked; no approved digest is compared.

**Questions and criteria lack positive admission.** Their [regex checks and length limits](/tmp/jev-judge-ask/PLAN.md:137) still admit unrecognised secrets and prohibited excerpts without identifying markers. The manifest does not govern these fields.

**The deny-list remains inadequate by itself**, even for advisory use. Keep it as defence in depth after approval of the complete outbound content.

No new answer-based authorization, cap-bypass or unavailable-as-answer defect is apparent in the governing specification. The parent approval remains restricted to its original slice.

### 3. Exactly what must change

1. **Bind outbound approval to reviewed content.** For the smallest first version, use a curated export with approved file paths and content hashes; reject added or changed bytes. Use reviewed question/criteria templates, or require equivalent approval of their exact text. A file’s presence in Git or a matching glob alone must not constitute review. Send only approved relative paths.

2. **Specify argument pairing.** Pair the nth question with the nth true and false criteria; reject unequal counts before any request.

3. **Make the tests prove the boundary.**
   - The `notes.md` refusal tests must use an otherwise admitted fixture: the shipped manifest currently excludes that path, so zero requests could prove only filename rejection.
   - Add zero-request tests for a new glob-matching file, changed approved content, and unapproved question/criteria text without recognisable secret or publisher markers.
   - Strengthen the replacement test: matching the hash of whatever was read is insufficient; bytes differing from the approved snapshot must be refused.
   - Mutation checks must demonstrate that bypassing each approval comparison makes its test fail.

Keep serial execution, the existing client and advisory-only output. No additional integration is required.

### 4. Rescore

| Evidence | Problem | Reuse | Security | UX | Testability | Cost | Total |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 24/25 | 20/20 | 15/15 | 9/15 | 9/10 | 8/10 | 5/5 | **90/100** |

Reviewed `BRIEF.md`, `PLAN.md`, `judge-ask-r1.md` and `parent-approval.md`. No files changed, tests executed or provider calls made. Client behaviour is assumed from the supplied specification, not independently verified. Next step: revise the three requirements above and resubmit for approval.