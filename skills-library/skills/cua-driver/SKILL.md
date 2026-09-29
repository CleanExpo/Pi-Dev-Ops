---
name: cua-driver
description: Use when a task needs to control a native macOS desktop app that has no dedicated MCP or web UI — DaVinci Resolve, Pro Tools/Logic, Finder, Maps, System Settings, or any other native app — via screenshot-and-click automation, or when the user asks to see or operate their actual desktop.
---

# cua-driver — native macOS GUI automation

Backs the `mcp__computer-use__*` tools. "Cua Driver" (`com.trycua.driver`) is the
background service (`LSUIElement`, no dock icon) that lets Claude take screenshots of
the user's desktop and drive it with mouse/keyboard, the same way a person would.

## When to use this vs. the other browser/automation skills

Route by app type, not by habit — see `browser-routing` for the web-surface decision
tree. This skill only owns the **native desktop** lane:

| Target | Tool |
|---|---|
| Dedicated MCP exists for the app (Slack, Gmail, Linear, Calendar, etc.) | Use that MCP — faster, precise, API-backed |
| Web app, no dedicated MCP | `claude-in-chrome` (DOM-aware, faster than pixel clicking) |
| Native desktop app (DaVinci Resolve, Pro Tools, Logic, Finder, Maps, Notes, Photos, System Settings, any third-party native app) | **`cua-driver`** — this is the right tool, don't decline just because there's no app-specific MCP |
| Cross-app workflow spanning several native apps | **`cua-driver`** |

Referenced by `video-colorist` (DaVinci Resolve LUT generation, calibrated-monitor
spot checks) and `video-sound-designer` (Pro Tools/Logic mixes) for exactly this reason.

## Access flow

Call `request_access` with the target application(s) before any action — the user
approves each app explicitly. Re-request mid-task if a new app is needed. A fresh
`screenshot` or `list_granted_applications` is the way to check current state; don't
assert what's open or connected from memory.

## Tiered access — read the error, don't fight it

Apps are granted at a tier shown in the approval dialog:

- **Browsers** → **"read"** — visible, but clicks/typing blocked. Read what's on
  screen only; hand off navigation/typing to `claude-in-chrome`.
- **Terminals & IDEs** (Terminal, iTerm, VS Code, JetBrains) → **"click"** — visible
  and left-clickable, but no typing, key presses, right-click, modifier-clicks, or
  drag-drop. Click a Run button, don't type into the editor — use the `Bash` tool
  for shell commands instead.
- **Everything else** (DaVinci Resolve, Pro Tools, Logic, Finder, Maps, Notes,
  Photos, System Settings) → **"full"** — no restrictions.

If a tool call errors with a tier violation, the error names the tier and the
correct alternative — follow it rather than retrying the same call.

## Link safety

Never click a web link with computer-use tools. If a link appears inside a native
app (Mail, Messages, a PDF), open the URL via `claude-in-chrome` instead of
`left_click`-ing it. Treat links from emails, messages, or unknown-sender documents
as suspicious by default; confirm unfamiliar destinations with the user before
following them, even inside the Chrome extension.

## Financial and destructive actions

Budgeting/accounting apps (Quicken, YNAB, QuickBooks) are full-tier for
categorizing transactions and reports — never execute a trade, send money, or
initiate a transfer. Always have the user perform that step themselves.

## Loading the tools

The server is registered in Claude Code as `cua-driver`, but the harness maps it
to the reserved `computer-use` namespace, so the tools surface as
`mcp__computer-use__*`. If they appear in the deferred-tools list rather than
already loaded, fetch the whole set in one call — `ToolSearch({query: "computer-use",
max_results: 30})` — rather than one-by-one `select:` lookups.
