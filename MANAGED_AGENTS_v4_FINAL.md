# Pi-CEO Managed Agents Protocol — v4 FINAL

_Adopted: 2026-04-09 | Board Vote: 8/8 unanimous | Ticket: RA-485_

---

## Overview

14-day parallel PoC comparing the existing Pi-CEO system (claude CLI subprocess) against the Anthropic Claude Managed Agents API (cloud-hosted sessions). Both systems run side-by-side every 6-hour cycle. Go/no-go decision at the end of 14 consecutive successful managed cycles.

**Runner:** `scripts/run_parallel_board.py`
**Metrics:** `.harness/poc-metrics/cycle-{N:04d}-{timestamp}.json`

---

## Kill Criteria

Abort the PoC immediately if any of the following are triggered:

1. **Session lifecycle incompatible** — idle timeout < 6h (cron-pattern incompatible)
2. **MCP connectivity failure** — 3+ consecutive cycles where managed system fails to use any MCP tool
3. **Cost overrun** — managed cycle cost > 5× raw API baseline for any single cycle

Kill criteria are checked automatically by `run_parallel_board.py` against the last 14 poc-metrics files.

---

## 6-Agent Roster

### Agent 1: Senior PM Coordinator (SPM)
- **Model:** `claude-sonnet-4-6`
- **Role:** Orchestrates the full board meeting. Runs all 6 phases, delegates to specialists, writes and saves final minutes.
- **Memory store:** `.harness/board-meetings/` (last 10 meeting cycles)
- **Tool access:** `agent_toolset_20260401` (full MCP + file access)
- **Invokes:** Agents 2–6 for specialised analysis phases

### Agent 2: Architecture Specialist
- **Model:** `claude-sonnet-4-6`
- **Role:** Phase 3 SWOT — technical architecture dimension. Evaluates codebase structure, debt, risks.
- **Memory store:** `.harness/leverage-audit.md` (architecture decisions baseline)
- **Input:** `spec.md` Section 2 + `leverage-audit.md` + last 10 `lessons.jsonl` entries
- **Output:** Architecture SWOT (3 Strengths, 3 Weaknesses, 2 Opportunities, 2 Threats), each referencing a specific file path or RA-xxx ticket

### Agent 3: Implementation Specialist
- **Model:** `claude-sonnet-4-6`
- **Role:** Phase 4 Sprint Recommendations — proposes concrete implementation tickets for the next cycle.
- **Memory store:** `lessons.jsonl` (implementation patterns, failure modes)
- **Input:** Architecture SWOT weaknesses + Linear board open items + `lessons.jsonl` last 20 entries
- **Output:** Ordered backlog of 3–7 items, each with title, effort (S/M/L), dependency list, and 3-bullet acceptance criteria

### Agent 4: Testing Specialist
- **Model:** `claude-sonnet-4-6`
- **Role:** Phase 2 Linear Review — quality gate perspective. Flags tickets touching test coverage or regression risk.
- **Memory store:** `scripts/smoke_test.py` (coverage reference)
- **Input:** Linear board state + recent session evaluator scores (from `lessons.jsonl`)
- **Output:** Coverage gap list, flaky test flags, regression risk assessment per open ticket

### Agent 5: Review Specialist
- **Model:** `claude-sonnet-4-6`
- **Role:** Phase 6 Update Linear — quality rubric gate. Validates proposals before ticket creation.
- **Rubric dimensions (each scored 1–5):**
  - Acceptance criteria specificity
  - Effort estimate confidence
  - Dependency mapping completeness
  - Risk identification
- **Minimum score to create ticket:** 14 / 20
- **Output:** Per-proposal: PASS (score ≥ 14, create ticket) or FAIL (score, rejection reason)

### Agent 6: Content/SEO Specialist
- **Model:** `claude-sonnet-4-6`
- **Role:** Monitors Pi-SEO scan results. Updates `executive-summary.md` for external communications.
- **Memory store:** `.harness/scan-results/` + `skills/pi-seo-scanner/SKILL.md` blast-radius scoring
- **Input:** `GET /api/projects/health` health summary
- **Output:** Updated `executive-summary.md` + Pi-SEO Linear tickets where blast_radius ≥ 9

---

## Board Meeting Protocol (6 Phases)

### Phase 1 — STATUS (SPM)

Read:
- `.harness/spec.md`
- `.harness/sprint_plan.md`
- `.harness/feature_list.json`
- `.harness/leverage-audit.md`
- Last 3 board meeting minutes from `.harness/board-meetings/`

Output: Current state summary (2 paragraphs max). No speculation — reference only what the files confirm.

### Phase 2 — LINEAR REVIEW (SPM + Testing Specialist)

Call `linear_list_issues` and `linear_sync_board`.

Classify issues:
- **Completed** since last meeting (completedAt > last meeting timestamp)
- **Blocked** (in-progress > 48h with no update)
- **Newly opened** (createdAt > last meeting timestamp)
- **Stale** (not updated in > 7 days, not Done)

Testing Specialist annotates any ticket referencing `tests/`, `smoke_test.py`, or evaluator scoring.

