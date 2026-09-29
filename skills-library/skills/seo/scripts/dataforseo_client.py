#!/usr/bin/env python3
"""DataForSEO API client used by every script in this skill pack.

Reads credentials from one of:
  1. Environment variables  DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD
  2. ~/.claude/skills/seo/.env  (KEY=VALUE per line)
  3. <repo>/.env  (when running from a clone)

All endpoints used here are POST /v3/<group>/<task>/live  — the synchronous
"live" variant — so every call returns data in a single round-trip.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_ROOT = "https://api.dataforseo.com/v3"
DEFAULT_TIMEOUT = 60
DEFAULT_LOCATION = "United States"
DEFAULT_LANGUAGE = "en"


def _candidate_env_files() -> list[Path]:
    paths = [
        Path.home() / ".claude" / "skills" / "seo" / ".env",
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]
    return [p for p in paths if p.is_file()]


def _load_env_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_PLACEHOLDER_MARKERS = ("your_", "your-", "yourlogin", "changeme", "_here", "xxxx", "<", "example.com")


def _is_placeholder(value: str) -> bool:
    """A non-empty credential that is obviously unfilled template text.

    A presence check alone is not enough. `cp .env.example .env` is the
    documented setup step, so placeholder text arrives as a NON-EMPTY value,
    passes `if not login`, and gets sent to DataForSEO — which answers 401 and
    surfaces as a traceback rather than "you haven't set your credentials".
    Observed 2026-08-10. The example file now ships empty values; this catches
    any .env already copied from the old one.
    """
    lowered = value.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _get_credentials() -> tuple[str, str]:
    if "DATAFORSEO_LOGIN" not in os.environ or "DATAFORSEO_PASSWORD" not in os.environ:
        for env_file in _candidate_env_files():
            _load_env_file(env_file)

    login = os.environ.get("DATAFORSEO_LOGIN", "").strip()
    password = os.environ.get("DATAFORSEO_PASSWORD", "").strip()
    if not login or not password or _is_placeholder(login) or _is_placeholder(password):
        sys.stderr.write(
            "ERROR: DataForSEO credentials missing or still placeholders.\n"
            "Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD as env vars,\n"
            "or fill them in at ~/.claude/skills/seo/.env (copy .env.example).\n"
            "API password is the string at https://app.dataforseo.com/api-access\n"
            "(NOT your account login password).\n"
            "Sign up: https://dataforseo.com/register\n"
        )
        sys.exit(2)
    return login, password


def _auth_header() -> str:
    login, password = _get_credentials()
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return f"Basic {token}"


class DataForSEOError(RuntimeError):
    pass


def call(endpoint: str, payload: list[dict[str, Any]] | dict[str, Any], *,
         timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """POST to DataForSEO and return the parsed JSON body.

    `payload` is the array DataForSEO expects (one task per element).
    Pass a single dict to wrap it automatically.
    """
    if isinstance(payload, dict):
        payload = [payload]

    url = f"{API_ROOT}/{endpoint.lstrip('/')}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": _auth_header(),
            "Content-Type": "application/json",
            "User-Agent": "dataforseo-claude/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = ""
        raise DataForSEOError(
            f"HTTP {exc.code} from {endpoint}: {err_body[:500]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise DataForSEOError(f"Network error contacting {endpoint}: {exc.reason}") from exc

    status = data.get("status_code")
    if status and status >= 40000:
        raise DataForSEOError(
            f"DataForSEO error {status} on {endpoint}: {data.get('status_message')}"
        )
    return data


def first_result(response: dict[str, Any]) -> dict[str, Any]:
    """Pull the first task's first result, the most common shape."""
    tasks = response.get("tasks") or []
    if not tasks:
        raise DataForSEOError("Empty tasks array in response.")
    task = tasks[0]
    if task.get("status_code", 20000) >= 40000:
        raise DataForSEOError(
            f"Task failed: {task.get('status_message')}"
        )
    results = task.get("result") or []
    if not results:
        return {}
    return results[0]


def all_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Concatenate `items` from every result in every task.

    DataForSEO endpoints come in two shapes:
      A) `result` is a list of objects, each with an `items` array
         (Labs, SERP, On-Page, most Backlinks endpoints).
      B) `result` is a flat list of objects with no `items` wrapper
         (Keywords Data search_volume, bulk_keyword_difficulty, etc.).

    We handle both: if a `result` element has no `items` key, treat the
    element itself as a row.
    """
    items: list[dict[str, Any]] = []
    for task in response.get("tasks") or []:
        for result in task.get("result") or []:
            sub = result.get("items")
            if sub is None:
                items.append(result)
            else:
                items.extend(sub)
    return items


def flat_results(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the flat result list from every task, ignoring any items wrapper.

    Use this when the endpoint puts row-level data directly in `result` and
    you don't want any `items`-style flattening.
    """
    rows: list[dict[str, Any]] = []
    for task in response.get("tasks") or []:
        rows.extend(task.get("result") or [])
    return rows


def poll_task(endpoint_check: str, task_id: str, *,
              max_wait: int = 90, interval: int = 5) -> dict[str, Any]:
    """For non-live endpoints: wait for a task ID to be ready and fetch it."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        time.sleep(interval)
        data = call(f"{endpoint_check}/{task_id}", [])
        task = (data.get("tasks") or [{}])[0]
        if task.get("status_code", 0) == 20000 and task.get("result"):
            return data
    raise DataForSEOError(f"Task {task_id} not ready within {max_wait}s")


def write_json(obj: Any, path: str | Path | None) -> None:
    """Pretty-print JSON to stdout or a file."""
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    if path is None or path == "-":
        sys.stdout.write(text + "\n")
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def normalize_domain(value: str) -> str:
    """Strip scheme / path / trailing slash so DataForSEO domain endpoints accept it."""
    value = value.strip()
    for prefix in ("https://", "http://"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
    value = value.split("/", 1)[0]
    if value.lower().startswith("www."):
        value = value[4:]
    return value.lower().rstrip(".")
