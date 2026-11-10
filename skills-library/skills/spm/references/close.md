# Close: write back what this run learned, then hand the tools back

The last step of every /spm run except the Answer lane. Before it, /spm had no write-back: what a
run learned lived only in its transcript and was lost at the next session.

Do these in order. Each is small; none waits on Phill.

## 1. Memory: one file per fact

For each fact a future session would otherwise re-learn the hard way (a founder ruling, a trap, a
path that moved, a tool flag that lies):

- Search first: grep the memory folder, and run `node <brain.js> find "<the fact in plain words>"`
  with the vault's `brain.js`, resolved as `references/interview.md` says (`SPM_BRAIN`, else
  `~/2nd-brain`, else `~/2nd Brain`). If that gives `UNPROVEN: vault ambiguous`, skip the vault
  search and rely on the memory grep. Update the existing file when one covers it; never
  write a second file for the same fact.
- New fact: one file in `~/.claude/projects/-Users-phillmcgurk/memory/<kebab-slug>.md`, with the
  frontmatter the folder already uses (`name`, `description`, `metadata.type`: `feedback` for a
  founder rule, `project` for project state, `reference` for where something lives). Body: the
  fact, the date, the evidence (command or file it came from), and why it matters.
- One index line in `MEMORY.md` under the matching heading: `[short title](file.md)`, plus at most
  a few words. One fact per line: never fuse two facts, dates or tickets on one line.
- Run `python3 ~/.claude/scripts/check-memory-index.py`; fix what it names.

Never store a secret, a token or a live credential value. "Where a key lives" is fine.

## 2. Wiki: durable learnings only

When the run produced a decision, method or finding that outlives this project (not a session
detail), run the `wiki-ingest` skill once at the end. One ingest per run, never per fact.

## 3. Check skills back in

Every skill this run checked out (§0b), by name: `skill_shelf.mjs checkin <name>`. Never `--all`:
it also unlinks checkouts other sessions are still using.

## 4. Journal event

One event per run, written by the script, never by hand:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/journal_event.py" --summary "<what changed>" \
  --lane <lane> --tier T<n> --next "<one sentence>"
```

Exit 3: the text held a secret; rewrite it without the secret. Exit 4: report `UNPROVEN: journal`.

## 5. Say it in one line

`Close: memory <n new, n updated> · wiki <ingested|n/a> · checked in <skills> · journal <ok|UNPROVEN>`.
