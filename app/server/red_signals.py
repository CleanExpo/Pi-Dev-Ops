"""red_signals.py — give every red signal a delivery path and an owner.

Audit 2026-09-30 rank #6. The /api/health/full watchdog polled port 8000
while uvicorn binds PORT (8080 on Railway), and dropped the 503 that carries
the alarm, so margot_route sat red for a month with nobody told. And even a
delivered alert went to Telegram only — nothing held it until someone acted.

This module holds:
  * ``health_full_url`` / ``fetch_health_full`` — poll the port uvicorn binds
    and treat the endpoint's 503 body as the snapshot it is;
  * ``health_full_ticket`` — who owns a red component, and whether the fix
    needs something only the founder can grant (label ``founder-only``);
  * ``upsert_red_linear_ticket`` — find-or-update ONE open Linear issue per
    red signal; a second is never created.
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.request
from typing import Any

from . import config
from .routes.health_aggregate import is_observed

LINEAR_URL = "https://api.linear.app/graphql"
TEAM_ID = "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673"
PROJECT_ID = "f45212be-3259-4bfb-89b1-54c122c939a7"
FOUNDER_ONLY_LABEL = "founder-only"

# A red whose fix needs something only the founder can grant — a credential,
# a Railway env var, a permission — is founder-only. Everything else belongs
# to the agent lane named in mission_control's action map.
FOUNDER_ONLY_COMPONENTS = frozenset({"schema_drift_db"})
FOUNDER_ONLY_HINTS = (
    "401", "403", "unauthori", "unauthent", "forbidden",
    "credential", "not set", "not configured", "api_key", "api key",
    "access token", "invalid token", "token expired", "key expired",
)
# An env var the founder sets (FOO_URL, FOO_KEY, ...) reported missing/absent.
# A bare "missing" is not enough: "missing llm-cost log" is an agent's repair.
_ENV_VAR = r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]*(URL|KEY|TOKEN|SECRET|PASSWORD)\b"
_MISSING = r"\b(missing|absent|unset|empty)\b"
_ENV_VAR_MISSING = re.compile(f"{_ENV_VAR}[^.]*{_MISSING}|{_MISSING}[^.]*{_ENV_VAR}")
# One writer per process: find-then-create is not atomic, so two concurrent
# upserts for one title would both see "none open" and both create.
_UPSERT_LOCK = threading.Lock()


def health_full_url() -> str:
    """Local /api/health/full on the port uvicorn binds (runtime_model_guard: PORT, default 8080)."""
    return f"http://127.0.0.1:{os.environ.get('PORT') or '8080'}/api/health/full"


def fetch_health_full(log) -> dict | None:
    """GET /api/health/full. A 503 is the "something is red" answer: parse its body.

    Any other failure returns None and is logged at WARNING — it used to be
    log.debug, which is how a month of failed polls stayed invisible.
    The route needs auth (#869), so the request carries a minted session.
    """
    try:
        from .auth import create_session_token  # noqa: PLC0415
        req = urllib.request.Request(health_full_url(), headers={
            "Accept": "application/json", "Authorization": f"Bearer {create_session_token()}"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
                return json.loads(resp.read())
        except urllib.error.HTTPError as http_err:
            if http_err.code != 503:
                raise
            return json.loads(http_err.read())
    except Exception as exc:  # noqa: BLE001
        log.warning("health_full watchdog: fetch failed (%s)", exc)
        return None


def observed_green(payload) -> bool:
    """Observed and ok:true. Only this ends a red; unobserved is unresolved."""
    return isinstance(payload, dict) and payload.get("ok") is True and is_observed(payload)


def health_full_ticket(name: str, payload: dict) -> dict[str, Any]:
    """Title, body, owner and founder-only flag for one red health_full component."""
    try:
        from .routes.mission_control import _OBSERVABILITY_ACTIONS  # noqa: PLC0415
        owner = _OBSERVABILITY_ACTIONS.get(name, {}).get("owner") or "Senior PM"
    except Exception:  # noqa: BLE001
        owner = "Senior PM"
    detail = f"{payload.get('error') or ''} {payload.get('note') or ''}"
    founder_only = (
        name in FOUNDER_ONLY_COMPONENTS
        or any(h in detail.lower() for h in FOUNDER_ONLY_HINTS)
        or bool(_ENV_VAR_MISSING.search(detail))
    )
    return {
        "title": f"[RED] health_full: {name}",
        "body": (
            f"/api/health/full reports component `{name}` red.\n\n"
            f"Payload: `{json.dumps(payload, default=str)[:500]}`"
        ),
        "owner": owner,
        "founder_only": founder_only,
    }


def _graphql(query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        LINEAR_URL,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": config.LINEAR_API_KEY},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        result = json.loads(resp.read())
    if result.get("errors"):
        raise RuntimeError(f"Linear errors: {str(result['errors'])[:200]}")
    return result.get("data") or {}


def _require_success(data: dict, field: str) -> dict:
    """Linear can answer 200 with success:false; treat that as the failure it is."""
    node = data.get(field)
    if not isinstance(node, dict) or node.get("success") is not True:
        raise RuntimeError(f"Linear {field} did not succeed: {str(node)[:120]}")
    return node


_FIND = """query RedTicket($title: String!, $project: ID!) {
    issues(first: 5, filter: {
        title: { eq: $title },
        state: { type: { in: ["triage", "backlog", "unstarted", "started"] } },
        project: { id: { eq: $project } }
    }) { nodes { id identifier title } }
}"""
_COMMENT = """mutation RedComment($input: CommentCreateInput!) {
    commentCreate(input: $input) { success }
}"""
_LABEL = """query FounderOnlyLabel($name: String!) {
    issueLabels(first: 20, filter: { name: { eq: $name } }) { nodes { id team { id } } }
}"""
_ADD_LABEL = """mutation RedAddLabel($id: String!, $labelId: String!) {
    issueAddLabel(id: $id, labelId: $labelId) { success }
}"""
_CREATE = """mutation RedCreate($input: IssueCreateInput!) {
    issueCreate(input: $input) { success issue { identifier } }
}"""


def _founder_only_label_id() -> str:
    """The founder-only label's id. Raises when it cannot be resolved: a
    founder-only red must never be filed as though an agent owned it."""
    nodes = (_graphql(_LABEL, {"name": FOUNDER_ONLY_LABEL}).get("issueLabels") or {}).get("nodes")
    # Team labels can share a name across teams: only a workspace label or this team's.
    usable = [
        n for n in (nodes if isinstance(nodes, list) else [])
        if isinstance(n, dict) and n.get("id") and (n.get("team") or {}).get("id") in (None, TEAM_ID)
    ]
    if not usable:
        raise RuntimeError(f"no '{FOUNDER_ONLY_LABEL}' label usable by team {TEAM_ID}")
    return usable[0]["id"]


def _open_matches(found: dict, title: str) -> list:
    """Open issues titled exactly ``title``. Raises unless issues.nodes is
    explicitly a list, so a malformed answer never reads as "none open"."""
    nodes = (found.get("issues") or {}).get("nodes") if isinstance(found.get("issues"), dict) else None
    if not isinstance(nodes, list):
        raise RuntimeError("Linear lookup returned no issues.nodes list")
    if any(not isinstance(n, dict) or not isinstance(n.get("title"), str) or not n.get("id") for n in nodes):
        raise RuntimeError("Linear lookup returned a node without id/title")
    return [n for n in nodes if n["title"] == title]


def _update(issue: dict, text: str, founder_only: bool) -> str | None:
    if founder_only:
        _require_success(_graphql(_ADD_LABEL, {"id": issue["id"], "labelId": _founder_only_label_id()}), "issueAddLabel")
    _require_success(_graphql(_COMMENT, {"input": {"issueId": issue["id"], "body": text}}), "commentCreate")
    return issue.get("identifier")


def _create(title: str, text: str, founder_only: bool) -> str | None:
    issue: dict[str, Any] = {
        "teamId": TEAM_ID, "projectId": PROJECT_ID,
        "title": title, "description": text, "priority": 2,
    }
    if founder_only:
        issue["labelIds"] = [_founder_only_label_id()]
    created = _require_success(_graphql(_CREATE, {"input": issue}), "issueCreate")
    # success:true means the issue exists. Never report that as unfiled: the
    # caller would retry and create a second one. The next find adopts it.
    return (created.get("issue") or {}).get("identifier") or "created-identifier-not-returned"


def upsert_red_linear_ticket(title: str, body: str, *, owner: str, founder_only: bool, log) -> str | None:
    """Serialised find-or-update; see ``_upsert``."""
    with _UPSERT_LOCK:
        return _upsert(title, body, owner=owner, founder_only=founder_only, log=log)


def _upsert(title: str, body: str, *, owner: str, founder_only: bool, log) -> str | None:
    """Comment on the open issue titled ``title``, or create it once. Returns its identifier.

    If the lookup fails or is malformed, nothing is created: a create after a
    failed find is how duplicate tickets are born. A founder-only red whose
    label cannot be resolved is not filed unlabelled; it logs an error.
    """
    if not config.LINEAR_API_KEY:
        log.warning("red ticket: LINEAR_API_KEY unset — not filed: %s", title)
        return None
    text = f"Owner: {owner}\nFounder-only: {'yes' if founder_only else 'no'}\n\n{body}"
    try:
        nodes = _open_matches(_graphql(_FIND, {"title": title, "project": PROJECT_ID}), title)
    except Exception as exc:  # noqa: BLE001
        log.error("red ticket: Linear lookup failed (%s) — not creating: %s", exc, title)
        return None
    try:
        if nodes:
            ident = _update(nodes[0], text, founder_only)
        else:
            ident = _create(title, text, founder_only)
        log.info("red ticket: %s %s (%s)", "updated" if nodes else "created", ident, title)
        return ident
    except Exception as exc:  # noqa: BLE001
        log.error("red ticket: Linear write failed (%s): %s", exc, title)
        return None
