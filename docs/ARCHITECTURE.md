# RSS → Intelligence Brief Pipeline — Architecture

**Status:** Implemented (Sprint 12)  
**Owner:** Pi-CEO autonomous system  
**Ticket refs:** Pi-Dev-Ops RA-series

---

## Overview

An n8n automation chain converts RSS feeds from 12+ sources into filtered intelligence briefs,
appended to a shared Google Doc, indexed in NotebookLM, summarised by Qwen 3 14B, and
delivered to Telegram.

No manual steps. No cron-on-Mac. Runs on the n8n Cloud or a Railway-hosted n8n instance.

---

## End-to-End Flow

```
[Schedule Trigger: every 30 min]
        │
        ▼
[Load RSS Sources]          ← config/rss-sources.yaml (baked into RSS_SOURCES_JSON env var)
        │ one item per source
        ▼
[Fetch RSS Feed]            ← n8n rssFeedRead node, continueOnFail=true
        │
        ▼
[Attach Source Metadata]    ← tag each item with feed_id, feed_name, category
        │
        ▼
[Keyword Filter]            ← config/keyword-filters.yaml rules; trusted sources bypass
        │
        ▼
[Any Items Pass Filter?]
   ├─ No  → [No Items — Skip] (log + exit)
   └─ Yes ▼
[Aggregate Items]           ← collect all filtered items into a single array
        │
        ▼
[Get Google Doc]            ← read current end-index via Google Docs API
        │
        ▼
[Build Append Request]      ← format timestamped header + item list as batchUpdate requests
        │
        ▼
[Append to Google Doc]      ← Google Docs batchUpdate; authenticated via service account
        │
        ▼
[Trigger NotebookLM Refresh] ← HTTP POST to /webhook/notebooklm-refresh
        │                       (separate workflow: n8n/workflows/notebooklm-refresh-trigger.json)
        │                       continueOnFail=true — brief proceeds even if NLM fails
        ▼
[Generate Qwen Brief]       ← POST to QWEN_API_URL/chat/completions (OpenAI-compatible)
        │                       model: qwen3:14b, temp: 0.3, max_tokens: 2048
        ▼
[Parse & Validate Brief]    ← strict JSON parse + schema check (date, headline, sections, ...)
        │
        ▼
[Format Telegram Message]   ← Markdown with section headers, item bullets, GDoc link
        │
        ▼
[Send to Telegram]          ← api.telegram.org/bot{TOKEN}/sendMessage
        │
        ▼
[Pipeline Complete]         ← log message_id, set status=delivered
```

---

## Workflow Files

| File | Purpose |
|------|---------|
| `n8n/workflows/rss-to-docs-pipeline.json` | Main pipeline (16 nodes) |
| `n8n/workflows/notebooklm-refresh-trigger.json` | Webhook receiver → NLM API |

Import both into n8n via **Workflows → Import from file**. Activate in order:
1. `notebooklm-refresh-trigger` first (its webhook URL is needed by the main pipeline)
2. `rss-to-docs-pipeline` second

---

## Configuration Files

| File | Contents |
|------|---------|
| `config/rss-sources.yaml` | 12 RSS feed URLs with poll intervals and categories |
| `config/keyword-filters.yaml` | Include/exclude keyword rules with weights; trusted source list |

At deploy time, serialize `rss-sources.yaml` → `RSS_SOURCES_JSON` env var (one-liner in startup):

```bash
python -c "
import yaml, json, sys
data = yaml.safe_load(open('config/rss-sources.yaml'))
print(json.dumps(data['sources']))
" > /tmp/sources.json
# then set RSS_SOURCES_JSON=$(cat /tmp/sources.json) in n8n env
```

---

## Environment Variables

All env vars are read from n8n's **Settings → Environment Variables** or the host environment.

| Variable | Required | Description |
|----------|----------|-------------|
| `RSS_SOURCES_JSON` | Yes | JSON array of source objects (from rss-sources.yaml) |
| `GDOC_INTELLIGENCE_DOC_ID` | Yes | Google Doc ID to append intel items to |
| `GDOC_BRIEF_URL` | Recommended | Full Google Doc URL embedded in Telegram message |
| `N8N_WEBHOOK_BASE_URL` | Yes | Base URL of the n8n instance (e.g. `https://n8n.example.com`) |
| `NOTEBOOKLM_API_URL` | Yes | NotebookLM API base URL |
| `NOTEBOOKLM_API_KEY` | Yes | API bearer token for NotebookLM |
| `NOTEBOOKLM_NOTEBOOK_ID` | Yes | Target notebook ID to refresh |
| `QWEN_API_URL` | Yes | OpenAI-compatible base URL (e.g. `http://qwen-host:8000/v1` or Ollama) |
| `QWEN_API_KEY` | Yes | Bearer token (`ollama` for local) |
| `QWEN_MODEL` | No | Model name, default `qwen3:14b` |
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Target chat / channel ID |

