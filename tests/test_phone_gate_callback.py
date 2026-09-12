"""RA-7530: an Approve/Deny tap arrives as callback_query, not message.

Before this fix the webhook only read data["message"], so a button tap
silently fell through to `return {"ok": True}` and the gate stayed pending
forever — the card just sat there. Confirmed by stashing the fix and
re-running: this test fails on the pre-fix code, passes after.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from app.server.auth import require_rate_limit
    from app.server.routes.webhooks import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_rate_limit] = lambda: None
    return TestClient(app, raise_server_exceptions=True)


def _pending_gate(gate_id: str) -> dict:
    return {
        "gate_id": gate_id, "session_id": "s", "tool_name": "Bash",
        "tool_input_summary": "echo x", "reason": "test", "status": "pending",
        "created_at": 0, "expires_at": 1e18, "resolved_at": None,
        "resolved_by": None, "chat_id": 789, "message_id": None,
    }


def test_telegram_webhook_approve_callback_resolves_gate(monkeypatch):
    """Also proves the button's loading spinner gets cleared: a mutant that
    drops the answer_callback_query call must fail this, not just leave the
    tap silently un-acknowledged in Telegram's UI."""
    import app.server.config as cfg
    from app.server.routes import phone, phone_gate_callback

    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setattr(cfg, "TELEGRAM_WEBHOOK_SECRET", "hook-secret")
    answered: list[tuple] = []
    monkeypatch.setattr(phone_gate_callback, "answer_callback_query", lambda *a: answered.append(a))

    gate_id = "testgate123456"
    phone._gates[gate_id] = _pending_gate(gate_id)

    resp = _client().post(
        "/webhook/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
        json={
            "update_id": 1,
            "callback_query": {"id": "cbid1", "data": f"approve:{gate_id}", "from": {"id": 789}},
        },
    )

    assert resp.status_code == 200
    assert phone._gates[gate_id]["status"] == "approved"
    assert answered == [("bot-token", "cbid1")]


def test_telegram_webhook_deny_callback_resolves_gate(monkeypatch):
    """A mutant narrowing the action allow-list to ('approve',) only must fail
    this, not just the approve test above."""
    import app.server.config as cfg
    from app.server.routes import phone, phone_gate_callback

    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setattr(cfg, "TELEGRAM_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr(phone_gate_callback, "answer_callback_query", lambda *a, **k: None)

    gate_id = "testgate654321"
    phone._gates[gate_id] = _pending_gate(gate_id)

    resp = _client().post(
        "/webhook/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
        json={
            "update_id": 2,
            "callback_query": {"id": "cbid2", "data": f"deny:{gate_id}", "from": {"id": 789}},
        },
    )

    assert resp.status_code == 200
    assert phone._gates[gate_id]["status"] == "denied"


def test_telegram_webhook_foreign_chat_cannot_approve(monkeypatch):
    """Found by independent review (codex, round 5): a gate_id is not secret
    (the local hook prints it to stderr on every poll), so anyone who can
    reach the webhook with a known gate_id must still be its own recipient."""
    import app.server.config as cfg
    from app.server.routes import phone, phone_gate_callback

    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setattr(cfg, "TELEGRAM_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr(phone_gate_callback, "answer_callback_query", lambda *a: None)

    gate_id = "testgateforeign"
    phone._gates[gate_id] = _pending_gate(gate_id)  # chat_id=789

    resp = _client().post(
        "/webhook/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
        json={
            "update_id": 3,
            "callback_query": {"id": "cbid3", "data": f"approve:{gate_id}", "from": {"id": 999}},
        },
    )

    assert resp.status_code == 200
    assert phone._gates[gate_id]["status"] == "pending"


def test_telegram_webhook_expired_gate_cannot_be_approved(monkeypatch):
    """Found by independent review (codex, round 5): resolve_gate only checked
    status, not expires_at, so a late tap could approve a gate the local hook
    had already given up on."""
    import app.server.config as cfg
    from app.server.routes import phone, phone_gate_callback

    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setattr(cfg, "TELEGRAM_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr(phone_gate_callback, "answer_callback_query", lambda *a: None)

    gate_id = "testgateexpired"
    gate = _pending_gate(gate_id)
    gate["expires_at"] = 1  # long past
    phone._gates[gate_id] = gate

    resp = _client().post(
        "/webhook/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
        json={
            "update_id": 4,
            "callback_query": {"id": "cbid4", "data": f"approve:{gate_id}", "from": {"id": 789}},
        },
    )

    assert resp.status_code == 200
    assert phone._gates[gate_id]["status"] == "expired"
