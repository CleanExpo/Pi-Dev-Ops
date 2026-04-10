# Pi-CEO Marathon Escalation Contract

**Question this document answers:** if the autonomous rails stop working while Phill is away, how does he find out, and what does he get?

**One-line answer:** `scripts/marathon_watchdog.py` runs every 30 minutes via a scheduled task. It runs six health checks. If anything critical breaks or requires a founder decision, it pushes a single Telegram message with a strict envelope format so the response is always: glance → decide → type reply. If the problem is safe to self-heal, it heals it silently and logs to `.harness/marathon-watchdog-status.json`.

---

## The envelope format

Every escalation push to Telegram follows this exact structure. It's deliberately short so it fits on a phone lock-screen preview and carries enough context that the founder's reply can be a single line.

```
[SEVERITY] MARATHON WATCHDOG - HH:MM UTC

BROKE (critical):
- <check_name>: <one-line detail>

WARN:
- <check_name>: <one-line detail>

TRIED:
- <what the watchdog attempted autonomously>

NEEDS YOU:
- [<check_name>] <exact decision or one-line command>

REPRODUCE: python3 scripts/marathon_watchdog.py
```

**Severity levels:**
- `CRITICAL` — test suite red, watchdog itself offline, or any check reporting `severity=critical`. Every critical escalation is a direct founder ask.
- `WARN` — something is stale or degraded but the rails are still moving. Escalated only if a founder decision is needed; otherwise logged silently.
- `OK` — no escalation; status written to disk only.

---

## The six health checks

Run every 30 minutes. Each returns `ok`, `severity`, `detail`, and optionally `auto_remediation` and `needs_founder`.

1. **heartbeat** — did the watchdog run itself successfully within the last 4h? Uses `.harness/marathon-watchdog-status.json` as a proxy for rail liveness. If stale, the watchdog task in Cowork → Scheduled has stopped firing.
2. **digest** — has a new Pi-SEO digest appeared in `.harness/monitor-digests/` within the last 2h? (hourly cadence, so 2h = missed a beat)
3. **tests** — does `python3 -m pytest tests/` exit 0? Red tests are always CRITICAL.
4. **lessons** — has `.harness/lessons.jsonl` been updated within 24h? (stale lessons can indicate no work is happening)
5. **scans** — are `.harness/scan-results/*/*.json` files being refreshed by the Railway cron within 12h?
6. **git** — is there unpushed work on `main`? (if yes, one-line ask: `git push origin main`)

Adding a check is one method in `marathon_watchdog.py` that returns a `Check` instance, plus an entry in `run_all_checks()`.

---

## Self-heal vs escalate

The watchdog classifies each run as `green`, `self_heal`, or `escalate`:

- **green** — nothing broken. Exit 0. Status file updated. No Telegram push.
- **self_heal** — only warns with no `needs_founder`. The watchdog logs what it did to stdout and the status file, then exits 1. Telegram stays quiet so Phill's phone doesn't buzz every 30 minutes.
- **escalate** — any critical, or any check with a `needs_founder` message. The watchdog pushes one Telegram message with the full envelope, writes the status file, and exits 2.

If the watchdog itself cannot push to Telegram (network failure, token expired), it exits 3 and writes the envelope to stderr for operator visibility. The next healthy run will push a cumulative summary.

---

## The inbound Telegram channel

Phill can send messages from his phone back to the marathon system. The loop is:

1. Phill types into the chat with `@piceoagent_bot` on Telegram
2. Every 5 minutes, `scripts/marathon_telegram_inbox.py` calls Telegram's `getUpdates` API, filters by allowed chat IDs, and writes each new message as `.harness/telegram-inbox/<update_id:012>.json`. The last-processed update_id is tracked in `.harness/telegram-inbox/.offset` so messages are never processed twice.
3. Every 30 minutes the watchdog drains the inbox at the start of its run, routes each message (see below), and appends an `INBOX:` block to the outbound envelope so Phill gets a confirmation the next time the watchdog speaks.

