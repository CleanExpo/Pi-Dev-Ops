# Pi CEO Dashboard

Autonomous code analysis platform. Paste a GitHub repo URL → 8-phase analysis → live terminal → results → PR.

## Setup

```bash
cd dashboard
npm install
```

Create `.env.local`:
```
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
TELEGRAM_BOT_TOKEN=...   # optional
ANALYSIS_MODEL=claude-opus-4-7
```

## Run locally

```bash
npm run dev   # http://localhost:3000
```

### Local dev auth

`npm run dev` uses `scripts/dev-env.sh`, which sources `.env.local` and auto-detects
unresolved `op://` 1Password references (created by `vercel env pull`). If `op` CLI
is signed in, secrets resolve via `op run`; otherwise the login password falls back
to **`dev`**. To override, set `DASHBOARD_PASSWORD=<plaintext>` in `.env.local`.

## Deploy to Vercel

`vercel.json` in the repo root sets `rootDirectory: "dashboard"` — Vercel picks this up automatically.

Set the same env vars in Vercel project settings.

## CLI alternative

```bash
chmod +x scripts/analyze.sh
./scripts/analyze.sh https://github.com/owner/repo [model] [branch]
```

Requires `claude` CLI to be installed and authenticated.
