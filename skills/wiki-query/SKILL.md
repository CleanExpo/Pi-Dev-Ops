---
name: wiki-query
description: Query the Brain-1 wiki before hitting external research. Returns an answer grounded in accumulated founder context plus a confidence score and go_external flag. Use on every Margot research request before firing deep_research or realtime calls — cache hit rate target 60-70% for repeat topics.
owner_role: Margot
status: wave-5
---

# wiki-query

Margot checks the wiki first. External research only fires when the wiki can't answer — or when the answer exists but the data might be stale.

## When to invoke

Before every `[RESEARCH]` sentinel resolution in `margot_bot.handle_turn`. The wiki-query result either:
- **Replaces** the external call (confidence=high, not time-sensitive)
- **Supplements** it (confidence=medium — wiki context injected alongside external findings)
- **Defers** entirely (confidence=low — skip wiki, go straight to external)

## Algorithm

1. Load `Wiki/index.md` — the page map.
2. **Identify relevant pages.** LLM call: given the query, name ≤5 pages from the index that are likely to contain an answer.
3. **Read those pages.** Load them from disk (max 5, max 1 500 chars each to bound prompt size).
4. **Synthesise an answer.** LLM call: answer the query from the page content. Return the answer plus a confidence assessment.
5. **Return.** Structured result with answer, pages consulted, confidence, go_external flag, and stale flag.

## Confidence → go_external mapping

| Confidence | Meaning | go_external |
|---|---|---|
| `high` | Answer found, complete, not time-sensitive | `False` |
| `medium` | Partial answer or possibly stale | `True` (supplement) |
| `low` | Not in wiki | `True` (skip wiki) |

Time-sensitive topics (market data, competitor moves, pricing, regulatory) always set `go_external=True` regardless of confidence — the wiki is a starting point, not a substitute for Gemini grounded search on fast-moving topics.

## Input schema

```json
{
  "query": "What is CCW's contract value?",
  "time_sensitive": false
}
```

## Output schema

```json
{
  "answer": "CCW signed a 12-month SaaS contract at $2,400/year on 2026-05-08.",
  "pages_consulted": ["ccw.md", "businesses-overview.md"],
  "confidence": "high" | "medium" | "low",
  "go_external": false,
  "stale": false,
  "error": null
}
```

## Python entry point

```python
from swarm.wiki_query import query

result = query("What is CCW's contract value?", time_sensitive=False)
if not result.go_external:
    # use result.answer directly
else:
    # inject result.answer as context, then fire external research
```

## Integration point in margot_bot

In `handle_turn`, before `_run_research_batch`:

```python
from .wiki_query import query as wiki_query

wiki_result = wiki_query(research_request.topic,
                         time_sensitive=(research_request.depth == "quick"))
if not wiki_result.go_external and wiki_result.answer:
    # substitute wiki answer — no external call needed
    research_findings.append({
        "topic": research_request.topic,
        "depth": "wiki",
        "summary": wiki_result.answer,
        "error": None,
    })
else:
    # fire external + optionally prepend wiki context
    ...
```

## Safety

- Read-only — never writes to the wiki. Use `wiki-ingest` for writes.
- Read from `config.BRAIN1_WIKI_DIR` only.
- Failure is always non-fatal — on error, `go_external=True` so Margot falls through to external research.

## Verification

```python
from swarm.wiki_query import query

r = query("What is CCW's first-response SLA?")
assert r.confidence in ("high", "medium")
assert "15 min" in r.answer or "15" in r.answer
assert "ccw.md" in r.pages_consulted

r2 = query("What did Anthropic announce this week?", time_sensitive=True)
assert r2.go_external is True
```

## References

- Wiki schema: `~/2nd Brain/2nd Brain/CLAUDE.md`
- Config: `swarm/config.py` → `BRAIN1_WIKI_DIR`
- Companion skills: `wiki-ingest` (Wave 5), `wiki-lint` (Wave 5)
