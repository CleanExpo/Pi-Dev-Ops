---
name: margot-bridge
description: Bridge from Pi-CEO orchestrator to Margot's standalone Gemini-powered research MCP server at ~/.margot/. Use when intent is research-shaped (deep_research / deep_research_max) or image-gen, or when corpus diagnostic is needed. Margot is owned separately; this skill never modifies her source.
owner_role: Margot
status: wave-1
---

# margot-bridge

Pi-CEO calls Margot via MCP. Margot is at `~/.margot/margot-deep-research/server.py` — a FastMCP server with five tools. This skill is the contract Pi-CEO uses to invoke them.

## Prerequisites (one-time admin, user-side)

Before this skill works end-to-end, Margot must be registered as an MCP server in the runtime that's calling her. **Pre-flight on 2026-05-01 confirmed she is not yet registered.**

### For Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` under `mcpServers` (create the block if missing):

```json
{
  "mcpServers": {
    "margot": {
      "command": "python3",
      "args": ["/Users/phill-mac/.margot/margot-deep-research/server.py"],
      "env": {
        "MARGOT_FILE_SEARCH_STORE": ""
      }
    }
  }
}
```

Restart Claude Desktop. Margot's tools appear as `mcp__margot__deep_research`, etc.

### For Claude Code (CLI)

```sh
claude mcp add margot python3 /Users/phill-mac/.margot/margot-deep-research/server.py
```

### For Pi-CEO orchestrator (server-side)

Margot's MCP runs as a subprocess. Pi-CEO orchestrator spawns it on demand; the Python `mcp` client library handles stdio transport. Wave 2 wiring lives in `swarm/orchestrator.py`.

## When to invoke

| Intent class (from intent-parser) | Margot tool | Sync or async |
|---|---|---|
| `research` (urgent, ≤30s budget) | `deep_research(topic, use_corpus=False)` | sync |
| `research` (corpus-grounded, ≤30s) | `deep_research(topic, use_corpus=True)` | sync |
| `research` (deep, no time pressure) | `deep_research_max(topic, use_corpus=True)` | async — returns `interaction_id` |
| `image` | `image_generate(prompt, aspect_ratio, image_size)` | sync |
| `diagnostic` (smoke test) | `corpus_status()` | sync |

## Async pattern for deep_research_max

```
1. Caller: dispatch_research(topic) → margot-bridge calls deep_research_max
2. Bridge returns: {"interaction_id": "...", "status": "dispatched", "eta_minutes": 5-20}
3. Bridge writes to .harness/margot_inflight.jsonl with timestamp + interaction_id + originating_session_id
4. swarm/orchestrator.py polls margot_inflight.jsonl every cycle
5. For each in-flight entry: bridge calls check_research(interaction_id)
   - status == "running": skip
   - status == "complete": move entry to .harness/margot_complete.jsonl, fan out to Scribe for draft
   - status == "failed": log + Telegram alert (no retry; Margot decides retries)
6. Stale entries (>1h with no status change) flagged for user review, not auto-cancelled
```

## Contract

**Inputs:** the canonical Telegram-intent payload from `intent-parser`:
```json
{
  "intent": "research",
  "topic": "...",
  "time_budget": "quick" | "deep",
  "use_corpus": true | false,
  "originating_session_id": "..."
}
```

**Outputs (sync):** Margot tool's raw response, unmodified, for the caller to thread to Scribe.

**Outputs (async):** `{"interaction_id": "...", "dispatched_at": "ISO-8601", "originating_session_id": "..."}` — caller does *not* block.

## Safety

- **Never print or log the API key.** Margot reads `~/.margot/gemini-api-key.txt` directly. Bridge does not pass it through any channel.
- **Kill-switch behaviour:** when `TAO_SWARM_ENABLED=0`, in-flight `interaction_id`s persist in `margot_inflight.jsonl`. They are NOT cancelled. On re-enable, polling resumes.
- **Corpus exposure:** if `MARGOT_FILE_SEARCH_STORE` points at user-private content (lessons.jsonl, memory), Margot's research output may quote it back. Caller's responsibility to redact via `pii-redactor` (Wave 2) before any send.
- **Cost ceiling:** Margot calls hit Gemini API (Phill's account, billed separately from Anthropic Max). No automatic ceiling in Wave 1; flag for Wave 3 audit-emit.

## Verification (Wave 1 smoke)

From Pi-CEO repo:
1. Call `margot-bridge` with `{"intent": "diagnostic"}` → invokes `corpus_status()` → expect non-empty response containing `MARGOT_TEXT_MODEL` and `MARGOT_DEEP_RESEARCH_AGENT` field names.
2. If MCP is not registered: skill returns `{"error": "margot mcp not reachable", "fix": "see Prerequisites in margot-bridge SKILL.md"}` and exits cleanly.

## Out of scope

- Modifying `~/.margot/` source — Margot is owned separately.
- Re-implementing Margot's tools inside Pi-CEO MCP server.
- Margot-as-swarm-role lifecycle binding (rejected during plan; light coupling chosen).
- Cloud-routine secret loading (deferred to Wave 2).

## References

- Margot source: `~/.margot/margot-deep-research/server.py` (read-only)
- Topology doc: `/Users/phill-mac/Pi-CEO/Second-Brain-Agent-Topology-2026-05-01.md`
- Plan: `/Users/phill-mac/.claude/plans/breezy-wiggling-map.md`
