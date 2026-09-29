---
name: connector-routing
description: Decide which connector path to use for a given integration task — Desktop MCP, claude.ai cloud connector, or Composio. Use when the user asks to "connect X", "talk to X from a routine", "post to X", or anywhere a third-party service (Linear, Slack, GitHub, Gmail, etc.) needs to be reached. Composio is the cross-environment default; claude.ai connectors are per-account fragile; Desktop MCP is local-only. Pick the right substrate before promising integration work.
---

# Connector Routing

The user has three substrates for reaching third-party services. Picking the wrong one is the single biggest source of "you said it was fixed, it's broken again" frustration.

## The three substrates

| Substrate | Where it lives | Stable? | Use for |
|---|---|---|---|
| **Desktop MCP** | `~/Library/Application Support/Claude/claude_desktop_config.json` | ✅ Stable, machine-local | Interactive Claude Code on this Mac (Linear, Perplexity already here) |
| **claude.ai cloud connector** | OAuth at https://claude.ai/customize/connectors | ⚠ Per-account fragile (multi-Gmail bites here) | Web claude.ai chat sessions where the user is signed in to the matching account |
| **Composio** | `~/.composio/composio` CLI + `phill.mcgurk_workspace` | ✅ Stable, account-independent, cross-environment | Cloud routines (CCR), automation, anywhere Desktop MCP can't reach |

## Decision tree

**Question 1: Where will the call actually run?**

- **In this Claude Code session on the user's Mac** → Use Desktop MCP if the toolkit is already configured there (Linear is). Use Composio CLI for anything else.
- **In a remote/cloud routine (CCR)** → Use Composio. Skip claude.ai connectors — they require account binding the cloud sandbox cannot guarantee.
- **In a claude.ai web chat** → Use claude.ai cloud connector IF the user confirms they are signed in to the account that owns the connector. Otherwise default to Composio.

**Question 2: Does the toolkit exist in Composio?**

```bash
~/.composio/composio search "<task>" --human
~/.composio/composio tools list <toolkit> --query "<keyword>"
```

If yes → use it. If no → fall back to Desktop MCP / direct API.

**Question 3: Is there account-state risk?**

If the integration involves OAuth and the user has multiple accounts on the same provider (Gmail, GitHub orgs, Linear workspaces), **default to Composio** — its `phill.mcgurk_workspace` is one stable identity, while claude.ai/Chrome multi-account contexts are the failure mode that has caused repeated "fixed-but-broken" cycles.

## When NOT to invoke this skill

- Trivial follow-ups on an integration the user has already chosen
- Pure local file/code work — no third-party service involved
- Read-only checks where the answer is obvious (e.g. "use the Linear MCP I already have")

## Hard rules

1. **Never claim a claude.ai cloud connector is "ready" without verifying it appears in the schedule skill's connector list.** If it's not there, it's not connected from this CLI's account.
2. **For any new cloud routine that needs a third-party API, use Composio first.** Don't reach for claude.ai connectors as the default — they're fragile.
3. **The user's Composio API key is in `phill.mcgurk_workspace`.** Treat it as a secret. Never write it to a skill file or memory entry. Pass to cloud routines via the routine prompt only.
4. **For local interactive work, prefer the Desktop MCP path when it already exists** (Linear, Perplexity) — it's zero-config and proven.

## Quick reference — what's connected where (as of 2026-04-27)

- **Desktop MCP**: Linear (working), Perplexity (working), Pi-CEO MCP (`mcp__pi-ceo__*`, working)
- **Composio (`phill.mcgurk_workspace`)**: linear (ACTIVE, `ca_YWZm5__2E7Z6`), youtube, outlook, reddit (active); elevenlabs, firecrawl (initiated, incomplete)
- **claude.ai cloud connectors**: history of intermittent visibility tied to multi-Gmail account confusion — assume unreliable until verified each session

## Pairing with composio-cloud-routine

For any cloud routine work, after picking Composio, jump to the `composio-cloud-routine` skill for the exact install + login + execute pattern that runs inside a CCR sandbox.
