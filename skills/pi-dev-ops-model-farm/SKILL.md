---
name: pi-dev-ops-model-farm
description: Multi-CLI agent farm orchestrator. Manages Claude Code (3x Max Plan accounts) and OpenAI Codex CLI (1x Max/Plus account) as tmux-based background workers. Receives routing requests from Pi-Dev-Ops /nexus, dispatches tasks, monitors health, and returns structured outputs via JSON-over-file IPC. Enables hybrid Claude+OpenAI execution without API billing.
allowed-tools: Read, Grep, Glob, Bash, Agent, terminal, process, cronjob
---

# Pi-Dev-Ops Model Farm — Claude + OpenAI Hybrid Orchestrator

## Overview

You have paid-tier access to:
- **3 × Claude Code (Max Plan)** — unlimited usage via OAuth
- **1 × OpenAI Codex CLI (ChatGPT/Plus/Max)** — flat-rate access

This skill turns those into a managed worker pool alongside Hermes' native OpenRouter models.

## Architecture

```
                Hermes Session (OpenRouter)
                         |
                         v
                    Pi-Dev-Ops /nexus
                         |
        +----------------+----------------+
        |                |                |
        v                v                v
   [Flagship]    [Claude Farm]   [OpenAI Farm]
   Free models   (3 workers)     (1 worker)
   Kimi, Nemo    Claude OAuth    Codex CLI
   DeepSeek      via tmux        via tmux
        |                |                |
        +----------------+----------------+
                         |
                     Results IPC
                  (JSON-over-file)
```

## Worker Definitions

| Worker | CLI | Auth | Model | Best For | Session File |
|--------|-----|------|-------|----------|--------------|
| `claude-1` | `claude` | Max Plan #1 | `claude-opus-5` | `/judge`, `/boardroom`, `/tao-judge` | `~/.hermes/.farm/claude-1.session` |
| `claude-2` | `claude` | Max Plan #2 | `claude-sonnet-5` | `/storm`, `/cto`, `security-audit` | `~/.hermes/.farm/claude-2.session` |
| `claude-3` | `claude` | Max Plan #3 | `claude-sonnet-5` | `/spm`, `/ceo-mode`, external comms | `~/.hermes/.farm/claude-3.session` |
| `codex-1` | `codex` | ChatGPT | Codex CLI default (see `codex --version`) | Coding agents, file editing, PR reviews | `~/.hermes/.farm/codex-1.session` |

## Farm Operations

### 1. Spin Up Workers

Create a tmux session per worker that passes `--print` to avoid interactive prompts:

```bash
# Claude worker (non-interactive, pipe-ready)
tmux new-session -d -s claude-1 -x 120 -y 40 \
  'claude --print --permission-mode bypassPermissions --model claude-opus-5 "$@"'

# Codex worker
tmux new-session -d -s codex-1 -x 120 -y 40 \
  'codex exec --dangerously-auto-approve "$@"'
```

### 2. Dispatch Task to Worker

Write a JSON envelope to the worker's input pipe:

```json
{
  "task_id": "uuid",
  "invoked_by": "pi-dev-ops/judge",
  "skill": "judge",
  "artefact_path": "D:/Pi-Dev-Ops/repo/src/auth.py",
  "prompt": "Full prompt text with all context",
  "output_format": "json|markdown|structured",
  "token_budget": 16000,
  "timeout_seconds": 300,
  "fallback_to": "claude-2"
}
```

Send via tmux:
```bash
# Write JSON to tmux stdin
echo '{"task_id":"abc","prompt":"..."}' > ~/.hermes/.farm/claude-1.in.json
# Trigger worker read
tmux send-keys -t claude-1 Enter
```

### 3. Collect Results

Worker logs symlink: `~/.hermes/.farm/<worker>.out.json`

```json
{
  "task_id": "abc",
  "completed_at": "2026-07-02T21:00:00Z",
  "status": "success|failure|timeout",
  "output": "...",
  "model_used": "claude-opus-5",
  "duration_seconds": 45,
  "tokens_used": {"prompt": 1200, "completion": 800},
  "tool_calls": 0
}
```

### 4. Health Monitor

Prometheus-style metrics file: `~/.hermes/.farm/metrics.jsonl`

```
{"timestamp":"...","worker":"claude-1","latency_ms":450,"queue_depth":0,"status":"ready"}
{"timestamp":"...","worker":"codex-1","latency_ms":1200,"queue_depth":1,"status":"busy"}
```

Cron job every 60s:
```
cronjob(action="create", schedule="60s", prompt="Read ~/.hermes/.farm/metrics.jsonl. If any worker status != ready for >3 checks, restart via tmux. If total workers ready <2, alert.")
```

### 5. Circuit Breaker & Fallback

