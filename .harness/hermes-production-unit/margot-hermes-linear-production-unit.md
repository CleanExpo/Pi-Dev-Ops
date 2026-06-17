# Margot-Led Hermes Linear Production Unit

Unit: `margot-hermes-linear-production-unit`
Generated: `2026-06-17T21:05:27.344239+00:00`

## Objective
Keep Pi-Dev-Ops Linear work moving continuously through a two-child Hermes production unit while preserving evidence gates and human approval.

## Shared Context
- Margot is production lead; child agents do not invent strategy or change priorities.
- Linear is the shared queue; Hermes Kanban mirrors visibility but is not the authority.
- Every issue must move by evidence: branch, PR, test output, smoke result, or explicit blocker.
- Human approval remains required for production deploys, billing, secrets, destructive data actions, and merges to main.

## Claim Contract
- Claim exactly one issue before work starts by moving it to In Progress or adding a visible claim comment.
- Skip issues already claimed by another agent or human.
- Work in an isolated branch/worktree; never push directly to main.
- If the same blocker repeats three times, stop that issue, comment the blocker, and pick the next safe issue.

## Merge Contract
- Open a PR with verification evidence attached.
- Do not mark Linear Done until the PR is merged and main CI/smoke is green.
- If verification fails, update Linear with the concrete failing command and leave the issue In Progress or Blocked.

## hermes-child-delivery-1
Lane: `delivery`

Build or repair the next narrow, agent-ready Linear item and open a PR with evidence.

