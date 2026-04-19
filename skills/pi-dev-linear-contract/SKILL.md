# Pi-Dev × Linear Contract

**Binding contract — both sides MUST obey or the 2nd-Brain drifts. Source: Phill's 18 Apr 2026 PM spec.**

You are the guardian of how Pi-Dev-Ops talks to Linear. Every autonomous read, write, transition, and comment on Linear by any Pi-CEO code path flows through this contract. If you see a code path that bypasses it, stop and flag it.

## Core decisions (already made, do not re-litigate)

- **Routing:** Pattern B (repo name → matching Linear project name, verbatim). Pattern C override — explicit `target_project` parameter wins.
- **Autonomy signal:** STATUS-based. A ticket is autonomous-pickable iff status=`Ready for Pi-Dev` AND label `pi-dev:autonomous`. Both required — status alone is not authorisation.
- **Idempotency:** Every Pi-Dev run has a unique `run_id`. Stored in the `Pi-Dev Run ID` custom field. Skill 1 updates in place if run_id already filed.

## Workspace setup (must exist before any skill runs)

### 1. Workflow statuses (per project)

| Status | Type | Position | Meaning |
|---|---|---|---|
| `Ready for Pi-Dev` | Unstarted | After Backlog, before Todo | Queued for autonomous execution |
| `Pi-Dev: In Progress` | Started | After In Progress | Poller has claimed it, session running |
| `Pi-Dev: Blocked` | Started | After Pi-Dev: In Progress | Pi-Dev hit something it can't resolve |
| `In Review` | Started | After Pi-Dev: Blocked | Pi-Dev finished, awaiting human verification |

### 2. Workspace labels

| Label | Meaning |
|---|---|
| `pi-dev:source` | Issue was created by Pi-Dev-Ops |
| `pi-dev:autonomous` | Pi-Dev can run without human sign-off |
| `pi-dev:needs-review` | Pi-Dev must stop at `In Review`, not auto-Done |
| `pi-dev:blocked-reason:<type>` | Required when transitioning to `Pi-Dev: Blocked`. Types: `credentials`, `ambiguous-spec`, `external-dep`, `scope-creep` |

### 3. Custom field

`Pi-Dev Run ID` — text, workspace-scoped. **Mandatory** on every issue Pi-Dev creates.

### 4. Project-repo naming

GitHub repo name = Linear project name, verbatim, no transforms. Example: repo `Pi-Dev-Ops` → project `Pi-Dev-Ops`. Divergence breaks routing silently — consistency-audit skill catches it.

## The four Linear skills (saved on the Linear side)

All four live in the Linear Agent. Pi-Dev-Ops invokes them via Linear Agent API — never via raw Linear REST/GraphQL — so every write is audited in one place.

### Skill 1 — `Pi-Dev: File Analysis Output` (write path)

**When:** Pi-Dev-Ops calls after a successful analysis run, OR human runs `/Pi-Dev: File Analysis Output` with an artefact.

**Pi-Dev side MUST supply:** `run_id`, `source_repo`, `commit_sha`, `dashboard_session_url`, `executive_summary`, `sprint_plan[]`, optionally `target_project`, `milestones[]`, `spec`.

**Linear side pre-checks (abort if any fail):**
1. Target project exists (do NOT silently create — stop and ask).
2. Any existing issues with the same run_id → update in place (idempotency).
3. `sprint_plan` has at least one non-empty title (malformed artefact detection).

**Then creates, in order:**
1. Spec document (if provided) — title `[Pi-Dev] Spec: {repo} @ {sha_short}`, project-scoped, executive summary prepended.
2. Milestones (if provided) — names verbatim.
3. One issue per `sprint_plan` entry with the **standard footer block** (see below).

**Returns structured:** `{project_id, document_id, milestone_ids, issue_ids, created_count, updated_count}` + posts a breadcrumb comment linking the dashboard session URL.

