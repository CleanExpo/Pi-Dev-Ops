# Pi-CEO Triage Rules — Autonomous Execution Policy
Date: 2026-05-08
Author: CEO Board deliberation (2026-05-08)

---

## RULE 1: SAFE TO AUTO-QUEUE AS LINEAR TICKET
Agent may create Linear ticket without human approval when Pi-CEO detects:
- `dependency_health` score drops more than 10 points from previous scan
- `deployment_health` drops to 0 (failed deployment)
- Outdated package version detected (non-breaking patch/minor updates only)

**Assign to:** Unite-Group team, priority = High, label = `agent-ready`

---

## RULE 2: HUMAN REVIEW REQUIRED
Agent must flag for Phill's review (create ticket but assign to Phill, NOT agent-ready):
- Any `security` finding on CCW-CRM (client system — zero tolerance)
- Any `security` finding with severity = critical
- Anything touching payment, auth, or production data models
- Score drops > 30 points in one scan (indicates major incident)
- New repository detected that isn't in the PROJECT_MAP

---

## RULE 3: NEVER AUTO-ACTION
No agent may take automated action on:
- Auth architecture changes
- Database schema changes
- Payment system modifications
- Production environment variables
- Any `carsi` or `ccw-crm` repository code changes (client data)
- Any action that would trigger an App Store review cycle (RestoreAssist)

---

## FINDING CLASSIFICATION TABLE
| Pi-CEO Score Dimension | Auto-queue threshold | Notes |
|---|---|---|
| security | NEVER auto-queue | Always human review |
| code_quality | score drop > 20 pts | Only lint/format fixes |
| dependencies | any finding | Dependabot-style auto-PR to feature branch only |
| deployment_health | score = 0 | Re-deploy from last green build |

---

## BRANCH AUTHORITY
Agents may push to: `feature/*` and `fix/*` branches ONLY
Agents may NOT push to: `main`, `production`, `release/*`
All agent PRs require human approval before merge.

---

## FIRST TARGET REPOSITORY
Until 3 successful autonomous cycles are validated:
Repository: CleanExpo/Unite-Group (unite-group CRM)
Reason: Internal tool, no external users, full CI, Phill has direct visibility
