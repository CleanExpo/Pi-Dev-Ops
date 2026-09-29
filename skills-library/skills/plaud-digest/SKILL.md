---
name: plaud-digest
version: 1.0.0
description: "Summarize multiple Plaud recordings into a digest. Use when the user says 'weekly report', 'digest of this month', 'what meetings did I have this week', 'recap of last quarter', or asks to roll up multiple recordings into one overview."
metadata:
  requires:
    bins: []
---

# plaud-digest

**Read [`plaud-shared`](../plaud-shared/SKILL.md) first.**

## When to use

- User asks for a roll-up across multiple recordings.
- Time window is explicit ("this week") or implicit ("recap of recent meetings").
- Scope is "what happened", not "find one specific meeting" (that's `plaud-find`).

## Steps

1. **Resolve the window.** Use the date interpretation table in `plaud-find` for relative phrases.
2. **List the corpus.** `list_files` with `date_from` / `date_to`. Cap at 50 recordings — if the window returns more, ask the user to narrow it.
3. **Fetch notes in batch.** For each recording, call `get_note`. Do **not** call `get_transcript` unless a specific recording merits a deeper pull.
4. **Synthesize.** Produce a structured digest:
   - **Headline** — one-line theme of the window.
   - **By recording** — one bullet per recording: `• name (date, duration) — one-sentence takeaway`.
   - **Recurring themes** — topics that appeared in ≥ 2 recordings.
   - **Open action items** — aggregated across recordings, deduplicated.
5. **Cite sources.** Every non-trivial claim must reference the recording it came from, using the file name (not the raw ID unless the user asked).

## Budget

- Hard cap: 50 `get_note` calls per digest. If the window has more recordings, compress or ask user to narrow.
- Skip recordings where `note_list` is empty — mention them at the end under "unsummarized".

## Anti-patterns

- Do not load transcripts just to pad the digest.
- Do not synthesize across windows the user didn't ask for ("while we're at it, here's last month too").
- Do not invent action items that aren't in the notes — only aggregate what's there.
