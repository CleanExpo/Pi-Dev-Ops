# Marathon Telegram Inbox

This directory is the inbound half of the marathon Telegram loop. Each file here is one message Phill sent from his phone while the autonomous rails were running. The poller writes them; the watchdog drains them.

## Layout

```
.offset                 last-processed Telegram update_id (never delete)
README.md               this file
<update_id>.json        one message from Phill, routed by the watchdog
```

## Message file schema

```json
{
  "update_id": 42,
  "message_id": 123,
  "chat_id": "8066...",
  "from": "Phill",
  "date": "2026-04-11T23:45:00+00:00",
  "text": "idea: add an RSS feed for the lessons file",
  "processed": false,
  "received_at": "2026-04-11T23:45:07+00:00",
  "route": "",
  "route_result": ""
}
```

`route` is set by the watchdog on drain. Allowed values:

- `fix:<check_name>` — known self-heal, watchdog attempted the fix
- `brief` — user asked for a plain-English summary + options
- `idea` — a new feature or bug the user wants queued; watchdog writes a brief to `.harness/ideas-from-phone/<update_id>.md` and replies with a confirmation + ticket placeholder
- `note` — anything else, logged for the next return-briefing

## How Phill uses this from his phone

Supported prefixes, case-insensitive:

- `fix <check>` — e.g. `fix tests` — watchdog runs a known remediation
- `brief me` — watchdog composes a plain-English briefing next run
- `idea: <text>` — queued as a new work item
- `feat: <text>` — same as `idea:`
- `note: <text>` — filed away without action
- anything else — treated as `note`

Replies are always sent back to the same chat via `send_telegram.py`.

## Garbage collection

Processed files older than 7 days are removed automatically on each poll run. `.offset` and `README.md` are never touched.
