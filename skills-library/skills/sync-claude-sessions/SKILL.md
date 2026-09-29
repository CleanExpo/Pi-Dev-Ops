---
name: sync-claude-sessions
description: B.U.I.L.D. Inflow pipeline #1 — mine the local Claude Code session lake (~/.claude/projects/**/*.jsonl) for CONTENT (intent, decisions, user corrections, tools, shipped PRs) and write redacted OKF digests into the 2nd Brain vault's process/sessions/ staging area. Use when the user says "sync sessions", "mine my session history", "ingest my Claude conversations", or as the first stage of /data-ingestion. Complementary to FABLE distill (which mines the same lake for rhythm metrics, not content).
---

# sync-claude-sessions

Turns your own terminal history — the richest training data you own — into
knowledge the self-improving loop can act on. One redacted digest per session.

## What it does

Walks `~/.claude/projects/**/*.jsonl` (808+ files, ~442 MB) and for each session
extracts: the opening **intent**, follow-up **user corrections/decisions**, the
**tools used** (histogram), the **conclusions** (last assistant output), and any
**shipped PRs** (`pr-link` events). Every text field is **redacted** before it
touches disk. Output is an OKF-formatted `session-digest` per session in
`~/2nd Brain/2nd Brain/process/sessions/`.

This is the **content** pass. It does NOT duplicate the FABLE distiller
(`~/Fabel Prompt Engineer/scripts/fable-distill.mjs`), which mines the same lake
for working-rhythm **metrics**. Run both; they are orthogonal.

## How to run

```bash
cd ~/Pi-Dev-Ops
python3 scripts/sync_claude_sessions.py --dry-run --limit 5   # safe sample → scratch
python3 scripts/sync_claude_sessions.py --since-last          # incremental (routine default)
python3 scripts/sync_claude_sessions.py                       # full re-scan
```

Flags: `--dry-run` (writes to `/private/tmp/.../scratch-session-digests`, never
updates the marker), `--since-last` (skip files unchanged since last run, via
`process/.sync-claude-sessions.json`), `--limit N`, `--out-dir PATH`.

## Security — non-negotiable

The redactor (`redact()`) strips full-length secret shapes BEFORE any write,
including the two that `scripts/secrets_check.py` misses: **`sk-ant-oat`
(Anthropic OAuth)** and **`AIza` (Google)**, plus Anthropic API, GitHub PAT/fine,
Linear, Slack, AWS, Stripe live, OpenAI, JWT, Bearer, and password/secret
assignments. Verify after any change to the pattern bank:

```bash
python3 scripts/test_sync_claude_sessions.py      # 23 assertions, must be ALL PASS
```

Gate (redactor as oracle): re-applying `redact()` to every output file must
change nothing. If it would, a secret leaked — fix the bank, re-run.

## Notes / known behaviour

- Resumed sessions share a `session_id`, so their digests dedup to the latest
  (744 sessions → 583 distinct digests on first run). Digests are derived data —
  safe to delete and re-mine anytime.
- After writing, regenerate the OKF index so `process/sessions/index.md` lists
  the new digests: `python3 ~/pi-seo-workspace/unite-group/apps/workspace/scripts/okf-index.py "$HOME/2nd Brain/2nd Brain"`.
- Spec: `~/Pi-Dev-Ops/docs/specs/2026-06-29-self-improving-system-build.md`.
- Next in the loop: `improve-system` reads these digests + the vault and proposes
  graded improvements; `/data-ingestion` orchestrates this + source-ingest + wiki sync.
