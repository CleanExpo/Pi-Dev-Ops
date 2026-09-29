---
name: ctx
description: Context health check. Shows token pressure and recommends one action to reduce waste.
disable-model-invocation: true
---

## Protocol

1. Estimate current context usage based on conversation length.
2. Count files read in this session (from tool history).
3. Note active MCP connections.
4. Check if any large files were read that could be freed.

## Output (one line each)

- **Context**: ~X% estimated usage
- **Files loaded**: N files (~X lines total)
- **MCP overhead**: N active servers
- **Recommendation**: ONE specific action (e.g., "compact now — save PROGRESS.md first", "disconnect unused MCP server X", "context is clean — continue working")
