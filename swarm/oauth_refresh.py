"""swarm/oauth_refresh.py — OAuth refresh-token sidecar.

Production credential management for the senior-bot providers that need
a current bearer token (Xero, Google Ads). OAuth tokens expire fast (Xero
30 min, Google Ads typically 1 h). Without a refresher, the providers
silently fall back to synthetic mid-cycle — observable but not great.

This module is the substrate. A small CLI (``python -m swarm.oauth_refresh
xero``) refreshes a single provider in one shot; a cron task fires it
every 20 minutes for Xero, every 30 minutes for Google Ads.

Token storage: ``.harness/swarm/oauth/<provider>.json`` with mode 0600,
shape ``{access_token, refresh_token, obtained_at, expires_in,
expires_at}``. ``expires_at`` lets a caller decide whether to refresh
without making a probe call.

Public API:
  load_token(provider, repo_root)           -> dict | None
  save_token(provider, payload, repo_root)
  needs_refresh(payload, *, skew_s=120)     -> bool
  refresh_xero(repo_root)                   -> dict | None
  refresh_google_ads(repo_root)             -> dict | None
  refresh_one(provider, repo_root)          -> bool

CLI:
  python -m swarm.oauth_refresh <provider>
  python -m swarm.oauth_refresh --all
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.oauth_refresh")

OAUTH_DIR_REL = ".harness/swarm/oauth"
HTTP_TIMEOUT_S = 10.0

# Provider → endpoint metadata
_PROVIDERS = {
    "xero": {
        "token_url": "https://identity.xero.com/connect/token",
        "client_id_env": "XERO_CLIENT_ID",
        "client_secret_env": "XERO_CLIENT_SECRET",
        "refresh_token_env": "XERO_REFRESH_TOKEN",
        "scope": "offline_access accounting.reports.read accounting.transactions.read",
        "out_access_env": "XERO_ACCESS_TOKEN",
    },
    "google_ads": {
        "token_url": "https://oauth2.googleapis.com/token",
        "client_id_env": "GOOGLE_ADS_CLIENT_ID",
        "client_secret_env": "GOOGLE_ADS_CLIENT_SECRET",
        "refresh_token_env": "GOOGLE_ADS_REFRESH_TOKEN",
        "scope": "https://www.googleapis.com/auth/adwords",
        "out_access_env": "GOOGLE_ADS_OAUTH_TOKEN",
    },
}


def _token_file(provider: str, repo_root: Path) -> Path:
    return repo_root / OAUTH_DIR_REL / f"{provider}.json"


# ── Read / write ────────────────────────────────────────────────────────────


def load_token(provider: str, repo_root: Path) -> dict[str, Any] | None:
    p = _token_file(provider, repo_root)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("oauth: %s token file unreadable (%s)", provider, exc)
        return None


def save_token(provider: str, payload: dict[str, Any],
                repo_root: Path) -> Path:
    p = _token_file(provider, repo_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return p


def needs_refresh(payload: dict[str, Any], *, skew_s: int = 120) -> bool:
    """True when the stored token expires within ``skew_s`` seconds.

    skew_s defaults to 2 minutes — refreshing before the actual expiry so
    the next API call doesn't race the boundary.
    """
    if not payload:
        return True
    expires_at = payload.get("expires_at")
    if expires_at is None:
        return True
    try:
        return float(expires_at) - time.time() < skew_s
    except (TypeError, ValueError):
        return True


# ── Refresh implementations ─────────────────────────────────────────────────


def _post_token_endpoint(*, url: str, body: dict[str, Any],
                          basic_auth: tuple[str, str] | None = None
                          ) -> dict[str, Any] | None:
    """POST application/x-www-form-urlencoded to a token endpoint.

    Returns the parsed JSON or None on any failure. httpx imported lazily.
    """
    try:
        import httpx  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("oauth: httpx import failed (%s)", exc)
        return None

    try:
        with httpx.Client(timeout=HTTP_TIMEOUT_S) as client:
            r = client.post(
                url,
                data=body,
                auth=basic_auth,
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            return r.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("oauth: refresh failed for %s (%s)", url, exc)
        return None


def _refresh_provider(provider: str, repo_root: Path) -> dict[str, Any] | None:
    cfg = _PROVIDERS.get(provider)
    if cfg is None:
        log.warning("oauth: unknown provider %r", provider)
        return None

    client_id = (os.environ.get(cfg["client_id_env"]) or "").strip()
    client_secret = (os.environ.get(cfg["client_secret_env"]) or "").strip()
    if not (client_id and client_secret):
        log.warning("oauth: %s — missing %s / %s",
                    provider, cfg["client_id_env"], cfg["client_secret_env"])
        return None

    # Prefer stored refresh_token over env so the rotated value persists
    stored = load_token(provider, repo_root) or {}
    refresh_token = stored.get("refresh_token") or (
        os.environ.get(cfg["refresh_token_env"]) or ""
    ).strip()
    if not refresh_token:
        log.warning("oauth: %s — no refresh_token in storage or env",
                    provider)
        return None

    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    if provider == "google_ads":
        body["client_id"] = client_id
        body["client_secret"] = client_secret
        basic_auth = None
    else:
        # Xero uses HTTP Basic for client credentials
        basic_auth = (client_id, client_secret)

    response = _post_token_endpoint(
        url=cfg["token_url"], body=body, basic_auth=basic_auth,
    )
    if response is None:
        return None

    now = time.time()
    expires_in = int(response.get("expires_in") or 1800)
    payload = {
        "access_token": response.get("access_token", ""),
        "refresh_token": response.get("refresh_token", refresh_token),
        "obtained_at": now,
        "expires_in": expires_in,
        "expires_at": now + expires_in,
        "token_type": response.get("token_type", "Bearer"),
    }
    save_token(provider, payload, repo_root)
    log.info("oauth: %s refreshed — expires in %ds", provider, expires_in)
    return payload


def refresh_xero(repo_root: Path) -> dict[str, Any] | None:
    return _refresh_provider("xero", repo_root)


def refresh_google_ads(repo_root: Path) -> dict[str, Any] | None:
    return _refresh_provider("google_ads", repo_root)


def refresh_one(provider: str, repo_root: Path) -> bool:
    """Refresh a single provider; return True on success."""
    out = _refresh_provider(provider, repo_root)
    return out is not None


# ── Activation helper for connectors ────────────────────────────────────────


def export_to_env(provider: str, repo_root: Path) -> bool:
    """Read the stored token for ``provider`` and export the access_token to
    the env var the connector reads (XERO_ACCESS_TOKEN /
    GOOGLE_ADS_OAUTH_TOKEN).

    Used by the orchestrator at startup + on each refresh, so connectors
    that read the env var directly pick up the rotated token without
    restart.
    """
    cfg = _PROVIDERS.get(provider)
    if cfg is None:
        return False
    payload = load_token(provider, repo_root) or {}
    if needs_refresh(payload):
        payload = _refresh_provider(provider, repo_root) or payload
    access = payload.get("access_token") or ""
    if not access:
        return False
    os.environ[cfg["out_access_env"]] = access
    return True


# ── CLI ─────────────────────────────────────────────────────────────────────


def _cli_main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--all":
        ok = all(refresh_one(p, repo_root) for p in _PROVIDERS)
        return 0 if ok else 1
    provider = argv[0]
    if provider not in _PROVIDERS:
        print(f"unknown provider: {provider!r}; "
              f"known: {sorted(_PROVIDERS)}", file=sys.stderr)
        return 2
    return 0 if refresh_one(provider, repo_root) else 1


if __name__ == "__main__":
    sys.exit(_cli_main(sys.argv[1:]))


__all__ = [
    "load_token", "save_token", "needs_refresh",
    "refresh_xero", "refresh_google_ads",
    "refresh_one", "export_to_env",
]
