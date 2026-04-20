# RA-826 — Google Workspace Update Monitor: Import Instructions

Two workflows to import. Import and configure the RSS monitor first; the weekly brief
depends on data it produces.

---

## Pre-requisites

### 1. Google Doc — "Pi-CEO Workspace Intel"

Create a Google Doc for the running log of filtered workspace updates:

1. Go to docs.google.com → New blank document
2. Name it: `Pi-CEO Workspace Intel`
3. Add a heading on line 1: `# Pi-CEO Workspace Intel`
4. Share it with the Google account you will use for n8n OAuth
5. Copy the Doc ID from the URL: `https://docs.google.com/document/d/**DOC_ID_HERE**/edit`

### 2. Google Docs OAuth credentials in n8n

1. n8n → Settings → Credentials → Add Credential → **Google Docs OAuth2 API**
2. Authenticate with the same Google account that owns the doc above
3. Name the credential: `Google Docs (Pi-CEO)`
4. After saving, open the credential record and copy the credential ID (shown in the URL)
5. Update the `Append to Google Doc` node in the RSS monitor workflow: set `credentials.googleDocsOAuth2Api.id` to that ID

### 3. NotebookLM — Pi-CEO Intel notebook

1. Open [notebooklm.google.com](https://notebooklm.google.com) and create a notebook named `Pi-CEO Intel`
2. Add source → Google Drive → select `Pi-CEO Workspace Intel`
3. After each n8n workflow run, open the notebook and click **Sync** on the Google Doc source
   — NotebookLM has no public API for programmatic refresh; this step is manual

### 4. Ollama with Qwen 3 14B (for weekly brief only)

```bash
ollama pull qwen3:14b   # one-time download (~8 GB)
ollama serve            # ensure Ollama is running before Sunday 09:00 UTC
```

---

## Environment Variables

Set in n8n → Settings → Variables:

| Variable | Value | Required by |
|---|---|---|
| `PI_CEO_RAILWAY_URL` | `https://pi-ceo-production.up.railway.app` | Both workflows |
| `PI_CEO_WEBHOOK_SECRET` | Value of `TAO_WEBHOOK_SECRET` from Railway env | Both workflows |
| `WORKSPACE_INTEL_DOC_ID` | Google Doc ID from step 1 above | RSS monitor |
| `TELEGRAM_BOT_TOKEN` | Bot token for `@piceoagent_bot` | Weekly brief |
| `TELEGRAM_CHAT_ID` | Chat ID for brief delivery (Phill: `8792816988`) | Weekly brief |
| `OLLAMA_BASE_URL` | `http://localhost:11434` (or Ollama host if remote) | Weekly brief |
| `OLLAMA_BRIEF_MODEL` | `qwen3:14b` | Weekly brief |

---

## Import Steps — Workflow 1: RSS Monitor

1. n8n → Workflows → **+** (New) → ⋮ → **Import from file**
2. Select: `.harness/n8n-workflows/RA-826-workspace-rss-monitor.json`
3. Save as: `RA-826 — Google Workspace Update Monitor`
4. Open the `Append to Google Doc` node → update credential ID (from step 2 of pre-requisites)
5. Toggle **Activate** (top right)

The workflow polls `https://workspaceupdates.googleblog.com/feeds/posts/default` every 6 hours.
Filtered entries (keywords: Gemini, MCP, agent, NotebookLM, automation, AI features) are:
- Appended to the Pi-CEO Workspace Intel Google Doc
- POSTed to `$PI_CEO_RAILWAY_URL/api/webhook/workspace-intel-refresh` for backend storage

## Import Steps — Workflow 2: Weekly Brief

1. n8n → Workflows → **+** (New) → ⋮ → **Import from file**
2. Select: `.harness/n8n-workflows/RA-826-workspace-weekly-brief.json`
3. Save as: `RA-826 — Weekly Workspace Update Brief`
4. Toggle **Activate**

Fires every Sunday at 09:00 UTC (7 PM AEST). Fetches the past week's stored intel from
`$PI_CEO_RAILWAY_URL/api/workspace-intel`, generates a brief via Qwen 3 14B, and sends
it to Telegram.

---

## Verify the RSS Monitor Is Working

1. Open the workflow → click **Execute Workflow** (manual test run)
2. Check the `Filter Keywords` node output — it should show matched entry count or `matched: false`
3. If matches found, check:
   - The Pi-CEO Workspace Intel Google Doc has a new `## YYYY-MM-DD — N update(s)` section
   - Railway logs show: `RA-826 workspace intel stored: date=... count=... source=n8n:workspace-rss-monitor`
4. If no matches: the RSS feed has no recent posts matching the keyword list — this is normal; wait for the next poll cycle or check `workspaceupdates.googleblog.com` for recent posts

## Verify the Weekly Brief Is Working

1. Run the RSS monitor workflow at least once first (so intel data exists)
2. Open the weekly brief workflow → click **Execute Workflow**
3. Check `Generate Brief (Qwen 3 14B)` node output — should contain the Qwen response
4. Check Telegram — brief should appear in `@piceoagent_bot` chat within seconds
5. If Ollama times out: ensure `qwen3:14b` is pulled and Ollama is running; increase node timeout if needed

---

## Architecture

```
workspaceupdates.googleblog.com (Atom/RSS)
  ↓ n8n RSS trigger (every 6 hours)
  ↓ Filter: keywords (Gemini, MCP, agent, NotebookLM, automation, AI features)
  ↓ n8n: append filtered updates to "Pi-CEO Workspace Intel" Google Doc
  ↓ n8n: POST /api/webhook/workspace-intel-refresh → Railway (JSONL storage)
        [manual] ↓ NotebookLM: Sync Google Doc source in Pi-CEO Intel notebook
  ↓ n8n weekly trigger (Sunday 09:00 UTC)
  ↓ GET /api/workspace-intel → fetch last 30 batches
  ↓ Qwen 3 14B (Ollama): generate executive brief (≤400 words, 3–5 bullets)
  ↓ Telegram: post brief to @piceoagent_bot
```

## Backend Endpoints

Both workflows communicate with the Pi-CEO Railway backend:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/webhook/workspace-intel-refresh` | POST | Receive filtered batch from n8n; store to `.harness/workspace-intel/YYYY-MM-DD.jsonl` |
| `/api/workspace-intel?limit=30` | GET | Return recent batches (newest-first) for the weekly brief |

Both endpoints require `X-Pi-CEO-Secret: $TAO_WEBHOOK_SECRET` header.
