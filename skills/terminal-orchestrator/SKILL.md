---
name: terminal-orchestrator
description: Safely manage long-running tmux-based dev workflows (build, test, watch, log tailing) on the local machine via a constrained command grammar. Use when an agent or operator wants to inspect tmux state, start a known profile, or run an allowlisted command inside a tracked session. NEVER use for production deploys, force-pushes, secret-exfiltrating commands, or anything matching the denylist. Read policy/ before executing.
---

# Terminal Orchestrator (Pi-Dev-Ops local)

## When to invoke

- An agent / operator asks "what's running in tmux?" → `tmux:list`, `tmux:status`
- Need to capture the last N lines from a pane → `tmux:tail`
- Need to bring up a known dev/test/jobs/logs profile → `tmux:start <profile>`
- Need to run an allowlisted command inside a tracked pane → `tmux:run`

## Hard rules (non-negotiable)

1. **Policy files are the source of truth.** Read `policy/denylist.txt`,
   `policy/allowlist.yaml`, `policy/secret_patterns.txt` before any decision.
2. **Validator gates every command.** The Python validator at
   `swarm/tmux_validator.validate_command()` is the only path. Never call
   `tmux send-keys` without a prior `ValidationResult(allowed=True)`.
3. **Pane targeting uses stable `pane_id` (`%N`).** Never address panes by
   `session:window.index`.
4. **Audit ledger is fail-closed.** If `.harness/audit/tmux-YYYY-MM-DD.jsonl`
   cannot be written (missing dir, fsync failure, append-only flag not set),
   the call MUST be refused before any state change.
5. **No production mutation.** Commands matching `policy/denylist.txt`
   production-mutation patterns are blocked at every autonomy level, including
   under explicit operator confirmation.

## Autonomy levels

| Level | Capability |
|---|---|
| L1 | Read-only: `tmux:list`, `tmux:status`, `tmux:tail` |
| L2 | Preview-first run/start of allowlisted profiles + commands |
| L3 | Explicit per-call operator confirmation for `tmux:stop` or commands not on L2 allowlist |

## Validator usage

```python
from swarm.tmux_validator import validate_command, redact_secrets

result = validate_command("pytest -x swarm/intake/")
if not result.allowed:
    # surface result.reason, result.denylist_match to caller
    return result.to_dict()
# only now safe to invoke tmux send-keys
```

## Implementation status

- **T1 (observer)** — not yet implemented (next phase, will land separately)
- **T2 (safe runner)** — gated on T1
- **T3 (self-healing)** — gated on T2 + autonomy-ledger
- **T4 (approval-ledger integration)** — gated on T3

## Provenance

This skill ships only the policy + validator. T1-T4 implementations land in
follow-up PRs gated on operator approval. See `2nd-brain/Sketches/02-tmux-agent.md`
for the fat-marker sketch and grill transcript.