### Assigned Linear Issues
- `RA-5042` P2 Pi-Dev-Ops: Implement Margot-led autonomous Linear production unit for two child Hermes Agents [https://linear.app/unite-group/issue/RA-5042]
- `RA-2142` P3 Pi-Dev-Ops: Implement hourly status reporting and verification loop [https://linear.app/unite-group/issue/RA-2142]

### Allowed Actions
- read repository files
- create feature branch/worktree
- edit safe-scope source/tests/docs
- run focused tests and project gates
- push branch and open PR
- comment progress/evidence in Linear

### Evidence Required
- changed files summary
- commands run with pass/fail result
- PR URL
- main SHA after merge when complete

### Stop Conditions
- protected file required
- secret/account/billing action required
- destructive migration or production data action required
- same failure repeats three times

### Escalation Path
Margot -> Senior PM -> Phill

## hermes-child-verification-1
Lane: `verification`

Truth-check active Linear work, close stale tickets with evidence, and create exact follow-up blockers.

### Assigned Linear Issues
- `RA-2989` P1 Pi-Dev-Ops: SECURITY+BILLING: leaked secrets and account rotation required [https://linear.app/unite-group/issue/RA-2989]
- `RA-2996` P2 Pi-Dev-Ops: EPIC: Pi-CEO agentic-OS audit and remediation follow-through [https://linear.app/unite-group/issue/RA-2996]

### Allowed Actions
- inspect code and CI state
- run read-only audits and focused tests
- update Linear descriptions/comments/status with evidence
- open blocker tickets for concrete gaps
- prepare PRs only for test/docs/safe-scope fixes

### Evidence Required
- file paths or live run URLs checked
- pass/fail/unknown classification
- status transition rationale
- next concrete gap per unresolved issue

### Stop Conditions
- issue requires human credential rotation
- evidence is inconclusive after two independent checks
- state change would hide a real unresolved production risk

### Escalation Path
Margot -> Board -> Phill

## Machine JSON
```json
{
  "children": [
    {
      "agent_id": "hermes-child-delivery-1",
      "allowed_actions": [
        "read repository files",
        "create feature branch/worktree",
        "edit safe-scope source/tests/docs",
        "run focused tests and project gates",
        "push branch and open PR",
        "comment progress/evidence in Linear"
      ],
      "assigned_issues": [
        {
          "description": "Create child-agent packets with claim rules, evidence gates, and escalation paths.",
          "identifier": "RA-5042",
          "priority": 2,
          "project": "Pi-Dev-Ops",
          "state": "In Progress",
          "title": "Implement Margot-led autonomous Linear production unit for two child Hermes Agents",
          "url": "https://linear.app/unite-group/issue/RA-5042"
        },
        {
          "description": "Create a recurring verified progress report loop suitable for NotebookLM/video consumption.",
          "identifier": "RA-2142",
          "priority": 3,
          "project": "Pi-Dev-Ops",
          "state": "Todo",
          "title": "Implement hourly status reporting and verification loop",
          "url": "https://linear.app/unite-group/issue/RA-2142"
        }
      ],
      "escalation_path": [
        "Margot",
        "Senior PM",
        "Phill"
      ],
      "evidence_required": [
        "changed files summary",
        "commands run with pass/fail result",
        "PR URL",
        "main SHA after merge when complete"
      ],
      "lane": "delivery",
      "mission": "Build or repair the next narrow, agent-ready Linear item and open a PR with evidence.",
      "stop_conditions": [
        "protected file required",
        "secret/account/billing action required",
        "destructive migration or production data action required",
        "same failure repeats three times"
      ]
    },
    {
      "agent_id": "hermes-child-verification-1",
      "allowed_actions": [
        "inspect code and CI state",
        "run read-only audits and focused tests",
        "update Linear descriptions/comments/status with evidence",
        "open blocker tickets for concrete gaps",
        "prepare PRs only for test/docs/safe-scope fixes"
      ],
      "assigned_issues": [
        {
          "description": "Human-owned credential rotation and billing/account recovery task; do not automate secrets.",
          "identifier": "RA-2989",
          "priority": 1,
          "project": "Pi-Dev-Ops",
          "state": "Todo",
          "title": "SECURITY+BILLING: leaked secrets and account rotation required",
          "url": "https://linear.app/unite-group/issue/RA-2989"
        },
        {
          "description": "Audit shipped work, verify remaining systemic issues, and split concrete blockers into follow-up tickets.",
          "identifier": "RA-2996",
          "priority": 2,
          "project": "Pi-Dev-Ops",
          "state": "Todo",
          "title": "EPIC: Pi-CEO agentic-OS audit and remediation follow-through",
          "url": "https://linear.app/unite-group/issue/RA-2996"
        }
      ],
      "escalation_path": [
        "Margot",
        "Board",
        "Phill"
      ],
      "evidence_required": [
        "file paths or live run URLs checked",
        "pass/fail/unknown classification",
        "status transition rationale",
        "next concrete gap per unresolved issue"
      ],
      "lane": "verification",
      "mission": "Truth-check active Linear work, close stale tickets with evidence, and create exact follow-up blockers.",
      "stop_conditions": [
        "issue requires human credential rotation",
        "evidence is inconclusive after two independent checks",
        "state change would hide a real unresolved production risk"
      ]
    }
  ],
  "claim_contract": [
    "Claim exactly one issue before work starts by moving it to In Progress or adding a visible claim comment.",
    "Skip issues already claimed by another agent or human.",
    "Work in an isolated branch/worktree; never push directly to main.",
    "If the same blocker repeats three times, stop that issue, comment the blocker, and pick the next safe issue."
  ],
  "generated_at": "2026-06-17T21:05:27.344239+00:00",
  "lead": "Margot",
  "merge_contract": [
    "Open a PR with verification evidence attached.",
    "Do not mark Linear Done until the PR is merged and main CI/smoke is green.",
    "If verification fails, update Linear with the concrete failing command and leave the issue In Progress or Blocked."
  ],
  "objective": "Keep Pi-Dev-Ops Linear work moving continuously through a two-child Hermes production unit while preserving evidence gates and human approval.",
  "shared_context": [
    "Margot is production lead; child agents do not invent strategy or change priorities.",
    "Linear is the shared queue; Hermes Kanban mirrors visibility but is not the authority.",
    "Every issue must move by evidence: branch, PR, test output, smoke result, or explicit blocker.",
    "Human approval remains required for production deploys, billing, secrets, destructive data actions, and merges to main."
  ],
  "unit_id": "margot-hermes-linear-production-unit"
}
```
