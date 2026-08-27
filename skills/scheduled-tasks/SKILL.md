---
name: scheduled-tasks
description: Guidelines for writing reliable scheduled task prompts via the Claude scheduled-tasks MCP.
---

# Scheduled Tasks

## When to apply

Apply these rules whenever writing or editing a scheduled task prompt that runs via the Claude scheduled-tasks MCP (desktop Claude session).

## Rules

- **Minimise tool-approval surface.** Scheduled tasks run inside the desktop Claude session and do NOT inherit the repo `.claude/settings.json` allowlist. Shrink every scheduled task prompt to a single shell command that calls a standalone Python helper script. This reduces the required tool approvals to Bash alone, which is approvable with one "Run now" click.

- **Never hardcode local Mac paths.** Scheduled tasks execute inside a fresh sandbox with a new session ID on every run. Hardcoded paths (e.g. `~/...`) will fail. Always discover the repo dynamically at the top of the task prompt:
  ```
  REPO=$(find /sessions -type d -name <repo-name> | head -1) && cd "$REPO"
  ```

- **No pytest or complex multi-tool operations in sandbox.** Sandbox environments lack installed packages. Never escalate CRITICAL based on test failures inside a scheduled task. Use `--collect-only` for import-level checks only — never run full test suites from a scheduled task.

- **Standalone helper scripts must use absolute dynamic path discovery.** Any Python script called by a scheduled task must discover its own repo root at runtime (e.g. via `pathlib.Path(__file__).resolve().parents[N]`). Never hardcode paths inside helper scripts either.

## Founder-output contract — mandatory

Scheduled tasks are workers, not narrators. Their job is to finish work and record evidence internally. They MUST NOT push ordinary engineering progress into Telegram/Margot.

Allowed founder-facing outputs are ONLY:

1. **VERIFIED COMPLETE** — the requested objective is finished and verification evidence exists.
2. **PROTECTED DECISION REQUIRED** — all safe work has already continued and one specific protected action genuinely needs Phill's approval. Include one recommended answer and the minimum evidence needed to decide.
3. **RECOVERY FAILED** — a real system failure remains after the task has already attempted safe diagnosis and remediation. State the single unresolved failure, recovery attempts, and exact next machine action. Do not send a generic blocker list.

Everything else stays internal.

### Explicitly forbidden founder-facing output

Do not send any of the following to Telegram/Margot as a scheduled-task result:

- `Status: YELLOW`, `Status: RED`, or traffic-light progress reports.
- `What changed`, `Evidence`, `Blockers`, `Next action`, `Lessons`, `Lesson learned`, or similar status-report templates for unfinished work.
- Partial diffs, compile checks, lint checks, or "X is wired but Y is still missing" reports when the worker can continue safely.
- A diagnosis followed by a future action the same task could execute now.
- Repeated explanations of an issue Phill has already reported.
- "Please file manually", "please run", or "please continue" when the system has a safe write/repair path available.

### Testing Brain rule

Unfinished findings, suspected defects, ambiguous evidence, regressions, and candidate fixes go to the internal **Testing Brain** lane, not to Phill.

Testing Brain must:

1. reproduce or prove the finding;
2. challenge the diagnosis with an independent check;
3. apply the safest repair available;
4. run the relevant verification again;
5. only promote the result when it is verified complete or genuinely requires protected human authority.

Use a triple-standard evidence bar for promoted findings: **reproduce + independent challenge + post-fix verification**. One passing compile/lint command is not completion evidence for an end-to-end feature.

### Continuation rule

A scheduled task must maintain the current Mission Control objective and look ahead beyond its immediate edit. Finishing one sub-step is not a reason to return control to the founder. Continue dependency-safe work until the objective is verified complete, all remaining useful work is protected, or the kill switch is active.

If a task discovers its own prompt is stale or conflicts with a newer Mission Control/Telegram objective, the newer canonical objective wins and the stale task must retire quietly rather than emitting another progress report.
