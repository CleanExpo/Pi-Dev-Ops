# Task Brief

[HIGH] [SPRINT-12] Set up automated Google Workspace update monitoring via RSS → n8n → NotebookLM

Description:
## Phase 2 — Foundation Build | Due: May 2

**The exact pattern that closes the update monitoring gap.** This is the RSS → n8n → Google Doc → NotebookLM refresh loop from the community that solves the problem Phill identified.

## Architecture

```
workspaceupdates.googleblog.com (RSS feed)
  ↓ n8n RSS trigger (poll every 6 hours)
  ↓ Filter: only posts matching keywords (Gemini, MCP, Scheduled Actions, NotebookLM, AI agents)
  ↓ n8n: append filtered updates to a Google Doc
  ↓ NotebookLM: refresh notebook source (the Google Doc is a source in the Pi-CEO Intel notebook)
  ↓ Qwen 3 14B: generate "Weekly Workspace Update" executive brief
  ↓ Telegram: post brief to @piceoagent_bot
```

## Setup steps

1. In n8n, add RSS Feed node: `https://workspaceupdates.googleblog.com/feeds/posts/default`
2. Add keyword filter (Gemini, MCP, agent, NotebookLM, scheduled, automation)
3. Add Google Docs node: append filtered items to running "Pi-CEO Workspace Intel" doc
4. Trigger NotebookLM refresh on the doc
5. Schedule weekly brief generation via Qwen 3 14B

## Acceptance

* n8n workflow active and polling RSS feed
* At least one filtered update captured and appended to Google Doc
* NotebookLM notebook reflects updated content
* Weekly brief delivered to Telegram

Linear ticket: RA-826 — https://linear.app/unite-group/issue/RA-826/sprint-12-set-up-automated-google-workspace-update-monitoring-via-rss
Triggered automatically by Pi-CEO autonomous poller.


## Session: 52cbfb296629
