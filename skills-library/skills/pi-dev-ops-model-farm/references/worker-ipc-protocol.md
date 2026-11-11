# Model Farm: spin up, dispatch and collect

Moved from SKILL.md (Farm Operations 1-3).

### 1. Spin Up Workers

Create a tmux session per worker that passes `--print` to avoid interactive prompts:

```bash
# Claude worker (non-interactive, pipe-ready)
tmux new-session -d -s claude-1 -x 120 -y 40 \
  'claude --print --permission-mode bypassPermissions --model claude-opus-5-5 "$@"'

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
  "model_used": "claude-opus-5-5",
  "duration_seconds": 45,
  "tokens_used": {"prompt": 1200, "completion": 800},
  "tool_calls": 0
}
```
