# Agent SDK Production Cut-Over Plan

**Linear:** RA-551
**Author:** Pi-CEO (autonomous)
**Date:** 2026-04-10
**Status:** Decision recorded — **NO-GO on Managed Agents API, GO on `claude_agent_sdk`**

---

## 1. PoC Outcome (evidence)

The original PoC plan (`MANAGED_AGENTS_v4_FINAL.md` lines 9–24) called for a 14-day parallel run of the existing `claude -p` subprocess path against the Anthropic Managed Agents API, with hard kill criteria:

1. Idle timeout < 6h (cron incompatibility)
2. 3+ consecutive MCP tool-use failures
3. Cost > 5× baseline per cycle

`.harness/poc-metrics/` contains the actual run record. Three files exist; zero successful real cycles:

| File | Cycle | Status | Detail |
|---|---|---|---|
| `cycle-0099-20260409-2203.json` | 99 | `error` | `Could not resolve authentication method. Expected either api_key or auth_token to be set` |
| `cycle-82211-20260409-2212.json` | 82211 | `error` | `400 invalid_request_error: config.setup_commands: Extra inputs are not permitted` |
| `cycle-82211-20260409-2213.json` | 82211 | `dry_run` | Agent + environment created, 0 streamed events |

**Score: 0 / 14 successful cycles. 2 / 3 runs hard-failed.** `MANAGED_AGENTS_v4_FINAL.md` lines 246–254 corroborate: 0 successful cycles, 1 auth failure, 2 dry-runs, blocker = no resolvable `ANTHROPIC_API_KEY` and a beta-API schema rejection on `config.setup_commands`.

Two of the three documented kill criteria were tripped before the evaluation window opened: consecutive failures (criterion 2) and an inability to even establish a baseline cost per cycle (criterion 3 unmeasurable). Criterion 1 (idle timeout) was never reached because no session ran long enough to test it.

## 2. Decision: NO-GO on Managed Agents API, GO on `claude_agent_sdk`

### Why NO-GO on Managed Agents API (`anthropic.beta.agents`)

- 0 / 14 successful PoC cycles
- Active 400 blocker on the beta schema (`config.setup_commands` field rejected)
- No baseline cost or latency data to compare against
- Beta surface area changes without notice — building production cut-over on top is high-risk

### Why GO on `claude_agent_sdk` (Python SDK)

- A working `claude_agent_sdk` adapter already exists in this monorepo at `telegram-bot/src/claude/sdk_integration.py` (1000+ lines, in production behind the Telegram bot)
- The adapter already handles: `ClaudeSDKClient` lifecycle, session resume, MCP server configuration, tool-use validation callbacks, and streaming event parsing
- The Python SDK is GA, not beta, and matches the existing `claude -p` subprocess semantics one-for-one
- The adapter pattern is reusable as-is for the Pi-CEO build pipeline — no greenfield code needed

The decision is therefore to **decommission the Managed Agents PoC code path** in `app/server/agents/board_meeting.py` (lines 417–567) and migrate every `claude -p` subprocess call site to the same adapter pattern that already powers the Telegram bot.

## 3. Migration sequence (3 phases, lowest blast-radius first)

### Phase 1 — Board meeting gap audit

- **Target:** `app/server/agents/board_meeting.py:241` (`_call_claude_for_discrepancies`)
- **Current shape:** single-shot `subprocess.run(["claude", "-p", prompt, "--output-format", "text", "--model", "claude-sonnet-4-6"], timeout=120)`
- **Why first:** smallest call site in the codebase. One prompt, no session resume, no JSON event stream, no retry loop, no budget tracking, no Linear sync. If the SDK adapter regresses here the only output that changes is `.harness/board-meetings/<date>-board-minutes.md`.
- **Reuses:** `ClaudeSDKClient` instantiation pattern at `telegram-bot/src/claude/sdk_integration.py:241-355`
- **Implementation note:** keep `re.search(r"\[.*\]", raw, re.DOTALL)` JSON-array extraction unchanged — the SDK returns the same text payload

### Phase 2 — Build sessions (highest value)

- **Targets:**
  - `app/server/sessions.py:434` — `_phase_generate` (main build)
  - `app/server/sessions.py:506-565` — `_phase_evaluate` (closed-loop quality gate with up to 2 adaptive retries)
