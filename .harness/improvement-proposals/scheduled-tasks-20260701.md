# Improvement Proposal: Scheduled Tasks

**Generated:** 2026-07-01  
**Source:** lessons.jsonl — 3 entries (3 warnings)  
**Proposed action:** Add a CLAUDE.md section  
**Target:** CLAUDE.md section: `## Scheduled Tasks Guidelines`

## Recurring Lessons (3 occurrences)

- ⚠️ **[marathon-session]** Scheduled-tasks MCP runs inside the desktop Claude session and does NOT inherit the repo .claude/settings.json allowlist. Shrink every scheduled task prompt to a single shell command calling a standalone Python helper — this minimises tool-approval surface to Bash alone, approvable with one Run now click. Never let a scheduled task prompt ask Claude to read files, compose text, and push messages as separate steps — each step is another potential prompt.
- ⚠️ **[marathon-session]** Scheduled-tasks MCP runs each task inside a fresh Cowork sandbox at /sessions/<random-id>/mnt/<folder>. The session ID changes every run, so hardcoding the user's local Mac path in a task prompt will fail on every execution. Always discover the repo dynamically with find /sessions -type d -name <repo> at the top of the task prompt, then cd into it. The heartbeat task proved this by self-recovering on first failure — assistant inside the scheduled task updated its own prompt and sent message ID 31.
- ⚠️ **[sprint-12-review]** Health check scripts that alert on first failure cause false positives from normal service restarts (e.g. n8n Docker container restart takes ~10s). Add a consecutive-failure threshold (2 failures) with a state file that persists between runs. Also add a cooldown period (30 min) between repeated alerts for the same service to prevent alert fatigue. State file path: ~/pi-ceo/logs/health_check_state.json.

## Proposed Content

Add the following section to CLAUDE.md:

```markdown
## Scheduled Tasks Guidelines

- Scheduled-tasks MCP runs inside the desktop Claude session and does NOT inherit the repo .claude/settings.json allowlist. Shrink every scheduled task prompt to a single shell command calling a standalone Python helper — this minimises tool-approval surface to Bash alone, approvable with one Run now click. Never let a scheduled task prompt ask Claude to read files, compose text, and push messages as separate steps — each step is another potential prompt.
- Scheduled-tasks MCP runs each task inside a fresh Cowork sandbox at /sessions/<random-id>/mnt/<folder>. The session ID changes every run, so hardcoding the user's local Mac path in a task prompt will fail on every execution. Always discover the repo dynamically with find /sessions -type d -name <repo> at the top of the task prompt, then cd into it. The heartbeat task proved this by self-recovering on first failure — assistant inside the scheduled task updated its own prompt and sent message ID 31.
- Health check scripts that alert on first failure cause false positives from normal service restarts (e.g. n8n Docker container restart takes ~10s). Add a consecutive-failure threshold (2 failures) with a state file that persists between runs. Also add a cooldown period (30 min) between repeated alerts for the same service to prevent alert fatigue. State file path: ~/pi-ceo/logs/health_check_state.json.
```

## Review Required

This proposal was auto-generated. A human must review and apply it.
Close this Linear ticket when applied or explicitly rejected.