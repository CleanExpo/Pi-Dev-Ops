---
name: margot-align
description: "Aligns Margot's knowledge corpus with the latest 2nd Brain wiki, Pi-CEO health data, and empire context. Runs sync scripts, verifies Supabase tables are current, and sends Margot a context refresh prompt. Use weekly or after major wiki updates. Model: claude-sonnet-5"
allowed-tools: Bash, Read
model: claude-sonnet-5
---

# Margot Alignment — Corpus Sync

Ensure Margot has the latest context before important sessions.

## Step 0: Drift gates (fail the run on drift)

Never sync a lying index into the corpus. Both must pass before Step 1:
```bash
node "$HOME/2nd Brain/2nd Brain/_system/brain.js" check    # vault + memory index ↔ files
node "$HOME/2nd Brain/2nd Brain/_system/brain.js" skills   # skills catalogue 2-place rule
```
Non-zero exit = drift: fix the listed lines first (regenerate OKF via
`~/Unite-Group/apps/workspace/scripts/okf-index.py "$HOME/2nd Brain/2nd Brain"`,
add/remove catalogue lines), re-run, then proceed.

## Step 1: Sync 2nd Brain wiki to Supabase
```bash
python3 ~/Pi-Dev-Ops/scripts/sync_wiki_to_supabase.py
```

## Step 2: Sync Pi-CEO harness state
```bash
python3 ~/Pi-Dev-Ops/scripts/sync_harness_to_supabase.py
```

## Step 3: Verify Supabase tables
Check row counts in wiki_pages, pi_ceo_health_snapshots, pi_ceo_activity, telegram_messages.

## Step 4: Send Margot a context brief via Telegram
Craft a message to the Telegram bot summarising what's been updated and ask Margot to confirm she's reading from the latest corpus.

## Output
Report: pages synced, health snapshots, activity rows, Margot confirmation.