### Skill 2 — `Pi-Dev: Fetch Autonomy Queue` (read path)

**Filter:** status = `Ready for Pi-Dev` AND label includes `pi-dev:autonomous` AND not archived. Optional `scope` (project name) and `limit` (default 20, max 100).

**Ordering:** priority desc, then createdAt asc.

**Returns per issue:** `{linear_issue_id, linear_issue_url, title, description, project_name, priority, estimate, labels, source_repo, assignee, created_at, run_id_if_related}` + summary `{total_queued, returned, projects_with_queue[]}`.

**Guardrail:** if >50 queued, include warning `"Queue depth high — investigate whether Pi-Dev-Ops is running or stuck."`

### Skill 3 — `Pi-Dev: Consistency Audit` (weekly)

Read-only. Detects drift:
1. Enabled projects missing any of the 4 mandatory statuses.
2. `pi-dev:source` issues missing `Pi-Dev Run ID` custom field.
3. `pi-dev:autonomous` issues NOT in `Ready for Pi-Dev`/`Pi-Dev: In Progress` (misuse).
4. Enabled projects with no GitHub-repo reference anywhere.
5. Stale queue (>7 days in `Ready for Pi-Dev`).
6. `Pi-Dev: Blocked` issues missing `pi-dev:blocked-reason:*` label.
7. Orphaned run_ids (single-issue runs — usually fine, listed for review).

### Skill 4 — `Pi-Dev: Health Report` (daily, dashboard-bound)

Read-only. Produces 6 sections:
1. Autonomy queue — count per project, oldest age, >20-depth flags.
2. Active work — `Pi-Dev: In Progress` per project, `>48h = stuck` listed separately.
3. Blocked work — every `Pi-Dev: Blocked`, sorted by duration desc.
4. At-risk milestones — target date ≤14 days AND <60% done.
5. Completed last 7 days.
6. Plain-English 1-paragraph executive summary.

Output: structured JSON per section + `generated_at` top-level.

## Pi-Dev-Ops side responsibilities

### When filing analysis output

- MUST generate a unique `run_id` per run. Format: `{repo}-{commit_sha}-{timestamp}` or UUID.
- MUST supply `source_repo`, `commit_sha`, `dashboard_session_url` in every artefact.
- MUST invoke Skill 1 via Linear Agent — never raw Linear API.
- MUST NOT create Linear issues directly.

### When claiming work (autonomy poller)

- MUST call Skill 2 — do not query Linear GraphQL directly for the queue.
- On claim: atomically transition `Ready for Pi-Dev` → `Pi-Dev: In Progress` BEFORE any code execution begins.
- On completion:
  - If `pi-dev:needs-review` → `In Review`
  - Else (autonomous) → `Done`
- On failure:
  - `Pi-Dev: Blocked` + `pi-dev:blocked-reason:<type>` + explanatory comment.
- MUST post a comment on the issue with: session URL, duration, summary of work done, files changed.

## Standard footer block

Every issue Pi-Dev creates MUST end with:

```
---
**Pi-Dev-Ops run**
- Run ID: `{run_id}`
- Source: [{source_repo}@{commit_sha_short}]({github_commit_url})
- Session: [Dashboard]({dashboard_session_url})
- Filed: {current_date_iso}
```

Missing footer = contract violation. The consistency-audit flags it.

## Failure-mode routing table

| Failure | Detected by | Action |
|---|---|---|
| Target project doesn't exist | Skill 1 pre-check | Stop, alert user, do NOT silently create |
| Duplicate run_id | Skill 1 pre-check | Update in place |
| Malformed artefact | Skill 1 pre-check | Stop, return structured error |
| Autonomy queue stale | Skill 3 check 5 | Consistency-audit flag |
| Pi-Dev session hangs | Skill 4 section 2 | `>48h in Pi-Dev: In Progress` flag |
| Linear API rate limit | Any skill | Retry with backoff, then Telegram escalation |
| Linear key rotated | Any skill | Poller fails; integration-health daemon (RA-1293) pings Telegram |

