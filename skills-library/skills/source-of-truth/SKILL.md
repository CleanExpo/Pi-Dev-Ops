---
name: source-of-truth
description: Use at the start of ANY task on Phill's machines (PC, Mac Mini, MacBook), before searching for what to do or re-discovering context. Board + shared learnings live on the Mini; claim before work, hand off with a result and a lesson.
---
# Source of truth (one board, one knowledge file)
Truth lives on the Mac Mini at `/Volumes/Mini Mini 2T Storage/ops/` (from PC/MacBook: `ssh mini`).
1. READ FIRST: `jobs.json` (work) and the top of `SHARED-KNOWLEDGE.md` (learnings). The session-start hook already injected both; don't re-discover what is there.
2. CLAIM before working: set the job's `status` to `doing` and `claimed_by` to your machine/agent (take `jobs.json.lock` while editing; back up first). If someone else has claimed it, do not start it; pick another or hand off.
3. NO NEW SIDE LISTS: no new TODO/notes files, watchers or clones for the same job. Reuse existing worktrees under `/Volumes/Mini Mini 2T Storage/worktrees/`.
4. HAND OFF: write the result back to the job (`status` review/done, `note` with evidence), and end your final message with one or more lines `LESSON: <one durable learning>`. The stop hook ships those to `ops/lessons-staging.jsonl`; the Mini merges them into SHARED-KNOWLEDGE.md.
5. Windows: hooks run through bash for Codex/Cursor; never write PowerShell-syntax hook commands there.
