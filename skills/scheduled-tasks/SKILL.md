---
name: scheduled-tasks
description: Guidelines for writing reliable scheduled task prompts via the Claude scheduled-tasks MCP.
---

# Scheduled Tasks

## When to apply

Apply these rules whenever writing or editing a scheduled task prompt that runs via the Claude scheduled-tasks MCP (desktop Claude session).

## Rules

- **Minimise tool-approval surface.** Scheduled tasks run inside the desktop Claude session and do NOT inherit the repo `.claude/settings.json` allowlist. Shrink every scheduled task prompt to a single shell command that calls a standalone Python helper script. This reduces the required tool approvals to Bash alone, which is approvable with one "Run now" click.

- **Never hardcode local Mac paths.** Scheduled tasks execute inside a fresh sandbox with a new session ID on every run. Hardcoded paths (e.g. `/Users/phill-mac/...`) will fail. Always discover the repo dynamically at the top of the task prompt:
  ```
  REPO=$(find /sessions -type d -name <repo-name> | head -1) && cd "$REPO"
  ```

- **No pytest or complex multi-tool operations in sandbox.** Sandbox environments lack installed packages. Never escalate CRITICAL based on test failures inside a scheduled task. Use `--collect-only` for import-level checks only — never run full test suites from a scheduled task.

- **Standalone helper scripts must use absolute dynamic path discovery.** Any Python script called by a scheduled task must discover its own repo root at runtime (e.g. via `pathlib.Path(__file__).resolve().parents[N]`). Never hardcode paths inside helper scripts either.
