---
name: restoreassist-scheduled-tasks
description: Use when creating, editing, or fixing scheduled tasks on claude.ai/code/scheduled for RestoreAssist cron endpoints
---

# RestoreAssist — Cloud Scheduled Task Management

## Overview

Manages the 4 RestoreAssist scheduled tasks on `claude.ai/code/scheduled` that trigger video pipeline cron endpoints.

## Credentials

- **CRON_SECRET**: never written here. It lives in the RestoreAssist DigitalOcean app (component `web`, type SECRET) and in the GitHub repo secret `CRON_SECRET`. The founder pastes it into each trigger's prompt; an agent never reads or copies it
- **Base URL**: `https://restoreassist.app`
- **Repo**: `CleanExpo/RestoreAssist`

## The 4 Triggers

| Name | ID | Endpoint | Schedule |
|------|----|----------|----------|
| RestoreAssist — Generate Content | `trig_01Dz2mApC4izdDrHubBWbpL2` | `/api/cron/generate-content` | Daily 6:00 AM GMT+10 |
| RestoreAssist — Poll HeyGen | (hourly) | `/api/cron/poll-heygen` | Hourly :10 |
| RestoreAssist — Distribute Content | `trig_016BoGwMAeDWpEiuKeCeVMoC` | `/api/cron/distribute-content` | Daily 9:10 AM GMT+10 |
| RestoreAssist — Collect Analytics | `trig_01KQo7obsiHCrhxdFaMxVTVX` | `/api/cron/collect-analytics` | Daily 12:00 PM GMT+10 |

## Plan Limits

The current plan allows **1 hourly** cloud scheduled session. Only one trigger can be Hourly — Poll HeyGen holds this slot. All others must use Daily or longer.

## Correct Prompt Template

```
Run the RestoreAssist {name} cron job by executing this command in Bash:

curl -s -w '\nHTTP_STATUS:%{http_code}' -X GET https://restoreassist.app/api/cron/{endpoint} -H 'Authorization: Bearer <CRON_SECRET>'

Report the HTTP status code and response body. A 200 response means success. Any non-200 is failure — report the full error.
```

## CRITICAL: Use `form_input`, Never `type`

The `type` action in Chrome mangles special characters in textareas:
- `'` becomes `restoreassist.pp` (drops letter)
- `Bearer` becomes `Berer`
- CRON_SECRET gets truncated

**Always use `form_input` with `ref_XX` to set textarea values.**

```
# Step 1 — read_page to get the textarea ref
mcp__Claude_in_Chrome__read_page (filter: interactive)
→ find textbox "Prompt" → note its ref_XX

# Step 2 — set value directly
mcp__Claude_in_Chrome__form_input ref=ref_XX value="<full prompt>"
```

## Edit Flow

1. Navigate to `https://claude.ai/code/scheduled/<trigger-id>`
2. Use `read_page` to find the unlabelled button refs near "Run now" — the edit (pencil) button is ref_66 or similar
3. Click edit button by ref, not by coordinate
4. Dialog opens — use `read_page` to find `textbox "Prompt"` ref
5. Use `form_input` to set the full prompt
6. Verify schedule is correct (Daily, not Hourly unless it's Poll HeyGen)
7. Scroll down — find Save button ref via `find "Save button"`
8. Click Save by ref

## Verification After Save

- Toast "Scheduled task saved." appears top-right
- "Runs daily at HH:MM GMT+10" (or "Runs every hour") shown
- Instructions panel shows correct URL with `restoreassist.app` (not `restoreasist`)
- Authorization header shows `Authorization: Bearer` (not `Authorizatio:`)
