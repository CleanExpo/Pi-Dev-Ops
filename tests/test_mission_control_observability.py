import asyncio

from app.server.routes import mission_control


def _run(coro):
    return asyncio.run(coro)


def test_observability_snapshot_turns_degraded_health_into_actions(monkeypatch):
    async def fake_gather_components():
        return {
            "hermes_gateway": {"ok": True, "observed": False, "status": "not_observed", "note": "no_heartbeat_file_on_this_host"},
            "telegram_polling": {"ok": True, "observed": False, "status": "not_observed", "note": "no_heartbeat_file"},
            "openrouter": {"ok": True, "observed": True, "status": "live", "last_call_at": "2026-06-17T04:04:57Z"},
        }

    monkeypatch.setattr(mission_control, "gather_components", fake_gather_components)

    result = _run(mission_control._observability_snapshot())

    assert result["source"] == "health_full"
    assert result["ok"] is True
    assert result["fully_observed"] is False
    assert result["red_components"] == []
    assert result["degraded_components"] == ["hermes_gateway", "telegram_polling"]
    assert [action["component"] for action in result["actions"]] == ["hermes_gateway", "telegram_polling"]
    assert result["actions"][0]["owner"] == "Hermes/Codex operator"
    assert "heartbeat" in result["actions"][0]["next_action"]


def test_observability_snapshot_prioritises_red_components(monkeypatch):
    async def fake_gather_components():
        return {
            "supabase": {"ok": False, "status": "red", "error": "probe failed"},
            "margot_route": {"ok": True, "observed": False, "status": "not_observed", "note": "no_conversations_yet"},
        }

    monkeypatch.setattr(mission_control, "gather_components", fake_gather_components)

    result = _run(mission_control._observability_snapshot())

    assert result["ok"] is False
    assert result["fully_observed"] is False
    assert result["red_components"] == ["supabase"]
    assert result["degraded_components"] == ["margot_route"]
    assert [action["component"] for action in result["actions"]] == ["supabase", "margot_route"]
    assert result["actions"][0]["severity"] == "high"
    assert result["actions"][0]["owner"] == "Data/CRM operator"


def test_railway_deploy_config_component_reads_repo_contract():
    result = mission_control._railway_deploy_config_component()

    assert result["ok"] is True
    assert result["status"] == "configured"
    assert result["mismatches"] == {}
