---
name: claude
description: Correct patterns for Claude SDK usage, subprocess vs API mode selection, MCP SDK imports, and streaming API call conventions in the Pi-Dev-Ops codebase.
---

# Claude SDK & Runtime Patterns

## When to apply

Apply whenever touching Claude SDK invocations, MCP server imports, subprocess vs API mode selection, or streaming message handling.

## Rules

- The TAO engine in `src/tao/` is stub scaffolding — it is NOT used by the web server. All intelligence is delegated to Claude via the SDK (API key mode). Check the `ANALYSIS_MODE` env var: Railway deployments must use API mode, not CLI mode.
- `claude -p` subprocess mode requires the Claude Code CLI installed in PATH. In cloud environments (Railway), Claude Code is NOT available — cloud deployments must use `ANTHROPIC_API_KEY` + SDK mode exclusively.
- MCP SDK subpath imports are required: `'@modelcontextprotocol/sdk/server/mcp.js'` and `'../server/stdio.js'`. The top-level `'@modelcontextprotocol/sdk'` import does NOT export `McpServer` directly — importing from it will fail silently or throw at runtime.
- When using `claude_agent_sdk.ClaudeSDKClient`, use the public `async for message in client.receive_response()` loop — NOT the private `_query.receive_messages()`. Private API methods break on SDK upgrades.
- The AbortController `signal` must be passed to `client.messages.stream()` as the second options argument: `client.messages.stream({...}, { signal })` — not inside the first object. Placing it inside the first argument silently ignores the abort signal.
