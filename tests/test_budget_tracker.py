"""tests/test_budget_tracker.py — RA-1909 phase-1 budget tracker tests."""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def isolated_log(tmp_path, monkeypatch):
    """Point budget_tracker at a temp log path and reload."""
    log = tmp_path / "llm-cost.jsonl"
    monkeypatch.setenv("BUDGET_TRACKER_LOG_PATH", str(log))
    # Drop any cached module so the env override takes effect on import
    sys.modules.pop("swarm.budget_tracker", None)
    from swarm import budget_tracker  # noqa: PLC0415
    yield budget_tracker, log
    sys.modules.pop("swarm.budget_tracker", None)


def test_record_cost_writes_jsonl(isolated_log, monkeypatch):
    bt, log = isolated_log
    # Stub Supabase mirror so we don't try to talk to the network
    monkeypatch.setattr(
        "app.server.supabase_log._insert", lambda *a, **kw: True, raising=False,
    )
    bt.record_cost(
        provider="openrouter", role="margot.casual",
        model="google/gemma-4-26b-a4b-it",
        cost_usd=0.0123, tokens_in=1000, tokens_out=200,
    )
    assert log.exists()
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["provider"] == "openrouter"
    assert row["role"] == "margot.casual"
    assert row["model"] == "google/gemma-4-26b-a4b-it"
    assert row["cost_usd"] == 0.0123
    assert row["tokens_in"] == 1000
    assert row["tokens_out"] == 200
    assert row["tenant_id"] == "pi-ceo"
    assert "ts" in row


def test_supabase_failure_does_not_break_record_cost(isolated_log, monkeypatch):
    bt, log = isolated_log

    def boom(*a, **kw):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(
        "app.server.supabase_log._insert", boom, raising=False,
    )
    # Must not raise
    bt.record_cost(
        provider="anthropic", role="planner", model="claude-opus-4-7",
        cost_usd=0.50, tokens_in=500, tokens_out=300,
    )
    # JSONL still written
    assert log.exists()
    assert json.loads(log.read_text(encoding="utf-8").strip())["cost_usd"] == 0.50


def test_record_cost_swallows_jsonl_write_error(tmp_path, monkeypatch):
    # Point at a path inside a non-existent unwritable parent — it auto-mkdirs,
    # so instead we point at an existing directory (write should fail open()).
    sys.modules.pop("swarm.budget_tracker", None)
    monkeypatch.setenv("BUDGET_TRACKER_LOG_PATH", str(tmp_path))  # dir, not file
    monkeypatch.setattr(
        "app.server.supabase_log._insert", lambda *a, **kw: True, raising=False,
    )
    from swarm import budget_tracker  # noqa: PLC0415
    # Must not raise
    budget_tracker.record_cost(
        provider="ollama", role="monitor", model="gemma4:latest",
        cost_usd=0.0, tokens_in=0, tokens_out=0,
    )


