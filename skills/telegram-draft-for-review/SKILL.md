---
name: telegram-draft-for-review
description: Draft an outbound Telegram message and gate it behind a human reaction (👍 send, ❌ revise) before any actual send happens. Sits in front of swarm/telegram_alerts.py for human-addressed messages. Required path for every Scribe outbound.
owner_role: Scribe (CoS shares)
status: wave-1
---

# telegram-draft-for-review

The HITL gate for outbound Telegram. **No human-addressed message ships without 👍.**

## Why this exists

Today, `swarm/telegram_alerts.py` sends unreviewed alerts. That's fine for system alerts (severity tags, [AGENT OUTPUT] prefix). It is *not* fine for messages that look like Phill speaking — replies to people, board comments, draft summaries.

This skill is the gate. It posts a draft to a private review chat (or a dedicated thread), waits for a 👍/❌ reaction, and only then sends the real message.

## Flow

```
1. Caller passes a draft payload:
   {
     "draft_text": "...",
     "destination_chat_id": "...",  // where the REAL message will go
     "destination_thread_id": null,
     "drafted_by_role": "Scribe" | "CoS" | "Margot",
     "originating_intent_id": "..." // ties back to intent-parser output
   }

2. Skill posts to REVIEW_CHAT_ID with format:
     ✏️ DRAFT (Scribe) — for chat -100xxx
     ─────────────────────────────────
     <draft_text>
     ─────────────────────────────────
     React 👍 to send · ❌ to revise · ⏳ to delay 24h

3. Skill writes a pending entry to .harness/telegram_drafts.jsonl:
   {
     "draft_id": "...",
     "review_message_id": "...",
     "destination_chat_id": "...",
     "draft_text": "...",
     "status": "pending",
     "drafted_at": "...",
     "expires_at": "+24h"
   }

4. The orchestrator's existing reaction listener (extended in Wave 2)
   matches reactions on review_message_id:
   - 👍 → status=sent → call existing send_telegram() path → audit log
   - ❌ → status=revise → notify originating role, optionally Margot for re-research
   - ⏳ → status=deferred, expires_at extended +24h
   - <no reaction by expires_at> → status=expired → log, do NOT send

5. Final state ALWAYS persisted. No silent send, no silent drop.
```

## Contract

**Input:** the JSON payload above.
**Output:** `{"draft_id": "...", "review_message_id": "...", "status": "pending"}` synchronously. Final-state callbacks are async (next orchestrator cycle).

## Safety bindings

- **Kill-switch:** when `TAO_SWARM_ENABLED=0`, drafts can still be *posted* to review chat (so the user sees what Pi-CEO would have done) but `status=sent` is not honoured — sends are halted at the send-call boundary.
- **Rate limit:** drafts inherit the existing `<1 msg/s, <20/min/group` limit on review chat. If breached, drafts are queued in `telegram_drafts.jsonl` with `status=queued` and posted on the next available slot.
- **PII redactor (Wave 2):** binds in front of *both* the review post and the eventual send. Wave 1 logs a warning if `pii-redactor` is missing but does not block the draft.
- **Audit log:** every status transition (pending → sent / revise / deferred / expired) appended to `.harness/swarm.jsonl` with full draft text and reaction metadata.

## Where the review chat lives

`REVIEW_CHAT_ID` is a new env var. Recommendation: a private 1:1 chat between Phill and Pi-CEO bot, separate from the existing swarm alert chat. Setting it up is a one-time config — flag if missing on first invocation.

## When NOT to use this skill

- System alerts (severity-tagged `[AGENT OUTPUT]` prefix) continue to ship via `swarm/telegram_alerts.py` directly. They are not addressed to people.
- Reaction-gate signals (👍/❌) on existing drafts — those route to the reaction handler, not this skill.
- Linear comments — Wave 2 `linear-comment-draft` extends this pattern to Linear; not yet built.

## Verification (Wave 1)

In test mode (`TAO_DRAFT_REVIEW_TEST=1`), the skill:
1. Accepts a draft payload.
2. Writes to `.harness/telegram_drafts.jsonl` *without* posting to Telegram.
3. Returns a synthetic `review_message_id`.
4. Accepts a synthetic reaction via stdin (not a real Telegram reaction).
5. Transitions state correctly: pending → sent on 👍, pending → revise on ❌, pending → deferred on ⏳, pending → expired after simulated 24h.

End-to-end live test happens in Wave 2 once the reaction listener is extended in `swarm/orchestrator.py`.

## Out of scope

- Real reaction-listening — extends `swarm/orchestrator.py`'s existing /ack listener; that's a Wave 2 wiring task.
- Multi-recipient gating (e.g. "send to A or B based on reaction") — Wave 3.
- Email or Slack draft-for-review — Wave 2 expansion.

## References

- Topology: `/Users/phill-mac/Pi-CEO/Second-Brain-Agent-Topology-2026-05-01.md`
- Existing send path (do not modify in Wave 1): `Pi-Dev-Ops/swarm/telegram_alerts.py`
- 15 mandatory safety controls: `/Users/phill-mac/Pi-CEO/Hermes-Swarm-Recommendation-2026-04-14.md` §5