---

## Google Docs Authentication

The pipeline uses a Google **service account** authenticated via n8n's built-in Google Docs node.

Setup:
1. Create a service account in Google Cloud Console with **Google Docs API** enabled.
2. Share the target Google Doc with the service account email (`editor` permission).
3. Download the JSON key and add it to n8n credentials under **Google Docs OAuth2** → service account mode.
4. Set credential name to `Google Service Account` (matches workflow JSON).

---

## Qwen 3 14B Inference

The pipeline calls any OpenAI-compatible endpoint. Recommended options:

| Option | `QWEN_API_URL` | Notes |
|--------|----------------|-------|
| Local Ollama | `http://localhost:11434/v1` | `ollama pull qwen3:14b` |
| vLLM on Railway | `https://qwen.railway.app/v1` | GPU plan required |
| Together.ai | `https://api.together.xyz/v1` | Set `QWEN_MODEL=Qwen/Qwen3-14B-Instruct` |
| OpenRouter | `https://openrouter.ai/api/v1` | `QWEN_MODEL=qwen/qwen-3-14b` |

The standalone script `scripts/generate_brief.py` wraps the same call and supports
`--dry-run` for local testing without a live endpoint.

---

## Standalone Brief Generator

`scripts/generate_brief.py` can run outside n8n for testing or manual runs:

```bash
# Dry run (no Qwen call) — verify JSON schema
echo '[{"title":"Test","link":"https://example.com","feed_name":"Test Feed"}]' \
  | python scripts/generate_brief.py --dry-run

# Real call + Telegram delivery
cat /tmp/filtered_items.json | python scripts/generate_brief.py --deliver

# Write brief to file
python scripts/generate_brief.py --input /tmp/items.json --output /tmp/brief.json
```

---

## Error Handling

| Stage | Failure mode | Recovery |
|-------|-------------|----------|
| RSS fetch | Network error / dead feed | `continueOnFail=true` — other feeds proceed |
| Keyword filter | All items excluded | `No Items — Skip` branch exits cleanly |
| Google Docs append | API error | n8n error workflow fires; pipeline stops |
| NotebookLM refresh | API error | `continueOnFail=true` — brief still generated |
| Qwen call | Timeout (>120 s) | n8n error workflow fires; Telegram not sent |
| Qwen JSON parse | Non-JSON response | `Parse & Validate Brief` throws → error workflow |
| Telegram send | API error | `Pipeline Complete` checks `ok` field and throws |

Configure an n8n **Error Workflow** at workflow settings level to send Telegram alerts
on any unhandled pipeline failure.

---

## Smoke Test

Run the full pipeline against mock inputs without hitting live APIs:

```bash
# 1. Verify generate_brief.py schema
echo '[{"title":"Claude 4 released","link":"https://anthropic.com","feed_name":"Anthropic Blog","feed_id":"anthropic-blog"}]' \
  | python scripts/generate_brief.py --dry-run | python -m json.tool

# 2. Validate n8n workflow JSON syntax
python -c "import json; json.load(open('n8n/workflows/rss-to-docs-pipeline.json')); print('OK')"
python -c "import json; json.load(open('n8n/workflows/notebooklm-refresh-trigger.json')); print('OK')"

# 3. Validate config YAML
python -c "import yaml; yaml.safe_load(open('config/rss-sources.yaml')); print('OK')"
python -c "import yaml; yaml.safe_load(open('config/keyword-filters.yaml')); print('OK')"
```

All four commands must print `OK` or valid JSON before deploying.

---

## Adding RSS Sources

Edit `config/rss-sources.yaml` and re-serialize to `RSS_SOURCES_JSON`.
The workflow reads the env var on every execution — no n8n restart required after env update.

## Adding Keyword Rules

Edit `config/keyword-filters.yaml`. The n8n `Keyword Filter` node embeds the rules inline
(for reliability in sandboxed n8n environments). After editing the YAML, copy the updated
include/exclude arrays into the corresponding Code node in `rss-to-docs-pipeline.json`.
