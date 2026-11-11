---
name: wiki-ingest
description: Ingest current session learnings into the Brain-1 wiki at ~/2nd Brain/2nd Brain/Wiki/. Updates existing pages in place, creates new pages for genuinely new topics, appends to log.md. Use when a significant working session ends with durable learnings or decisions worth keeping.
allowed-tools: Read, Edit, Write, Bash
---

# Wiki Ingest — Session Learnings

Write this session's durable knowledge into the Brain-1 wiki so Margot has it next time.

<!-- SOP: seek-latest-before-task -->
## Step 0: Seek latest before ingest (SOP `seek-latest-before-task`)

Before writing anything, pull what other machines published since you last looked, so you
update the current page rather than a stale copy:

```bash
python3 "$HOME/2nd-brain/2nd Brain/_system/post_ingest.py" --seek
```

It fetches `origin/main` of CleanExpo/brain-1 and merges it; `BLOCKED` (exit 3) means a
merge conflict: resolve it by hand before ingesting. Then search the index and log for related
learnings and rule changes before deciding which pages to touch.
<!-- /SOP: seek-latest-before-task -->

## Step 1: Orient

Read the index and identify which pages are relevant to what changed this session:

```bash
cat ~/2nd\ Brain/2nd\ Brain/Wiki/index.md
```

## Step 2: Identify affected pages

For each significant change or decision from this session, match it to an existing page.
Cap at 10–15 pages max. Don't update pages that don't need it.

Common mappings:
- Hermes jobs / cron changes → `hermes-agent.md`
- Swarm architecture changes → `pi-ceo-architecture.md`
- Wave progress → `wave-roadmap.md`
- New business facts → the relevant business page
- New clients or deals → `businesses-overview.md` + client page
- System priorities → `operational-priorities-q2-2026.md`

## Step 3: Update pages in place

For each affected page:
1. Read the current page
2. Edit ONLY the sections that changed — don't rewrite whole pages
3. Update the frontmatter `updated:` date to today
4. Use `[[double-bracket]]` links for cross-references

Format for frontmatter:
```
---
type: wiki
updated: YYYY-MM-DD
---
```

## Step 4: Create new pages (only if needed)

If a genuinely new topic emerged that doesn't fit any existing page:
1. Create `~/2nd Brain/2nd Brain/Wiki/<slug>.md`
2. Add it to `Wiki/index.md` under the right section

## Step 5: Append to log.md

```
YYYY-MM-DD | ingest | page1.md, page2.md | one-line summary of what changed
```

## Step 6: Refresh OKF indexes

Keep the vault navigable (Open Knowledge Format) — regenerate `index.md` across all
folders so agents read the index first instead of keyword-matching. Idempotent;
preserves hand-authored indexes (those lacking the `okf:generated` marker).

```bash
python3 "$HOME/2nd Brain/2nd Brain/_system/okf-index.py" "$HOME/2nd Brain/2nd Brain"
```

After regenerating, revert date-only churn so the commit stays surgical — keep only
indexes whose content changed:

```bash
git diff --numstat | awk '$1==1 && $2==1 {print substr($0, index($0,$3))}' | tr -d '"' \
  | while IFS= read -r f; do git checkout -- "$f"; done
```

## Step 7: Sync to Supabase corpus

```bash
SUPABASE_SERVICE_ROLE_KEY=$(grep SUPABASE_UNITE_GROUP_SERVICE_KEY ~/.hermes/.env | cut -d= -f2-) \
  python3 ~/Pi-Dev-Ops/scripts/sync_wiki_to_supabase.py
```

## Applied-learning capture (said-it-twice rule)

If you had to re-explain something, hit a repeated failure, or found a workaround for a tool
limitation this session, capture it once — never explain it a third time. Keep each to ONE
bullet under 15 words, no rationale, only things that save a future session. Route it to the
right home: a memory file for agent-behaviour/feedback lessons, the relevant wiki page for
domain knowledge. Adding the fact that matters and dropping the dead one is curation, not
hoarding. See [[feedback-no-status-bloat]].

<!-- SOP: seek-latest-before-task -->
## Step 8: Publish in the same cycle (index -> git -> corpus, hard-coded)

Steps 6-7 are not optional and not "later". Commit the ingest in the vault; the brain-1
`post-commit` hook then runs `2nd Brain/_system/post_ingest.py`, which refreshes OKF indexes
(dropping date-only churn), commits them, merges `origin/main`, pushes `main` (never forced)
and syncs changed pages into Supabase `wiki_pages`. Check the result before you say the
learning is saved:

```bash
python3 "$HOME/2nd-brain/2nd Brain/_system/post_ingest.py" --status   # result: PASS/FAIL/UNAVAILABLE/BLOCKED
```

Anything but `PASS` means the learning is not published: fix and rerun
`post_ingest.py` (add `--full-sync` for a full corpus refresh). If the hook is missing on a
machine, install it with `sh "$HOME/2nd-brain/2nd Brain/_system/install-post-ingest-hook.sh"`.
<!-- /SOP: seek-latest-before-task -->

## Rules

- Every sentence carries information — no filler, no commentary
- Sources/ files are immutable — never edit them
- Touch only what this session actually changed
- `index.md` and `log.md` need updating even if no content pages changed
- An ingest is not saved until `post_ingest.py --status` reads `PASS`
