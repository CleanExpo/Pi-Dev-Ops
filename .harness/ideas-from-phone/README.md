# Ideas From Phone

This directory holds ideas, feature requests, and bug reports that Phill sent from his phone via Telegram while the marathon rails were running. Markdown files are human-readable receipts; JSONL files are the automation queue consumed by `scripts/process_ideas_inbox.py`.

## How they land here

1. Phill types into Telegram from his phone: `idea: add an RSS feed for the lessons file`
2. `scripts/marathon_telegram_inbox.py` runs on a 5-minute scheduled task, polls Telegram's `getUpdates` API, writes the raw message to `.harness/telegram-inbox/<update_id>.json`
3. `scripts/marathon_watchdog.py` runs on a 30-minute scheduled task, drains the inbox, classifies the message (`idea`, `fix`, `brief`, `note`), and writes the idea to this directory as both a dated Markdown receipt and a daily JSONL queue record
4. `.github/workflows/ideas_inbox_drain.yml` runs `scripts/process_ideas_inbox.py`, which expands each unprocessed JSONL idea into the 2nd brain, creates the Linear ticket, and marks the JSONL record processed

## Filename format

`<update_id:012>.md` — zero-padded Telegram update ID so files sort chronologically.

`YYYY-MM-DD.jsonl` — one JSON object per queued idea. This is the source of truth for the Linear drain job.

## File format

```
# Idea from Phill via Telegram

**Received:** <ISO timestamp>
**From:** Phill

## Raw text

<whatever Phill typed after "idea:">

## Status

Queued. Not yet planned.
```

## JSONL automation format

```json
{"ts":"2026-06-17T02:00:00+00:00","user_name":"Phill","text":"add an RSS feed for lessons","source":"telegram","processed":false,"telegram":{"update_id":42,"message_id":123,"chat_id":"8066...","received_at":"2026-06-17T02:00:00+00:00"}}
```

The drain job only creates Linear work for records where `processed` is false.