- **Why second:** these own the JSON event stream, the budget tracker, and the Linear sync — the highest-leverage code in the platform. The SDK supports streaming and tool-use events natively, so retry-with-feedback logic gets simpler, not more complex.
- **Hooks to preserve unchanged:**
  - `BudgetTracker` instantiation at `sessions.py:644-645`
  - Cost parsing at `sessions.py:163-164` (`evt.get("cost_usd")`)
  - Linear "In Review" transition at `sessions.py:672-675`
- **Constraint:** keep `_run_claude` function signature stable so the surrounding `run_build()` orchestrator does not change

### Phase 3 — Pipeline + orchestrator (user-facing CLI)

- **Targets:**
  - `app/server/pipeline.py:283-305` — `_run_claude()` used by `/spec` and `/plan` slash commands
  - `app/server/orchestrator.py:35-38` — `_decompose_brief()` used by N-worker fan-out
- **Why last:** these are the most user-visible surfaces (`/spec`, `/plan` are the entry points to the Ship Chain). Migrating them last means a stable rollback path is in place by the time they flip.
- **Untouched:** `_resolve_claude_bin()` at `pipeline.py:247-273` stays in place as the fallback resolver

## 4. Kill criteria (per phase)

A phase is rolled back if any of these trip during validation:

| Criterion | Threshold | Measurement |
|---|---|---|
| Session lifecycle | SDK init + completion ≤ 2× current `claude -p` p50 latency | wall-clock from phase start to phase end |
| MCP connectivity | 0 unhandled MCP tool errors over 5 consecutive runs | exception count from `ClaudeSDKClient` |
| Cost | token cost per phase ≤ 1.25× current baseline | `BudgetTracker` at `sessions.py:644-645` |
| Auth | `ANTHROPIC_API_KEY` resolvable from `.env.local` at process start | startup probe in `app/server/main.py` |

The auth criterion is the immediate blocker today (see `feedback_env_anthropic_key.md` memory: the `claude` CLI sets `ANTHROPIC_API_KEY=""` in shell, so the dev script must `source .env.local` to override).

## 5. Rollback plan

- **Feature flag:** `TAO_USE_AGENT_SDK={0|1}` env var added to `app/server/config.py` alongside the existing `TAO_CLAUDE_CMD = os.environ.get("TAO_CLAUDE_CMD", "claude")` constant
- **Per-call-site dispatch:** every migrated function reads the flag at call time. On flag-off, or on `import claude_agent_sdk` failure, or on session-init exception, the function falls through to the existing `subprocess.run(["claude", "-p", ...])` path
- **Granular flip:** the flag is checked per phase, so Phase 1 can ship on SDK while Phases 2 and 3 stay on subprocess
- **No deletion until cutover:** the existing `_run_claude` / subprocess paths remain in the tree until all three phases have run cleanly for at least 7 consecutive days

## 6. Phase 1 implementation ticket (filed)

A single Linear ticket is created against the Pi - Dev -Ops project as RA-551's required Phase 1 follow-up:

**Title:** `[ARCH] Phase 1 — migrate board_meeting._call_claude_for_discrepancies to claude_agent_sdk`
**Priority:** High
**Status:** Todo

The ticket links back to RA-551, points at `app/server/agents/board_meeting.py:241` and the reusable adapter at `telegram-bot/src/claude/sdk_integration.py:241-355`, and lists:

- Acceptance: gap-audit phase runs against SDK behind `TAO_USE_AGENT_SDK=1`
- Acceptance: subprocess fallback fires on flag-off
- Acceptance: no regression in `.harness/board-meetings/` output size (current baseline: 7338 bytes per `cycle-82211-20260409-2213.json`)

Phases 2 and 3 will be filed as separate tickets after Phase 1 ships and runs cleanly for 7 days.

---

## Files referenced

| Path | Purpose |
|---|---|
| `.harness/poc-metrics/*.json` | PoC evidence |
| `MANAGED_AGENTS_v4_FINAL.md` | Original kill criteria + PoC status |
| `app/server/agents/board_meeting.py:241` | Phase 1 target |
| `app/server/sessions.py:434,506-565,644-645,672-675` | Phase 2 targets + budget/Linear hooks |
| `app/server/pipeline.py:247-305` | Phase 3 targets + binary resolver |
| `app/server/orchestrator.py:35-38` | Phase 3 fan-out target |
| `app/server/config.py` | Feature-flag location (`TAO_USE_AGENT_SDK`) |
| `telegram-bot/src/claude/sdk_integration.py:241-355` | Reusable SDK adapter pattern |
| `.harness/config.yaml` | Agent model tiers |
| `CLAUDE.md` lines 74–76 | Strategic direction reference |
