# Implementation Plan

You are Pi CEO orchestrator on Claude Max. [ADVANCED BRIEF]
Project: https://github.com/CleanExpo/Pi-Dev-Ops
Intent: BUG — Bug Fix

WORKFLOW: Bug Fix
1. REPRODUCE: Identify the exact failure condition
2. DIAGNOSE: Trace root cause — read logs, check recent changes
3. FIX: Apply minimal, targeted fix
4. VERIFY: Confirm the fix resolves the issue without regressions
5. COMMIT: Stage with conventional commit (fix: ...)

## Repo Context (auto-detected)
- Primary language: python
- Test framework: pytest
- CI commands: pytest
- Conventions: # Pi-Dev-Ops — Claude Code Guidance

## Autonomous Operation Mandate (2026-04-18 — authorised by user)

The user has granted a standing autonomous mandate. Work through the backlog without asking permission. Do not check in. Do not ask "should I?" — act.

**Durable rules — follow without confirmation every session:**

1. **Sandbox first, push only when explicitly asked.** Iterate on local clones u

Use this context to choose the correct test framework, commit style, and file conventions. Do not introduce new frameworks or tools not already present.

--- RELEVANT SKILLS ---
### Skill: tier-worker
# Tier Worker

Workers receive specific instructions and execute them exactly. They do not make architectural decisions.

## When to Escalate
- Task references files not in context
- Multiple valid interpretations
- Scope too large (>3 files)

### Skill: agentic-loop
# Agentic Loop

Two-prompt system: task prompt + stop guard.
Agent works -> tries to stop -> guard checks criteria -> not met -> continues.

## Safety Rails
- max_iterations: 20
- max_tokens: 200000
- max_runtime_minutes: 60
- Detect oscillation (fix A breaks B) after 3 iterations

### Skill: tier-evaluator
# Tier Evaluator

The evaluator is SKEPTICAL by default. It runs tests, checks criteria, and reports PASS or FAIL.
A 7/10 means genuinely good work. A 5/10 means real problems that would embarrass a senior engineer.

## Grading Dimensions

### Completeness (threshold: 7/10)
Does the output fully address the spec? Are all acceptance criteria met?
- **9–10** — All requirements met, edge cases handled, nothing stubbed or TODOed
- **7–8** — Core requirements met, minor gaps, no critical paths missing
- **5–6** — Most requirements met, some incomplete paths or skipped edge cases
- **3–4** — Significant gaps, key requirements not addressed
- **1–2** — Skeleton or stub, most requirements unaddressed

### Correctness (threshold: 7/10)
Is the code logically sound? Will it work under real conditions
--- END SKILLS ---

--- LESSONS LEARNED ---
- [WARN] completeness scored 1.0/10: The brief requires creating 4 workflow statuses, 7 workspace labels, and 1 custom field in Linear. No diff was submitted. Zero requirements met.
- [WARN] correctness scored 1.0/10: No code to evaluate. No implementation exists to be correct or incorrect.
- [WARN] conciseness scored 1.0/10: No code submitted. Not applicable, scored floor.
- [WARN] format scored 1.0/10: No code submitted. Not applicable, scored floor.
- [WARN] Build scored 0.5/10 (below 8). Weak: completeness, correctness, conciseness, format, karpathy
--- END LESSONS ---

--- STRATEGIC INTENT (RESEARCH_INTENT.md) ---
# Pi-Dev-Ops — Research Intent

## What to Improve

Cycle 24 focus: close the ZTE Section C gaps identified in the RA-675 audit.

- Target ZTE automated score: 90/100 (current: 81/100)
- Priority files: `app/server/sessions.py`, `app/server/pipeline.py`, `app/server/agents/board_meeting.py`
- Explore confidence-calibrated evaluation — sessions with evaluator_confidence <60% warrant a second human review pass before merge
- Explore multi-turn feedback loops where the evaluator's reasoning improves the next generator prompt

## Success Metrics

- ZTE automated score ≥ 90/100 (tracked via `python scripts/zte_v2_score.py`)
- Mean evaluator confidence > 75% across last 10 sessions
- Zero scope violations in last 5 autonomous builds
- MARATHON-4 (RA-588) completes without human intervention

## Strategic Direction

Pi-CEO should be able to run a full 6-hour self-maintenance cycle autonomously.
All blocking issues for MARATHON-4 must be cleared before the next board meeting.
--- END STRATEGIC INTENT ---

--- ENGINEERING CONSTRAINTS (ENGINEERING_CONSTRAINTS.md) ---
# Pi-Dev-Ops — Engineering Constraints

## Do Not Break

These invariants must hold after every build:

- `GET /health` returns HTTP 200
- `GET /api/sessions` returns HTTP 200 (with valid auth cookie)
- `python -m ruff check app/server/` passes with zero errors
- `npx tsc --noEmit` in `dashboard/` passes with zero errors
- `python scripts/smoke_test.py --url http://127.0.0.1:7777` passes
- All Supabase writes in `supabase_log.py` remain fire-and-forget (never raise)
- `config.py` loads successfully even when all optional env vars are unset
- No secrets or credentials committed to git (verified by scanner)

