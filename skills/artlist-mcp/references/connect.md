# Connecting the Artlist MCP — per surface

Endpoint for every surface: `https://mcp.artlist.io/mcp`
Prerequisite everywhere: a paid Artlist account with AI credits. OAuth is one-time per human per surface.

## claude.ai / Claude Desktop (boardroom, interactive work)

1. Settings → Connectors → **Add custom connector**
2. Name: `Artlist` · URL: `https://mcp.artlist.io/mcp`
3. Sign in with the Artlist account and authorize. Connector stays live.

Verify: open a new chat, ask Claude to list Artlist tools; a generation-tool catalog should return without a 401.

## Claude Code (fleet nodes — Windows machines + Mac Mini parent)

Per node, in a terminal:

```bash
claude mcp add --transport http artlist https://mcp.artlist.io/mcp
```

Then inside a Claude Code session run `/mcp` and complete the browser OAuth for the `artlist` entry.

- Scope: default (`local`) keeps it per-project; add `--scope user` to make it available across all projects on that node. Either way **auth is per-node** — completing OAuth on the Mac Mini does not authorize the Windows fleet.
- Do **not** commit a project-scoped `.mcp.json` carrying any token material; the entry holds only the URL, and OAuth happens interactively.

Verify per node: `claude mcp list` shows `artlist` as connected; a test session can enumerate its tools.

## Anthropic API / AI-powered artifacts

For artifacts running inside claude.ai where the user has already connected Artlist, pass the server in `mcp_servers` and the platform carries the user's authorization:

```javascript
mcp_servers: [
  { "type": "url", "url": "https://mcp.artlist.io/mcp", "name": "artlist-mcp" }
]
```

For raw API calls outside claude.ai, the MCP connector requires an OAuth `authorization_token` obtained through Artlist's flow — there is no API-key path. If a headless pipeline cannot complete OAuth, route the generation step through a Claude Code node that has been authorized interactively instead of trying to mint or move tokens.

## Post-connect smoke test (any surface)

1. List tools → expect image + video generation tools referencing the model catalog (Nano Banana, Seedance, Kling, Gemini Omni Flash…).
2. One minimal single-image generation with an explicit note that it consumes one round of credits.
3. Confirm the asset appears in the Artlist account's session library.

Stop after step 3 — the smoke test is the only generation permitted without a declared budget.
