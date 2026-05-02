"""tests/test_oauth_refresh.py — OAuth refresh-token sidecar smoke."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import oauth_refresh as OR  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for k in [
        "XERO_CLIENT_ID", "XERO_CLIENT_SECRET", "XERO_REFRESH_TOKEN",
        "XERO_ACCESS_TOKEN",
        "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_OAUTH_TOKEN",
    ]:
        monkeypatch.delenv(k, raising=False)


# ── load / save round-trip ──────────────────────────────────────────────────


def test_save_and_load_round_trip(tmp_path):
    payload = {
        "access_token": "at-1", "refresh_token": "rt-1",
        "obtained_at": 1700.0, "expires_in": 1800,
        "expires_at": 3500.0, "token_type": "Bearer",
    }
    p = OR.save_token("xero", payload, tmp_path)
    assert p.exists()
    loaded = OR.load_token("xero", tmp_path)
    assert loaded == payload


def test_load_missing_returns_none(tmp_path):
    assert OR.load_token("xero", tmp_path) is None


def test_save_writes_mode_600(tmp_path):
    p = OR.save_token("xero", {"access_token": "x"}, tmp_path)
    mode = p.stat().st_mode & 0o777
    assert mode == 0o600


def test_save_atomic_replace(tmp_path):
    """Two saves leave only the final payload — no leftover .tmp file."""
    OR.save_token("xero", {"access_token": "first"}, tmp_path)
    OR.save_token("xero", {"access_token": "second"}, tmp_path)
    out = OR.load_token("xero", tmp_path)
    assert out == {"access_token": "second"}
    leftovers = list((tmp_path / OR.OAUTH_DIR_REL).glob("*.tmp"))
    assert leftovers == []


# ── needs_refresh ───────────────────────────────────────────────────────────


def test_needs_refresh_no_payload():
    assert OR.needs_refresh({}) is True


def test_needs_refresh_no_expiry_field():
    assert OR.needs_refresh({"access_token": "x"}) is True


def test_needs_refresh_expired():
    assert OR.needs_refresh({"expires_at": time.time() - 100}) is True


def test_needs_refresh_within_skew():
    # 60 s remaining < default 120s skew → refresh
    assert OR.needs_refresh({"expires_at": time.time() + 60}) is True


def test_needs_refresh_plenty_of_time():
    assert OR.needs_refresh({"expires_at": time.time() + 600}) is False


def test_needs_refresh_garbage_expiry():
    assert OR.needs_refresh({"expires_at": "not-a-number"}) is True


# ── _refresh_provider ───────────────────────────────────────────────────────


def test_refresh_unknown_provider_returns_none(tmp_path):
    assert OR._refresh_provider("nope", tmp_path) is None


def test_refresh_missing_client_creds(tmp_path, monkeypatch):
    """Without client_id/secret env, no call is made and None is returned."""
    out = OR._refresh_provider("xero", tmp_path)
    assert out is None


def test_refresh_missing_refresh_token(tmp_path, monkeypatch):
    monkeypatch.setenv("XERO_CLIENT_ID", "cid")
    monkeypatch.setenv("XERO_CLIENT_SECRET", "csec")
    # No XERO_REFRESH_TOKEN, no stored token
    out = OR._refresh_provider("xero", tmp_path)
    assert out is None


def test_refresh_xero_happy_path(tmp_path, monkeypatch):
    monkeypatch.setenv("XERO_CLIENT_ID", "cid")
    monkeypatch.setenv("XERO_CLIENT_SECRET", "csec")
    monkeypatch.setenv("XERO_REFRESH_TOKEN", "rt-original")

    captured = {}

    def fake_post(*, url, body, basic_auth):
        captured["url"] = url
        captured["body"] = body
        captured["basic_auth"] = basic_auth
        return {
            "access_token": "new-access",
            "refresh_token": "rt-rotated",
            "expires_in": 1800,
            "token_type": "Bearer",
        }

    monkeypatch.setattr(OR, "_post_token_endpoint", fake_post)
    out = OR.refresh_xero(tmp_path)
    assert out is not None
    assert out["access_token"] == "new-access"
    assert out["refresh_token"] == "rt-rotated"
    assert out["expires_in"] == 1800
    assert out["expires_at"] > time.time()

    # Xero uses Basic auth for client creds
    assert captured["basic_auth"] == ("cid", "csec")
    assert captured["url"] == "https://identity.xero.com/connect/token"
    assert captured["body"]["grant_type"] == "refresh_token"
    assert captured["body"]["refresh_token"] == "rt-original"

    # Persisted to disk
    saved = OR.load_token("xero", tmp_path)
    assert saved is not None
    assert saved["access_token"] == "new-access"


def test_refresh_google_ads_uses_body_creds(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_ADS_CLIENT_SECRET", "csec")
    monkeypatch.setenv("GOOGLE_ADS_REFRESH_TOKEN", "rt")

    captured = {}

    def fake_post(*, url, body, basic_auth):
        captured.update({"url": url, "body": body, "basic_auth": basic_auth})
        return {"access_token": "ya29.x", "expires_in": 3600}

    monkeypatch.setattr(OR, "_post_token_endpoint", fake_post)
    out = OR.refresh_google_ads(tmp_path)
    assert out is not None
    assert out["access_token"] == "ya29.x"
    # Google uses body creds, not Basic auth
    assert captured["basic_auth"] is None
    assert captured["body"]["client_id"] == "cid"
    assert captured["body"]["client_secret"] == "csec"


def test_refresh_uses_stored_refresh_token_over_env(tmp_path, monkeypatch):
    """A previously-rotated refresh_token from disk takes precedence."""
    monkeypatch.setenv("XERO_CLIENT_ID", "cid")
    monkeypatch.setenv("XERO_CLIENT_SECRET", "csec")
    monkeypatch.setenv("XERO_REFRESH_TOKEN", "rt-from-env")
    OR.save_token("xero", {"refresh_token": "rt-from-disk",
                              "access_token": "a"}, tmp_path)

    seen = {}

    def fake_post(*, url, body, basic_auth):
        seen["rt"] = body["refresh_token"]
        return {"access_token": "x", "expires_in": 100}

    monkeypatch.setattr(OR, "_post_token_endpoint", fake_post)
    OR.refresh_xero(tmp_path)
    assert seen["rt"] == "rt-from-disk"


def test_refresh_endpoint_failure_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("XERO_CLIENT_ID", "cid")
    monkeypatch.setenv("XERO_CLIENT_SECRET", "csec")
    monkeypatch.setenv("XERO_REFRESH_TOKEN", "rt")
    monkeypatch.setattr(OR, "_post_token_endpoint",
                         lambda **kw: None)
    assert OR.refresh_xero(tmp_path) is None


# ── export_to_env ───────────────────────────────────────────────────────────


def test_export_to_env_uses_stored_when_fresh(tmp_path, monkeypatch):
    OR.save_token("xero", {
        "access_token": "stored-fresh",
        "expires_at": time.time() + 3600,
    }, tmp_path)
    assert OR.export_to_env("xero", tmp_path) is True
    assert os.environ.get("XERO_ACCESS_TOKEN") == "stored-fresh"


def test_export_to_env_refreshes_when_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("XERO_CLIENT_ID", "cid")
    monkeypatch.setenv("XERO_CLIENT_SECRET", "csec")
    monkeypatch.setenv("XERO_REFRESH_TOKEN", "rt")
    OR.save_token("xero", {
        "access_token": "stale",
        "expires_at": time.time() - 10,
    }, tmp_path)
    monkeypatch.setattr(OR, "_post_token_endpoint",
                         lambda **kw: {"access_token": "fresh-via-refresh",
                                       "expires_in": 1800})
    assert OR.export_to_env("xero", tmp_path) is True
    assert os.environ.get("XERO_ACCESS_TOKEN") == "fresh-via-refresh"


def test_export_to_env_unknown_provider(tmp_path):
    assert OR.export_to_env("unknown", tmp_path) is False


def test_export_to_env_no_token_available(tmp_path):
    assert OR.export_to_env("xero", tmp_path) is False


# ── CLI ─────────────────────────────────────────────────────────────────────


def test_cli_help_returns_zero():
    assert OR._cli_main([]) == 0
    assert OR._cli_main(["--help"]) == 0


def test_cli_unknown_provider_returns_2():
    assert OR._cli_main(["nope"]) == 2


def test_cli_refresh_one_failure_returns_1(monkeypatch):
    """Without env, refresh fails → CLI exits 1."""
    monkeypatch.setattr(OR, "refresh_one", lambda *a, **kw: False)
    rc = OR._cli_main(["xero"])
    assert rc == 1


def test_cli_refresh_one_success_returns_0(monkeypatch):
    monkeypatch.setattr(OR, "refresh_one", lambda *a, **kw: True)
    assert OR._cli_main(["xero"]) == 0


def test_cli_all_runs_every_provider(monkeypatch):
    seen = []
    monkeypatch.setattr(
        OR, "refresh_one",
        lambda p, rr: (seen.append(p) or True),
    )
    assert OR._cli_main(["--all"]) == 0
    assert set(seen) == set(OR._PROVIDERS.keys())
