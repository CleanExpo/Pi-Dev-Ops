# Pi Dev Ops — CLAUDE.md

## Project Overview

Pi Dev Ops is a **split-screen AI DevOps companion** for non-technical CEOs. It sits beside Claude Desktop CLI:
- **Left pane:** Claude Desktop CLI — writing code, running analysis
- **Right pane:** Pi Dev Ops — orchestrating sessions, tracking progress, pushing to Linear

The core problem it solves: AI tools get you to ~90% of a working product. Pi Dev Ops bridges the final 10% — persistence, deployment, structured output, Linear integration — operating at a "senior engineering team" level.

**Architecture:** FastAPI Python backend (`app/server/`) + Next.js Vercel dashboard (`dashboard/`) + vanilla JS static frontend (`app/static/`).

---

## Repository Structure

```
C:\Pi Dev Ops\
├── app/
│   ├── server/
│   │   ├── main.py          # FastAPI app — all routes + WebSocket
│   │   ├── sessions.py      # Build session lifecycle (5-phase pipeline)
│   │   ├── auth.py          # HMAC session tokens + rate-limit
│   │   ├── config.py        # All env-var config with defaults
│   │   ├── persistence.py   # Session JSON file persistence (atomic writes)
│   │   ├── gc.py            # Workspace garbage collection
│   │   └── lessons.py       # .harness/lessons.jsonl read/append
│   ├── static/
│   │   └── index.html       # Vanilla JS frontend (dark theme, WebSocket terminal)
│   └── workspaces/          # Cloned repos (temp, gitignored)
├── dashboard/               # Next.js app — deployed on Vercel
│   ├── app/(main)/dashboard/page.tsx   # Main analysis UI (two-column layout)
│   ├── lib/claude.ts        # Claude client: CLI mode (Max plan) or SDK mode (API key)
│   ├── hooks/useSSE.ts      # SSE hook for streaming
│   └── components/          # Terminal, PhaseTracker, ResultCards, ActionsPanel
├── .harness/
│   ├── config.yaml          # TAO agent config (planner/generator/evaluator)
│   ├── lessons.jsonl        # Institutional memory (append-only JSONL)
│   └── spec.md              # Generated analysis output
├── src/tao/                 # TAO engine schemas (dataclasses — not used by web server)
├── mcp/pi-ceo-server.js     # MCP server — Claude Desktop <-> Pi CEO via stdio JSON-RPC
└── CLAUDE.md                # This file
```

---

## Development Environment Setup

### Python Backend (FastAPI)

```bash
# From repo root
pip install -r requirements.txt

# Run development server (port 7777)
python -m uvicorn app.server.main:app --host 127.0.0.1 --port 7777 --reload
```

**Required env vars** (set in `.env` or shell):
```
TAO_PASSWORD=your-password          # Login password (auto-generates if unset)
TAO_SESSION_SECRET=hex-string       # HMAC secret (auto-generates if unset)
TAO_WORKSPACE=app/workspaces        # Where repos are cloned
TAO_LOGS=app/logs                   # Session JSON persistence directory
TAO_MAX_SESSIONS=3                  # Max concurrent build sessions
TAO_RATE_LIMIT=30                   # Requests per minute per IP
TAO_GC_MAX_AGE=14400                # Seconds before completed workspaces are GC'd (4h)
TAO_ALLOWED_ORIGINS=https://...     # Extra CORS origins (comma-separated)
```

### Next.js Dashboard

```bash
cd dashboard
npm install
npm run dev   # http://localhost:3000
```

**Dashboard env vars** (in `dashboard/.env.local`):
```
ANTHROPIC_API_KEY=sk-ant-...        # If set, uses SDK mode (Vercel-compatible)
                                    # If absent, uses CLI mode (claude -p subprocess)
NEXT_PUBLIC_API_URL=http://localhost:7777  # FastAPI backend URL
```

### Windows Notes

- Shell: Use bash syntax throughout (WSL or Git Bash)
- Claude Code CLI: `claude` must be in PATH
- Python subprocess: `asyncio.create_subprocess_exec` is used throughout — avoid `shell=True`

---

## Key Files — What They Do

### `app/server/sessions.py`
The heart of the system. `run_build()` is a 5-phase async pipeline:
1. **Clone** — `git clone --depth 1` into `app/workspaces/{session_id}/`
2. **Analyze** — list workspace files
3. **Check Claude** — `claude --version` to confirm CLI is present
4. **Run Claude** — `claude -p {spec} --model {model} --verbose --output-format stream-json`; parses JSONL events and streams to WebSocket
5. **Push** — `git add -A && git commit && git push origin HEAD`

`parse_event()` handles stream-json output from Claude Code: `system`, `assistant` (text + tool_use), `tool_result`, `result` event types.

