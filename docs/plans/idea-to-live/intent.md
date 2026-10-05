# Intent: one pathway from idea to verified-live, with plan-to-done as its planning layer

**Intent revision:** r1, 28 September 2026 (Australia/Brisbane). **Status:** DRAFT — not accepted.
Acceptance would be recorded as a receipt here; none exists yet (see Open questions D0).
**Contract:** Capture Intent (Problem · Proposed outcome · Affected users and systems ·
Constraints · Open questions), as `plan-to-done` step 4 requires.

## Problem

An idea Phill approves does not reliably become a feature that works on the live site. The
repository carries it part of the way and then stops at seven points, documented with evidence in
[pathway.md](pathway.md): a GO never starts a build, nothing promotes the ticket, the poller may be
off in production, deploy leaves no receipt, "complete" means "merged" rather than "working live",
there is no whole-project definition of done, and the ship-chain docs end at "ship".

Separately, there is no single written rule for *which model or paid plan does which job*. The
code encodes one answer (`swarm/fleet_value_optimizer.py`, `app/server/provider_policy.py`,
`app/server/model_policy.py`); the 28 Sept 2026 routing reference encodes another. They disagree
in seven places, out of ten compared ([routing-reconciliation.md](routing-reconciliation.md)).

## Proposed outcome

1. **A planning layer under the command surface.** `/plan-to-done` sits beside `/judge`, `/spm`,
   `/session-handoff` and `/resume-from-handoff` in the CLAUDE.md command table. `/judge` decides
   whether to build, `/spm` specifies a change, and `/plan-to-done` writes the whole-project packet
   that says what "finished and live" means and what is missing. The v1.1 candidate is held,
   unmodified and hash-verified, at [`../plan-to-done-v1.1/`](../plan-to-done-v1.1/README.md).
2. **One routing reference** for models and plans, ordered by the standing money rule:
   [model-and-plan-routing.md](../plan-to-done-v1.1/plan-to-done/references/model-and-plan-routing.md)
   (the 28 Sept 2026 text, unchanged). Where it disagrees with running code it is a **proposal**,
   and the reconciliation file says so row by row.
3. **An end-to-end chain** in which every stage from idea to live proof leaves a receipt, and
   "done" means a named check passed against the live URL for the specific feature — not a merge.

Observable signs the outcome is reached (none are true today):

- `/plan-to-done` is invocable in Claude Code from a promoted home, and its eval suite has a
  recorded run with pass rate and cost.
- For one real idea: packet → GO → eligible ticket → build → review receipt → merge → deploy
  receipt naming the live commit → feature-specific live check → PASS, each step linked.
- Code and routing reference agree, or each disagreement has a recorded decision.

## Affected users and systems

- **Phill** — approves ideas, holds the money line and any production switch.
- **Idea pipeline** — `app/server/idea_pipeline/`, `scripts/process_ideas_inbox.py`.
- **Autonomy and build** — `app/server/autonomy.py`, `session_phases.py`, `spec_pipeline/`.
- **Review and receipts** — `app/server/board_review.py`, adversary phase, `CleanExpo/skills-library`'s `pr-release-gate`.
- **Model routing** — `app/server/model_policy.py`, `model_registry.py`, `config.py`, `provider_policy.py`, `swarm/fleet_value_optimizer.py`, `swarm/budget_tracker.py`.
- **Mission Control** — `/control` hub (`dashboard/lib/control/nav.ts`), `docs/model-fabric-mission-control.md`.
- **Library** — `CleanExpo/skills-library`, the package's proposed canonical home.

## Constraints

- **Money (standing rule, 10 Sept 2026):** no new spending; metered lanes under a $5/day ceiling;
  existing subscriptions used first. Routing and lane order:
  [model-and-plan-routing.md](../plan-to-done-v1.1/plan-to-done/references/model-and-plan-routing.md).
  Note the code today blocks every metered lane (`provider_policy.py:36-43` dispatch, refusal at `:77-78`; asserted by
  `tests/test_subscription_policy.py`) and its daily default is $20, visibility only
  (`swarm/budget_tracker.py:6,45`).
- **No irreparable change, no change to the foundation** (the other two standing guardrails).
- **Planning is not building.** `plan-to-done` writes documents only; its hard rules forbid code,
  tickets, commits and deploys during a planning run.
- **Candidate stays quarantined** until its eval suite has run and it is promoted through
  `skills-library` — the package's own adoption rule (`README.md`, "Library fit").
- **Model policy in code wins until changed in code.** `OPUS_ALLOWED_ROLES`, the Fable canary and
  the subscription-only transport check are enforced; a markdown file does not override them.

## Open questions

| ID | Question | Kind | Owner | How it resolves |
|---|---|---|---|---|
| D0 | Is Pi-Dev-Ops under "acceptance by cross-model audit" (10 Sept decision) or "human-merge-only, no UG-AUTONOMY-001 exception" (`docs/session-handoffs/20260911-1230-0eca2639.md:212`)? | Owner decision (direction) | Phill | **Decided 28 Sept 2026 (RA-7818): human merge only.** Cross-model audit is review evidence, not acceptance |
| D1 | Keep Claude-Code-only frontmatter (no claude.ai sync) or go spec-only + `skillOverrides`? | Owner decision | skills-library maintainer | Package `ENHANCEMENT-REVIEW.md` §6 |
| D2 | TypeSafe intake: vendor plugin marketplace or pinned vault? | Owner decision | skills-library maintainer | Same |
| D3 | Does the `plan-review` workflow count toward the two-round review cap? | Owner decision | skills-library maintainer | Same |
| E1 | Is `TAO_AUTONOMY_ENABLED` still `0` in production? | Evidence gap | ops | Read the current Railway startup log |
| E2 | Do the package's 30 evals pass? | Evidence gap | skills-library | `claude plugin eval` run with recorded pass rate and cost |
| E3 | Do the routing reference's vendor figures still match their pages? | Evidence gap | this session | Re-verification table in [routing-reconciliation.md](routing-reconciliation.md) |
