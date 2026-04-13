# 05 — Running the Full System

Everything you need to go from zero to a running Pi-CEO instance.

---

## Prerequisites

| Requirement | Min version | Notes |
|-------------|------------|-------|
| Python | 3.11+ | `python3 --version` |
| Node.js | 18+ | For the dashboard and MCP server |
| claude CLI | Latest | `claude --version`; install from Claude Code |
| git | Any | Must be on PATH |

---

## Environment variables

Copy `.env.example` to `.env.local`. Required vars:

```bash
# Authentication
TAO_PASSWORD=your-strong-password         # Dashboard login password

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...              # Required for Agent SDK mode

# Linear (optional — enables two-way sync)
LINEAR_API_KEY=lin_api_...

# Supabase (optional — enables gate_check logging)
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# Telegram (optional — enables build alerts)
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_ALERT_CHAT_ID=8792816988

# Pipeline tuning (all optional — defaults shown)
TAO_EVALUATOR_THRESHOLD=8
TAO_EVALUATOR_MAX_RETRIES=2
TAO_EVALUATOR_MODEL=sonnet
TAO_USE_AGENT_SDK=1                       # Always 1 in production
TAO_AUTONOMY_BUDGET=0                     # 0 = use per-request budget_minutes
```

---

## Start the backend

```bash
cd /path/to/Pi-Dev-Ops

# Install Python deps
pip install -r requirements.txt

# Start server (dev)
cd app && uvicorn server.main:app --host 127.0.0.1 --port 7777 --reload
```

The server logs structured JSON. On first start you should see:
```json
{"level":"INFO","logger":"pi-ceo.config","msg":"Password hash generated from TAO_PASSWORD..."}
{"level":"INFO","logger":"pi-ceo.main","msg":"Pi CEO server starting on 127.0.0.1:7777"}
```

---

## Start the dashboard

```bash
cd dashboard
npm install
npm run dev   # → http://localhost:3000
```

Log in with the password you set in `TAO_PASSWORD`.

---

## Your first build

**Via the dashboard:** paste a GitHub repo URL and a brief, click Build.

**Via the API:**

```bash
curl -s -X POST http://127.0.0.1:7777/api/build \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(cat .session-token)" \
  -d '{
    "repo_url": "https://github.com/your-org/your-repo",
    "brief": "add a health check endpoint at /health that returns {ok: true}",
    "model": "sonnet"
  }'

# → {"session_id": "abc123", "status": "created"}
```

Poll status:
```bash
curl http://127.0.0.1:7777/api/sessions/abc123
```

---

## Reading session output

Each build produces an SSE stream. The dashboard consumes it automatically.
Key event types in the output:

| Event type | Meaning |
|------------|---------|
| `phase` | A workflow phase started (e.g. `[3/5] Generate`) |
| `system` | Pipeline metadata (intent, tier, score) |
| `output` | Raw generator output from Claude |
| `eval` | Evaluator score + dimension breakdown |
| `success` | Build complete |
| `error` | Build failed with reason |

---

## Running the standalone demo

No server required. Exercises the full core chain against a temp git repo:

```bash
# Default demo (creates temp workspace)
python scripts/pi_essentials.py "add a hello-world function to main.py"

# Against your own repo
python scripts/pi_essentials.py "fix the broken test in test_auth.py" /path/to/your/repo
```

Expected output:
```
🚀 Ship Chain — intent=FEATURE model=sonnet threshold=8.0/10
   Brief: add a hello-world function to main.py

[BUILD] Attempt 1/3
  ...

[EVAL]  Scoring...
  Score: 8.7/10 (threshold: 8.0/10)

✅ PASS — 8.7/10 — build shipped
Result: {'score': 8.7, 'status': 'passed', 'attempts': 1, 'duration_s': 47.3}
```

---

## Smoke test (against prod)

```bash
python scripts/smoke_test.py --url https://your-railway-url.railway.app \
  --password "$TAO_PROD_PASSWORD"
```

This test is also run automatically in CI after every push to main (via
`.github/workflows/ci.yml` job `smoke-prod`).

---

## Key files to know

```
app/server/
  config.py      — all env var defaults, password hash, session secret
  sessions.py    — the full async pipeline (run_build, create_session)
  brief.py       — classify_intent, build_structured_brief, complexity tiers
  budget.py      — AUTONOMY_BUDGET interpolation table
  core/          — importable Ship Chain primitives
  advanced/      — Sprint 9 enhancement layer

.harness/
  config.yaml                 — runtime thresholds + budget anchors
  lessons.jsonl               — accumulated build lessons
  intent/RESEARCH_INTENT.md   — strategic steering (edit to change priorities)
  intent/ENGINEERING_CONSTRAINTS.md
  intent/EVALUATION_CRITERIA.md
  plan-discoveries/           — plan variation logs

scripts/
  pi_essentials.py  — standalone 268-line Ship Chain reference
  smoke_test.py     — prod smoke test
  sdk_metrics.py    — analyse .harness/agent-sdk-metrics/
```

---

*End of Ship Chain Educational Series.*  
*To continue: read `app/server/sessions.py` — it is the source of truth for how all layers connect.*