`_sessions = {}` — in-memory dict. `persistence.py` saves/restores this across restarts.

### `app/server/auth.py`
- `create_session_token()` — JSON payload + HMAC-SHA256 signature (`{payload}.{sig}`)
- `verify_session_token()` — timing-safe comparison + expiry check
- `_req_log = {}` — per-IP timestamp lists; GC runs every 5 minutes inline in `check_rate_limit()`
- Auth accepted via cookie (`tao_session`) OR `Authorization: Bearer {token}` header

### `app/server/persistence.py`
Atomic JSON file writes: write to `{LOG_DIR}/sessions/{sid}.json.tmp` then `os.replace()` to final path. Prevents corrupt files on crash. Session IDs are sanitised (alphanumeric only) before use in file paths.

### `app/server/gc.py`
Removes completed/failed/killed workspaces older than `GC_MAX_AGE`. Scans for orphan dirs (present on disk but not in `_sessions`). Runs every 30 minutes as a background asyncio task; also exposed as `POST /api/gc`.

### `dashboard/lib/claude.ts`
Dual-mode Claude client:
- **CLI mode** (default, local only): spawns `claude -p {prompt} --model {model} --output-format text`
- **API mode** (when `ANTHROPIC_API_KEY` is set): uses `@anthropic-ai/sdk` streaming — works on Vercel serverless

### `mcp/pi-ceo-server.js`
MCP server connects Claude Desktop to Pi CEO. Exposes tools: `get_zte_score`, `get_sprint_plan`, `get_feature_list`, `get_last_analysis`, `generate_board_notes`, `list_harness_files`. Run via stdio; Claude Desktop adds it in MCP settings.

---

## Code Conventions

### Python
- **asyncio throughout** — use `async def`, `asyncio.create_subprocess_exec`, `await asyncio.sleep()`
- **Dataclasses** for models (`BuildSession`, `TaskSpec`, `TaskResult`)
- **Config** always via `os.environ.get("TAO_X", default)` in `config.py` — never hardcode
- **Error handling** — log to session output via `em(session, "error", msg)`, set `session.status = "failed"`, return
- **No `shell=True`** in subprocess calls — always pass args as list
- **Session ID sanitisation** — `re.sub(r'[^a-zA-Z0-9]', '', sid)` before any file path use

### TypeScript / Next.js
- **Tailwind utility classes** for layout; inline `style={{}}` for the Pi color tokens
- **Color tokens:** `--bg: #0A0A0A`, `--border: #2A2727`, `--orange: #E8751A`, `--text: #F0EDE8`, `--muted: #888480`, `--green: #4ADE80`, `--red: #F87171`
- **Font stack:** Bebas Neue (headings), Barlow Condensed (labels), IBM Plex Mono (code/terminal)
- **No default exports** on lib files; default exports on page/component files only
- **SSE over WebSocket** in dashboard — `useSSE` hook handles reconnect

### Git / Commits
- **Conventional commits:** `feat:`, `fix:`, `chore:`, `security:`, `docs:`
- **Co-author line:** `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
- **Branch:** work on `main` for solo dev; feature branches for Linear issues

---

## Cloud Deployment

### FastAPI — Railway / Render
- `RAILWAY_ENVIRONMENT` or `RENDER` env var detected — cloud mode (secure cookies, SameSite=None)
- TLS terminated by Railway proxy — do NOT add `TrustedHostMiddleware`
- CORS: add your Railway URL to `TAO_ALLOWED_ORIGINS`

### Next.js Dashboard — Vercel
- Set `ANTHROPIC_API_KEY` — enables API mode (required for Vercel serverless)
- Set `NEXT_PUBLIC_API_URL` — points to Railway backend
- Dashboard URL: https://dashboard-unite-group.vercel.app

---

## Linear Integration

Issues tracked in Linear project **"Pi - Dev - Ops"** (team: RA).

Issue IDs referenced in code comments: `RA-449` through `RA-461`.

Update issues as work completes — mark `In Progress` when starting, `Done` when smoke-tested.

---

## Smoke Test Checklist

No automated test suite yet. Run these after any backend change:

```
[ ] Server starts:  python -m uvicorn app.server.main:app --port 7777
[ ] Login works:    POST /api/login with correct password -> 200 + cookie
[ ] Auth enforced:  GET /api/sessions without cookie -> 401
[ ] Rate limit:     31 rapid requests -> 429
[ ] Build starts:   POST /api/build with valid repo_url -> session_id
[ ] WebSocket:      /ws/build/{sid} receives output lines
[ ] Persistence:    restart server -> GET /api/sessions shows prior session
[ ] GC:             POST /api/gc -> {"removed": N}
[ ] Lessons:        GET /api/lessons -> seed entries; POST -> appends
[ ] Dashboard:      npm run dev -> localhost:3000 renders, no console errors
```
