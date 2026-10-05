---
name: plaud-export
version: 1.0.0
description: "Push Plaud content or a generated artifact to Notion, Slack, HubSpot, Linear, Gmail, or a custom webhook. Use when the user says 'save to Notion', 'post to Slack', 'send to webhook', 'file this in HubSpot', or asks to deliver recording content to an external system."
metadata:
  requires:
    bins: []
---

# plaud-export

**Read [`plaud-shared`](../plaud-shared/SKILL.md) first.**

## When to use

- User has a ready artifact (from `plaud-followup`) or recording content and wants to **deliver** it somewhere.
- Destination is an external system (not the chat).

## Out of scope

- Generating the artifact — that's `plaud-followup`.
- Reading recording content — that's `plaud-read`.

This skill is the final leg: take content that already exists and send it.

## Steps

1. **Confirm the payload.**
   - Recording summary (raw `get_note` content)?
   - Generated artifact (email, SOAP, brief — already drafted)?
   - Raw transcript excerpt?
2. **Confirm the destination + identifiers.** Ask for the exact target. Plaud does not store destination credentials.
3. **Deliver using the MCP tool or integration available in the user's environment.** Plaud MCP itself does not expose a `push` tool — this skill assumes another MCP (Notion MCP, Slack MCP, a webhook tool, Gmail send) is available in the session.
4. **Report the delivery URL** (Notion page URL, Slack message permalink, webhook HTTP status) back to the user.

## Destination identifier cheat-sheet

| Destination | Required identifier | Typical ask |
|---|---|---|
| Notion | page ID or database ID | "Which Notion page should this go under?" |
| Slack | channel name or ID | "Which channel? (e.g., `#sales` or `C0123`)" |
| HubSpot / Salesforce | CRM object ID (deal / contact / company) | "Which deal/contact should this attach to?" |
| Linear | team or project ID | "Which Linear team or project?" |
| Gmail | recipient email(s) | "Who should this email go to?" |
| Webhook | full URL | "Paste the webhook URL" |

## Anti-patterns

- Never persist destination credentials in the conversation or in files. Assume the MCP host provides them.
- Never send to a default destination ("I'll put it in `#general`") — always confirm.
- Never alter the artifact content during delivery. If Slack needs mrkdwn, convert format without changing meaning.
