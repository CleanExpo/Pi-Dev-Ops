"""swarm/portfolio_pulse_finance.py — RA-1891 (child of RA-1409).

Finance section provider for the daily Portfolio Pulse. Plugs into the
foundation (RA-1888) via ``portfolio_pulse.set_section_provider``.

For each project, surfaces:
  * Stripe MRR — from the latest CFO snapshot in
    ``.harness/swarm/cfo_state.jsonl`` (matched on business_id == project_id).
    Falls back to a synthetic figure when the ledger is absent or has no
    matching row.
  * Daily Pi-CEO LLM cost — best-effort read of
    ``.harness/llm-cost.jsonl`` (one row per model call). Reports the
    sum of cost_usd entries dated today UTC. When the file is missing,
    emits the pending-RA-1909 placeholder.
  * Monthly burn — from the same CFO snapshot's net_burn field.

Every figure is labelled ``(live)`` or ``(synthetic)`` per the RA-1891
acceptance criteria. Any read error returns the synthetic fallback —
the pulse must never fail because of a finance-section problem.

Constraints from RA-1891:
  * Read-only — never write anywhere
  * stdlib only (json, pathlib)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import portfolio_pulse

log = logging.getLogger("swarm.portfolio_pulse.finance")

CFO_STATE_FILE_REL = ".harness/swarm/cfo_state.jsonl"
LLM_COST_FILE_REL = ".harness/llm-cost.jsonl"

# Synthetic fallbacks — keep coherent with the CFO bot's synthetic
# provider so the pulse stays readable when live data is missing.
SYNTHETIC_MRR_USD = 0.0
SYNTHETIC_BURN_USD = 0.0


# ── Data shapes ─────────────────────────────────────────────────────────────


@dataclass
class FinanceFigures:
    """One project's finance snapshot for the pulse section."""
    mrr_usd: float
    mrr_source: str          # "live" | "synthetic"
    daily_llm_cost_usd: float | None  # None → pending RA-1909
    cost_source: str         # "live" | "pending"
    monthly_burn_usd: float
    burn_source: str         # "live" | "synthetic"


# ── Ledger readers ──────────────────────────────────────────────────────────


def _read_last_cfo_row(project_id: str, repo_root: Path
                         ) -> dict[str, Any] | None:
    """Return the latest cfo_state.jsonl row whose business_id matches
    ``project_id``. None when the file is missing, unreadable, or has
    no matching row.
    """
    p = repo_root / CFO_STATE_FILE_REL
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("portfolio_pulse_finance: cfo_state read failed (%s)", exc)
        return None
    last: dict[str, Any] | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("business_id") == project_id:
            last = row
    return last


def _today_iso_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_today_llm_cost(repo_root: Path) -> float | None:
    """Return the sum of today's cost_usd entries from llm-cost.jsonl.

    Returns ``None`` when the file is absent (cost tracking pending
    RA-1909). On parse error, returns 0.0 — file exists but is empty
    of usable rows.
    """
    p = repo_root / LLM_COST_FILE_REL
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("portfolio_pulse_finance: llm_cost read failed (%s)", exc)
        return 0.0
    today = _today_iso_date()
    total = 0.0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        ts = (row.get("ts") or row.get("timestamp") or "")
        if not isinstance(ts, str) or not ts.startswith(today):
            continue
        try:
            total += float(row.get("cost_usd") or 0.0)
        except (TypeError, ValueError):
            continue
    return round(total, 4)


# ── Figure assembly ─────────────────────────────────────────────────────────


