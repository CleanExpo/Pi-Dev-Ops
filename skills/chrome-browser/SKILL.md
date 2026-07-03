---
name: chrome-browser
description: Use when the user asks to browse, click, navigate, fill a form, screenshot, or read content from a live website via the claude-in-chrome MCP tools — or whenever a task needs to drive an actual Chrome tab rather than fetch static HTML.
---

# chrome-browser — driving Chrome via the claude-in-chrome MCP tools

Patterns for the `claude-in-chrome` MCP tool set: `navigate`, `computer`, `read_page`,
`get_page_text`, `find`, `tabs_context_mcp`, `tabs_create_mcp`, `tabs_close_mcp`,
`form_input`, `javascript_tool`, `read_console_messages`, `read_network_requests`,
`browser_batch`, `gif_creator`, `file_upload`, `upload_image`, `resize_window`,
`select_browser`, `switch_browser`, `list_connected_browsers`, `shortcuts_list`,
`shortcuts_execute`.

## Load the tools first

If these tools are deferred (unloaded), load the core set in one `ToolSearch` call —
never one tool at a time, each separate call wastes a round-trip:

```
ToolSearch query: "select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__tabs_create_mcp"
```

Add task-specific tools to that **same** call when the task obviously needs them —
`read_console_messages` / `read_network_requests` for debugging, `form_input` for
forms, `gif_creator` for recordings, `javascript_tool` for page scripting. Only issue
a second `ToolSearch` call if the task later needs a tool you didn't anticipate.

Never hardcode the `mcp__claude-in-chrome__*` prefix outside a `ToolSearch` query —
resolve by capability, not by memorized string.

## Check tab context before acting

Call `tabs_context_mcp` before your first `navigate` or `computer` call in a session.
It tells you which tabs already exist and which is active — don't assume a blank
tab or that yours is the only one open. If the user is mid-workflow in a specific
tab, act on that tab rather than opening a new one.

## Reading page content: read_page vs get_page_text vs find

- **`get_page_text`** — fast plain-text extraction. Default choice when you need to
  know what's on the page (an article, a form's visible labels, search results) and
  don't need DOM structure or element handles to act on.
- **`read_page`** — structured DOM read (roles, element references, hierarchy). Use
  when you need to *act* next — click a specific button, fill a specific field — and
  `get_page_text` alone doesn't give you an addressable target.
- **`find`** — locate a specific element by description when you already know what
  you're looking for and don't need the whole page. Cheaper than a full `read_page`
  for one-target lookups (e.g. "find the submit button").

Rule of thumb: reading to *understand* → `get_page_text`. Reading to *act* →
`read_page` or `find`. Don't call `read_page` for a full DOM dump when `find` for one
element would do — it costs more context for no benefit.

## Navigation and tabs

- `navigate` changes the current tab's URL. `tabs_create_mcp` opens a new tab —
  prefer this over `navigate` when the user's current tab holds context you'd lose
  (an in-progress form, a login session tied to that tab's history).
- Close tabs you opened for a sub-task with `tabs_close_mcp` once done, unless the
  user is likely to want the result tab left open (e.g. they asked you to "open X for
  me" — that's a deliverable, not scratch work).
- `browser_batch` groups multiple browser actions into one call — use it for a known
  sequence (navigate → find → click → read) instead of round-tripping each step
  individually when the sequence doesn't depend on intermediate results changing the
  plan.

## Acting on the page

- `computer` drives raw mouse/keyboard actions (click, scroll, type) against
  coordinates or elements — the general-purpose actuator.
- `form_input` is purpose-built for filling form fields; prefer it over `computer`
  when the target is a labeled input, select, or textarea — it's more reliable than
  coordinate-based typing.
- `javascript_tool` executes JS in the page context — use for reading computed state
  the DOM tools don't expose, or triggering behavior no visible control maps to
  cleanly. Don't use it to bypass a form the user could fill normally; prefer the
  visible-UI path so the result matches what a human would have done.

## Debugging

- `read_console_messages` and `read_network_requests` are diagnostic, not action
  tools — reach for them when a page isn't behaving as expected (a click did
  nothing, a form didn't submit) before guessing at a fix.
- `gif_creator` records a visual trace of a session — use when the deliverable is
  showing someone *what happened*, not just reporting it in text.

## Common pitfalls

- **Acting before checking tab context.** Calling `navigate` or `computer` cold, without
  `tabs_context_mcp` first, risks acting in the wrong tab or clobbering the user's
  in-progress work.
- **Full `read_page` when `find` would do.** A structured DOM dump for a single-element
  lookup burns context for no gain.
- **Treating `javascript_tool` as a shortcut past a broken UI.** If a button doesn't
  respond, that's a signal to debug via `read_console_messages`, not to script around
  the symptom — the underlying issue (page not loaded, wrong tab, stale selector) will
  resurface.
- **Leaving tabs open indefinitely.** Scratch tabs opened mid-task should be closed
  with `tabs_close_mcp` once their purpose is served, or they accumulate across a
  session.
- **One tool at a time via `ToolSearch`.** Always batch the anticipated tool set into
  a single `ToolSearch` call at the start of a browser task.

## Out of scope

This skill does not, and cannot, configure which Anthropic account or subscription
plan (e.g. Max Plan) the Chrome extension authenticates against. That binding happens
at `claude login`, outside anything a skill's markdown content can read or influence.
If a user asks to "connect the right plan," say so directly rather than attempting a
workaround here.

**Completion criterion:** the tools needed for the task are loaded via one batched
`ToolSearch` call, `tabs_context_mcp` has been checked before the first action, and
the chosen read tool (`get_page_text` / `read_page` / `find`) matches whether the goal
is understanding or acting.
