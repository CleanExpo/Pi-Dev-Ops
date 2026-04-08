# Spike: Full Codebase Analysis

_Date: 2026-04-08 | Analyst: Pi CEO Orchestrator (Claude Sonnet 4.6) | Sprint: 4 / Cycle 6_

---

## 1. Research — What Was Read

### Skills (23/23)
All 23 skill files verified present and structurally sound. Key findings:

| Skill | Finding |
|-------|---------|
| `token-budgeter` | ✅ Cost fields filled in (Opus $15, Sonnet $3, Haiku $1.25/M output) |
| `tao-skills` | ✅ All 23 skills correctly listed including `ceo-mode` in Meta layer |
| `ceo-mode` | Minimal body (3 lines) — intentionally terse; works as activation flag |
| `agentic-loop` | Safety rails documented: max 20 iterations, 200k tokens, 60 min runtime |
| `hooks-system` | 6 hook types defined; only 2 (PreToolUse, PostToolUse) active in code |

### TAO Engine (`src/tao/`)
| Module | Finding |
|--------|---------|
| `skills.py` | Complete. Cache via `_SKILLS_CACHE` global; `invalidate_cache()` exists but not called at runtime. |
| `budget/tracker.py` | Records tokens per tier. No cost calculation. Gap: no `cost_usd()` method. |
| `tiers/config.py` | YAML loader; `TierConfig` dataclass; `MODEL_MAP` present. |
| `schemas/artifacts.py` | `TaskSpec`, `TaskResult`, `Escalation` dataclasses. |
| `agents/__init__.py` | **Empty (1 blank line).** All agent dispatch happens via `claude -p` subprocess. |

### Server (`app/server/`)
| Module | Finding |
|--------|---------|
| `brief.py` | PITER priority order correct (hotfix→bug→chore→spike→feature). Lesson fallback: uses 3 most recent general lessons when no intent-specific ones exist. |
| `sessions.py` | `list_sessions()` returns `last_phase` — dashboard could use this for Phase[] array. |
| `main.py` | `GET /health` endpoint exists, returns `{"status": "ok", "sessions": N}`. Not in spec. No `GET /api/capabilities`. |

### Harness State (`.harness/`)
| File | Status |
|------|--------|
| `executive-summary.md` | ✅ Exists and fully written |
| `spec.md` | ✅ Living spec (updated this session) |
| `handoff.md` | ✅ Sprint 3 complete, Sprint 4 candidates listed |
| `leverage-audit.md` | ✅ 60/60 |
| `lessons.jsonl` | ✅ 18 entries seeded |

---

## 2. Summary — Findings

### What Is Working Well
1. **PITER + ADW pipeline** is complete and correctly wired. The intent ordering bug (chore/spike vs feature) was fixed in RA-470.
2. **Closed-loop evaluator** is a genuine blocking gate. Critique injection means retries are meaningfully different from the first attempt.
3. **Lesson injection** provides real institutional memory. The `_get_lesson_context()` fallback ensures context is always non-empty.
4. **MCP server** is fully functional with 11 tools including the newly working `get_last_analysis` (reads `executive-summary.md`).
5. **Security posture** is solid: HMAC tokens, timing-safe comparison, path traversal protection, security headers on all responses.

### What Is Incomplete or Inconsistent

| Gap | Impact | Effort |
|-----|--------|--------|
| `src/tao/agents/__init__.py` empty | Python orchestration layer is absent; fine for current CLI-subprocess approach but blocks programmatic task trees | Medium |
| `GET /api/capabilities` missing | Machine-to-machine API discovery not possible | Low (1 route) |
| Dashboard `lib/types.ts` vs `/api/sessions` mismatch | Dashboard expects `phases: Phase[]`; backend returns flat `status` string | Medium |
| `scripts/smoke_test.py` absent | Regression gate exists only as a manual markdown checklist | Medium |
| `BudgetTracker` → no cost estimation | Token counts recorded but never converted to $ despite skill having pricing | Low |
| `hooks-system` 4/6 hooks unimplemented | Stop + SubagentStop hooks not wired | Low-Medium |

---

## 3. Recommendations

### Approach A — Minimum viable Sprint 4 (3 items)

**A1: `GET /api/capabilities`** — One route, returns hardcoded JSON describing all API actions.
Closes the `agentic-layer` skill gap with minimal effort.

```python
@app.get("/api/capabilities")
async def capabilities():
    return {
        "version": "1.0",
        "actions": [
            {"method": "POST", "path": "/api/build", "description": "Start a build session"},
            {"method": "POST", "path": "/api/build/parallel", "description": "Fan-out parallel builds"},
            {"method": "POST", "path": "/api/webhook", "description": "GitHub/Linear webhook"},
            ...
        ]
    }
```

**A2: `BudgetTracker.cost_usd(model_map)`** — Add a method that converts token counts to USD.
The model pricing is now in `token-budgeter/SKILL.md`; mirror it as a constant in `tracker.py`.

**A3: Phase[] serialisation in `/api/sessions`** — Add a `phases` field to `list_sessions()` by mapping `_PHASE_ORDER` against `last_completed_phase`. Resolves dashboard type mismatch.

### Approach B — Full Sprint 4 (all gaps)

Adds to A:
- `scripts/smoke_test.py` (converts `.harness/qa/smoke-test.md` into runnable checks)
- `src/tao/agents/__init__.py` `AgentDispatcher` class
- Wire `Stop` + `SubagentStop` hooks from `hooks-system` skill

### Trade-off

Approach A closes all ZTE skill gaps and dashboard alignment in one session (~2-3 hours).
Approach B adds operational safety (smoke test) and opens the Python orchestration path but adds 2-4 more sessions of work.

**Recommendation: Approach A first, then P4-G (smoke_test.py) as standalone chore.**
The capabilities endpoint, cost estimation, and phase alignment are high-value/low-risk changes that unblock both MCP tooling and the dashboard without architectural risk.
