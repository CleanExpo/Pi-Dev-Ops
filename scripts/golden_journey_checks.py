"""UNI-2652 — A8 / A9 / A10 checkers for the golden journey.

Pure functions. The live wrapper in golden_journey.py feeds them HTTP
results; tests feed fixtures. None of this grows run_pipeline_smoke.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request


# UNI-2646's contract, plus the ticket's shorter /ready alias.
READY_PATHS = ("/api/health/ready", "/ready")

_A1_SID = re.compile(r"\[A1 PASS\] session spawned:\s+(\S+)")
_PR_URL = re.compile(r"PR URL:\s+(\S+)")
_RESULT = re.compile(r"RESULT:\s+(PASS|FAIL)")
_COMPLETE_STATUSES = frozenset({"complete"})
_NOT_SHIPPED_STATUSES = frozenset({"failed", "killed", "interrupted", "blocked"})
_HEADING = re.compile(r"^#{1,3}\s+(requirement|change|test)\b", re.I | re.M)


@dataclass
class SmokeCapture:
    sid: str | None = None
    pr_url: str | None = None
    smoke_passed: bool = False


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def parse_smoke_output(text: str) -> SmokeCapture:
    """Read sid / PR URL / PASS from the smoke script's own stdout."""
    sid = _first(_A1_SID, text)
    raw_pr = _first(_PR_URL, text)
    pr_url = _extract_pr_url(raw_pr) if raw_pr else None
    result = _first(_RESULT, text)
    return SmokeCapture(sid=sid, pr_url=pr_url, smoke_passed=result == "PASS")


def probe_ready(opener, base: str) -> Check:
    """A8 — /ready (or /api/health/ready) must be HTTP 200 before a journey."""
    last = Check("A8", False, "no ready path answered")
    for path in READY_PATHS:
        code, _body = _http_get(opener, base, path)
        if code == 200:
            return Check("A8", True, f"{path} → 200")
        last = Check("A8", False, f"{path} → HTTP {code}")
        if code not in {404, 405}:
            return last
    return last


def gate_agrees_with_session(gate: dict[str, Any], session: dict[str, Any]) -> Check:
    """A9 — gate row shipped/push_ok and session.status must tell the same story."""
    status = str(session.get("status") or "")
    shipped = _as_bool(gate.get("shipped", gate.get("push_ok")))
    if shipped is None:
        return Check("A9", False, "gate row missing shipped/push_ok")
    if not status:
        return Check("A9", False, "session missing status")
    if status in _COMPLETE_STATUSES:
        ok = shipped is True
        return Check("A9", ok, f"status={status} shipped={shipped}")
    if status in _NOT_SHIPPED_STATUSES:
        ok = shipped is False
        return Check("A9", ok, f"status={status} shipped={shipped}")
    return Check("A9", False, f"status={status} is not a terminal the gate can agree with")


def pr_maps_requirement_to_change_to_test(body: str) -> Check:
    """A10 — PR body maps Requirement → Change → Test, each with content."""
    if not (body or "").strip():
        return Check("A10", False, "empty PR body")
    hits = [(m.start(), m.group(1).lower()) for m in _HEADING.finditer(body)]
    names = [name for _pos, name in hits]
    if names[:3] != ["requirement", "change", "test"]:
        return Check("A10", False, f"headings={names} (need Requirement, Change, Test in order)")
    sections = _split_sections(body)
    empty = [k for k in ("requirement", "change", "test") if not sections.get(k)]
    if empty:
        return Check("A10", False, f"empty sections: {empty}")
    return Check("A10", True, "requirement → change → test")


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def _extract_pr_url(raw: str) -> str | None:
    match = re.search(r"https://github\.com/\S+/pull/\d+", raw)
    return match.group(0) if match else (raw if raw.startswith("http") else None)


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _split_sections(body: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    current = ""
    buf: list[str] = []
    for line in body.splitlines():
        match = _HEADING.match(line)
        if match:
            if current:
                parts[current] = "\n".join(buf).strip()
            current = match.group(1).lower()
            buf = []
            continue
        if current:
            buf.append(line)
    if current:
        parts[current] = "\n".join(buf).strip()
    return parts


def _http_get(opener, base: str, path: str) -> tuple[int, str]:
    req = Request(f"{base.rstrip('/')}{path}")
    try:
        with opener.open(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 — probe must never crash the journey
        return 0, str(exc)


def load_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def load_json_object(text: str) -> dict[str, Any]:
    data = load_json(text)
    return data if isinstance(data, dict) else {}
