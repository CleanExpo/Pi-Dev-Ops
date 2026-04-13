# Pi-CEO Ship Chain — Educational Series

**Karpathy-10 reference** (`RA-683`). Five notebooks, from algorithm to production.

---

## What this series covers

Pi-CEO converts a plain-English brief and a GitHub URL into a committed,
evaluated, and shipped code change — automatically. This series explains
how that works, one layer at a time.

Each document is self-contained. Read them in order or jump straight to the
layer you care about.

---

## Series map

| # | Document | What you learn |
|---|----------|----------------|
| 01 | [The Algorithm](01-the-algorithm.md) | The five pure functions of the Ship Chain |
| 02 | [Intent Classification](02-intent-classification.md) | How briefs become PITER categories and ADW workflows |
| 03 | [The Evaluator](03-the-evaluator.md) | How a second AI pass scores, routes, and retries |
| 04 | [Karpathy Optimisations](04-karpathy-optimisations.md) | Budget, scope, plan discovery, brief complexity, confidence routing |
| 05 | [Running the Full System](05-running-the-system.md) | Dev setup, env vars, first build, reading the output |

---

## Reference files

| File | Role |
|------|------|
| `scripts/pi_essentials.py` | Standalone 268-line Ship Chain — zero external deps |
| `app/server/core/` | Production core layer (classify, build_spec, generate, evaluate, decide) |
| `app/server/advanced/` | Sprint 9 enhancement layer (budget, plan_discovery, complexity) |
| `app/server/sessions.py` | Full async pipeline wiring all layers together |
| `.harness/config.yaml` | Runtime config: thresholds, models, budget anchors |
| `.harness/intent/` | Per-project steering: RESEARCH_INTENT, ENGINEERING_CONSTRAINTS, EVALUATION_CRITERIA |
