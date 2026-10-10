# Judge Approval Policy

Judge is a pre-build gate. On 2026-10-10 Phill ratified: "Lets bring down the Approval to
95, but still chasing 100%." This supersedes the prior 100-only and 85-point build floors.
The build floor is 95/100; the target remains an earned 100/100.

## Decisions

- **REJECT**: Do not build.
- **REDUCE SCOPE**: Proposal is too large, vague, risky, or unsupported.
- **APPROVE EXPERIMENT**: Propose only a small reversible proof with its own bounded scope
  and explicit authority. This is not ordinary build approval and cannot bypass a hard block.
- **APPROVE BUILD**: The named build scope may proceed after separate user confirmation
  following the report and any required project admission. This does not approve activation,
  push, deployment, or release.

## Score thresholds

- 0–69: reject
- 70–94: reduce scope or experiment; NOT BUILD APPROVED
- 95–99: APPROVE BUILD only when every hard block and mandatory build criterion is cleared;
  record each remaining non-blocking gap, owner, closure action, and evidence required before
  its dependent stage. Keep pursuing 100.
- 100: APPROVE BUILD only when genuinely earned for the judged stage, with no unresolved
  scored quality or evidence gap and no hard block. Never inflate or round up a score.
- 0–94 never authorises an ordinary build. A score is evidence about a named scope, not authority.

## Hard blocks

Judge must block approval regardless of score if, for the proposed scope:

- First-source evidence is missing
- The problem is unclear
- Existing capability has not been checked
- Security/privacy risk is unreviewed or a material finding remains unresolved
- Billing/spend or included-capacity authority is unproven for a live action
- Workspace trust or hook/tool permission is unproven for a workspace-sensitive action
- Required user/project authority or admission is missing
- A mandatory `must_fix`, isolation, or irreversibility finding remains unresolved
- There is no test plan
- The build is too broad to reverse safely

## Evidence and stage boundaries

A concrete verification plan can earn pre-build testability credit. Future tests must be
labelled `PLANNED`, never passed; they do not earn execution-evidence credit. Report executed
checks with the candidate identity and observed result. Completion and release still require
their applicable checks to execute and pass on the actual candidate. Keep live activation
held until fresh model, billing, workspace, and other applicable receipts exist; a local
source review or build score cannot substitute for them.