**Routes (case-insensitive prefix match):**

- `fix <check>` / `@claude fix <check>` / `fix it` → route `fix:<check>` — the watchdog will attempt a known-safe remediation on the next run and log the result
- `brief me` / `brief` / `briefing` / `summary` → route `brief` — watchdog composes a plain-English briefing with options
- `idea: <text>` / `feat: <text>` / `feature: <text>` → route `idea` — watchdog files the raw text to `.harness/ideas-from-phone/<update_id>.md` for Phill to promote to Linear on return
- `note: <text>` → route `note` — filed away
- anything else → route `note`

**Green-run push exception.** The watchdog normally stays silent on OK runs to save phone battery. The one exception: if the inbox had new messages, the watchdog pushes a short green envelope with the `INBOX:` block so Phill knows his messages were received. This is the only case where an OK run generates a Telegram buzz.

## Two response modes Phill can use

### Mode A — "fix it yourself"
Reply on Telegram with `@claude fix <check_name>` or just `fix it`. The next watchdog run will read the last status file, see the ack, and (for known-fixable patterns like the Cowork mount-path bug from 2026-04-11) apply a canned remediation. Unknown issues fall back to Mode B.

### Mode B — "give me the summary + questions"
Reply with `brief me` on Telegram. The next watchdog run composes a `BRIEFING` message with:
- What broke (in plain English, not just the check output)
- What's been tried
- Exactly three options with pros/cons
- The one command Phill needs to run OR the one decision he needs to make

This is useful when Phill wants to understand what's going wrong before authorising a fix.

### Mode C — "here's a new idea, plan it for me"
Type `idea: <whatever you're thinking>` on Telegram. The watchdog files it to `.harness/ideas-from-phone/` for review on return. Deliberate design: ideas are NOT auto-promoted to Linear — that would violate rule 7 on the "never autonomously" list. The human has to bless each one.

---

## What the watchdog will NEVER do autonomously

A short list, deliberately. Anything on this list always escalates, never self-heals:

1. Rotate any API key or secret
2. Execute any `git push --force`, `git reset --hard`, or history rewrite
3. Modify Railway env vars
4. Delete any file in `.harness/lessons.jsonl`, `.harness/decisions/`, or any monitor-digest
5. Call any paid API (OpenAI, Anthropic) in a loop without a circuit breaker
6. Merge any branch to `main`
7. Create or modify a scheduled task that would further amplify the agent's own scope
8. Send email, Slack, or Telegram to anyone except Phill
9. Execute trades, move money, or initiate financial transfers

These are guardrails against the classic failure modes of autonomous loops. If any of these become necessary, the escalation envelope will say so in the `NEEDS YOU` block.

---

## Fallback escalation channels

If Telegram is unreachable, the watchdog currently exits 3 and writes to stderr. Planned improvements (tracked as a future Linear ticket):

- **Gmail draft** — write an escalation draft to the founder's Gmail via the Gmail MCP so there's a visible envelope on the next email sync
- **Linear issue** — auto-create an Urgent issue with the alert envelope as the description, so the board reflects the state even if Phill doesn't check Telegram
- **Railway webhook** — POST the alert to a small webhook endpoint that the Pi-CEO service already exposes, which writes to a dashboard

---

## Testing the watchdog

Any time the watchdog is modified, run:

```bash
TAO_WATCHDOG_DRY=1 python3 scripts/marathon_watchdog.py
```

This runs all checks, composes the envelope, but does not push to Telegram or write the status file. Use `TAO_WATCHDOG_QUIET=1` to suppress the "green" heartbeat logging.

---

## Contract ownership

This contract lives at `.harness/ESCALATION.md` and is the source of truth. The watchdog script, the scheduled task, and the MARATHON-STATUS return briefing all reference it. If the contract changes, the changes must land in a single commit that updates this file, the script, and the task prompt together.
