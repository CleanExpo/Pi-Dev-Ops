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
ANALYSIS_MODEL=claude-opus-4-5-20250514
```

## Run locally

```bash
npm run dev   # http://localhost:3000
```

## Deploy to Vercel

`vercel.json` in the repo root sets `rootDirectory: "dashboard"` — Vercel picks this up automatically.

Set the same env vars in Vercel project settings.

## CLI alternative

```bash
chmod +x scripts/analyze.sh
./scripts/analyze.sh https://github.com/owner/repo [model] [branch]
```

Requires `claude` CLI to be installed and authenticated.
