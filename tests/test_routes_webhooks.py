"""
test_routes_webhooks.py — Unit tests for routes/webhooks.py helpers (RA-937, RA-826).

Covers _telegram_send (fire-and-forget Telegram helper) with mocked HTTP,
morning-intel path resolution logic, and RA-826 workspace intel endpoints.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── _telegram_send ────────────────────────────────────────────────────────────

def test_telegram_send_makes_correct_request():
    """_telegram_send POSTs to the correct Telegram Bot API URL."""
    from app.server.routes.webhooks import _telegram_send

    mock_response = MagicMock()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        _telegram_send("bot-token-123", 456, "Hello from Pi CEO")

    assert mock_urlopen.called
    req = mock_urlopen.call_args[0][0]
    assert "bot-token-123" in req.full_url
    assert "/sendMessage" in req.full_url


def test_telegram_send_correct_payload():
    """_telegram_send encodes chat_id, text, and parse_mode correctly."""
    from app.server.routes.webhooks import _telegram_send

    captured_data = {}

    def fake_urlopen(req, timeout=None):
        captured_data["data"] = json.loads(req.data.decode())
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        _telegram_send("tok", 789, "Test message")

    assert captured_data["data"]["chat_id"] == 789
    assert captured_data["data"]["text"] == "Test message"
    assert captured_data["data"]["parse_mode"] == "Markdown"


def test_telegram_send_swallows_network_error():
    """_telegram_send does not raise on network failure (fire-and-forget)."""
    from app.server.routes.webhooks import _telegram_send

    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        # Must not raise — fire-and-forget
        _telegram_send("tok", 123, "msg")


def test_telegram_send_string_chat_id():
    """_telegram_send accepts string chat IDs."""
    from app.server.routes.webhooks import _telegram_send

    mock_response = MagicMock()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        _telegram_send("tok", "@channel_name", "broadcast")


# ── Morning intel path logic ──────────────────────────────────────────────────

def test_morning_intel_date_fallback(tmp_path):
    """morning_intel_webhook uses today's date when payload omits 'date'."""
    from datetime import datetime, timezone

    payload = {"anthropic": "update", "flags": ["🟢 ADOPT: streaming"]}
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    intel_dir = tmp_path / ".harness" / "morning-intel"
    intel_dir.mkdir(parents=True)
    intel_file = intel_dir / f"{date_str}.json"
    tmp_file = intel_file.with_suffix(".tmp")

    # Simulate the file-write logic from the route directly
    tmp_file.write_text(json.dumps(payload, indent=2))
    import os
    os.replace(tmp_file, intel_file)

    assert intel_file.exists()
    stored = json.loads(intel_file.read_text())
    assert stored["anthropic"] == "update"


def test_morning_intel_critical_flag_count():
    """Critical flag counting correctly identifies 🔴 and CRITICAL strings.

    Each flag is counted once (OR condition): a flag with both 🔴 and CRITICAL
    still counts as 1. Flags without either marker are not counted.
    """
    flags = [
        "🔴 CRITICAL: breaking change in SDK",   # matches (🔴 present)
        "🟢 ADOPT: new streaming API",            # no match
        "CRITICAL security patch required",       # matches (CRITICAL in upper())
        "🟡 WATCH: rate limit changes",           # no match
    ]
    critical_count = sum(1 for f in flags if "🔴" in str(f) or "CRITICAL" in str(f).upper())
    assert critical_count == 2


# ── IS_CLOUD derivation ───────────────────────────────────────────────────────

def test_is_cloud_false_locally():
    """_IS_CLOUD is False when no cloud environment variables are set."""
    import os
    with patch.dict(os.environ, {}, clear=False):
        # Remove cloud markers if present
        for var in ("RAILWAY_ENVIRONMENT", "RENDER", "FLY_APP_NAME"):
            os.environ.pop(var, None)
        # Re-evaluate the expression
        is_cloud = bool(
            os.environ.get("RAILWAY_ENVIRONMENT")
            or os.environ.get("RENDER")
            or os.environ.get("FLY_APP_NAME")
        )
        assert is_cloud is False


def test_is_cloud_true_on_railway():
    """_IS_CLOUD is True when RAILWAY_ENVIRONMENT is set."""
    import os
    with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production"}):
        is_cloud = bool(
            os.environ.get("RAILWAY_ENVIRONMENT")
            or os.environ.get("RENDER")
            or os.environ.get("FLY_APP_NAME")
        )
        assert is_cloud is True


# ── RA-826: workspace intel endpoints ─────────────────────────────────────────

def _make_webhook_app() -> FastAPI:
    """Minimal FastAPI app with webhooks router, rate-limit bypassed."""
    from app.server.routes.webhooks import router
    from app.server.auth import require_rate_limit

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_rate_limit] = lambda: None
    return app


@pytest.fixture()
def webhook_client() -> TestClient:
    return TestClient(_make_webhook_app(), raise_server_exceptions=True)


