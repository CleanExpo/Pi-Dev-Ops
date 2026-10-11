# Health monitor, circuit breaker and cost accounting

Moved verbatim from SKILL.md.

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
