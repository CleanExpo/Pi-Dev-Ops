---
name: shared-knowledge
description: Use when changing, installing or debugging the fleet's session-start context and LESSON harvest (sot_hook.py, sot_compact.py), or when approving lessons into SHARED-KNOWLEDGE.
---

# Shared knowledge: session context and the lessons quarantine

Every Claude, Codex and Cursor session on the PC, Mini and MacBook runs `sot_hook.py start` at SessionStart and `sot_hook.py end` at Stop. Installed copies live in `~/.local/bin`; this folder is the source.

Start injects only what every session needs (RA-8118, 28/10/2026: context is a budget): board counts and the ids claimed by this machine, the Grok notes pointer, and the founder-rule sections (headings naming HARD RULE or Phill) from the top 45 lines of `ops/SHARED-KNOWLEDGE.md`. Everything else is pulled when needed:

- `sot_hook.py board`: one line per open or claimed job for this machine.
- `sot_hook.py show <id>`: one full card. Off the Mini, run it as `ssh mini python3 ~/.local/bin/sot_hook.py show <id>`.

Work updates go back to the card, not into the transcript. A new rule that every session must see needs a `HARD RULE` or `Phill` heading in the top 45 lines, or start will not carry it.

## What a lesson goes through

1. `end` reads only the Stop payload's `last_assistant_message` (the tool sets it to the model's own reply). Tool output, files and subagent reports are never scanned. Cursor sends no such field, so its lessons pause and each `end` logs `found=False`.
2. Each lesson is staged quarantined with an `id`, `source` and `read_external` (outside-content tools used in that turn, or `unknown`). Off the Mini it goes over ssh; each `end` appends its lessons to `~/.local/state/sot-spool.jsonl` under one local lock and sends everything past `sot-spool.jsonl.sent`, a byte offset that moves only after the Mini took the lines (the spool is emptied in place once all of it is sent). Nothing is renamed or moved, so a crash at worst re-sends, and each line's `cid` makes a re-send the same row on the Mini.
3. On the Mini, `ingest` stamps the quarantine whatever the sender says. Bare text from an old harvester is `source: unverified`.
4. `sot_compact.py` (launchd every 15 min) reads the whole new lines of the append-only `ops/lessons-staging.jsonl` past `ops/.lessons-staging.cursor` and appends them to `ops/lessons-quarantine.jsonl` under the shared `.sot-compact.lock`; the cursor moves only after that append is on disk, and rows are deduped by id, so a crash loses and duplicates nothing. Staging is never renamed, so a writer that still holds it open (an old hook mid-rollout) appends where the next run reads. It never promotes anything. Approved rows stay in the quarantine marked `approved`, so a re-read cannot bring them back. Only `approve`, run on a terminal, merges lessons into SHARED-KNOWLEDGE.
5. The intake filter (09/11/2026) runs inside that same compact step, because every writer (the hook and `site_watch.mjs`, which appends to staging directly) reaches the quarantine only there. A closing tag captured into a lesson (`...</message>`) is stripped. A lesson whose normalised text matches a quarantined row from the last 14 days is not quarantined again; a line goes to `ops/lessons-repeats.jsonl` naming the row it repeats (`of`), so how often a lesson recurs is still measurable. Rows from status tools (`site-watch`) go to `ops/lessons-nonlesson.jsonl`. Side files are written before the quarantine and the cursor, so a crash may repeat a side line but never loses a lesson. Why: on 09/11 about 44% of 3,666 staged rows were this noise, one lesson 747 times. The hook also strips the tag at harvest; compact re-applies it for senders still on an old hook.

## Approving (Phill only, from Terminal)

```
python3 ~/.local/bin/sot_compact.py list
python3 ~/.local/bin/sot_compact.py approve <id> [<id> ...]
python3 ~/.local/bin/sot_compact.py kinds
python3 ~/.local/bin/sot_compact.py approve-kind <KEY>
python3 ~/.local/bin/sot_compact.py reject-kind <KEY>
```

Approving one kind at a time replaces approving one lesson at a time. `ops/lesson-kinds.json` holds kind proposals written by the RSI lane: each kind has a `key`, `name`, `definition` and `design_change`, and `assign` maps quarantine ids to keys. `kinds` shows each proposed rule, its pending count and three sample lessons. `approve-kind` merges ONE rule line for the kind into AUTO LESSONS (deduped, so approving twice adds nothing) and marks the kind's pending lessons `approved`. `reject-kind` marks them `rejected` and merges nothing. Both refuse without a terminal or for an unknown key, and both append an audit line naming the kind and ids. The proposal file is agent-written: nothing in it counts until Phill approves on a terminal, entries without all four fields are ignored, and each field is capped at 240 characters. The `assign` ids must be quarantine ids.

`approve` refuses without a terminal, so an agent's shell cannot approve. It merges at once. `ops/lessons-approvals.jsonl` is an audit log that nothing reads to decide, so an event appended to it by any other process promotes nothing. The terminal check stops an agent's normal shell, not a determined same-user process, and such a process could write SHARED-KNOWLEDGE.md directly anyway. Closing that needs a separate OS user for the ops folder, which is founder-gated. Read `OUTSIDE CONTENT` before approving: a lesson written in a turn that fetched a page may be that page talking.

## Deploying a change

Reader first, so a quarantined row is never read by an old compact: copy `sot_compact.py` on the Mini, then `sot_hook.py` on the Mini, then `sot_hook.py` on the PC and MacBook. Roll back in the reverse order, and move `ops/lessons-staging.jsonl` aside to `ops/.lessons-quarantine/` before rolling compact back. Snapshot both installed files and `ops/SHARED-KNOWLEDGE.md` first.

## Tests

`python3 skills/shared-knowledge/tests/test_sot.py` (any python3; set `SOT_OPS`, `SOT_STATE`, `SOT_DEBUG_DIR` to isolate). Never run an older copy of these scripts in a test: before 26/10/2026 they had the live ops path written into them.
