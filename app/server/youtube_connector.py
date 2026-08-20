"""Direct YouTube connector for the UG-N intent catalog.

Implements:
  - Google OAuth URL generation + callback token exchange
  - token persistence for subsequent pulls
  - lightweight live YouTube signal extraction
  - Google My Activity / Takeout-style import normalization
"""
from __future__ import annotations

import json
import secrets
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .youtube_intent import upsert_catalog

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
OAUTH_STATE_PATH = Path(".harness/ugn_intent_youtube/oauth.json")
YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _get_client_id() -> str:
    from os import environ

    return (
        environ.get("YOUTUBE_OAUTH_CLIENT_ID")
        or environ.get("GOOGLE_OAUTH_CLIENT_ID")
        or ""
    ).strip()


def _get_client_secret() -> str:
    from os import environ

    return (
        environ.get("YOUTUBE_OAUTH_CLIENT_SECRET")
        or environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
        or ""
    ).strip()


def _default_redirect_uri() -> str:
    from os import environ

    return (
        environ.get("YOUTUBE_OAUTH_REDIRECT_URI")
        or environ.get("GOOGLE_OAUTH_REDIRECT_URI")
        or ""
    ).strip()


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_oauth_state() -> dict[str, Any]:
    return _read_json(
        OAUTH_STATE_PATH,
        {
            "connected": False,
            "state": "",
            "scope": YOUTUBE_SCOPE,
            "access_token": "",
            "refresh_token": "",
            "expires_at": "",
            "updated_at": _now(),
        },
    )


def save_oauth_state(state: dict[str, Any]) -> None:
    state["updated_at"] = _now()
    _write_json(OAUTH_STATE_PATH, state)


def build_oauth_start_payload(redirect_uri: str | None = None) -> dict[str, Any]:
    client_id = _get_client_id()
    effective_redirect = (redirect_uri or _default_redirect_uri()).strip()
    state_token = secrets.token_urlsafe(18)
    base = {
        "configured": bool(client_id and effective_redirect),
        "state": state_token,
        "redirect_uri": effective_redirect,
        "scope": YOUTUBE_SCOPE,
    }
    state = load_oauth_state()
    state["state"] = state_token
    state["redirect_uri"] = effective_redirect
    save_oauth_state(state)

    if not base["configured"]:
        return {
            **base,
            "auth_url": None,
            "missing": [
                k
                for k, present in (
                    ("YOUTUBE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_ID", bool(client_id)),
                    ("YOUTUBE_OAUTH_REDIRECT_URI / GOOGLE_OAUTH_REDIRECT_URI", bool(effective_redirect)),
                )
                if not present
            ],
        }

    params = {
        "client_id": client_id,
        "redirect_uri": effective_redirect,
        "response_type": "code",
        "scope": YOUTUBE_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state_token,
        "include_granted_scopes": "true",
    }
    return {**base, "auth_url": f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"}


def _post_form(url: str, body: dict[str, str]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def exchange_code(code: str, state_value: str, redirect_uri: str | None = None) -> dict[str, Any]:
    if not code:
        raise ValueError("missing code")
    oauth_state = load_oauth_state()
    expected_state = str(oauth_state.get("state") or "")
    if expected_state and state_value and state_value != expected_state:
        raise ValueError("state mismatch")

    client_id = _get_client_id()
    client_secret = _get_client_secret()
    effective_redirect = (redirect_uri or oauth_state.get("redirect_uri") or _default_redirect_uri()).strip()
    if not client_id or not client_secret or not effective_redirect:
        raise ValueError("oauth not configured")

    payload = _post_form(
        GOOGLE_TOKEN_URL,
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": effective_redirect,
            "grant_type": "authorization_code",
        },
    )
    access_token = str(payload.get("access_token") or "")
    refresh_token = str(payload.get("refresh_token") or oauth_state.get("refresh_token") or "")
    expires_in = int(payload.get("expires_in") or 3600)
    expires_at = datetime.now(timezone.utc).timestamp() + expires_in

    oauth_state.update(
        {
            "connected": bool(access_token),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": payload.get("token_type", "Bearer"),
            "scope": payload.get("scope", YOUTUBE_SCOPE),
            "expires_at": datetime.fromtimestamp(expires_at, timezone.utc).isoformat(),
        }
    )
    save_oauth_state(oauth_state)
    return {
        "connected": oauth_state["connected"],
        "scope": oauth_state["scope"],
        "expires_at": oauth_state["expires_at"],
    }


def _refresh_access_token_if_needed() -> str:
    state = load_oauth_state()
    access_token = str(state.get("access_token") or "")
    refresh_token = str(state.get("refresh_token") or "")
    expires_at = str(state.get("expires_at") or "")
    if access_token and expires_at:
        try:
            if datetime.fromisoformat(expires_at.replace("Z", "+00:00")) > datetime.now(timezone.utc):
                return access_token
        except ValueError:
            pass
    if not refresh_token:
        raise ValueError("no refresh token available")

    client_id = _get_client_id()
    client_secret = _get_client_secret()
    if not client_id or not client_secret:
        raise ValueError("oauth client credentials missing")

    payload = _post_form(
        GOOGLE_TOKEN_URL,
        {
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        },
    )
    new_access_token = str(payload.get("access_token") or "")
    if not new_access_token:
        raise ValueError("refresh failed to produce access_token")
    expires_in = int(payload.get("expires_in") or 3600)
    state["access_token"] = new_access_token
    state["expires_at"] = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() + expires_in,
        timezone.utc,
    ).isoformat()
    state["connected"] = True
    save_oauth_state(state)
    return new_access_token


