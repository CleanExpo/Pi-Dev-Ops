---
name: artlist-mcp
description: Use when a task needs AI image or video generation — campaign visuals, hero shots, product or social video, thumbnails, ad creative, localized creative variants — through the official Artlist MCP (mcp.artlist.io, 100+ models incl. Nano Banana, Seedance 2.0, Kling, Gemini Omni Flash). Use also before any autonomous run that could touch media generation, because it carries the credit-spend gate. Covers connection per surface, model selection, the iterate-in-conversation loop, and failure handling.
---

# Artlist MCP

Official remote MCP for Artlist's AI Toolkit: image and video generation across 100+ models, invoked from inside a Claude conversation or agent run. Assets return inline and auto-save to a session library in the Artlist account.

## Ground truth (verified 2026-07-10)

- **Endpoint:** `https://mcp.artlist.io/mcp` — remote streamable-HTTP MCP, OAuth-protected (unauthenticated → 401). Launched by Artlist 2026-07-06.
- **There is no open-source Artlist MCP.** GitHub code search for the endpoint returns nothing; no repo, npm package, or awesome-mcp listing implements one; Artlist publishes no official GitHub org. Community "artlist" repos are downloaders/scrapers, several ToS-violating. **Never build or adopt a bespoke Artlist server — connect the official one.** Artlist exposes no public generation REST API; the MCP is the sanctioned programmatic surface.
- **Billing:** paid Artlist accounts with AI credits. Every generation consumes credits; MCP usage is excluded from unlimited-generation plans. Treat every call as real spend.
- **Not in the Claude connector directory** — it is added as a *custom connector*. See `references/connect.md`.

## How to use it

1. **Discover tools at runtime.** The model catalog (100+ and changing) is exposed through the server's live tool list — resolve by capability via ToolSearch, never hardcode `mcp__…` prefixes. That list is the source of truth; if a named model is missing, re-list before concluding it's gone.
2. **Brief, don't prompt-engineer.** Describe the deliverable (subject, mood, format, market); the server maps intent to model parameters. Ask the MCP itself for a model recommendation when the brief is ambiguous.
3. **Iterate in-thread.** brief → 2–3 directions → review inline → pick one → refine ("darker", "wider", "more movement") → localize variants. Context persists; never re-brief from scratch.
4. **Match model to brief-part.** Verify against the live list: stills/hero → Nano Banana or Gemini Omni Flash; motion/product video → Seedance 2.0 (2.5 announced) or Kling.
5. **Retrieval.** Every generation lands in a dedicated session in the Artlist account, searchable by description — cite the session when handing assets on, so nothing is re-generated (re-generation = duplicate spend).

## Governance — charter-bound

Generation consumes paid credits, so it sits under the **spend** rules of `self-improvement-charter`:

- **Autonomous / unattended runs:** generation permitted only when the run declares a pre-approved credit budget at start. On exhaustion: stop and report. An agent never raises its own cap; a denied spend gate is terminal.
- **No unattended bulk loops.** Batch generation (campaign matrices, per-market fan-outs) requires explicit human sign-off on batch size before the first call.
- **Interactive sessions:** confirm with the human before any burst larger than ~3 generations.
- **Auth is per-human, per-surface.** OAuth tokens are never exported, shared between fleet nodes, or committed. A 401 means re-authenticate through the official flow — nothing else.
- **Licensing check before shipping.** Confirm the account tier covers the intended commercial use before an asset leaves the boardroom or lands in client work.

## Nexus wiring

Registered in `agentskills.json`; consumers (CCW-CRM boardroom, fleet nodes, Synthex) receive it through the live-fetched Nexus Prompt — **never fork this file into a consuming repo**, same rule as the Nexus Prompt. Boardroom runs count as autonomous runs and pass through the spend gate above. Pairs with other connectors in one conversation (Drive brand guides, Linear briefs): pull context first, then generate.

## Failure modes

| Symptom | Meaning | Action |
|---|---|---|
| 401 from endpoint | OAuth expired or never completed | Re-auth via the surface's official flow; do not retry blind |
| Credit/quota error | Budget exhausted | Stop, report spend, await human — never retry-loop |
| Named model absent | Catalog rotated | Re-list tools; pick nearest equivalent or ask MCP to recommend |
| Connector missing on a fleet node | Node never authorized | Follow `references/connect.md`; auth is per-node, no fleet-wide token |

## References

- `references/connect.md` — connection steps for claude.ai/Desktop, Claude Code (fleet nodes), and the API, plus post-connect verification. Read when installing on a new node.
