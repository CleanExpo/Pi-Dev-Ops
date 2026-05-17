---
name: curator-scheduled-tasks-unknown
description: Operational rules for authoring and debugging scheduled tasks that run via the Claude scheduled-tasks MCP. Covers the three hardwired lessons — session isolation, dynamic path discovery, and health-check grace periods — that repeatedly caused silent failures or false-positive alerts across the Pi-CEO portfolio.
owner_role: Curator
status: proposed
---

# curator-scheduled-tasks-unknown

Distillation of three recurring pipeline failures in the `scheduled-tasks` category. Each rule maps to a production incident. Follow them before writing a new scheduled task prompt or debugging a broken one.

## Why this exists

Three lessons appeared independently across two sprint reviews and a marathon session:

1. Scheduled-tasks MCP inherits the **desktop Claude session**, not the repo's `.claude/settings.json`. Every tool call that is not pre-approved at the desktop level blocks silently.
2. Each task fires inside a **fresh Cowork sandbox** with a new random session ID. Any hardcoded local path breaks on every run.
3. Health-check scripts that alert on the **first failure** trigger false positives during normal service restarts. Transient blips are indistinguishable from real outages without a grace window.

The existing `skills/scheduled-tasks/SKILL.md` covers rule 1 and 2 at a high level. This skill adds the health-check lesson, tightens the runnable checklists, and provides explicit verification steps for all three.

## When to use

- Writing a new scheduled task prompt for the Claude scheduled-tasks MCP.
- Debugging a task that silently does nothing (rule 1), crashes with a path error (rule 2), or pages repeatedly on service boot (rule 3).
- Reviewing a PR that adds or modifies a task prompt or a helper script called by a task.

## When NOT to use

- Tasks run via GitHub Actions, Railway cron, or `asyncio.sleep` poller loops — those DO inherit their environment and can use absolute paths safely.
- One-shot scripts invoked manually from the terminal — path and permission rules are different.
- Non-Python helpers (Node, shell-only) — dynamic path discovery differs; adapt the pattern rather than copying verbatim.

## Pipeline

### Rule 1 — Minimise tool-approval surface

Scheduled tasks run inside the desktop Claude session. That session does NOT load the repo `.claude/settings.json` allowlist. Any tool not pre-approved at the desktop level will block and produce no output.

Checklist before shipping a task prompt:
- Reduce the prompt to a single `Bash` command that calls a standalone helper script.
- The helper script does all real work — file reads, API calls, git commands.
- Bash is the only tool that needs desktop approval. One click unblocks the task.
- Never embed multi-step tool sequences (Read + Edit + Bash) directly in the task prompt.

Verification: run the task from the Claude desktop scheduled-tasks panel. If Claude asks for tool permission mid-run, collapse the prompt further.

### Rule 2 — Dynamic path discovery, no hardcoded paths

Each task fires inside `/sessions/<random-id>/mnt/<folder>` — a fresh sandbox on every run. Paths that worked on the previous run no longer exist.

Required pattern at the top of every helper script:

```python
import subprocess, pathlib

def find_repo(name: str) -> pathlib.Path:
    result = subprocess.run(
        ["find", "/sessions", "-type", "d", "-name", name],
        capture_output=True, text=True, timeout=10,
    )
    hits = [p for p in result.stdout.strip().splitlines() if p]
    if not hits:
        raise RuntimeError(f"Repo directory '{name}' not found under /sessions")
    return pathlib.Path(hits[0])
```

And inside any Python helper script that lives inside the repo:

```python
REPO_ROOT = pathlib.Path(__file__).resolve()
while not (REPO_ROOT / ".git").exists():
    REPO_ROOT = REPO_ROOT.parent
    if REPO_ROOT == REPO_ROOT.parent:
        raise RuntimeError("Could not locate repo root")
```

Never pass paths as hard-coded strings to subprocess calls, open(), or importlib.

Verification: delete the session sandbox directory and re-run the task. The helper must find the repo and complete without a `FileNotFoundError`.

### Rule 3 — Health-check grace periods prevent false-positive alerts

Scripts that probe a service and alert immediately on the first failed probe send false alerts during normal Railway or Vercel cold starts, deploys, and OS-level TCP resets. The service is not broken — it is restarting.

Required pattern for any health-check helper:

```python
import time, httpx

MAX_ATTEMPTS = 3
RETRY_DELAY_S = 15

def probe(url: str, password: str) -> bool:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = httpx.post(url, json={"password": password}, timeout=10)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_DELAY_S)
    return False
```

Rules:
- Minimum 3 probes with at least 15 s between attempts before raising an alert.
- Log each failed attempt with attempt number and error class — never swallow failures silently.
- Escalate (Telegram / Linear ticket) only after all probes fail.
- Do not treat HTTP 5xx as permanent until the grace window is exhausted.

Verification: take down the target service, run the health check, confirm it waits through all retry attempts before alerting. Restart the service mid-retry and confirm it exits green.

## Verification (end-to-end)

1. Create a new scheduled task prompt containing only:
   `python /path-discovery-via-find/scripts/smoke_check.py`
2. Confirm the task panel shows only a `Bash` tool request — no `Read`, `Edit`, or file-picker prompts.
3. In `smoke_check.py`, print the resolved repo root. Run the task. Confirm the path resolves correctly without hardcoded segments.
4. Temporarily stop the backend. Run a health-check task. Confirm it retries 3 times, then fires a single Telegram alert — not one alert per probe.
5. Restart the backend between probe 1 and probe 2. Confirm the task exits green without alerting.

## References

- Lesson source: `.harness/lessons.jsonl` rows ts `2026-04-11T23:00:01Z`, `2026-04-11T23:15:00Z`, `2026-04-16T06:00:04Z`
- Related skill: `skills/scheduled-tasks/SKILL.md` (higher-level companion; this skill extends it)
- Surface-treatment prohibition: RA-1109 (silent success = broken feature; applies to scheduled-task output too)
- Railway cold-start pattern: `CLAUDE.md` section "Do-while pattern" — startup catch-up for overdue crons
