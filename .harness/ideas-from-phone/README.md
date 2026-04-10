# Ideas From Phone

This directory holds ideas, feature requests, and bug reports that Phill sent from his phone via Telegram while the marathon rails were running. Each file is one idea.

## How they land here

1. Phill types into Telegram from his phone: `idea: add an RSS feed for the lessons file`
2. `scripts/marathon_telegram_inbox.py` runs on a 5-minute scheduled task, polls Telegram's `getUpdates` API, writes the raw message to `.harness/telegram-inbox/<update_id>.json`
3. `scripts/marathon_watchdog.py` runs on a 30-minute scheduled task, drains the inbox, classifies the message (`idea`, `fix`, `brief`, `note`), and writes the idea to this directory as a dated markdown file
4. Next manual session: Phill reads these files, promotes the good ones to Linear issues, discards the rest

## Filename format

`<update_id:012>.md` — zero-padded Telegram update ID so files sort chronologically.

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

## Not autonomous promotion to Linear

Deliberate design choice: the watchdog does NOT auto-create Linear issues from inbox messages. That would amplify the agent's scope without a human in the loop, which violates rule 7 in `.harness/ESCALATION.md`. Instead, the watchdog files the idea here and on return Phill promotes it himself in one `mcp__pi-ceo__linear_create_issue` call per keeper.
