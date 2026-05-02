---
name: intent-parser
description: Classify an inbound Telegram message into one of six intent types so the Chief of Staff can route to the right role. Use this on every Telegram message that lands in Pi-CEO before any routing decision.
owner_role: Chief of Staff
status: wave-1
---

# intent-parser

Maps a Telegram message to one of six intents, plus extracted parameters. Lightweight regex layer + Claude classification fallback. Output is a JSON payload that downstream skills consume.

## The six intents

| Intent | Trigger shape | Fields extracted | Routes to |
|---|---|---|---|
| `research` | Question form, "what / find / research / look up / check the latest" | `topic`, `time_budget` (quick/deep), `use_corpus` | Margot via `margot-bridge` |
| `ticket` | "file / create / open / track" + project/title hint | `team`, `project`, `title`, `priority` | Dispatcher → Linear MCP |
| `reply` | "tell / message / reply / draft / respond to" + recipient | `recipient`, `medium` (telegram/email/linear), `body_hint` | Scribe → `telegram-draft-for-review` |
| `reminder` | "remind / nudge / chase me / on Thursday" + time | `when` (ISO-8601 absolute), `what` | Dispatcher (Wave 2 calendar) |
| `flow` | Multi-step ("first do X then Y"), or explicit "run the flow" | `steps[]` (3+ ordered actions) | Dispatcher (`dispatcher-core`) |
| `unknown` | Doesn't match above | raw message | CoS clarification (one Telegram follow-up) |

## Algorithm

1. **Fast path (regex).** Match against ~12 high-precision patterns per intent. If exactly one matches with confidence, return that intent + extracted fields.
2. **Claude classification (slow path).** If 0 or ≥2 fast-path matches, send the message to Claude with a 6-class classifier prompt. Returns intent + reasoning trace + confidence score.
3. **Confidence floor.** Below 0.6 confidence → `intent: unknown`. Don't route on guesses.
4. **Date parsing.** Always convert relative dates ("Thursday", "tomorrow morning") to absolute ISO-8601 in the user's local timezone before returning. Per CLAUDE.md `auto memory` rule.
5. **PII guard.** If raw message contains a credit card / account number / SSN-shape regex hit, intent forced to `unknown` AND a warning logged. Don't process sensitive intents through the pipeline. (Hardens against the Hermes Sprint 1 SWARM-005 PII filter requirement.)

## Output schema (canonical)

```json
{
  "intent": "research" | "ticket" | "reply" | "reminder" | "flow" | "unknown",
  "confidence": 0.0-1.0,
  "fields": {
    "...": "..."
  },
  "raw_message": "...",
  "originating_chat_id": "...",
  "originating_message_id": "...",
  "received_at": "ISO-8601"
}
```

## When NOT to use this skill

- For messages that are literal commands (`/ack`, `/panic`, `/turbopack`) — those bypass intent parsing entirely and route to the existing command handler in `swarm/orchestrator.py`.
- For Telegram reactions (👍 ❌) on existing draft messages — those are HITL-gate signals, not new intents. Routes to `telegram-draft-for-review`'s reaction handler.
- For broadcast group messages where Pi-CEO is not @mentioned — rate limit + ignore unless explicit @mention.

## Verification (Wave 1)

Paste 10 sample Telegram messages — 3 research, 3 ticket, 2 reply, 2 reminder — into the parser. Expect ≥8/10 classified correctly with confidence ≥0.6. Sample set:

1. "what's the latest on Hermes v0.13?" → `research` (quick)
2. "look up reviews of Vercel Workflow DevKit" → `research` (quick)
3. "deep dive on UK SMB SaaS pricing 2026" → `research` (deep)
4. "file a Linear ticket for the auth bug in CARSI" → `ticket` (GP team)
5. "open a P2 in Pi-Dev-Ops about the Telegram /panic gap" → `ticket` (RA team)
6. "track this: dashboard widget broken" → `ticket` (raw → ask)
7. "tell Margot to draft a reply to John about the brief" → `reply` (telegram, recipient=John)
8. "draft a Slack message to the team about the deploy freeze" → `reply` (slack — Wave 2)
9. "remind me Thursday to check the spike result" → `reminder` (Thursday → 2026-05-07)
10. "nudge me at 4pm tomorrow about the EOD send" → `reminder` (2026-05-02 16:00)

## Out of scope

- Multi-language input — English only in Wave 1.
- Voice transcription — Wave 3 if Margot's image-gen is reused as a transcription frontier.
- Threaded conversation context — each message classified independently in Wave 1.

## References

- Topology: `/Users/phill-mac/Pi-CEO/Second-Brain-Agent-Topology-2026-05-01.md`
- Existing Telegram cmd handler (do not modify): `Pi-Dev-Ops/swarm/orchestrator.py`
