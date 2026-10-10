# Judge Approval Policy

On 2026-10-10 Phill retained 95 for promotion and an earned 100 target, then allowed
bounded reversible development below 95. The local development minimum is 85/100.
This supersedes a single 95 build floor without weakening any hard guard.

## Decisions and stages

- **REJECT**: Do not proceed with the proposed scope.
- **REDUCE SCOPE**: Clarify or narrow an unsupported, risky, or sub-85 development scope.
- **APPROVE EXPERIMENT**: At 85+, the named bounded reversible local development scope may
  proceed under separate explicit user/project authority. It does not approve promotion,
  automated SDK implementation, push, merge, deployment, spending, or live activation.
- **APPROVE BUILD**: Promotion/ordinary build eligibility requires 95+ and every mandatory
  criterion cleared. Existing callers default to this stage. Applicable user/project,
  candidate validation, review, admission, activation, and release gates remain required.

## Score thresholds

- 0–69: reject.
- 70–84: reduce scope; not development approved.
- 85–94: eligible only for bounded reversible local development/experiments; never promotion.
- 95–99: eligible for the explicitly requested stage when all hard guards pass.
- 100: quality target, earned only with supported evidence and no unresolved scored gap.

At 85–99 record complete nonblocking deductions: name, accountable owner, closure action,
required evidence, and category. Permitted categories are clear_problem, reuse_existing,
ux_clarity, and testability. A numeric score never reclassifies a mandatory gap as optional.
Keep the actual stage, floor, score and deduction records in reports and handoffs. Never
round up, fabricate 100, or present planned tests as passed execution evidence.

## Hard blocks

Judge must block either stage at every score if, for the proposed scope:

- First-source evidence is missing, empty, unsupported, conflicting, or not checked.
- The problem is unclear or existing capability has not been checked.
- Security/privacy risk is unreviewed or a material finding remains unresolved.
- Billing/spend or included-capacity authority is unproven for a live action.
- Workspace trust or hook/tool permission is unproven for a workspace-sensitive action.
- Required user/project authority or admission is missing.
- A mandatory must_fix, isolation, rollback, or irreversibility finding remains unresolved.
- There is no concrete test plan or the scope is too broad to reverse safely.
- The report, evidence, or deduction records are malformed or an explicit honest ceiling applies.

## Convergence and execution boundaries

Development convergence stops at its first qualifying 85+ preparation packet; promotion
continues pursuing 100 and can retain a qualified 95–99 at its bound. An explicit substantive
honest ceiling still blocks both stages; reaching an iteration bound alone must not invent one
for an otherwise qualified packet. The machine development stage returns development_ready:
SPM/board preparation only, no SDK implementation executed and no promotion performed. It
returns before workspace creation, builder/oracle execution, Git, push, merge, or shipping,
even with score 100 and shipping enabled. Public adapters retain default promotion; explicit
stage selection is currently available through the core callable only.

The initial Judge, SPM and board planning calls still require applicable included-route,
billing, provider-access and workspace authority. A score below 95 does not clear provider
fallback access or authorise paid inference. Preparation-only scope preserves those gates.

A concrete verification plan earns pre-build testability; future checks are PLANNED, never
passed. Separately authorised local agent/human work can develop the bounded scope and close
deductions. Before promotion, run the applicable tests and independent review on the exact
candidate and obtain fresh 95+ approval. Preserve all existing stronger release gates and
fresh model, billing, workspace, authority, and activation receipts. A local review or
preparation packet cannot substitute for them.
