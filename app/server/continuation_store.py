"""Durable storage adapter for Mission Control continuation state.

Supabase is the cross-machine source of truth when configured. Callers retain a
local-file fallback so continuation never becomes unavailable merely because an
observability/database read is temporarily unavailable.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

log = logging.getLogger("pi-ceo.continuation_store")
TABLE = "continuation_horizons"
DEFAULT_KEY = "founder:primary"


def _cfg() -> tuple[str, str]:
    from . import config
    return config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY


def load(key: str = DEFAULT_KEY) -> dict[str, Any]:
    url, token = _cfg()
    if not url or not token:
        return {}
    params = urllib.parse.urlencode({
        "key": f"eq.{key}",
        "select": "state",
        "limit": "1",
    })
    req = urllib.request.Request(
        f"{url}/rest/v1/{TABLE}?{params}",
        headers={"apikey": token, "Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            rows = json.loads(response.read())
        if rows and isinstance(rows[0].get("state"), dict):
            return rows[0]["state"]
    except Exception as exc:  # noqa: BLE001
        log.warning("continuation durable read failed: %s", exc)
    return {}


def save(state: dict[str, Any], key: str = DEFAULT_KEY) -> bool:
    url, token = _cfg()
    if not url or not token:
        return False
    payload = json.dumps({"key": key, "state": state}).encode()
    req = urllib.request.Request(
        f"{url}/rest/v1/{TABLE}",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "apikey": token,
            "Authorization": f"Bearer {token}",
            "Prefer": "return=minimal,resolution=merge-duplicates",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            response.read()
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("continuation durable write failed: %s", exc)
        return False
