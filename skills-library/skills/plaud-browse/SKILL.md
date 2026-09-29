---
name: plaud-browse
version: 1.0.0
description: "Browse, list, or paginate through Plaud recordings. Use when the user says 'what recordings do I have', 'show my recent recordings', 'list my recordings', or asks to see the most recent uploads."
metadata:
  requires:
    bins: []
---

# plaud-browse

**Read [`plaud-shared`](../plaud-shared/SKILL.md) first** for auth and output conventions.

## When to use

- User wants to see what is in their library without a specific target in mind.
- User explicitly asks for a page, or says "next page", "more results".
- User asks "what's the most recent recording" — fetch page 1 and return the top item.

## Steps

1. Call `list_files` with `page=1` and `page_size=20` (default). No `query` / `date_from` / `date_to` unless the user said something that matches `plaud-find`.
2. Present results in a compact table: **ID**, **NAME**, **DATE** (`YYYY-MM-DD`), **DURATION** (`5m23s` style).
3. If the page looks like the whole library (fewer than `page_size` returned), tell the user there is no next page.
4. If the user asks for more, increment `page` by 1 and call again.

## Anti-patterns

- Do **not** fetch every page eagerly; pagination is lazy.
- Do **not** call `get_note` or `get_transcript` during a browse — that belongs to `plaud-read` and burns tokens.
- Do **not** expose raw timestamps or durations in milliseconds.

## Example

User: "show me my recordings"

Agent:
- `list_files(page=1, page_size=20)`
- Render table, mention "page 1, say 'next page' for more"
