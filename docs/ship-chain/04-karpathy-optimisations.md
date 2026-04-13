# 04 — Karpathy Optimisations

The core Ship Chain works. The Karpathy series makes it faster, cheaper, and
safer by adding a thin enhancement layer on top without touching the core logic.

Each optimisation is independently toggleable. Disable any of them and the
core pipeline continues to work exactly as before.

---

## RA-674 — Confidence-weighted evaluator

**Problem:** Binary pass/fail misses the case where a build passes the score
threshold but the model is uncertain. These builds quietly ship with low
confidence and cause regressions.

**Solution:** Three-tier routing based on score × confidence matrix.
See [03 — The Evaluator](03-the-evaluator.md) for full details.

**Toggle:** Always active. Thresholds tunable via `TAO_EVAL_*` env vars.

---

## RA-676 — Session Scope Contract

**Problem:** Autonomous builds sometimes modify far more files than the brief
implies, creating noise and unintended side effects.

**Solution:** Callers pass a `scope` dict with `{type, max_files_modified}`.
Before the evaluator runs, Pi-CEO checks `git diff HEAD~1 --name-only`. If the
file count exceeds the ceiling, the session is flagged and a Telegram alert
fires.

```json
{ "scope": { "type": "single-file", "max_files_modified": 3 } }
```

**Toggle:** Opt-in per request. No scope = no check.

Source: `app/server/sessions.py::_check_scope_adherence()`

---

## RA-677 — AUTONOMY_BUDGET

**Problem:** The right model, timeout, and retry count depend on how much time
is available. Hardcoded defaults are either too aggressive or too conservative.

**Solution:** A single `budget_minutes` integer maps to a full parameter set
via linear interpolation across 5 anchor points:

| Minutes | Model | Threshold | Max retries | Timeout |
|---------|-------|-----------|-------------|---------|
| 10 | haiku | 7.0 | 1 | 90s |
| 30 | haiku | 7.5 | 1 | 150s |
| 60 | sonnet | 8.0 | 2 | 240s |
| 120 | sonnet | 8.5 | 2 | 360s |
| 240 | opus | 9.0 | 3 | 480s |

```bash
# Set a global default (overridable per request)
TAO_AUTONOMY_BUDGET=60
```

Source: `app/server/budget.py::budget_to_params()`

---

## RA-678 — Markdown Intent Architecture

**Problem:** Strategic steering (what to prioritise, what must not break) lived
only in system prompts — not accessible to project owners.

**Solution:** Three Markdown files in `<workspace>/.harness/intent/` are
automatically injected into every generator brief:

| File | Purpose |
|------|---------|
| `RESEARCH_INTENT.md` | ZTE targets, sprint goals, what the CEO cares about |
| `ENGINEERING_CONSTRAINTS.md` | Hard invariants: endpoints that must not break, lint gates |
| `EVALUATION_CRITERIA.md` | Raised thresholds, zero-tolerance list, lesson policy |

Missing files are silently skipped. No Python changes required to update
steering — edit the Markdown.

Source: `app/server/brief.py::_load_intent_files()`

---

## RA-679 — Plan Variation Discovery

**Problem:** The generator receives one framing of the brief and commits to it.
If that framing is suboptimal, the build underperforms even when the code
is technically correct.

**Solution:** Before the generator runs, three plan variants are generated in
parallel using haiku (fast + cheap), scored by a lightweight eval, and the
winner is prepended to the generator spec:

| Variant | Approach |
|---------|---------|
| A — Direct | Minimal diff, no scope creep |
| B — Correctness-First | Tests → implement → verify |
| C — Leverage Existing | Scan for reusable code first |

Discovery logs persist to `.harness/plan-discoveries/`. After 50 discoveries,
pattern analysis proposes RESEARCH_INTENT.md updates.

**Toggle:** `plan_discovery: true` in `BuildRequest`. Off by default.

Source: `app/server/agents/plan_discovery.py::discover_best_plan()`

---

## RA-681 — Progressive Brief Complexity

**Problem:** Simple briefs (fix a typo) receive the same 1200-token context
dump as architecture migrations. This wastes tokens and adds noise for simple
tasks.

**Solution:** Auto-classify each brief as `basic` / `detailed` / `advanced`
and adjust spec verbosity accordingly:

| Tier | Spec size | Quality gate |
|------|-----------|-------------|
| `basic` | ~500 tokens | Minimal checklist |
| `detailed` | ~1200 tokens | 4-dimension gate (default) |
| `advanced` | ~1800 tokens | Extended gate with confidence target + risk register |

**Toggle:** Auto-detected. Override via `complexity_tier` on `BuildRequest`.

Source: `app/server/brief.py::classify_brief_complexity()`

---

## Import map

```python
# Core layer — no enhancement layer required
from app.server.core import classify, build_spec, generate, evaluate, decide

# Enhancement layer — each module independently importable
from app.server.advanced import budget, plan_discovery, complexity
```

---

## Next

[05 — Running the Full System](05-running-the-system.md): env vars, first
build, reading session output, and how to verify everything is working.