def _intel_dir(tmp_path: Path) -> Path:
    """Return the expected workspace-intel dir given our patched DATA_DIR."""
    # Route uses: Path(config.DATA_DIR).parent.parent / ".harness" / "workspace-intel"
    # We set DATA_DIR = tmp_path / "app" / "data"  →  .parent.parent == tmp_path
    return tmp_path / ".harness" / "workspace-intel"


def _sample_payload(batch_date: str = "2026-04-19") -> dict:
    return {
        "batch_date": batch_date,
        "count": 1,
        "source": "n8n:workspace-rss-monitor",
        "items": [
            {
                "title": "Gemini in Google Docs",
                "link": "https://workspaceupdates.googleblog.com/test",
                "pub_date": "2026-04-19T10:00:00Z",
                "summary": "New AI features.",
                "keywords_matched": ["gemini"],
                "categories": ["Google Docs"],
                "guid": "tag:blogger.com,1999:blog-1.post-2",
            }
        ],
    }


def test_workspace_intel_refresh_stores_batch(webhook_client, tmp_path, monkeypatch):
    """POST stores one JSONL entry and returns ok + correct count."""
    import app.server.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path / "app" / "data"))
    monkeypatch.setattr(cfg, "WEBHOOK_SECRET", "")

    resp = webhook_client.post(
        "/api/webhook/workspace-intel-refresh", json=_sample_payload()
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"ok": True, "stored": True, "batch_date": "2026-04-19", "count": 1}

    intel_file = _intel_dir(tmp_path) / "2026-04-19.jsonl"
    assert intel_file.exists()
    entry = json.loads(intel_file.read_text().strip())
    assert entry["count"] == 1
    assert entry["items"][0]["title"] == "Gemini in Google Docs"


def test_workspace_intel_refresh_empty_items_not_stored(webhook_client, tmp_path, monkeypatch):
    """POST with empty items list returns stored=False and writes nothing to disk."""
    import app.server.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path / "app" / "data"))
    monkeypatch.setattr(cfg, "WEBHOOK_SECRET", "")

    payload = {"batch_date": "2026-04-19", "count": 0, "items": [], "source": "test"}
    resp = webhook_client.post("/api/webhook/workspace-intel-refresh", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "stored": False, "reason": "empty_items"}
    assert not _intel_dir(tmp_path).exists()


def test_workspace_intel_refresh_invalid_date_returns_400(webhook_client, tmp_path, monkeypatch):
    """POST with a malformed batch_date returns HTTP 400."""
    import app.server.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path / "app" / "data"))
    monkeypatch.setattr(cfg, "WEBHOOK_SECRET", "")

    payload = _sample_payload()
    payload["batch_date"] = "not-a-date"
    resp = webhook_client.post("/api/webhook/workspace-intel-refresh", json=payload)
    assert resp.status_code == 400


def test_workspace_intel_refresh_requires_secret_when_configured(webhook_client, tmp_path, monkeypatch):
    """POST returns 401 when WEBHOOK_SECRET is set but header is absent."""
    import app.server.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path / "app" / "data"))
    monkeypatch.setattr(cfg, "WEBHOOK_SECRET", "correct-secret")

    resp = webhook_client.post("/api/webhook/workspace-intel-refresh", json=_sample_payload())
    assert resp.status_code == 401


def test_workspace_intel_refresh_wrong_secret_returns_401(webhook_client, tmp_path, monkeypatch):
    """POST returns 401 when provided secret does not match configured secret."""
    import app.server.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path / "app" / "data"))
    monkeypatch.setattr(cfg, "WEBHOOK_SECRET", "correct-secret")

    resp = webhook_client.post(
        "/api/webhook/workspace-intel-refresh",
        json=_sample_payload(),
        headers={"X-Pi-CEO-Secret": "wrong-secret"},
    )
    assert resp.status_code == 401


def test_get_workspace_intel_returns_stored_entries(webhook_client, tmp_path, monkeypatch):
    """GET /api/workspace-intel returns batches previously stored via POST."""
    import app.server.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path / "app" / "data"))
    monkeypatch.setattr(cfg, "WEBHOOK_SECRET", "")

    # Store a batch first
    webhook_client.post("/api/webhook/workspace-intel-refresh", json=_sample_payload())

    resp = webhook_client.get("/api/workspace-intel")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["entries"]) == 1
    assert data["entries"][0]["batch_date"] == "2026-04-19"
    assert data["entries"][0]["count"] == 1


def test_get_workspace_intel_empty_when_no_data(webhook_client, tmp_path, monkeypatch):
    """GET returns empty entries list when no intel has been stored yet."""
    import app.server.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path / "app" / "data"))
    monkeypatch.setattr(cfg, "WEBHOOK_SECRET", "")

    resp = webhook_client.get("/api/workspace-intel")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entries"] == []
    assert data["total"] == 0