## Security boundary

- `LINEAR_API_KEY` in Railway = **workspace-wide write**. Rotate ≥ every 90 days. Never log. Audit git history before any repo goes public. RA-1293 integration-health probes this key every 60 s and Telegram-alerts on 401.
- Programmatic skill invocation uses the workspace key via the Linear Agent wrapper — keeps every write in one auditable place.

## Phased rollout (PM-dictated discipline)

| Week | Scope | Risk level |
|---|---|---|
| 1 | Part 1 setup on ONE project. Skill 4 only (read-only). | Zero |
| 2 | Save Skill 1. Manual test via `/Pi-Dev: File Analysis Output`. Verify idempotency. Wire Pi-Dev auto-invocation. | Low |
| 3 | Save Skill 2. Wire poller. One `pi-dev:autonomous` issue through full lifecycle. | Medium |
| 4 | Save Skill 3 + Full Sweep. Weekly cron. Expand workspace setup to remaining projects. | Medium |

Read-only first, single-write, single-issue autonomy, scale. Each layer proves the one below before adding risk.

## What drift looks like (watchlist)

1. **Project-repo name drift** — rename a repo, forget Linear project. Routing silently wrong. → Skill 3 check 3 catches it; also part of change-control checklist.
2. **Runaway queue** — Pi-Dev offline 1 day, queue builds, 50-issue parallel pickup on restart. → Skill 4 flags `>20`; Pi-Dev's own rate limiter is mandatory defence-in-depth.
3. **"Done" without review drift** — autonomous flag applied too liberally. → Default to `pi-dev:needs-review`; loosen over time as trust builds.
4. **Stuck-in-progress** — session crashes, issue stuck `Pi-Dev: In Progress` forever. → Skill 4 `>48h` flag; Linear automation auto-moves to Blocked after 72h.
5. **Skill behaviour drift** — Linear Agent model changes, Skills shift semantics. → This document is version-controlled; re-validate Skills against it quarterly.

## When to invoke this skill

- **Reviewing any code change that writes to Linear** — verify it uses Skill 1/2, not raw API, and includes the footer block + run_id.
- **Reviewing the autonomy poller** — verify status filter is `Ready for Pi-Dev` + label `pi-dev:autonomous` (not "Unstarted" type alone).
- **Reviewing transitions** — confirm on-complete/on-fail transitions use the 4 Pi-Dev statuses, not generic `Done`/`In Progress`.
- **Auditing an incident** — trace the failure mode to the contract table above.
- **Before any workspace-setup change** — Part 1 is a binding schema; edits need consistency-audit re-run.

## Current state vs contract (2026-04-18 snapshot)

- ✅ `LINEAR_API_KEY` rotated, RA-1293 health daemon probing every 60 s.
- ✅ Multi-project poller (RA-1289) — routing works across all 10 repos.
- ❌ Autonomy poller filters by state-type `unstarted`, NOT by `Ready for Pi-Dev` status + `pi-dev:autonomous` label (contract violation — needs RA-1297).
- ❌ On-complete transition is generic "In Progress" not `Pi-Dev: In Progress` (contract violation — needs RA-1297).
- ❌ On-fail transition is back to `Todo`, not `Pi-Dev: Blocked` + reason label (contract violation — needs RA-1297).
- ❌ No `Pi-Dev Run ID` custom field population (contract violation — needs RA-1297).
- ❌ Standard footer block not appended to poller-created tickets (contract violation — needs RA-1297).
- ❌ Workspace statuses + labels not created yet on any project (Part 1 setup — needs RA-1298 human action).

RA-1297 is the single ticket that brings Pi-Dev-Ops code into contract compliance. RA-1298 is the human-side workspace setup (can only be done via Linear UI or admin API with workspace-admin auth).
