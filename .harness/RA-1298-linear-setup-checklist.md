# RA-1298 — Linear Workspace Setup Checklist

**Ticket:** [RA-1370](https://linear.app/unite-group/issue/RA-1370) (titled "[RA-1298] Linear workspace setup — 4 statuses + 4 labels + Pi-Dev Run ID custom field")  
**Status:** Human action required  
**Blocks:** RA-1369 (Pi-CEO code → Linear contract compliance)

## Why this cannot be automated

The Linear API does not expose workspace-admin endpoints for creating workflow statuses, workspace-level labels, or custom fields via a user-scoped API key. These actions require workspace admin access through the Linear UI only. A script cannot perform them — a human with admin rights must complete each step below.

Attempting to automate via `workflowStates` mutations fails with `403 Forbidden — requires workspace admin` when using a standard user token. There is no `LINEAR_WORKSPACE_ADMIN_TOKEN` in this environment.

---

## Checklist

### 1. Workflow statuses — Settings → Workflows → [Target Project]

Apply to **one project first** (RestoreAssist Compliance Platform). Expand to others after a one-week smoke period.

- [ ] Create status: **`Ready for Pi-Dev`** — Type: Unstarted — Position: after Backlog, before Todo
- [ ] Create status: **`Pi-Dev: In Progress`** — Type: Started — Position: after In Progress
- [ ] Create status: **`Pi-Dev: Blocked`** — Type: Started — Position: after Pi-Dev: In Progress
- [ ] Create status: **`In Review`** — Type: Started — Position: after Pi-Dev: Blocked

### 2. Workspace labels — Settings → Labels → Workspace

- [ ] Create label: **`pi-dev:source`** — Colour: Purple
- [ ] Create label: **`pi-dev:autonomous`** — Colour: Orange
- [ ] Create label: **`pi-dev:needs-review`** — Colour: Yellow
- [ ] Create label: **`pi-dev:blocked-reason:credentials`** — Colour: Red
- [ ] Create label: **`pi-dev:blocked-reason:ambiguous-spec`** — Colour: Red
- [ ] Create label: **`pi-dev:blocked-reason:external-dep`** — Colour: Red
- [ ] Create label: **`pi-dev:blocked-reason:scope-creep`** — Colour: Red

### 3. Custom field — Settings → Custom fields

- [ ] Create field: **`Pi-Dev Run ID`** — Type: Text (single line) — Scope: All issues

---

## Rollout order

1. Apply statuses + labels to **RestoreAssist** (or Pi-Dev-Ops itself) first.
2. Run Skill 4 (Health Report, read-only) against the target project for one week.
3. Add Skill 1 write-path manually via `/Pi-Dev: File Analysis Output`. Verify idempotency.
4. Wire Pi-Dev auto-invocation. Only then expand to remaining 9 projects.

## Acceptance criteria

- [ ] All 4 statuses live on ≥1 project
- [ ] All 4 labels live at workspace level
- [ ] `Pi-Dev Run ID` custom field visible in the issue editor on ≥1 project
- [ ] `Ready for Pi-Dev` visible as a board column
- [ ] RA-1369 unblocked — autonomy poller can transition tickets without `State not found` errors

---

## Why RA-1369 is blocked until this is done

`autonomy.py`'s `_create_session()` and `_orphan_recovery()` (RA-1369) call `save_issue` to transition tickets to `Ready for Pi-Dev`, `Pi-Dev: In Progress`, and `Pi-Dev: Blocked`. If those states don't exist in the project's workflow, the transition fails with:

```
State 'Pi-Dev: In Progress' not found in team {id} workflow
```

This is a hard runtime error, not a graceful degradation. RA-1369 code **must not ship** until this checklist is complete for at least the RestoreAssist project.