def test_daily_total_usd_sums_today_only(isolated_log, monkeypatch):
    bt, log = isolated_log
    today = datetime.now(timezone.utc).date().isoformat()
    yesterday = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).date().isoformat()
    rows = [
        {"ts": f"{today}T00:00:01+00:00", "tenant_id": "pi-ceo", "provider": "openrouter", "role": "monitor", "model": "x", "cost_usd": 1.5, "tokens_in": 0, "tokens_out": 0},
        {"ts": f"{today}T12:00:00+00:00", "tenant_id": "pi-ceo", "provider": "anthropic", "role": "planner", "model": "y", "cost_usd": 2.25, "tokens_in": 0, "tokens_out": 0},
        {"ts": f"{yesterday}T12:00:00+00:00", "tenant_id": "pi-ceo", "provider": "anthropic", "role": "planner", "model": "y", "cost_usd": 99.0, "tokens_in": 0, "tokens_out": 0},
        {"ts": f"{today}T03:00:00+00:00", "tenant_id": "other", "provider": "anthropic", "role": "planner", "model": "y", "cost_usd": 50.0, "tokens_in": 0, "tokens_out": 0},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    total = bt.daily_total_usd(tenant_id="pi-ceo")
    assert total == pytest.approx(3.75)


def test_by_provider_24h_aggregates(isolated_log):
    bt, log = isolated_log
    today = datetime.now(timezone.utc).date().isoformat()
    rows = [
        {"ts": f"{today}T00:00:01+00:00", "tenant_id": "pi-ceo", "provider": "openrouter", "role": "monitor", "model": "x", "cost_usd": 0.10, "tokens_in": 0, "tokens_out": 0},
        {"ts": f"{today}T12:00:00+00:00", "tenant_id": "pi-ceo", "provider": "anthropic", "role": "planner", "model": "y", "cost_usd": 1.00, "tokens_in": 0, "tokens_out": 0},
        {"ts": f"{today}T13:00:00+00:00", "tenant_id": "pi-ceo", "provider": "openrouter", "role": "margot.casual", "model": "x", "cost_usd": 0.20, "tokens_in": 0, "tokens_out": 0},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    out = bt.by_provider_24h()
    assert out["openrouter"] == pytest.approx(0.30)
    assert out["anthropic"] == pytest.approx(1.00)


def test_by_role_24h_aggregates(isolated_log):
    bt, log = isolated_log
    today = datetime.now(timezone.utc).date().isoformat()
    rows = [
        {"ts": f"{today}T00:00:01+00:00", "tenant_id": "pi-ceo", "provider": "openrouter", "role": "monitor", "model": "x", "cost_usd": 0.10, "tokens_in": 0, "tokens_out": 0},
        {"ts": f"{today}T12:00:00+00:00", "tenant_id": "pi-ceo", "provider": "anthropic", "role": "planner", "model": "y", "cost_usd": 1.00, "tokens_in": 0, "tokens_out": 0},
        {"ts": f"{today}T13:00:00+00:00", "tenant_id": "pi-ceo", "provider": "openrouter", "role": "monitor", "model": "x", "cost_usd": 0.05, "tokens_in": 0, "tokens_out": 0},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    out = bt.by_role_24h()
    assert out["monitor"] == pytest.approx(0.15)
    assert out["planner"] == pytest.approx(1.00)


def test_check_ceiling_under(isolated_log, monkeypatch):
    bt, log = isolated_log
    today = datetime.now(timezone.utc).date().isoformat()
    log.write_text(json.dumps({
        "ts": f"{today}T00:00:01+00:00", "tenant_id": "pi-ceo",
        "provider": "anthropic", "role": "planner", "model": "y",
        "cost_usd": 5.00, "tokens_in": 0, "tokens_out": 0,
    }) + "\n")
    monkeypatch.setenv("DAILY_SPEND_LIMIT_USD", "20.00")
    over, total = bt.check_ceiling()
    assert over is False
    assert total == pytest.approx(5.00)


def test_check_ceiling_over(isolated_log, monkeypatch):
    bt, log = isolated_log
    today = datetime.now(timezone.utc).date().isoformat()
    log.write_text(json.dumps({
        "ts": f"{today}T00:00:01+00:00", "tenant_id": "pi-ceo",
        "provider": "anthropic", "role": "planner", "model": "y",
        "cost_usd": 25.00, "tokens_in": 0, "tokens_out": 0,
    }) + "\n")
    monkeypatch.setenv("DAILY_SPEND_LIMIT_USD", "20.00")
    over, total = bt.check_ceiling()
    assert over is True
    assert total == pytest.approx(25.00)


def test_check_ceiling_equal(isolated_log, monkeypatch):
    bt, log = isolated_log
    today = datetime.now(timezone.utc).date().isoformat()
    log.write_text(json.dumps({
        "ts": f"{today}T00:00:01+00:00", "tenant_id": "pi-ceo",
        "provider": "anthropic", "role": "planner", "model": "y",
        "cost_usd": 20.00, "tokens_in": 0, "tokens_out": 0,
    }) + "\n")
    monkeypatch.setenv("DAILY_SPEND_LIMIT_USD", "20.00")
    over, total = bt.check_ceiling()
    assert over is True  # >= is over-limit
    assert total == pytest.approx(20.00)


def test_check_ceiling_explicit_limit_arg(isolated_log):
    bt, log = isolated_log
    today = datetime.now(timezone.utc).date().isoformat()
    log.write_text(json.dumps({
        "ts": f"{today}T00:00:01+00:00", "tenant_id": "pi-ceo",
        "provider": "anthropic", "role": "planner", "model": "y",
        "cost_usd": 3.00, "tokens_in": 0, "tokens_out": 0,
    }) + "\n")
    over, total = bt.check_ceiling(limit_usd=2.50)
    assert over is True
    over2, total2 = bt.check_ceiling(limit_usd=10.00)
    assert over2 is False


def test_daily_total_returns_zero_on_missing_log(tmp_path, monkeypatch):
    sys.modules.pop("swarm.budget_tracker", None)
    monkeypatch.setenv(
        "BUDGET_TRACKER_LOG_PATH", str(tmp_path / "does-not-exist.jsonl"),
    )
    from swarm import budget_tracker  # noqa: PLC0415
    assert budget_tracker.daily_total_usd() == 0.0
    assert budget_tracker.by_provider_24h() == {}
    assert budget_tracker.by_role_24h() == {}
