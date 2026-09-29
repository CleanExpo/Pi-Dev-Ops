---
name: seo
description: "Full SEO toolkit powered by the DataForSEO API. Replaces the data layer of an SEO agency: keyword research, competitor analysis, rank tracking, backlink audits, technical site crawls, content gap analysis and client-ready PDF reports, all from real Google search data, not scraping. The entry point for any domain, URL or keyword handed over for SEO analysis; dispatches the seo-* sub-skills."
allowed-tools: Read, Grep, Glob, Bash, WebFetch, Write, Agent
---

# SEO Agency Killer — Claude Code Skill (April 2026)

> **Philosophy:** One command in, real Google data out. No browsing, no scraping,
> no guesswork — every metric below comes straight from DataForSEO's live APIs.

---

## Phase 0: First-Run Setup Check

Every `/seo ...` request starts here — API calls fail without credentials.

```bash
cat ~/.claude/skills/seo/.env 2>/dev/null
```

Credentials are configured when `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD` are present and
are not the placeholders `your_login_email_here` / `your_api_password_here`. **If configured**,
continue to the requested command silently. **If not configured**, STOP and run the full setup
wizard (signup links, credential parsing, the `chmod 600` write, and the verification-result
table) in [`references/setup-wizard.md`](references/setup-wizard.md). Never echo credentials back,
never put them in tool output, never commit them to git.

---

## Quick Reference

| Command | What It Does |
|---------|-------------|
| `/seo audit <domain>` | Full SEO audit with parallel subagents → composite SEO Score (0-100) + PDF |
| `/seo quick <domain>` | 60-second snapshot — top metrics, no subagents |
| `/seo keywords <seed>` | Keyword research (volume, CPC, difficulty, intent, related, long-tail) |
| `/seo technical <domain>` | Technical site audit (On-Page API: speed, schema, errors, redirects) |
| `/seo competitors <domain>` | Find competitors, get SERP overlap, content gap |
| `/seo content <domain>` | Content quality + topical authority + missing topics |
| `/seo backlinks <domain>` | Backlink profile, top referring domains, anchor text, toxicity |
| `/seo rankings <domain> <keywords...>` | On-demand rank check across keyword set |
| `/seo content-gap <you> <competitor>` | Keywords competitors rank for that you don't |
| `/seo compare <domain1> <domain2>` | Head-to-head domain comparison |
| `/seo watchlist add/list/check` | Track multiple domains/keywords across runs |
| `/seo report <domain>` | Markdown deliverable |
| `/seo report-pdf <domain>` | Client-ready PDF report from saved audit JSON |

The exact script invocation and output spec for every command above are in
[`references/commands.md`](references/commands.md). Read it for the requested command before
running.

**Always invoke through the launcher — never call the scripts directly.**

```bash
./run.sh backlinks summary --domain example.com      # macOS / Linux / Git Bash
```
```powershell
.\run.ps1 backlinks summary --domain example.com     # Windows PowerShell
```

The launcher resolves this skill's own venv (`.venv/bin/python` or
`.venv/Scripts/python.exe`) and refuses to run without it, rather than falling
back to a system Python that lacks the dependencies.

Calling a script directly is only correct on macOS/Linux. The shebang is
`#!/usr/bin/env python3`, which Windows ignores entirely — you would silently
get system Python and an ImportError from deep inside the script. It previously
pointed at one specific Mac's venv interpreter, so it resolved on exactly one
machine (corrected 2026-08-10).

---

## Setup

1. Sign up at https://l.dataforseo.com/4epETnH (free trial includes $1 credit).
2. Copy `.env.example` to `~/.claude/skills/seo/.env` and fill in `DATAFORSEO_LOGIN` /
   `DATAFORSEO_PASSWORD`. The shared client at
   [scripts/dataforseo_client.py](scripts/dataforseo_client.py) reads it.

---

## Output Conventions

- Save all intermediate JSON to `~/.claude/skills/seo/output/<domain>-<command>.json`
- Always print a tight executive summary first (≤8 lines), then the detail
- Use score badges: 🟢 80+, 🔵 60-79, 🟡 40-59, 🔴 <40
- End every audit with a "Top 3 Actions This Week" section

---

## DataForSEO API Notes

- All scripts use the **live** endpoint variants (synchronous, no polling)
  except `on_page/site` which requires a true crawl
- Default location is `United States`, language `en` — pass `--location` /
  `--language` to override (e.g. `--location "United Kingdom" --language en`)
- A typical full audit costs ~$0.10-0.30 in DataForSEO credits
- The shared client is at [scripts/dataforseo_client.py](scripts/dataforseo_client.py)

---

## When NOT To Use This Skill

- AI search visibility (ChatGPT, Perplexity, Gemini citations) → use `/geo` instead
- Google Business Profile / local pack tracking → DataForSEO has it but a
  dedicated local-SEO tool would be a better fit
- Pure content writing (no data needed) → use a content skill directly