Output: Linear board delta table.

### Phase 3 — SWOT (Architecture Specialist)

Read `spec.md` Section 2 and last 10 `lessons.jsonl` entries.

Constraints:
- Each SWOT item references a specific file path (`app/server/sessions.py:142`) or RA-xxx ticket
- No generic observations ("the codebase is well-structured" is rejected)
- Weaknesses must be actionable (they feed Phase 4)

### Phase 4 — SPRINT RECOMMENDATIONS (Implementation Specialist)

Input: Phase 3 SWOT weaknesses + Phase 2 blocked tickets + `lessons.jsonl` failure patterns.

Each recommendation must include:
- Title (imperative, ≤ 60 chars)
- Effort: S (< 2h) | M (2–8h) | L (> 8h)
- Dependencies (list of RA-xxx or file paths that must be complete first)
- Acceptance criteria (exactly 3 bullets, testable)
- Priority justification (references specific SWOT item or blocked ticket)

Output: Ordered list of 3–7 items. First item is highest-leverage.

### Phase 5 — SAVE MINUTES (SPM)

Write to `.harness/board-meetings/{YYYY-MM-DD}-{HH}00-board-minutes.md`.

```markdown
# Pi-CEO Board Meeting — Cycle {N}
**Date:** {ISO date} AEST
**Attendees:** SPM, Architecture, Implementation, Testing, Review, Content/SEO

## Decisions
- [D-1] ...

## Action Items
| Item | Owner | Deadline | Ticket |
|------|-------|----------|--------|

## Risk Register Updates
- [R-new] ...
- [R-closed] ...

## Next Meeting
{timestamp + 6h}
```

### Phase 6 — UPDATE LINEAR (Review Specialist + SPM)

For each ticket proposal from Phase 4:
1. Review Specialist scores against quality rubric (min 14/20)
2. If PASS: SPM calls `linear_create_issue` with team `RestoreAssist`, project `Pi - Dev -Ops`
3. If FAIL: logs rejection reason, does not create ticket

Output: Created ticket IDs list + rejection log.

---

## Outcome Chain Loop

Each cycle feeds the next:

```
Cycle N minutes
  → lessons.jsonl append (if evaluator identifies new pattern)
  → Linear tickets created (Phase 6)
  → meta_agent.py reads lessons.jsonl every 4 cycles
      → proposes .harness/meta-proposals/{date}.md
      → human reviews + applies to CLAUDE.md
  → sprint_plan.md updated (manually after each board meeting sprint recs)
```

---

## Memory Store Design

Until Managed Agents persistent memory stores are fully available via API, simulate with these file-backed stores:

| Agent | Memory Store | File |
|-------|-------------|------|
| SPM | Board meeting history | `.harness/board-meetings/` |
| Architecture | Architecture decisions | `.harness/leverage-audit.md` |
| Implementation | Implementation patterns | `.harness/lessons.jsonl` |
| Testing | Coverage history | `scripts/smoke_test.py` + evaluator scores |
| Review | Quality rubric history | `.harness/contracts/eval-contract.md` |
| Content/SEO | SEO findings history | `.harness/scan-results/` |

---

## PoC Evaluation Metrics

Collected per cycle to `.harness/poc-metrics/cycle-{N:04d}-{timestamp}.json`:

```json
{
  "timestamp": "ISO-8601",
  "cycle": 99,
  "existing_system": {
    "system": "existing",
    "status": "found | not_found",
    "latest_minutes": "filename",
    "minutes_size": 7338
  },
  "managed_agents": {
    "system": "managed_agents",
    "status": "success | dry_run | error",
    "duration_s": 45.2,
    "events_count": 18,
    "tools_used": ["list_harness_files", "get_zte_score"],
    "minutes_length": 3200,
    "error": "string | null"
  },
  "comparison": {
    "managed_duration_s": 45.2,
    "managed_events": 18,
    "managed_tools": 7,
    "managed_status": "success | dry_run | error",
    "existing_status": "found | not_found"
  }
}
```

---

## Migration Decision Framework (Day 14)

At the end of 14 consecutive successful managed cycles, evaluate:

| Criterion | Threshold | Weight |
|-----------|-----------|--------|
| Cycle success rate | 14/14 = 100% | Required |
| Avg duration | ≤ 2× existing system | High |
| MCP tool call accuracy | All 6 Pi-CEO tools used per cycle | High |
| Minutes quality | ≥ same character count as existing | Medium |
| Cost per cycle | ≤ 5× API baseline | Required (kill criterion) |

If all Required criteria met and ≥ 2 of 3 High criteria met: **MIGRATE**.

Otherwise: **EXTEND** 7 more cycles or **ABORT** depending on which criteria failed.

---

## Current PoC Status

| Metric | Value |
|--------|-------|
| Successful managed cycles | 0 |
| Failed cycles | 1 (cycle-0099: authentication error) |
| Dry-run cycles | 2 (cycle-82211) |
| Blocker | `ANTHROPIC_API_KEY` not set in runner environment |
| Next action | `export ANTHROPIC_API_KEY=<key> && python scripts/run_parallel_board.py` |
