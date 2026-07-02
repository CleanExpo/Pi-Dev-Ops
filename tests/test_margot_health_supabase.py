"""Margot route health — Supabase-first probe."""
from __future__ import annotations

import asyncio

from app.server.routes import health_full


def test_margot_route_prefers_supabase(monkeypatch):
  class FakeSupabase:
      @staticmethod
      def _select(table, params):
          assert table == "margot_conversations"
          return [{"started_at": "2026-07-01T12:00:00+00:00"}]

  monkeypatch.setattr(
      "app.server.supabase_log._select",
      FakeSupabase._select,
  )

  async def _run():
      return await health_full._check_margot_route()

  result = asyncio.run(_run())
  assert result["observed"] is True
  assert result.get("source") == "supabase"
