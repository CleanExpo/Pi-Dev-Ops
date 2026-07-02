"""fleet_value_optimizer.py — RA-6908 / OM-4: quota-aware plan maximiser (dry-run first).

Sits beside ``model_policy`` (correctness) and ``provider_router`` (cost
minimisation). This module maximises monthly entitlement usage across the
fleet's paid plans — use-it-or-lose-it budgets, not marginal-cost minimisation.

Plans (env-overridable monthly token/request budgets):
  * claude_max_1..3 — Anthropic Max workhorse lanes (default: spill to Max first)
  * codex           — OpenAI Codex precision-only (never autonomous loops)
  * minimax         — media / long-context overflow
  * openrouter      — cheap / experimental overflow

Default mode is **dry_run** (``TAO_FLEET_OPTIMIZER_MODE=dry_run``): emits
recommendations + monthly utilisation reports without changing live routing.
Set ``TAO_FLEET_OPTIMIZER_MODE=live`` only after ``scripts/fleet_value_dryrun.py``
shows acceptable utilisation (founder gate per RA-6908).

Public API:
  is_dry_run() -> bool
  monthly_utilization_report() -> dict
  recommend_plan(role, *, task_class="default") -> ScheduleDecision
  apply_if_live(decision, fallback) -> ProviderModel-like tuple
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

log = logging.getLogger("swarm.fleet_value_optimizer")

PlanId = Literal[
    "claude_max_1",
    "claude_max_2",
    "claude_max_3",
    "codex",
    "minimax",
    "openrouter",
]

# Roles that must never route to Codex (autonomous / high-volume loops).
_CODEX_BLOCKED_ROLES = frozenset({
    "generator",
    "evaluator",
    "monitor",
    "guardian",
    "intent_classify",
    "scribe.draft",
    "sprinkle.lessons",
    "sprinkle.triage",
    "sprinkle.feedback",
    "sprinkle.pulse",
    "sprinkle.board_prebrief",
})

# Preference order when maximising under-utilised entitlements.
_DEFAULT_PLAN_ORDER: tuple[PlanId, ...] = (
    "claude_max_1",
    "claude_max_2",
    "claude_max_3",
    "minimax",
    "openrouter",
    "codex",
)

_ROLE_PLAN_HINTS: dict[str, tuple[PlanId, ...]] = {
    "planner": ("claude_max_1", "claude_max_2", "claude_max_3"),
    "orchestrator": ("claude_max_1", "claude_max_2", "claude_max_3"),
    "board": ("claude_max_1", "claude_max_2"),
    "generator": ("claude_max_1", "claude_max_2", "claude_max_3"),
    "evaluator": ("claude_max_1", "claude_max_2", "claude_max_3"),
    "margot.synthesis": ("claude_max_1", "claude_max_2"),
    "margot.casual": ("openrouter", "minimax"),
    "research": ("claude_max_2", "openrouter"),
    "margot.truth_check": ("codex", "claude_max_1"),
}


@dataclass(frozen=True)
class PlanEntitlement:
    plan_id: PlanId
    monthly_request_budget: int
    provider: str
    model_id: str
    description: str = ""


@dataclass
class ScheduleDecision:
    role: str
    recommended_plan: PlanId
    provider: str
    model_id: str
    reason: str
    dry_run: bool
    utilization_pct: float
    alternatives: list[PlanId] = field(default_factory=list)


def _mode() -> str:
    return (os.environ.get("TAO_FLEET_OPTIMIZER_MODE") or "dry_run").strip().lower()


def is_dry_run() -> bool:
    return _mode() != "live"


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def default_entitlements() -> dict[PlanId, PlanEntitlement]:
    """Built-in plan table; monthly budgets env-overridable per plan."""
    return {
        "claude_max_1": PlanEntitlement(
            plan_id="claude_max_1",
            monthly_request_budget=_env_int("TAO_FLEET_MAX1_MONTHLY_REQUESTS", 50_000),
            provider="claude_print",
            model_id=(os.environ.get("TAO_TOP_MODEL") or "claude-opus-4-8").strip(),
            description="Primary Max workhorse",
        ),
        "claude_max_2": PlanEntitlement(
            plan_id="claude_max_2",
            monthly_request_budget=_env_int("TAO_FLEET_MAX2_MONTHLY_REQUESTS", 50_000),
            provider="claude_print",
            model_id=(os.environ.get("TAO_MID_MODEL") or "claude-sonnet-5").strip(),
            description="Secondary Max lane",
        ),
        "claude_max_3": PlanEntitlement(
            plan_id="claude_max_3",
            monthly_request_budget=_env_int("TAO_FLEET_MAX3_MONTHLY_REQUESTS", 50_000),
            provider="claude_print",
            model_id=(os.environ.get("TAO_MID_MODEL") or "claude-sonnet-5").strip(),
            description="Tertiary Max overflow",
        ),
        "codex": PlanEntitlement(
            plan_id="codex",
            monthly_request_budget=_env_int("TAO_FLEET_CODEX_MONTHLY_REQUESTS", 5_000),
            provider="openai",
            model_id=(os.environ.get("TAO_CODEX_MODEL") or "gpt-5.3-codex").strip(),
            description="Precision-only; no autonomous loops",
        ),
        "minimax": PlanEntitlement(
            plan_id="minimax",
            monthly_request_budget=_env_int("TAO_FLEET_MINIMAX_MONTHLY_REQUESTS", 20_000),
            provider="minimax",
            model_id=(os.environ.get("TAO_MINIMAX_MODEL") or "MiniMax-M2.5").strip(),
            description="Media / long-context",
        ),
        "openrouter": PlanEntitlement(
            plan_id="openrouter",
            monthly_request_budget=_env_int("TAO_FLEET_OPENROUTER_MONTHLY_REQUESTS", 100_000),
            provider="openrouter",
            model_id=(os.environ.get("TAO_CHEAP_REMOTE_MODEL") or "google/gemma-4-26b-a4b-it").strip(),
            description="Overflow / experimental",
        ),
    }


def _provider_to_plan(provider: str) -> PlanId | None:
    p = (provider or "").strip().lower()
    if p == "claude_print":
        return "claude_max_1"
    if p == "openai" or p == "codex":
        return "codex"
    if p == "minimax":
        return "minimax"
    if p == "openrouter":
        return "openrouter"
    if p == "anthropic":
        return "claude_max_1"
    return None


def monthly_usage_counts(*, month_key: str | None = None) -> dict[PlanId, int]:
    """Count requests per plan from budget_tracker JSONL for the UTC month."""
    month = month_key or _month_key()
    counts: dict[PlanId, int] = {p: 0 for p in default_entitlements()}
    try:
        from swarm import budget_tracker  # noqa: PLC0415

        for row in budget_tracker._iter_rows():  # noqa: SLF001 — test hook
            ts = str(row.get("ts", ""))
            if not ts.startswith(month):
                continue
            plan = _provider_to_plan(str(row.get("provider", "")))
            if plan:
                counts[plan] = counts.get(plan, 0) + 1
    except Exception as exc:  # noqa: BLE001
        log.debug("fleet_value_optimizer: usage read failed: %s", exc)
    return counts


def monthly_utilization_report(*, month_key: str | None = None) -> dict[str, Any]:
    """Per-plan utilisation snapshot for Mission Control / dry-run CLI."""
    ents = default_entitlements()
    usage = monthly_usage_counts(month_key=month_key)
    plans: list[dict[str, Any]] = []
    for plan_id, ent in ents.items():
        used = usage.get(plan_id, 0)
        budget = ent.monthly_request_budget
        pct = round(100.0 * used / budget, 2) if budget else 0.0
        plans.append({
            "plan_id": plan_id,
            "used_requests": used,
            "budget_requests": budget,
            "utilization_pct": pct,
            "provider": ent.provider,
            "model_id": ent.model_id,
            "description": ent.description,
        })
    return {
        "month": month_key or _month_key(),
        "mode": _mode(),
        "dry_run": is_dry_run(),
        "plans": plans,
    }


def _utilization_pct(plan_id: PlanId, usage: dict[PlanId, int], ents: dict[PlanId, PlanEntitlement]) -> float:
    ent = ents[plan_id]
    used = usage.get(plan_id, 0)
    if not ent.monthly_request_budget:
        return 0.0
    return round(100.0 * used / ent.monthly_request_budget, 2)


def _candidate_plans(role: str, *, task_class: str) -> tuple[PlanId, ...]:
    role_key = (role or "").strip().lower()
    if role_key in _CODEX_BLOCKED_ROLES:
        hinted = _ROLE_PLAN_HINTS.get(role_key, _DEFAULT_PLAN_ORDER)
        return tuple(p for p in hinted if p != "codex")
    if task_class == "autonomous_loop":
        return tuple(p for p in _DEFAULT_PLAN_ORDER if p != "codex")
    return _ROLE_PLAN_HINTS.get(role_key, _DEFAULT_PLAN_ORDER)


def recommend_plan(role: str, *, task_class: str = "default") -> ScheduleDecision:
    """Pick the most under-utilised eligible plan for this role."""
    ents = default_entitlements()
    usage = monthly_usage_counts()
    candidates = list(_candidate_plans(role, task_class=task_class))
    if not candidates:
        candidates = list(_DEFAULT_PLAN_ORDER)

    # Maximise entitlement: prefer lowest utilisation among eligible plans.
    ranked = sorted(
        candidates,
        key=lambda pid: (_utilization_pct(pid, usage, ents), pid),
    )
    chosen = ranked[0]
    ent = ents[chosen]
    util = _utilization_pct(chosen, usage, ents)
    reason = (
        f"maximise monthly entitlement: {chosen} at {util}% util "
        f"(role={role}, task_class={task_class})"
    )
    if role in _CODEX_BLOCKED_ROLES and "codex" in _ROLE_PLAN_HINTS.get(role, ()):
        reason += "; codex blocked for autonomous role"

    return ScheduleDecision(
        role=role,
        recommended_plan=chosen,
        provider=ent.provider,
        model_id=ent.model_id,
        reason=reason,
        dry_run=is_dry_run(),
        utilization_pct=util,
        alternatives=ranked[1:4],
    )


def format_report(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2)


__all__ = [
    "PlanEntitlement",
    "PlanId",
    "ScheduleDecision",
    "default_entitlements",
    "format_report",
    "is_dry_run",
    "monthly_usage_counts",
    "monthly_utilization_report",
    "recommend_plan",
]
