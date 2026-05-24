# tests/swarm/pilot/test_db_session.py
from unittest.mock import MagicMock
from swarm.pilot import db_session


def test_current_tenant_slug_from_env(monkeypatch):
    monkeypatch.setenv("PILOT_TENANT_SLUG", "duncan")
    assert db_session.current_tenant_slug() == "duncan"


def test_current_tenant_slug_defaults_to_phill(monkeypatch):
    monkeypatch.delenv("PILOT_TENANT_SLUG", raising=False)
    assert db_session.current_tenant_slug() == "phill"


def test_with_tenant_context_calls_set_config():
    client = MagicMock()
    with db_session.with_tenant_context(client, "phill"):
        pass
    client.rpc.assert_any_call("set_config", {
        "setting_name": "app.current_tenant_slug",
        "new_value": "phill", "is_local": True,
    })


def test_with_tenant_context_resets_on_exit():
    client = MagicMock()
    with db_session.with_tenant_context(client, "phill"):
        pass
    calls = [c for c in client.rpc.call_args_list
             if c.args[0] == "set_config" and c.args[1]["new_value"] == ""]
    assert calls, "with_tenant_context did not reset app.current_tenant_slug on exit"
