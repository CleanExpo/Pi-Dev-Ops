---
name: plaud-shared
version: 1.0.0
description: "First read before any Plaud operation. Auth flow, error handling, output conventions, token refresh. Use when the user mentions Plaud for the first time in a session, or when any other Plaud skill is invoked."
metadata:
  requires:
    bins: []
---

# plaud-shared

**CRITICAL — read this before calling any Plaud tool.** Applies to every other `plaud-*` skill.

## Authentication

- Plaud MCP uses OAuth. MCP tokens are stored in `~/.plaud/tokens-mcp.json` and refreshed automatically. The terminal CLI uses `~/.plaud/tokens.json` separately.
- If any tool returns an auth error (message includes `Not authenticated` or `401`), call the `login` tool and wait for the browser callback. Do **not** retry the original tool until login returns success.
- Never ask the user to paste tokens. The `login` tool handles the whole flow.

## Tool inventory

| Tool | Purpose |
|---|---|
| `login` | Open browser for OAuth; blocks until callback or 2-min timeout |
| `logout` | Revoke and clear tokens |
| `get_current_user` | Verify who is signed in |
| `list_files` | Browse, paginate, filter recordings (supports `query`, `date_from`, `date_to`) |
| `get_file` | Full record incl. `presigned_url`, `source_list`, `note_list` |
| `get_note` | AI-generated summary and action items |
| `get_transcript` | Timestamped transcript with speaker labels |

## Error semantics

| Pattern in error message | Meaning | What to do |
|---|---|---|
| `401` / `Not authenticated` | Token missing or expired | Call `login`, then retry |
| `404` | File ID does not exist | Tell the user the ID is wrong; do not retry |
| `500` | Backend error (often an invalid ID too — see §7.1 of proposal) | Retry once; if still 500, treat as NOT_FOUND |
| `fetch failed` / `ECONNREFUSED` | Network problem | Abort; tell user to check connection |

## Output conventions

When presenting recordings to the user:

- Always show name, date, duration, and file ID — users need the ID to ask follow-up questions.
- Format durations human-readable: `23s`, `5m23s`, `1h05m`. Raw milliseconds are for logs only.
- Format dates as `YYYY-MM-DD` in local time.
- Transcripts: preserve `[MM:SS - MM:SS] Speaker: content` format.
- Notes: render Markdown directly.

## Data model quick reference

- `duration` field is **milliseconds**.
- `source_list` — array; each item with `data_type === "transaction"` holds the transcript segments (JSON-encoded string in `data_content`).
- `note_list` — array; each item with `data_type === "auto_sum_note"` holds the AI summary (Markdown in `data_content`).
- `presigned_url` — expires in 24 hours; re-fetch with `get_file` if stale.

## When to load which sibling skill

| User intent | Skill to follow |
|---|---|
| "List / show / browse my recordings" | `plaud-browse` |
| "Find the meeting about X" / "from Monday" | `plaud-find` |
| "Show transcript / summary / audio" | `plaud-read` |
| "Weekly digest" / "what did I have this month" | `plaud-digest` |
| "Draft follow-up" / "action items" / "thank-you email" | `plaud-followup` |
| "Save to Notion / Slack / webhook" | `plaud-export` |