| Condition | Action |
|-----------|--------|
| Worker timeout (30s no response) | Retry once, then fallback route |
| 3 consecutive timeouts | Mark worker DOWN, alert, retry on next worker |
| All Claude workers DOWN | Route to OpenRouter paid fallback |
| All workers DOWN | Queue for next session + handoff |

### 6. Cost Accounting

Since Claude Max and Codex are flat-rate, emit usage telemetry for visibility:

```json
{
  "billing_type": "flat_rate",
  "monthly_cost_aud": 85.00,
  "claude_sessions_used": 3,
  "codex_sessions_used": 1,
  "tasks_dispatched": 47,
  "tasks_failed": 2,
  "total_tokens_consumed": {"claude": 120000, "codex": 45000},
  "openrouter_tokens_aved": 165000,
  "est_savings_aud": 35.00
}
```

## Routing Matrix (Pi-Dev-Ops /nexus Integration)

The `/nexus` skill dispatches to the farm via this decision table:

| Skill | Gate Stakes | Default Worker | Fallback |
|-------|-------------|----------------|----------|
| `/judge` | Final approval | `claude-1` (Opus) | `claude-2` → OpenRouter |
| `/boardroom` | Multi-model consensus | `claude-1`, `claude-2`, `codex-1` | Parallel OpenRouter |
| `/tao-judge` | Loop termination | `claude-1` (Opus) | `claude-2` |
| `/storm` | Deep multi-facet audit | `claude-2` (Sonnet) | OpenRouter |
| `/spm` | Spec generation | `claude-3` | OpenRouter |
| `/ceo-mode` | Board/strategic | `claude-3` (Sonnet) | OpenRouter |
| `/cto` | Architecture decisions | `claude-2` | OpenRouter |
| `/security-audit` | Security review | `claude-2` | OpenRouter |
| `/tao-loop` coding | Code generation | `codex-1` (o3) | `claude-2` |
| Root `/tao` | Full autonomous mission | Farm round-robin | — |

## Operational Commands

```bash
# List all farm workers
pi-dev-ops-farm status

# Restart a worker
pi-dev-ops-farm restart claude-1

# Force task to specific worker
pi-dev-ops-farm dispatch --worker claude-1 --task "Review this file" --file src/auth.py

# Scale workers up/down (dynamic range 1-3 per type)
pi-dev-ops-farm scale claude 3
pi-dev-ops-farm scale codex 1

# Emergency drain (finish in-flight, stop accepting new)
pi-dev-ops-farm drain

# Garbage-collect stale sessions
pi-dev-ops-farm gc
```

## File Locations

| File | Path |
|------|------|
| Farm skill | `skills/pi-dev-ops-model-farm/SKILL.md` |
| Farm daemon | `skills/pi-dev-ops-model-farm/scripts/model-farm.py` |
| Farm starter | `skills/pi-dev-ops-model-farm/scripts/init-farm.sh` |
| Farm config | `~/.hermes/.farm/farm-config.json` |
| Task queue | `~/.hermes/.farm/queue.jsonl` |
| Results buffer | `~/.hermes/.farm/<worker>.out-<taskid>.json` |
| Metrics log | `~/.hermes/.farm/metrics.jsonl` |
| Health log | `~/.hermes/.farm/health.jsonl` |

## Initialization Checklist

- [ ] All 3 Claude accounts logged in (`claude auth login` x3)
- [ ] Codex account logged in (`codex login` x1)
- [ ] Python 3.11+ available (`python3 --version`)
- [ ] `claude` CLI on PATH (Winget install)
- [ ] `codex` CLI on PATH (npm install -g @anthropic-ai/codex)
- [ ] Farm directory created (`mkdir -p ~/.hermes/.farm`)
- [ ] Run `python3 model-farm.py --start` to spin workers
- [ ] Test dispatch: write a `.in-*.json` task file and confirm result `.out-*.json` appears
- [ ] Hermes config updated with `model_farm.enabled: true`
- [ ] Cron health monitor set up if needed
## Safety Rules

1. Never run destructive CLI commands (rm, git reset --hard, rm -rf) through claude/codex farm workers without Hermes-level approval.
2. Farm workers are READ-ONLY by default. Edit mode requires explicit `--yolo` or `--dangerously-auto-approve` flag set by Pi-Dev-Ops gate.
3. External-facing outputs from farm workers still get CEO/Board gate before delivery.
4. Credential isolation: farm workers have their own auth (OAuth); they never share API keys with Hermes/OpenRouter.

## References
- Hermes `terminal-orchestrator` skill — tmux session management
- Hermes `hermes-agent` skill — CLI spawning patterns
- Claude Code CLI docs — `claude --print`, permission modes
- OpenAI Codex CLI docs — `codex exec`, `--dangerously-auto-approve`
