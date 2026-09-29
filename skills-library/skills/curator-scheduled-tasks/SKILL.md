---
name: curator-scheduled-tasks
description: Use when authoring, debugging, or reviewing scheduled tasks that run via the Claude Code scheduled-tasks MCP — covers sandbox isolation, settings inheritance gaps, health-check false-positive avoidance, and repo discovery inside Cowork mounts.
owner_role: pi-ceo-operator
status: active
---

# Scheduled Tasks — Isolation, Inheritance, and Health-Check Hygiene

## Why this exists

Three hard-won lessons from marathon sessions exposed a cluster of silent failure modes specific to scheduled tasks running under the Claude Code MCP harness:

1. The scheduled-tasks MCP shares the desktop Claude session but does NOT inherit the project `.claude/settings.json`. Permissions and tool allowlists defined at project level are invisible to the task runner.
2. Every task executes inside a fresh Cowork sandbox mounted at `/sessions/<random-id>/mnt/<folder>`. The repo path changes on every run — hard-coded paths break silently.
3. Health-check scripts that alert on the first failure produce false positives from normal service restarts. The symptom is a flood of alerts that train humans to ignore them.

## When to use

- Authoring a new scheduled task or cron routine in Claude Code.
- Debugging a task that passes locally but fails silently under the MCP harness.
- Reviewing a PR that adds or modifies a file under `scripts/`, `.claude/`, or any routine file consumed by the scheduler.
- Investigating "alert fatigue" from a health or uptime check.
- Any task that reads a repo path at runtime rather than compile time.

## When NOT to use

- Tasks running directly in GitHub Actions — Actions inherit env and paths explicitly; this skill does not apply.
- Railway cron jobs or Vercel cron functions — those environments are fully configured at deploy time.
- One-off `claude -p` invocations in a terminal session — no Cowork sandbox is involved.

## Pipeline

### 1. Discover the repo dynamically

Never hard-code the workspace path. The Cowork sandbox mounts at a non-deterministic UUID path.

```bash
REPO_DIR=$(find /sessions -type d -name <repo-name> 2>/dev/null | head -1)
if [ -z "$REPO_DIR" ]; then
  echo "ERROR: repo not found in /sessions" >&2
  exit 1
fi
```

Run every subsequent command relative to `$REPO_DIR`, not to an assumed path like `/home/user/<repo>`.

### 2. Keep tasks to single shell commands calling standalone helpers

The scheduled-tasks MCP does not load `.claude/settings.json`. Avoid constructs that rely on:
- Project-level tool allowlists
- `CLAUDE.md` behavioral overrides
- Custom MCP server registrations that are only declared in the desktop session

A task that needs Python logic should call a self-contained script:

```bash
python /abs/path/to/script.py --flag value
```

Not an inline `claude -p "..."` that expects project permissions to be present.

### 3. Never escalate CRITICAL from a Cowork sandbox

`ModuleNotFoundError`, missing env vars, and import failures inside a Cowork sandbox are environment issues, not production incidents. Log the failure, exit non-zero, and let the harness record it. Real signal comes from GitHub Actions, not sandbox stderr.

### 4. Write health checks with a consecutive-failure gate

A single failed probe can reflect a normal restart, a cold-start delay, or a transient network hiccup. Alert only after N consecutive failures.

```python
import json, pathlib, time, sys

STATE_FILE = pathlib.Path("/tmp/health_state.json")
ALERT_THRESHOLD = 3  # alert after this many consecutive failures

state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"failures": 0}

ok = probe_endpoint()  # returns True/False

if ok:
    state["failures"] = 0
else:
    state["failures"] += 1

STATE_FILE.write_text(json.dumps(state))

if not ok and state["failures"] >= ALERT_THRESHOLD:
    send_alert(f"Service down for {state['failures']} consecutive checks")
    sys.exit(1)
```

Keep `STATE_FILE` outside the Cowork mount — the mount is destroyed at task end.

### 5. Provide explicit permission grants for any autonomous harness

Three layers are required for fully headless execution:
- `.claude/settings.json` — `permissions.defaultMode: bypassPermissions`
- `ClaudeAgentOptions(permission_mode='bypassPermissions')` at every SDK call site
- `--dangerously-skip-permissions` on any subprocess `claude -p` invocation

Missing any single layer causes a silent stall. There is no error; the task simply produces no output.

### 6. Handle cron trigger reset on redeploy

`cron-triggers.json` `last_fired_at` reverts to the git-committed value on every redeploy. Use `abs(now - last_fired)` in the debounce check and fire any overdue trigger within 10 seconds of boot. Log every skipped poll so silent non-execution is visible.

## Verification

After authoring or modifying a scheduled task, confirm all of the following before marking the ticket done:

- [ ] Repo path is discovered dynamically via `find /sessions`; no hard-coded absolute paths.
- [ ] Task body is a single shell command invoking a standalone script — no inline `claude -p` that assumes project permissions.
- [ ] Health check accumulates a consecutive-failure counter stored outside `/sessions/`.
- [ ] Alert threshold is at least 2 consecutive failures (3 recommended).
- [ ] Autonomous harness tasks have all three permission layers present.
- [ ] `cron-triggers.json` debounce uses `abs()` and fires overdue triggers at boot.
- [ ] A test run of the task under the MCP harness (not just locally) produces the expected stdout/exit code.
- [ ] Any `ModuleNotFoundError` in sandbox output is classified as environment noise, not a production alert.
