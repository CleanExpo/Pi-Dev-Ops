---
name: kill-switch-binding
description: Telegram /panic command + dashboard kill button. Halts every role (CoS, Margot bridge, Scribe sends, Dispatcher mid-flow, Curator) within one cycle. Two-of-N + 2FA enforcement on dashboard side; Telegram side trusts only the configured operator chat_id. Closes the kill-switch safety control.
owner_role: Chief of Staff (entry point) + Guardian (enforcer)
status: wave-3
---

# kill-switch-binding

The `TAO_SWARM_ENABLED=0` env flag is the existing kill-switch. This skill adds two new entry points so the user can halt the swarm from anywhere — and adds the 2-of-N gate the Hermes-Swarm Recommendation §5 requires.

## Three entry points

### 1. Telegram `/panic` command

User types `/panic` from the configured operator chat. CoS poller catches it (extends the existing `/ack` polling logic), writes a `kill_switch_triggered` audit row, and sets `TAO_SWARM_ENABLED=0` via:
- File-flag at `.harness/swarm/kill_switch.flag` (created/touched on `/panic`, deleted on `/resume`).
- Orchestrator's `_check_kill_switch()` extended to ALSO read the file-flag.

Why a file-flag and not a process env var: env vars don't propagate to a running process. File-flag is read every cycle. Cheap and reliable.

`/panic` does NOT require 2FA — Telegram trust is established by the operator chat_id allowlist already in place. Speed matters more than extra friction here; halting is reversible.

### 2. Dashboard kill button (2-of-N + 2FA)

Dashboard adds a red `Halt Swarm` button. Click → modal asking for:
1. The user's TOTP code (from authenticator app)
2. A second approver (any allowlisted user with their own TOTP)

Both required. On approval:
- POST `/api/swarm/kill` with both TOTPs → server validates → file-flag set + audit row.
- Telegram alert fires to the operator chat: "Swarm halted via dashboard by {user1}+{user2}."

The 2-of-N gate exists because the dashboard kill is durable across restarts (file-flag persists), while `/panic` is operator-only and revertible by a single operator. Symmetry of trust matches symmetry of permanence.

### 3. Programmatic / CI-side `/resume` (operator-only)

Telegram `/resume` from the operator → file-flag deleted, audit row, swarm resumes on next cycle.

`/resume` does require operator chat verification but no 2FA — same logic as `/panic`. Permanence is reverted by the same authority that set it.

## What halts (and what doesn't)

| Component | Halts on kill-switch? |
|---|---|
| Existing swarm cycle (Guardian/Builder/Scribe/Click) | Yes — already gated on `TAO_SWARM_ENABLED` |
| CoS Telegram poller | Yes — but `/panic` and `/resume` continue to be processed (special case at the poll-level, BEFORE the gate check) |
| Margot bridge — in-flight `interaction_id`s | Persist; resume polls them on next cycle. **In-flight requests are NOT cancelled.** Gemini bills regardless. |
| Dispatcher mid-flow | Pause at next step boundary. State persisted. Resume from the same state. |
| Scribe sends | All gated through `draft_review`. Approval reaction in halted state is converted to `deferred` automatically (already implemented in `draft_review.mark_reaction`). |
| Curator | Read-only by design — keep running but cannot write SKILL.md without HITL gate. |
| Webhooks (Gmail / Calendar) | Continue to ACK Pub/Sub (don't break Google's contract) but skip dispatch. Intake jsonl keeps recording so backlog can be processed on resume. |
| Daily report cron | Pauses. Suppress to avoid alarming the user with "swarm fine" while it's halted. |

## Audit + alerting

Every halt + resume writes to `audit-emit`:
```json
{
  "type": "kill_switch_triggered" | "kill_switch_resumed",
  "actor_role": "CoS" | "Dashboard",
  "fields": {
    "trigger_source": "telegram_panic" | "dashboard_2fa" | "telegram_resume",
    "approvers": ["user1", "user2"],   // dashboard only
    "reason": "..."                     // optional, from /panic message text after the command
  }
}
```

Telegram alert on every transition (regardless of source).

## Loop guard

If `/panic` fires more than 5 times in 1 hour, escalate to Telegram with `severity=critical` and prevent further `/resume` until user manually deletes `.harness/swarm/kill_switch.flag` AND posts an explicit `/resume-confirm <reason>` from the operator chat. Prevents oscillation attacks.

## Verification

1. Set `TAO_SWARM_ENABLED=1`. Confirm swarm runs.
2. Post `/panic` from operator Telegram chat.
3. Within 1 cycle (≤5 min): file-flag exists, swarm cycle log shows "Kill-switch fired", Telegram alert posted.
4. Post `/resume` → file-flag gone, cycle log shows resume, alert posted.
5. Post `/panic` 6 times in 1 hour → escalation alert + `/resume` blocked until manual flag deletion.
6. Dashboard side: click kill button without TOTP → 401. With one TOTP → 401. With both → 200, file-flag set, alert posted.

## Out of scope

- Per-role kill-switch (halt only Margot, leave Scribe running) — Wave 4.
- Time-bounded halt (`/panic 1h`) — Wave 4.
- Cross-org kill (halt swarm in CARSI from Pi-CEO) — separate concern, requires distributed kill protocol.
- Hardware kill switch — out of scope for Pi-CEO.

## References

- Hermes-Swarm Recommendation §5 — 15 mandatory safety controls, kill-switch row
- Existing kill-switch: `swarm/orchestrator.py` `_check_kill_switch()` + `swarm/config.py` `SWARM_ENABLED`
- Existing operator chat: `swarm/config.py` `TELEGRAM_CHAT_ID`
- Topology: `/Users/phill-mac/Pi-CEO/Second-Brain-Agent-Topology-2026-05-01.md`
