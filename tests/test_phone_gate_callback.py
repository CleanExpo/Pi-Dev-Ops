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
    import app.server.config as cfg
    from app.server.routes import phone, phone_gate_callback

    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setattr(cfg, "TELEGRAM_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr(phone_gate_callback, "answer_callback_query", lambda *a, **k: None)

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
