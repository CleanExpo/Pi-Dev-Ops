---
name: empire-status
description: "Instant empire status snapshot. Queries Pi-CEO, Supabase, Linear, and Hermes to produce a 30-second executive briefing on the state of all 6 businesses. Use anytime to get a pulse check. Model: llama-3.3-70b (free — routine query)."
allowed-tools: Bash, WebFetch
model: meta-llama/llama-3.3-70b-instruct
---

# Empire Status — 30-Second Pulse Check

Run these three calls in parallel and produce a formatted status report.

## Call 1: Pi-CEO health
```bash
PI_TOKEN=$(grep PI_CEO_API_KEY /tmp/ug-dev.local 2>/dev/null || grep PI_CEO_API_KEY ~/.hermes/.env | cut -d= -f2- | tr -d '"')
curl -s -X POST "https://pi-dev-ops-production.up.railway.app/api/login" \
  -H "Content-Type: application/json" -d "{\"password\":\"$PI_TOKEN\"}" -c /tmp/es.txt
HEALTH=$(curl -s https://pi-dev-ops-production.up.railway.app/api/projects/health -b /tmp/es.txt)
AUTONOMY=$(curl -s https://pi-dev-ops-production.up.railway.app/api/autonomy/status -b /tmp/es.txt)
echo "HEALTH=$HEALTH"
echo "AUTONOMY=$AUTONOMY"
```

## Call 2: Linear open tickets
Count open [Pi-CEO AUTO] tickets, in-progress tickets, and done in last 24h.

## Call 3: Hermes cron status
```bash
cd ~/.hermes/hermes-agent && .venv/bin/python3 -c "
from cron.jobs import list_jobs
import sys; sys.path.insert(0,'.')
jobs = list_jobs()
ok = sum(1 for j in jobs if j.get('last_status')=='ok')
err = sum(1 for j in jobs if j.get('last_status')=='error')
total = len(jobs)
print(f'CRONS: {ok}/{total} ok, {err} errors')
" 2>/dev/null
```

## Output format:
```
EMPIRE STATUS — [HH:MM AEST]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Pi-CEO:    [N] polls · [autonomy]% autonomy · [last_poll]s ago
Crons:     [N]/[total] healthy
Linear:    [open] open · [in-progress] running · [done_24h] done today
ARR:       $[total_arr]/yr

BUSINESSES:
[name] [health]/100  [status]
...

ALERTS: [list any score <50 or errors]
```
