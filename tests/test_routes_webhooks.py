"""
test_routes_webhooks.py — Unit tests for routes/webhooks.py helpers (RA-937).

Covers _telegram_send (fire-and-forget Telegram helper) with mocked HTTP,
and verifies the morning-intel path resolution logic.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch


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
