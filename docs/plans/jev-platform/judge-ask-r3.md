**100/100 — APPROVE BUILD.** Rev 4 resolves the round-2 conditions at the specification level. This approves implementation, not deployment or verified runtime behaviour.

| Round-2 condition | Verdict |
|---|---|
| Approval bound to exact file content | **Resolved.** Listed relative path plus approved SHA-256; transmission uses the same checked buffer. |
| Positive admission for questions and criteria | **Resolved.** Reviewed templates replace free text; unknown template IDs are refused. |
| Deterministic question/criteria pairing | **Resolved.** Each template contains its question and both criteria; duplicate selections are refused. |
| Non-vacuous refusal fixtures | **Resolved.** Fixtures must otherwise qualify for admission; the approved PEM fixture specifically exercises content screening. |
| Reject new files and changed approved content | **Resolved.** Explicit zero-request tests cover both. |
| Replacement test checks approved bytes | **Resolved.** Replacement with different bytes must fail the approved-digest comparison. |
| Mutation tests prove admission enforcement | **Resolved.** Bypassing digest, path, template or committed-manifest checks must break a test. |

**No new P0/P1 defect identified.** The inherited requirements retain confined descriptor-based reads, serial execution, fixed attempt caps, reservation retention after uncertain failures, bounded deadlines and unavailable output without probabilities. Answers remain advisory and cannot authorize an action.

**The deny-list alone remains inadequate.** Rev 4 supplies the required minimal addition: positive approval of exact outbound content. The manifest’s human review point is the trust boundary; the helper’s generated hash establishes identity, not safety. Review must cover the actual file contents and complete templates.

Nothing further needs adding for this first version. Keep the existing client and serial processing. Superseded glob-manifest, free-text question and `altered`-scoring behaviour must not survive implementation.

| Evidence | Problem | Reuse | Security | UX | Testability | Cost | Total |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 25/25 | 20/20 | 15/15 | 15/15 | 10/10 | 10/10 | 5/5 | **100/100** |

Reviewed `BRIEF.md`, `PLAN.md`, `parent-approval.md`, `judge-ask-r1.md` and `judge-ask-r2.md`. No files changed, implementation tests executed or provider calls made. Inherited client behaviour remains unverified. Next step: implement Rev 4 and satisfy the specified offline and mutation gates.