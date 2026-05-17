# ADR 003: Interactive game mode — native Telegram inline-keyboard cards + voice-reply fork + two-verb pause-state + scope separation

**Date:** 2026-05-15
**Status:** Accepted

## Context

The original Pilot bot plan (`docs/superpowers/plans/2026-05-14-agency-bot-pilot.md` L150) promised "Reply STOP to pause" in the greeting template, but `feedback.py` shipped no STOP handler. The grill-with-docs smoke test flagged this as one of 7 real gaps. Q4 of the grill session escalated beyond the STOP-only question into a broader UX architecture decision: how DOES Pilot's live stream surface to a CEO who's driving, walking, or in meetings on a phone?

Phill's framing: the YouTuber-Magnus "Tinder-swipe" pattern (per `[[research-browser-harness-pm-synthesis-2026-05-14]]`) is the right metaphor — but a Telegram Mini App rebuild is heavy AND triggers iOS microphone permission prompts that break the frictionless feel. Native Telegram primitives (inline keyboards + voice messages) give "90% of the gamified feel of a Mini App with 10% of the engineering effort."

## Decision

**Three locked pieces:**

### 1. Suggestion card UX — native Telegram InlineKeyboardMarkup
Every Pilot suggestion ships as a `sendMessage` with `reply_markup` containing an `InlineKeyboardMarkup`. Never plain text.

Button layout:
- **Row 1 (per-card):** `[✅ Agree]` `[❌ Dismiss]` `[🎙 Discuss]`
- **Row 2 (per-card optional + always-present in greeting):** `[⏸ PAUSE 24h]` `[⏹ STOP]`

Card lifecycle: sent → user taps → callback handler fires → `editMessageReplyMarkup` updates the card to a processed state (greyed buttons + ✓/✗ marker) → next card queues.

### 2. Discuss verb — voice-reply branch
`[🎙 Discuss]` triggers a voice-reply branch. User records a Telegram native voice message; Pilot's voice handler downloads via `getFile`, transcribes, routes the result into the discussion thread for that suggestion.

No Telegram Mini App. No iOS microphone permission prompts. The user's existing Telegram voice UI is the input surface.

### 3. Pause-state state machine — two-verb contract
Stored on `pilot_preferences`. Enum:
- `active` — emit suggestions per configured cadence.
- `paused-hard` — indefinite pause, set by `[⏹ STOP]`. Resumes only on `RESUME` typed message OR tenant config flip.
- `paused-until-{ISO-8601-timestamp}` — soft time-boxed pause, set by `[⏸ PAUSE 24h]`. Auto-resumes when `now() > ts`.

### Scope separation (the critical clarification)
Pause-state halts the **interactive live stream only**. The daily L4 Karpathy executive digest (from `[[spec-karpathy-pipeline-audit-2026-05-15]]`) continues independently — it's the async catch-up mechanism that survives any pause. STOP doesn't blackhole the user; it just turns the live cadence off until the next morning's digest summarises whatever Pilot noticed.

## Consequences

**Easier:**
- ≤3-tap triage per suggestion — matches CEO-mobile reality.
- Voice replies via native Telegram = zero new permission prompts, zero new SDK surface.
- Per-card state visualisation (`editMessageReplyMarkup`) gives free history scroll-back — every old card shows what was decided.
- Pause-state is data, not a special-cased flag — `paused-until-{ts}` query is `WHERE pause_state LIKE 'paused-until-%' AND parsed_ts > now()`.
- L4 digest survives pause-state — user never blackholes themselves from awareness, only from interruption.

**Harder:**
- Schema: `pilot_preferences.pause_state` TEXT NOT NULL with CHECK constraint validating the enum shape, plus index on parsed `paused-until` timestamp for cadence-cron lookups.
- Telegram callback handler must distinguish row-1 vs row-2 button categories — single dispatch table with per-action handler functions.
- Voice transcription pipeline is a new dependency (model + audio download + transcription routing) — its own ADR if Phill picks a non-OpenAI Whisper path.
- `editMessageReplyMarkup` requires storing the `chat_id` + `message_id` of every sent card — new `pilot_suggestion_messages` table or denormalised columns on `pilot_suggestions`. Plan-time decision.
- Greeting template (Pilot bot plan L150) needs rewriting: "Reply STOP to pause" → "Tap ⏹ STOP for hard pause, ⏸ PAUSE 24h for soft pause. Daily digest runs regardless."

