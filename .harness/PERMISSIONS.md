# Pi-CEO Permission Hardening Contract

**Rule:** once a run goes to code, there is no stopping to ask for permission. Every interactive prompt is a marathon-killer. Permissions are pre-granted at three layers before any autonomous work begins. No exceptions.

This document is the single source of truth for how permissions work across the Pi-CEO stack. Reference it whenever adding a new call site, cron job, or scheduled task.

---

## The three layers

### Layer 1 — `.claude/settings.json` (project-level allowlist)

Location: `/.claude/settings.json` (committed to repo, applies to every Claude CLI invocation run in this working directory).

Current posture:
- `permissions.defaultMode = "bypassPermissions"` — no prompts ever, no confirmations
- `permissions.allow` pre-approves every tool the autonomous rails need: `Bash(python3:*)`, `Bash(pytest:*)`, `Bash(git:*)`, `Read(*)`, `Write(*)`, `Edit(*)`, `Glob(*)`, `Grep(*)`, WebFetch on the six allowed domains, WebSearch, and every `mcp__pi-ceo__*` and `mcp__scheduled-tasks__*` tool
- `permissions.deny` blocks destructive patterns: `sudo`, `rm -rf /`, `dd`, `mkfs`, unbounded pipe-to-shell from remote URLs

Any new tool added to an autonomous rail MUST be added to the allow list BEFORE it ships. A permission prompt at runtime is a regression.

### Layer 2 — Agent SDK options (in-process Python)

Every `ClaudeSDKClient` created inside `app/server/` uses:

```python
options = ClaudeAgentOptions(
    cwd=workspace,
    model=model,
    allowed_tools=[],
    permission_mode="bypassPermissions",
)
```

Reference implementation: `app/server/sessions.py:204-222` (`_run_claude_via_sdk`). When Phase 3 ships and the helper moves to `app/server/claude_runner.py`, the same mode must be set on construction. Grep target: `permission_mode="bypassPermissions"`.

### Layer 3 — Claude CLI subprocess flags (`CLAUDE_EXTRA_FLAGS`)

Defined at `app/server/config.py`:

```python
_INTERACTIVE         = os.environ.get("TAO_CLAUDE_INTERACTIVE", "0") == "1"
CLAUDE_EXTRA_FLAGS   = [] if _INTERACTIVE else ["--dangerously-skip-permissions"]
```

Every subprocess `claude -p` invocation in the codebase MUST splice `*config.CLAUDE_EXTRA_FLAGS` into its argv between the executable and the first user flag. Patched call sites (as of 2026-04-11):

1. `app/server/agents/board_meeting.py:284` — board-meeting audit
2. `app/server/sessions.py:254` — `_run_single_eval`
3. `app/server/sessions.py:572` — `_phase_generate` subprocess fallback
4. `app/server/sessions.py:716` — `_phase_evaluate` retry subprocess fallback
5. `app/server/orchestrator.py:39` — planner decomposition
6. `app/server/pipeline.py:285` — `_run_claude` generic runner

Local developers who want the old behaviour (interactive prompts for exploration) set `TAO_CLAUDE_INTERACTIVE=1` in their shell. Railway and every scheduled task leaves this unset, so the flag is always injected.

---

## Scheduled tasks (desktop Claude, not Railway)

The three marathon scheduled tasks (`marathon-telegram-heartbeat`, `marathon-pi-seo-dryrun-hourly`, `marathon-anthropic-refresh-weekly`) run inside the desktop Claude session via the scheduled-tasks MCP. They do NOT inherit the repo `.claude/settings.json`.

**Design rule:** each task prompt is a SINGLE shell command, nothing else. The Claude session that executes the task only needs one tool (`Bash`), which the user pre-approves with one "Run now" click. After that first approval, every future run reuses the stored grant.

Current prompts call these self-contained helpers:
- `scripts/marathon_heartbeat.py` — reads digest + runs pytest + composes + sends Telegram
- `scripts/marathon_pi_seo_dryrun.py` — aggregates scans + writes digest + diffs critical + sends alert
- `python3 -m app.server.agents.anthropic_intel_refresh` — fetches docs + diffs + writes brief

None of them require the scheduled-task Claude to read files, compose text, or use multiple tools. This is deliberate: the smaller the tool surface, the smaller the approval ask.

**Activation checklist (one-time, before going away):**
1. Open Cowork → Scheduled tab
2. For each of the three marathon tasks, click "Run now"
3. Approve `Bash` when prompted
4. Verify the run completes and the output looks sane
5. Subsequent runs will fire without any prompt

---

## Railway cron (production)

Railway invokes the Claude CLI directly. The CLI inherits settings from `.claude/settings.json` in the working directory, so Layer 1 covers it. Layer 3 adds `--dangerously-skip-permissions` as belt-and-braces in case settings.json is ever missing or misconfigured.

Required Railway env vars:
- `ANTHROPIC_API_KEY` — otherwise the SDK and CLI both fall over immediately
- `TAO_USE_AGENT_SDK=1` — to exercise the SDK path (Phase 2+)
- `TAO_CLAUDE_INTERACTIVE` — MUST NOT be set. Leave unset so `CLAUDE_EXTRA_FLAGS` includes the skip flag.
- `TELEGRAM_BOT_TOKEN`, `ALLOWED_USERS` — for alert push

---

## How to add a new call site without breaking this contract

1. If calling via subprocess: splice `*config.CLAUDE_EXTRA_FLAGS` into argv.
2. If calling via SDK: construct `ClaudeAgentOptions` with `permission_mode="bypassPermissions"`.
3. If the call uses a new tool type (e.g., a new MCP): add it to `.claude/settings.json` → `permissions.allow`.
4. If it's a new scheduled task: prompt must be one shell command; the underlying helper must be a standalone Python or shell script with no LLM tool dependency.
5. Grep-verify before merging:
   ```
   grep -rn "claude.*-p" app/server/ | grep -v CLAUDE_EXTRA_FLAGS
   ```
   If this returns anything, the contract is broken.

---

## What happens if a prompt slips through anyway

Detection:
- Scheduled-tasks heartbeat missing a beat at the 3-hour mark → something stalled
- Telegram alert channel silent for over 6 hours → something stalled
- Pi-SEO digest file stops appearing hourly → something stalled

Mitigation:
- Railway cron jobs have a 10-minute timeout at the job level. If the process hangs on a prompt, Railway kills it and logs "cron job exceeded timeout". Check Railway logs first.
- Scheduled-tasks MCP surfaces errors in the task's session log. Check the "Scheduled" sidebar in Cowork.
- Kill switch: set `TAO_CLAUDE_INTERACTIVE=1` to revert to interactive mode while debugging.

---

## Founder responsibility

Phill does not write code in this repo. But the one-time "Run now" click for each scheduled task is a founder action that cannot be delegated to the agent. Do that click once, verify green, and the rails run themselves.
