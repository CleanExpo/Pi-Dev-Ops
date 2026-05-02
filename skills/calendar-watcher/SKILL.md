---
name: calendar-watcher
description: Convert calendar event creation/modification/deletion into Pi-CEO actions. Use for time-anchored triggers — meeting prep 30min before, post-meeting summary, conflict detection, schedule reflow when an urgent block lands. Pairs with email-listener for the "calendar invite arrived in email" pattern.
owner_role: Chief of Staff
status: wave-2
---

# calendar-watcher

Google Calendar push → CoS dispatch. Time-anchored autonomy.

## Why this exists

Pi-CEO has cron triggers (morning briefing, SEO weekly/monthly) but no event-driven calendar awareness. The user keeps moving meetings, accepting late invites, blocking focus time — and currently has to remember to ask Pi-CEO for prep / summary / reflow each time. This skill makes calendar a first-class event source.

## Trigger model

**Push notifications via Google Calendar Watch API** — `events.watch` returns a channel that posts to a webhook on every change. Same shape as Gmail's push.

**Two scopes:**
1. Primary user calendar (`phill.mcgurk@gmail.com`) — high-signal.
2. Optional secondary calendars (Unite-Group shared cal, RA shared cal) — flag per-calendar with env var `CALENDAR_WATCHER_CALENDARS` (JSON list).

## Event types handled

| Calendar change | Pi-CEO response |
|---|---|
| **New event accepted** | If from external sender + subject matches research keywords → dispatch Margot pre-read. Else → mark for prep timer. |
| **Event starts in 30m** | Trigger a prep-brief flow: Margot quick research on attendees + recent emails with them + any related Linear tickets → Telegram digest (gated by review chat) |
| **Event ends** | Trigger a follow-up flow: ask user via Telegram for summary points → Scribe drafts a meeting note → save to Linear or doc store |
| **Event modified (time/place changed)** | Re-fire prep timers. If conflict with another event introduced → Telegram alert. |
| **Event deleted/declined** | Cancel pending prep flows for that event. |
| **Long focus block (>2h) declined** | Telegram alert — "you just declined a focus block, want to reschedule?" |

## Flow (example: 30-min prep)

```
1. Watch fires on calendar change
2. /api/webhook/calendar route (NEW in app/server/routes/webhooks.py)
3. Handler computes delta vs last snapshot in .harness/calendar_state.json
4. For each upcoming event with no prep_timer set: schedule a cron entry
   for (start_time - 30m) via existing app/server/cron_scheduler.py
5. At T-30: cron fires a Dispatcher flow:
   step1: Margot deep_research(topic="meeting with {attendee}", use_corpus=true)
   step2: Linear search for related tickets (mcp.linear.list_issues with attendee mentions)
   step3: telegram-draft-for-review with prep digest
6. User 👍 → digest sent to user's Telegram, not the meeting attendees
```

## Contract

**Inputs:** Google Calendar push notification on watched calendar(s).
**Outputs:** zero or more Dispatcher flows scheduled, calendar state delta logged to `.harness/calendar_state.json`.

## Safety bindings

- **Read-only by default.** This skill does NOT create, modify, or delete calendar events. Wave 3 may add scheduling, but Wave 2 is observe + trigger only.
- **Attendee privacy.** Prep-brief includes attendee names and emails. NEVER auto-shares brief with anyone other than the user. The brief is a private digest, not a meeting agenda.
- **No auto-reply to invites.** Accepting/declining invites is a user-only action — never automated.
- **Quiet hours.** Default: no Telegram alerts between 22:00 and 06:00 user-local time, unless event is `<2h away`. Override per-event by user.
- **Loop guard.** If a single event modification produces >5 prep timers in 1h (e.g. someone is moving the same meeting repeatedly), skill backs off and Telegrams the user once.

## Where the auth lives

Same Composio pattern as `email-listener` — calendar OAuth via `phill.mcgurk_workspace`. No tokens on disk.

## Verification

1. Manually create a calendar event 35 minutes in the future from now → expect prep-flow scheduled.
2. At T-30: digest appears in review chat.
3. Modify event time → reschedule confirmed in `calendar_state.json`.
4. Delete event before T-30 → flow cancelled, no digest sent.
5. Quiet-hours test: schedule a flow at 23:30 local → no Telegram fires until next day (or override).

## When NOT to use

- One-off "remind me at 3pm" requests — that's `reminder` intent through `intent-parser` → calendar entry creation in Wave 3. Calendar-watcher is for events the user already booked, not new bookings.
- Recurring meeting prep where the agenda never changes (standups) — too noisy. Add a `pi-ceo:no-prep` tag to the event title to skip.

## Out of scope for Wave 2

- Calendar event *creation* by Pi-CEO — Wave 3.
- Multi-timezone normalization beyond user-local — Wave 3 if user travels.
- Conflict-resolution proposals (suggesting reschedules) — Wave 3.
- Apple Calendar / Outlook Calendar — Composio Outlook is INITIATED but incomplete per memory; Wave 3 candidate.

## References

- Topology: `/Users/phill-mac/Pi-CEO/Second-Brain-Agent-Topology-2026-05-01.md`
- Composio substrate: `~/.claude/projects/-Users-phill-mac-Pi-CEO/memory/project_composio_substrate.md`
- Existing cron scheduler: `Pi-Dev-Ops/app/server/cron_scheduler.py`
- Google Calendar push: https://developers.google.com/calendar/api/guides/push
