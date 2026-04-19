# Task Brief

[HIGH] [RA-1298] Linear workspace setup — 4 statuses + 4 labels + Pi-Dev Run ID custom field

Description:
## Contract reference

Skill: `skills/pi-dev-linear-contract/SKILL.md` (Part 1 of the contract, [RA-1296](https://linear.app/unite-group/issue/RA-1296/ci-failure-cleanexpopi-dev-ops-smoke-test-e2e-production-on-main)).

## Action (human, Linear UI — cannot be automated without workspace-admin API)

### Per every Pi-Dev-Ops-enabled project (starts with 1 for rollout week 1):

**Workflow statuses** (Settings → Workflows):

| Status | Type | Position |
| -- | -- | -- |
| `Ready for Pi-Dev` | Unstarted | After Backlog, before Todo |
| `Pi-Dev: In Progress` | Started | After In Progress |
| `Pi-Dev: Blocked` | Started | After Pi-Dev: In Progress |
| `In Review` | Started | After Pi-Dev: Blocked |

### Workspace level (Settings → Labels → Workspace):

| Label | Colour |
| -- | -- |
| `pi-dev:source` | Purple |
| `pi-dev:autonomous` | Orange |
| `pi-dev:needs-review` | Yellow |
| `pi-dev:blocked-reason:credentials` | Red |
| `pi-dev:blocked-reason:ambiguous-spec` | Red |
| `pi-dev:blocked-reason:external-dep` | Red |
| `pi-dev:blocked-reason:scope-creep` | Red |

### Custom field (Settings → Custom fields):

* Name: `Pi-Dev Run ID`
* Type: Text (single line)
* Scope: All issues

## Rollout order

1. Apply to ONE project first — pick the highest-traffic one (RestoreAssist or Pi-Dev-Ops itself).
2. Run read-only Skill 4 (Health Report) against it for a week.
3. Add Skill 1 (write path) manually via `/Pi-Dev: File Analysis Output`. Verify idempotency.
4. Wire Pi-Dev auto-invocation. Only then expand to remaining 9 projects.

## Blocks

[RA-1297](https://linear.app/unite-group/issue/RA-1297/silent-sync-queue-failed-jobs-have-no-dead-letter-alerting-silently) code compliance can't ship until the statuses and labels exist — otherwise transitions reference non-existent states and fail with `State 'Pi-Dev: In Progress' not found in team {id} workflow`.

## Acceptance

* All 4 statuses live on ≥1 project.
* All 4 labels live at workspace level.
* Custom field visible in issue editor on ≥1 project.
* `Ready for Pi-Dev` visible as a board column.

Linear ticket: RA-1370 — https://linear.app/unite-group/issue/RA-1370/ra-1298-linear-workspace-setup-4-statuses-4-labels-pi-dev-run-id
Triggered automatically by Pi-CEO autonomous poller.


## Session: e1b2015ce6bd
