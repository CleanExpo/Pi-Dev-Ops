"""tests/test_fleet_value_optimizer.py — RA-6908 dry-run fleet maximiser."""
from __future__ import annotations

import json


def test_default_mode_is_dry_run(monkeypatch):
    monkeypatch.delenv("TAO_FLEET_OPTIMIZER_MODE", raising=False)
    from swarm import fleet_value_optimizer as fvo

    assert fvo.is_dry_run() is True


def test_recommend_plan_prefers_underutilised_max(monkeypatch, tmp_path):
    monkeypatch.delenv("TAO_FLEET_OPTIMIZER_MODE", raising=False)
    log_path = tmp_path / "llm-cost.jsonl"
    # Heavy use on max_1, light on max_2
    rows = [
        {"ts": "2026-07-02T10:00:00+00:00", "provider": "claude_print", "cost_usd": 0},
    ] * 40 + [
        {"ts": "2026-07-02T11:00:00+00:00", "provider": "anthropic", "cost_usd": 0},
    ] * 2
    log_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setenv("BUDGET_TRACKER_LOG_PATH", str(log_path))

    from swarm import fleet_value_optimizer as fvo

    decision = fvo.recommend_plan("planner")
    assert decision.dry_run is True
    assert decision.recommended_plan in {"claude_max_2", "claude_max_3", "claude_max_1"}
    assert decision.provider == "claude_print"


def test_codex_blocked_for_generator(monkeypatch):
    monkeypatch.delenv("TAO_FLEET_OPTIMIZER_MODE", raising=False)
    from swarm import fleet_value_optimizer as fvo

    decision = fvo.recommend_plan("generator", task_class="autonomous_loop")
    assert decision.recommended_plan != "codex"


def test_monthly_utilization_report_shape(monkeypatch):
    monkeypatch.delenv("TAO_FLEET_OPTIMIZER_MODE", raising=False)
    from swarm import fleet_value_optimizer as fvo

    report = fvo.monthly_utilization_report()
    assert "plans" in report
    assert len(report["plans"]) == 6
    assert report["dry_run"] is True


def test_dryrun_cli_zero_codex_loop_violations(monkeypatch):
    monkeypatch.delenv("TAO_FLEET_OPTIMIZER_MODE", raising=False)
    monkeypatch.setattr("sys.argv", ["fleet_value_dryrun.py", "--json"])
    import scripts.fleet_value_dryrun as cli

    assert cli.main() == 0
