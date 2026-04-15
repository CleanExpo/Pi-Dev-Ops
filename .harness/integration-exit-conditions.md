# Integration Exit Conditions

**Ratified:** Board Cycle 25 — 14 April 2026  
**Mandated by:** Contrarian board member  
**Principle:** Define exit thresholds BEFORE production use. Know when to abandon, not after sunk cost.

---

## notebooklm-mcp-cli Exit Conditions

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Tool breakage (auth / browser timeout) | 3 failures in 30 days | Evaluate direct REST API (`notebooklm.googleapis.com`) |
| Query quality degradation | Avg score drops below 6/10 across 10 consecutive queries | Evaluate Gemini Enterprise API (RA-830) |
| Session cost exceeds budget | >$50/month attributed to MCP overhead | Switch to batch REST API calls |
| Maintenance burden | >2 hours/week keeping browser session alive | Abandon MCP, move to REST |

**Current status:** Phase 1 (monitored experiment). Exit evaluation triggered at first threshold breach.

---

## Gemini Scheduled Actions Exit Conditions

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Missed schedule executions | 2+ misses in 30 days | Replace with pure n8n CRON jobs |
| Execution latency | Consistent >5 min delay from scheduled time | Replace with n8n CRON |
| Cost | >$30/month for scheduled action compute | Evaluate n8n self-hosted alternative |
| Reliability | 3 consecutive failures with no Gemini support resolution | Full n8n migration |

---

## n8n Self-Hosted Exit Conditions

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Docker container instability | >3 unplanned restarts/week | Migrate to n8n Cloud |
| Workflow execution failures | >10% failure rate on core workflows | Review workflow design or upgrade n8n |
| Storage exhaustion | Disk usage >80% on host machine | Archive old executions or expand volume |

---

## Monitoring Alerts (Telegram → `@piceoagent_bot`)

Each threshold triggers an alert via the existing `_telegram_alert()` in `cron.py`:

- **notebooklm auth failure** → alert immediately on failure 1, escalate on failure 3
- **Gemini scheduled miss** → alert on first miss, escalate if second miss within 30 days
- **n8n container restart** → alert on restart, escalate at restart 3

Alert format:
```
⚠️ EXIT CONDITION WARNING
Integration: notebooklm-mcp-cli
Trigger: Auth failure #2 of 3
Threshold: 3 failures in 30 days → REST API evaluation
Action: Review .harness/integration-exit-conditions.md
```

---

## Review Schedule

- Reviewed at every board meeting (monthly)
- Thresholds may be adjusted by board vote only
- Next review: Enhancement Review Board — 6 May 2026 (RA-949)
