"""
app/server/advanced — Sprint 9 Ship Chain enhancement layer (RA-682).

This package re-exports the Karpathy-series optimisations that augment the
core Ship Chain. Each module is independently importable; none are required
for the core pipeline to function.

Enhancements in this layer
───────────────────────────
budget          (RA-677)  AUTONOMY_BUDGET single-knob: maps minutes → model,
                          eval_threshold, max_retries, timeout.

scope           (RA-676)  Session Scope Contract: file-count ceiling enforced
                          before eval, Telegram alert on violation.

plan_discovery  (RA-679)  Plan variation loop: 3 haiku-generated approaches,
                          scored, best prepended to generator spec.

complexity      (RA-681)  Progressive brief complexity: auto-classifies brief
                          as basic/detailed/advanced and adjusts spec verbosity.

confidence      (RA-674)  Three-tier confidence routing: AUTO-SHIP FAST /
                          PASS / PASS+FLAG based on score × confidence matrix.

intent_files    (RA-678)  Markdown intent architecture: RESEARCH_INTENT.md +
                          ENGINEERING_CONSTRAINTS.md + EVALUATION_CRITERIA.md
                          injected into every brief from <workspace>/.harness/.

Dependency graph
────────────────
                    sessions.py  (full pipeline)
                         │
               ┌─────────┴─────────┐
            core/               advanced/
         (Ship Chain)        (optimisations)
               │                   │
           brief.py            budget.py
           lessons.py          agents/plan_discovery.py
           config.py           agents/auto_generator.py

Usage
─────
    from app.server.advanced import budget, plan_discovery, complexity
    params = budget.budget_to_params(minutes=60)
    enriched_spec, meta = await plan_discovery.discover_best_plan(brief, spec)
    tier = complexity.classify_brief_complexity(brief)
"""

from app.server import budget  # noqa: F401
from app.server.agents import plan_discovery  # noqa: F401
from app.server.brief import classify_brief_complexity as complexity  # noqa: F401

__all__ = ["budget", "plan_discovery", "complexity"]
