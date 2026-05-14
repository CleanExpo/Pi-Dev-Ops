"""Unite-Group Hermes plugin — native portfolio data tools for Margot.

Registers 4 tools that give Margot live access to portfolio business data
without requiring round-trips through the Pi-CEO API or Claude Code sessions:

  ug_portfolio_health  — Pi-CEO Supabase health snapshots for all 6 businesses
  ug_ccw_kpis          — CCW client KPIs (ARR, jobs, wiki pages)
  ug_wave_status       — Linear project/milestone progress across all repos
  ug_6pager_summary    — Latest senior agent 6-pager from Supabase/wiki

All handlers are read-only and safe to run autonomously.
"""

from __future__ import annotations

from .tools import (
    UG_PORTFOLIO_HEALTH_SCHEMA,
    UG_CCW_KPIS_SCHEMA,
    UG_WAVE_STATUS_SCHEMA,
    UG_6PAGER_SCHEMA,
    _handle_ug_portfolio_health,
    _handle_ug_ccw_kpis,
    _handle_ug_wave_status,
    _handle_ug_6pager_summary,
)

_TOOLS = (
    ("ug_portfolio_health", UG_PORTFOLIO_HEALTH_SCHEMA, _handle_ug_portfolio_health, "📊"),
    ("ug_ccw_kpis",         UG_CCW_KPIS_SCHEMA,         _handle_ug_ccw_kpis,         "💰"),
    ("ug_wave_status",      UG_WAVE_STATUS_SCHEMA,      _handle_ug_wave_status,      "🌊"),
    ("ug_6pager_summary",   UG_6PAGER_SCHEMA,           _handle_ug_6pager_summary,   "📄"),
)


def register(ctx) -> None:
    """Register all Unite-Group tools. Called once by the plugin loader."""
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="unite-group",
            schema=schema,
            handler=handler,
            emoji=emoji,
        )
