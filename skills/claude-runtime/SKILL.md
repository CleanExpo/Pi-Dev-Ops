---
name: claude-runtime
description: Rules for invoking Claude correctly — subprocess vs SDK mode, stream-json parsing, MCP SDK imports, Railway vs local environment differences.
---

# Claude Runtime Best Practices

Apply when writing code that invokes Claude (subprocess, SDK, or MCP).

## Rules

- **TAO engine (`src/tao/`) is stub scaffolding.** It is not used by the web server. All intelligence is delegated to `claude -p` subprocess via `stream-json` output. Parse events: `system`, `assistant` (text + `tool_use`), `tool_result`, `result`.

- **`claude -p` subprocess requires Claude Code CLI in PATH.** In cloud (Railway), the CLI is NOT available — cloud deployments must use `ANTHROPIC_API_KEY` + `claude_agent_sdk`. Check `TAO_USE_AGENT_SDK` env var to switch paths.

- **MCP SDK subpath imports are required.** Use `@modelcontextprotocol/sdk/server/mcp.js` and `@modelcontextprotocol/sdk/server/stdio.js`. The top-level `@modelcontextprotocol/sdk` import does NOT export `McpServer` directly.

- **`claude_agent_sdk` is the chosen Python SDK path.** Managed Agents API (`client.beta.agents`) was rejected — 0 successful PoC cycles, schema blocker on `config.setup_commands`. See `.harness/agents/sdk-migration-plan.md`.
