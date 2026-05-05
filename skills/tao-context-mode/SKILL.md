---
name: tao-context-mode
description: Summary-index + on-demand expansion. Walks a repo once, summarises every source file (~200B vs raw 5-50KB), and serves the FULL file only when callers `expand(path)`. Port of `context-mode`. No LLM calls — pure regex + first-comment synopsis. Deterministic; sha256-keyed for invalidation.
owner_role: Tier-Worker (context primitive, called by orchestrator + tao-loop)
status: wave-1
linear: RA-1969
---

# tao-context-mode

The build/expand pattern: callers consume the compact CodebaseIndex (path + summary + symbols) as their working context, and only `expand()` files actually needed for the current task.

## When to trigger

- TAO session starts and the planner needs codebase awareness without flooding the model context window.
- A new tao-loop iteration is about to start and the autoresearch lens flags rising tokens/turn.
- An agent is asked "where does X live?" and needs a low-cost lookup before reading.

## Public API

```python
from app.server.tao_context_mode import build_index, expand, stats

index = build_index(Path("/repo"))
content = expand(index, "app/server/main.py")
print(stats(index))   # files_indexed, bytes_indexed, expansions, hit_rate
```

## Validation harness

`python scripts/validate_tao_context_mode.py --repo-root .` compares context-mode against the **vcc baseline** (RA-1967 deterministic compactor) — NOT against the raw harness. The board memo threshold is median ≥40% additional reduction over vcc. Per the 2026-05-05 board verdict, falling short is WATCH not REJECT — the infrastructure ships, the experiment log gates merge.

## Out of scope

- Semantic summarisation / LLM-based file synopsis (kept algorithmic on purpose).
- Cross-repo or cross-session indexing (one CodebaseIndex per repo, in-memory).
- Runtime invalidation — sha256 drift logs a warning; re-run `build_index` to refresh.