def _youtube_get(path: str, params: dict[str, str], access_token: str) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    url = f"{YOUTUBE_API_BASE}/{path}?{query}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _normalize_live_items(activities: dict[str, Any], subscriptions: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in activities.get("items", []) or []:
        snippet = row.get("snippet") or {}
        title = str(snippet.get("title") or "").strip()
        if not title:
            continue
        desc = str(snippet.get("description") or "")
        channel = str(snippet.get("channelTitle") or "youtube-activity")
        items.append(
            {
                "video_id": str((row.get("contentDetails") or {}).get("upload", {}).get("videoId") or ""),
                "title": title,
                "channel": channel,
                "description": desc,
                "tags": ["youtube-live", "activity"],
                "watch_count_window": 1,
                "selected_by_user": True,
            }
        )
    for row in subscriptions.get("items", []) or []:
        snippet = row.get("snippet") or {}
        title = str(snippet.get("title") or "").strip()
        if not title:
            continue
        items.append(
            {
                "video_id": str(row.get("id") or ""),
                "title": title,
                "channel": title,
                "description": str(snippet.get("description") or ""),
                "tags": ["youtube-live", "subscription"],
                "watch_count_window": 1,
                "selected_by_user": True,
            }
        )
    return items


def pull_live_signals() -> dict[str, Any]:
    access_token = _refresh_access_token_if_needed()
    activities = _youtube_get(
        "activities",
        {"part": "snippet,contentDetails", "mine": "true", "maxResults": "50"},
        access_token,
    )
    subscriptions = _youtube_get(
        "subscriptions",
        {"part": "snippet", "mine": "true", "maxResults": "50"},
        access_token,
    )
    items = _normalize_live_items(activities, subscriptions)
    result = upsert_catalog(items)
    return {
        "fetched_items": len(items),
        "accepted": result.accepted,
        "excluded": result.excluded,
        "total": result.total,
        "status_breakdown": result.status_breakdown,
    }


def _normalize_takeout_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    title = str(entry.get("title") or "").strip()
    if not title:
        return None
    channel = "unknown"
    subtitles = entry.get("subtitles") or []
    if subtitles and isinstance(subtitles, list):
        first = subtitles[0] or {}
        channel = str(first.get("name") or channel)
    return {
        "video_id": str(entry.get("titleUrl") or title),
        "url": str(entry.get("titleUrl") or ""),
        "title": title.replace("Watched ", "").strip(),
        "channel": channel,
        "description": str(entry.get("description") or ""),
        "tags": ["youtube-takeout", "history-import"],
        "selected_by_user": True,
    }


def import_takeout(payload: dict[str, Any]) -> dict[str, Any]:
    raw_entries = payload.get("entries")
    if raw_entries is None and isinstance(payload.get("items"), list):
        raw_entries = payload.get("items")
    if raw_entries is None and isinstance(payload, list):
        raw_entries = payload
    if not isinstance(raw_entries, list):
        raise ValueError("expected entries list")

    counter: dict[str, int] = defaultdict(int)
    canonical: dict[str, dict[str, Any]] = {}
    for row in raw_entries:
        if not isinstance(row, dict):
            continue
        normalized = _normalize_takeout_entry(row)
        if not normalized:
            continue
        key = str(normalized.get("video_id") or normalized.get("title"))
        counter[key] += 1
        canonical[key] = normalized

    items = []
    for key, base in canonical.items():
        items.append({**base, "watch_count_window": counter[key]})
    result = upsert_catalog(items)
    return {
        "imported_entries": len(raw_entries),
        "unique_items": len(items),
        "accepted": result.accepted,
        "excluded": result.excluded,
        "total": result.total,
        "status_breakdown": result.status_breakdown,
    }
