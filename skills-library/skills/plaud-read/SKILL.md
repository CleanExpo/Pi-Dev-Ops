---
name: plaud-read
version: 1.0.0
description: "Read the transcript, AI summary, notes, or download audio for a specific Plaud recording. Use when the user says 'show the transcript', 'summarize this', 'what was said', 'get audio', 'the notes from', or names a specific recording to dig into. Also covers extracting structured fields from a recording."
metadata:
  requires:
    bins: []
---

# plaud-read

**Read [`plaud-shared`](../plaud-shared/SKILL.md) first.**

## When to use

- User names a specific recording (by name or ID) and wants to read its content.
- User asks for "transcript", "summary", "action items", "audio", "who said what", or a structured extraction ("action items, decisions, attendees").
- If the user did **not** specify a recording, hand off to `plaud-find` (by topic) or `plaud-browse` (by recency) first.

## Tool selection matrix

| User wants | Tool | Notes |
|---|---|---|
| AI summary, TL;DR, action items | `get_note` | Returns Markdown; usually enough — try this before `get_transcript` |
| Verbatim quotes, full dialogue | `get_transcript` | Timestamped; larger |
| Audio download link | `get_file` then use `presigned_url` | Link expires in 24h |
| Full metadata + availability flags | `get_file` | Check `source_list` / `note_list` populated before claiming content exists |

## Structured extraction workflow

If the user provides a schema (e.g., `{"action_items": [], "decisions": [], "attendees": []}`):

1. Call `get_note` first — the AI summary usually already contains these fields.
2. Only call `get_transcript` if the summary is missing a required field.
3. Return JSON matching the user's schema. Mark any missing field with `null` and note why.

Common schemas:
- Sales: `{ "pain_points": [], "follow_ups": [], "deal_stage": "" }`
- Clinical: `{ "diagnoses": [], "medications": [], "next_appointment": "" }`
- Project: `{ "action_items": [], "decisions": [], "attendees": [] }`

## Output

- Transcripts: preserve `[MM:SS - MM:SS] Speaker: content`. Do not reformat timestamps.
- Summaries: render Markdown directly in the reply.
- Audio: print the URL and mention "expires in 24h".

## Anti-patterns

- Do not call `get_transcript` speculatively — it's the largest payload.
- Do not paraphrase the AI summary unless the user asked; quote it verbatim.