**Now hard to undo:**
- Once users learn the 3-button + 2-button card UX, switching to typed-only mode forces re-training.
- Voice as a first-class triage verb sets an expectation; removing `[🎙 Discuss]` would feel like a regression.
- Pause-state being decoupled from the L4 digest is a deliberate scope-separation users will rely on.

## Alternatives considered

- **Shape A — STOP as hard global pause (no PAUSE 24h):** rejected. Binary state with no soft-pause surfaces the "forget it's off" failure mode Q4 flagged. Users who STOP after a bad suggestion silently lose all future ideas.
- **Shape B — STOP as 24h soft pause only (no hard STOP):** rejected. Forces users who want permanent off to retype STOP daily — annoying, breaks the friction budget.
- **Shape D — Drop the STOP promise from greeting, no handler:** rejected. Silently broken contract is worse than missing feature.
- **Telegram Mini App rebuild:** rejected. Heavy engineering (web app + Telegram Web App API + auth), iOS microphone permission prompts, ongoing maintenance burden — Phill's framing: "10% effort, 90% gamified feel" via native primitives.
- **Plain-text Q&A pings:** rejected. Re-introduces the "wall of text" friction that the Tinder-swipe pattern is specifically designed to kill.

## Implementation path (deferred to `superpowers:writing-plans`)

Plan-time concerns, NOT glossary-time. The plan agent receives this ADR as a locked input and authors:

1. Schema migration — `pilot_preferences.pause_state` TEXT NOT NULL DEFAULT 'active' with CHECK constraint; new `pilot_suggestion_messages(suggestion_id, chat_id, message_id)` table for `editMessageReplyMarkup` lookups.
2. Telegram callback handler dispatch table — one function per button (`handle_agree`, `handle_dismiss`, `handle_discuss`, `handle_pause_24h`, `handle_stop`).
3. Voice handler — `getFile` download → transcription provider call → discussion-thread router.
4. Card emitter refactor — `pilot/composer.py` produces `sendMessage` payloads with `InlineKeyboardMarkup`; legacy plain-text path removed.
5. Pause-state-aware scheduler — `pilot/scheduler.py` checks pause_state at cadence-cron tick; emits only when `active` OR `paused-until-{ts}` with `ts < now()`.
6. L4 digest scope-separation enforcement — daily executive digest cron reads from `pilot_suggestions` directly, ignores pause_state. Test asserts the digest fires for paused-hard tenants.
7. Greeting template rewrite — embed the 2-row keyboard layout in the welcome card; document the scope separation explicitly.

Per `[[feedback-substrate-change-discipline]]`: shadow-run the card UX in a single-tenant test bot for ≥10 real triage cycles before flipping the production cadence cron. Per `[[feedback-tight-code]]`: the callback dispatch table ≤80 lines.

## Cross-refs

- `[[context.md#suggestion-card]]` · `[[context.md#discuss-verb]]` · `[[context.md#pause-state]]` · `[[context.md#interactive-game-mode]]`
- `[[adrs/001-pillar-canonicalisation]]` — companion (cards display pillar chips per the array-typed cardinality)
- `[[adrs/002-tenant-identification]]` — companion (pause_state is per-tenant, RLS-isolated)
- `[[research-browser-harness-pm-synthesis-2026-05-14]]` — the Magnus "Tinder-swipe" source pattern
- `[[grill-output-pilot-bot-pilot-2026-05-15]]` — the smoke test that surfaced the STOP contract gap
- `[[spec-karpathy-pipeline-audit-2026-05-15]]` — the L4 daily digest this ADR explicitly scope-separates from
- `[[agency-bot-design-2026-05-14]]` · `[[agency-tinder-game-design-2026-05-15]]`
- `[[feedback-no-repeating-alerts]]` (the single-shot discipline this honours via pause_state) · `[[feedback-substrate-change-discipline]]` · `[[feedback-tight-code]]`