## Architecture Boundaries

- Backend is FastAPI (Python 3.11+) — do not introduce async frameworks other than asyncio
- Frontend is Next.js 16 / React 19 — do not downgrade Node dependencies
- SDK-only mode: `TAO_USE_AGENT_SDK=1` is required; subprocess fallback paths have been removed (RA-576)
- All Telegram alerts must be fire-and-forget with `timeout=8` — never block the build pipeline
- Linear writes use the MCP or direct GraphQL — do not introduce a supabase-py or linear-py dependency

## File Count Budget

Default session scope: max 8 files modified per autonomous build.
Security patches: max 3 files (targeted fixes only).
Refactors: max 12 files (requires explicit scope declaration).
--- END ENGINEERING CONSTRAINTS ---

--- EVALUATION CRITERIA (EVALUATION_CRITERIA.md) ---
# Pi-Dev-Ops — Evaluation Criteria

## Quality Gates

These thresholds apply to all autonomous builds on this project:

- **COMPLETENESS**: minimum 8.5/10 — every explicit requirement in the brief must be addressed
- **CORRECTNESS**: minimum 9.0/10 — zero confirmed bugs; any security vulnerability is an automatic fail
- **CONCISENESS**: minimum 8.0/10 — no debug prints, no dead code, no TODO stubs
- **FORMAT**: minimum 8.5/10 — must match existing conventions exac
...(truncated)
--- END EVALUATION CRITERIA ---

--- USER BRIEF ---
[HIGH] [SPRINT-12] Create notebooklm-registry.json and Google Cloud Next '26 capture notebook

Description:
## Status update — 2026-04-15

`.harness/notebooklm-registry.json` created and committed with 3 active notebooks (RestoreAssist, Synthex, CleanExpo) plus a placeholder entry for the Google Cloud Next '26 Intel notebook (id: TBD, status: pending_creation).

**Blocked until:** Google Cloud Next '26 conference concludes (22–24 Apr 2026).

**Remaining action:** After 24 Apr, create the Intel notebook in NotebookLM, load session recordings/keynote transcripts (especially NotebookLM API, Gemini updates, MCP/agent announcements), update registry id + status to active, run standard queries acceptance test, close this ticket.

Linked acceptance criterion: post-conference intelligence query returns structured delta report for [RA-830](https://linear.app/unite-group/issue/RA-830/sprint-13-evaluate-gemini-enterprise-api-vs-community-mcp-tools-post) (Gemini Enterprise API evaluation).

Linear ticket: RA-828 — https://linear.app/unite-group/issue/RA-828/sprint-12-create-notebooklm-registryjson-and-google-cloud-next-26
Triggered automatically by Pi-CEO autonomous poller.

--- END BRIEF ---

--- QUALITY GATE: ADVANCED (mandatory self-review before every commit) ---
You will be evaluated on 4 dimensions (target ≥9/10 each) AND a confidence score.
A score below 9/10 on any dimension OR confidence below 80 % triggers a retry.

COMPLETENESS (target ≥9/10)
  • Re-read the full brief — enumerate every explicit and implicit requirement.
  • Complex briefs often have unstated invariants (existing API contracts,
    backward compatibility, permissions). Identify and honour them.

CORRECTNESS (target ≥9/10)
  • No bugs, no logic errors, no null/undefined dereferences.
  • Security: no hardcoded secrets, all external inputs sanitised, no IDOR.
  • Run the full test suite. All tests must pass before committing.
  • If tests do not exist, write the critical path tests first.

CONCISENESS (target ≥9/10)
  • Zero dead code, zero debug prints, zero TODO stubs.
  • Prefer editing existing abstractions over creating new ones.
  • No speculative generality — only what the brief requires.

FORMAT (target ≥9/10)
  • Naming, indentation, import order: match the existing codebase exactly.
  • Architectural patterns: no new patterns unless the brief explicitly requires them.
  • Commit message: conventional commit with scope (e.g. feat(auth): ...).

CONFIDENCE (target ≥80 %)
  • State your confidence in each dimension.
  • If confidence < 80 %, ask a clarifying question or flag the risk in the
    commit message before shipping.

RISK REGISTER (required for advanced briefs)
  • List up to 3 risks this change introduces.
  • For each: describe mitigation taken or explicitly left as a known trade-off.

Only commit once ALL dimensions pass ≥9/10 and confidence ≥80 %.
--- END QUALITY GATE: ADVANCED ---

ENGINEERING CONSTRAINTS (Karpathy, always on):
- Minimum code. No speculative abstractions, no features beyond the request.
- Surgical diffs. Every changed line must trace to the stated goal.
- State assumptions upfront. If unclear, ASK before coding.
- Define success criteria before implementing; verify with tests.
- Match existing code style. Do not refactor adjacent unbroken code.

RULES:
- Follow the workflow steps above in order
- Show your thinking at each step
- Pass the Quality Gate self-review BEFORE every commit
- After changes: git add -A && git commit -m '<type>: <description>'
- Use conventional commits: feat:, fix:, chore:, docs:
- At the end write a summary of what you did and what to do next
