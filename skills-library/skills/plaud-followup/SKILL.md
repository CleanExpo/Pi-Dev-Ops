---
name: plaud-followup
version: 1.0.0
description: "Turn a Plaud recording into a follow-up email, thank-you note, action-item list, SOAP note, or meeting brief. Use when the user says 'draft follow-up', 'what were the action items', 'send thank-you email', 'turn this into a SOAP note', 'write the recap', or names an artifact to generate from a recording."
metadata:
  requires:
    bins: []
---

# plaud-followup

**Read [`plaud-shared`](../plaud-shared/SKILL.md) first.**

## When to use

- User wants a **generated document** grounded in one recording.
- Target format is explicit (email, SOAP note, brief, action-item list) or implicit ("write the follow-up").
- If the user wants to *send* the output to Notion / Slack / a webhook, chain into `plaud-export` after drafting.

## Steps

1. **Identify the recording.** If the user didn't name one, hand off to `plaud-find` or `plaud-browse`.
2. **Fetch source content.**
   - `get_note` first — usually enough for summaries and action items.
   - `get_transcript` only if the artifact needs verbatim quotes (e.g., legal memo) or speaker attribution (e.g., SOAP).
3. **Generate the artifact** in the requested format. Ground every claim in the source; do not invent attendees, dates, decisions, or numbers.
4. **Present to the user** in the chat, then ask if they want to refine or export.

## Artifact templates

### Follow-up email
- To: attendees (from notes if listed).
- Subject: "Follow-up — {recording name}, {date}".
- Opening line: thanks + one-line meeting summary.
- Body: 3–5 bullets of key points.
- Action items: numbered list with owner and due date if mentioned.
- Closing: "Let me know if I missed anything."

### Thank-you email
- Short. One paragraph. One concrete thing you learned or appreciated from the call.

### Action-item list
- Plain markdown: `- [ ] {owner}: {item} (due {date})`.
- Mark owner as `?` if unclear from notes — do not guess.

### SOAP note (clinical)
- **Subjective** — patient's words (from transcript).
- **Objective** — observations (from transcript, not inferred).
- **Assessment** — summary's diagnosis if present.
- **Plan** — action items and next appointment.

### Meeting brief
- Attendees, date, duration, decisions, risks, next steps.

## Anti-patterns

- Never invent email recipients. If attendees weren't captured, ask the user.
- Never invent due dates. Mark as `due: TBD` if not stated.
- Do not send the email — this skill drafts. Handoff to `plaud-export` for delivery.
