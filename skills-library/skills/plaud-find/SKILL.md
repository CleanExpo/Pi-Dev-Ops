---
name: plaud-find
version: 1.0.0
description: "Find a specific Plaud recording by name keyword, date range, or topic. Use when the user says 'find the Weekly Sync', 'the meeting from Monday', 'the call about Q2', 'recordings last week', or describes what they're looking for rather than listing."
metadata:
  requires:
    bins: []
---

# plaud-find

**Read [`plaud-shared`](../plaud-shared/SKILL.md) first.**

## Background

Plaud's `list_files` API does **not** accept `query` / `date_from` / `date_to` server-side — unknown params are silently ignored. Filtering happens client-side.

The MCP `list_files` tool accepts the same three optional params and performs the filter for you: pass the user's keyword and/or date window and let the tool paginate up to 5 pages.

## Steps

1. **Elicit criteria if vague.** If the user just said "find a recording", ask for at least one of:
   - a name keyword (even a partial match),
   - a rough date or date range,
   - a duration range (less useful, ask only if name and date fail).
2. **Call `list_files`** with the filter params you gathered:
   - `query=<keyword>` — case-insensitive substring match on `name`.
   - `date_from=YYYY-MM-DD`, `date_to=YYYY-MM-DD` — inclusive window on `created_at`.
   - Omit any that the user did not specify.
3. **If zero matches**, ask the user to broaden one axis (shorter keyword, wider date range).
4. **If many matches** (> 10), return the top 10 sorted by `created_at` desc and mention the total.
5. **Never auto-load transcripts**. Present the match list and wait for the user to pick one — that triggers `plaud-read`.

## Date interpretation rules

| User phrase | Filter |
|---|---|
| "today" | `date_from` = today, `date_to` = today |
| "yesterday" | both = yesterday |
| "this week" | Monday of this week → today |
| "last week" | Monday of last week → Sunday of last week |
| "this month" | 1st of this month → today |
| "last month" | 1st → last day of previous month |
| "from Monday" | `date_from` = the most recent Monday, no `date_to` |

Resolve relative dates against the **current date** (from conversation context), not the model's training cutoff.

## Example

User: "find the customer onboarding call from last week"

Agent:
- `list_files(query="onboarding", date_from="2026-04-13", date_to="2026-04-19")`
- Return matches: "Found 2 recordings. `abc123` Customer Onboarding — Acme (2026-04-15, 42m), `def456` Onboarding Q&A (2026-04-17, 18m). Which one?"