def _gather_figures(project_id: str, repo_root: Path) -> FinanceFigures:
    """Collect MRR + burn + cost figures with per-field live/synthetic
    labelling. Defensive: any read error degrades to synthetic fallback.
    """
    mrr_usd = SYNTHETIC_MRR_USD
    mrr_source = "synthetic"
    burn_usd = SYNTHETIC_BURN_USD
    burn_source = "synthetic"
    try:
        row = _read_last_cfo_row(project_id, repo_root)
    except Exception as exc:  # noqa: BLE001
        log.warning("portfolio_pulse_finance: cfo lookup raised (%s)", exc)
        row = None
    if row is not None:
        try:
            mrr_usd = float(row.get("mrr") or 0.0)
            mrr_source = "live"
        except (TypeError, ValueError):
            pass
        try:
            burn_usd = float(row.get("net_burn") or 0.0)
            burn_source = "live"
        except (TypeError, ValueError):
            pass

    daily_cost: float | None
    try:
        daily_cost = _read_today_llm_cost(repo_root)
    except Exception as exc:  # noqa: BLE001
        log.warning("portfolio_pulse_finance: llm_cost lookup raised (%s)", exc)
        daily_cost = None
    cost_source = "live" if daily_cost is not None else "pending"

    return FinanceFigures(
        mrr_usd=mrr_usd,
        mrr_source=mrr_source,
        daily_llm_cost_usd=daily_cost,
        cost_source=cost_source,
        monthly_burn_usd=burn_usd,
        burn_source=burn_source,
    )


# ── Markdown rendering ──────────────────────────────────────────────────────


def _fmt_usd(amount: float) -> str:
    return f"${amount:,.0f}"


def _render_finance(fig: FinanceFigures) -> str:
    if fig.cost_source == "pending":
        cost_line = "**Daily Pi-CEO cost:** $0.00 (pending RA-1909)"
    else:
        cost = fig.daily_llm_cost_usd or 0.0
        cost_line = (
            f"**Daily Pi-CEO cost:** ${cost:,.2f} "
            f"(from .harness/llm-cost.jsonl live)"
        )
    return (
        f"**MRR:** {_fmt_usd(fig.mrr_usd)} "
        f"(from Stripe {fig.mrr_source})\n"
        f"{cost_line}\n"
        f"**Monthly burn:** {_fmt_usd(fig.monthly_burn_usd)} "
        f"(from Xero {fig.burn_source})"
    )


# ── Provider ────────────────────────────────────────────────────────────────


def finance_section_provider(project_id: str,
                               repo_root: Path) -> tuple[str, str | None]:
    """Section provider for the ``finance`` slot. Returns the rendered
    markdown body. Never raises — read failures degrade to synthetic.
    """
    try:
        fig = _gather_figures(project_id, repo_root)
        return _render_finance(fig), None
    except Exception as exc:  # noqa: BLE001 — defensive top-level guard
        log.warning("portfolio_pulse_finance: section raised for %s (%s)",
                    project_id, exc)
        fig = FinanceFigures(
            mrr_usd=SYNTHETIC_MRR_USD, mrr_source="synthetic",
            daily_llm_cost_usd=None, cost_source="pending",
            monthly_burn_usd=SYNTHETIC_BURN_USD, burn_source="synthetic",
        )
        return _render_finance(fig), str(exc)


def provider(project_id: str, *,
               repo_root: Path) -> portfolio_pulse.PulseSection:
    """Composite finance PulseSection — task-contract entry point.

    Mirrors the github sibling's ``provider()`` shape. Useful for callers
    that want a single rendered block rather than the slot-dispatch
    return.
    """
    body, err = finance_section_provider(project_id, repo_root)
    return portfolio_pulse.PulseSection(name="finance", body_md=body,
                                          error=err)


def register() -> None:
    """Idempotent registration. Replaces the foundation placeholder."""
    portfolio_pulse.set_section_provider("finance", finance_section_provider)


# Self-register on import — sibling-child plug-point convention.
register()


__all__ = [
    "FinanceFigures",
    "finance_section_provider", "provider", "register",
    "CFO_STATE_FILE_REL", "LLM_COST_FILE_REL",
    "SYNTHETIC_MRR_USD", "SYNTHETIC_BURN_USD",
]
