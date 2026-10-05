"""
autonomy.py — Linear autonomy-queue poller + autonomous build pickup (RA-584, RA-1369).

Polls every portfolio Linear project on a TAO_AUTONOMY_POLL_INTERVAL cadence
(default 300 s) for the autonomous-work queue and starts a build session per
ticket. The autonomy-pickup signal is defined by the Pi-Dev × Linear contract
(skills/pi-dev-linear-contract/SKILL.md) and requires BOTH:

  1. Linear status name == "Ready for Pi-Dev"  (dedicated autonomy status)
  2. Label "pi-dev:autonomous" present          (explicit human authorisation)

Neither alone is sufficient. The previous filter (state.type=unstarted +
priority<=2) accidentally claimed every high-priority Todo across the
workspace, including triage-pending tickets.

Per ticket:
  1. Transition → Pi-Dev: In Progress (fallback: In Progress)
  2. Build a structured brief
  3. Infer intent + scope from labels / estimate
  4. Trigger create_session() to start the 5-phase build pipeline
  5. On failure, park → team Blocked state + label, release claim (never Ready)

Startup recovery:
  6. Any ticket left In Progress by a prior process instance with no live
     session → transition to Pi-Dev: Blocked + label
     pi-dev:blocked-reason:session-lost + comment explaining.

All actions logged to .harness/autonomy.jsonl.

Kill switch: TAO_AUTONOMY_ENABLED=0  (default: on)
"""
import asyncio
import json
import logging
import os
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any
from app.server import config_loader, session_lease
from .autonomy_evidence import calc_effective_autonomy as _calc_effective_autonomy, generation_blocked
from app.server.autonomy_eligibility import (
    AUTONOMY_LABEL as _AUTONOMY_LABEL,
    MACHINE_SHIP_LABEL as _MACHINE_SHIP_LABEL,
    READY_STATUS_NAME as _READY_STATUS_NAME,
)
from app.server import autonomy_queue as _aq
from .autonomy_orphan_queries import _IN_PROGRESS_QUERY, _RECOVERY_TARGET_QUERY
from .autonomy_orphan_support import (
    issue_pages, needs_recovery_success, orphan_completion, recovery_comment_present,
    record_recovery_attempt, record_recovery_success, transition_orphan_issue,
)
from .autonomy_linear_rate import (
    LinearRateLimitError,
    has_linear_rate_limit_error as _has_linear_rate_limit_error,
    linear_rate_limited,
    mark_linear_rate_limited as _mark_linear_rate_limited,
)

log = logging.getLogger("pi-ceo.autonomy")

_LINEAR_ENDPOINT = "https://api.linear.app/graphql"


_AUTONOMY_LOG = (
    Path(os.path.dirname(__file__)).parents[1] / ".harness" / "autonomy.jsonl"
)

# Pi - Dev -Ops project / team constants (matches config/harness/projects.json)
_PROJECT_ID = "f45212be-3259-4bfb-89b1-54c122c939a7"
_TEAM_ID    = "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673"
_DEFAULT_REPO_URL = "https://github.com/CleanExpo/Pi-Dev-Ops"

# RA-1289 — portfolio registry. Poller spans every project in config/harness/projects.json
# so Urgent/High Todos on target-repo boards (Synthex, Unite-Group, CARSI, DR-NRPG…)
# trigger autonomous builds — not just Pi-Dev-Ops's own board.
_PROJECTS_JSON = (
    config_loader.PROJECTS_JSON
)




def _load_portfolio_projects() -> list[dict]:
    """Load `config/harness/projects.json` → list of dicts with the fields the poller needs.

    Each entry: {project_id, team_id, repo_url, name}.
    Projects without `linear_project_id` are skipped (can't filter by project).
    The Pi-Dev-Ops entry is always included as the first item for backwards compat.
    """
    try:
        registry = json.loads(_PROJECTS_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Autonomy: projects.json load failed (%s) — falling back to Pi-Dev-Ops only", exc)
        return [{
            "project_id": _PROJECT_ID,
            "team_id": _TEAM_ID,
            "repo_url": _DEFAULT_REPO_URL,
            "name": "Pi - Dev -Ops",
        }]

    out: list[dict] = []
    for p in registry.get("projects", []):
        project_id = p.get("linear_project_id")
        team_id    = p.get("linear_team_id")
        repo       = p.get("repo")
        if not project_id or not team_id or not repo:
            continue
        out.append({
            "project_id": project_id,
            "team_id":    team_id,
            "repo_url":   f"https://github.com/{repo}",
            "name":       p.get("linear_project_name") or p.get("id") or repo,
        })
    return out

# In-memory state (for /api/autonomy/status)
_last_poll_at: float = 0.0
_poll_count: int = 0
_recent_events: list[dict] = []

# RA-1973 — watchdog diagnostic surface. The poller crashed silently for 16 h
# on Railway prod on 2026-05-05 because the `while True` body had no try/except.
# `_poller_iteration_errors` counts iteration crashes (loop survived), and
# `_last_iteration_error` stores the most recent traceback summary so /health
# and /api/autonomy/status can surface it.
_poller_iteration_errors: int = 0
_last_iteration_error: dict | None = None

# RA-1973 — per-team orphan-recovery state map. Hard-coding "Pi-Dev: Blocked"
# only worked for the RA team workflow. DR-NRPG and other teams 500'd because
# that state name doesn't exist on their boards. "Todo" is the universal
# fallback (every team has it). Override at process boot via the
# TAO_ORPHAN_RECOVERY_STATES env var (JSON dict: team_uuid -> state_name).
_RA_TEAM_ID         = "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673"
_DR_NRPG_TEAM_ID    = "43811130-ac12-47d3-9433-330320a76205"
_SYN_TEAM_ID        = "b887971b-6761-4260-a111-b94dbb628ebe"
_GP_TEAM_ID         = "91b3cd04-86eb-422d-81e2-9aa37db2f2f5"
_UNI_TEAM_ID        = "ab9c7810-4dd6-4ce2-8e8f-e1fc94c6b88b"

_DEFAULT_ORPHAN_RECOVERY_STATES: dict[str, str] = {
    _RA_TEAM_ID:      "Pi-Dev: Blocked",  # RA — original choice, preserved
    _DR_NRPG_TEAM_ID: "Todo",
    _SYN_TEAM_ID:     "Todo",
    _GP_TEAM_ID:      "Todo",
    _UNI_TEAM_ID:     "Todo",
}
_ORPHAN_RECOVERY_FALLBACK_STATE = "Todo"


def _load_orphan_recovery_state_map() -> dict[str, str]:
    """Load per-team orphan-recovery state map, env-overridable at boot.

    Parse `TAO_ORPHAN_RECOVERY_STATES` once at module import. Falls back to
    `_DEFAULT_ORPHAN_RECOVERY_STATES` on JSON parse failure (logs a warning).
    """
    raw = os.environ.get("TAO_ORPHAN_RECOVERY_STATES", "").strip()
    if not raw:
        return dict(_DEFAULT_ORPHAN_RECOVERY_STATES)
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("TAO_ORPHAN_RECOVERY_STATES must decode to a dict")
        # Merge over defaults so partial overrides keep the default fallbacks.
        merged = dict(_DEFAULT_ORPHAN_RECOVERY_STATES)
        for k, v in parsed.items():
            if isinstance(k, str) and isinstance(v, str):
                merged[k] = v
        return merged
    except Exception as exc:
        log.warning(
            "Autonomy: TAO_ORPHAN_RECOVERY_STATES parse failed (%s) — using defaults",
            exc,
        )
        return dict(_DEFAULT_ORPHAN_RECOVERY_STATES)


_ORPHAN_RECOVERY_STATE_BY_TEAM: dict[str, str] = _load_orphan_recovery_state_map()
_unknown_team_warned: set[str] = set()


def _recovery_state_for(team_id: str) -> str:
    """Return the orphan-recovery state name for a team_id; Todo as ultimate fallback."""
    state = _ORPHAN_RECOVERY_STATE_BY_TEAM.get(team_id)
    if state:
        return state
    if team_id not in _unknown_team_warned:
        log.warning(
            "Autonomy: unknown team_id %s for orphan recovery — using fallback '%s'",
            team_id, _ORPHAN_RECOVERY_FALLBACK_STATE,
        )
        _unknown_team_warned.add(team_id)
    return _ORPHAN_RECOVERY_FALLBACK_STATE


def _send_watchdog_telegram(message: str) -> None:
    """Best-effort Telegram alert via raw urllib. Silent on failure.

    Only fires when both TELEGRAM_BOT_TOKEN and TELEGRAM_ALERT_CHAT_ID env
    vars are set. Uses a 5 s timeout and never re-raises — the watchdog must
    not crash because of a failed alert.
    """
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_ALERT_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        url     = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
        req     = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5).close()
    except Exception as exc:
        log.warning("Autonomy watchdog: Telegram alert failed: %s", exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _gql(api_key: str, query: str, variables: dict | None = None, *, timeout: int = 15) -> dict[str, Any]:
    if linear_rate_limited():
        raise LinearRateLimitError("Linear rate limited; retry after cooldown")
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        _LINEAR_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise _mark_linear_rate_limited() from None
        # GraphQL can return quota errors as HTTP 400 with earlier, long errors.
        # Read a bounded complete envelope; an oversized response is unknown, so
        # stop further Linear requests instead of treating truncation as nonquota.
        raw = exc.read(65537)
        if len(raw) > 65536:
            raise _mark_linear_rate_limited() from None
        try:
            if _has_linear_rate_limit_error(json.loads(raw)):
                raise _mark_linear_rate_limited() from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        raise RuntimeError(f"Linear HTTP {exc.code}") from None
    if _has_linear_rate_limit_error(data):
        raise _mark_linear_rate_limited()
    if "errors" in data:
        raise RuntimeError("Linear GQL errors")
    return data.get("data", {})


def _log_event(event: dict) -> None:
    global _recent_events
    entry = {**event, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    _AUTONOMY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(_AUTONOMY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    _recent_events.append(entry)
    _recent_events = _recent_events[-20:]  # keep last 20 in memory


# ---------------------------------------------------------------------------
# Linear API calls
# ---------------------------------------------------------------------------

# RA-1369 / UNI-2648 — pickup contract is issue_is_claimable (eligibility.py).
# The old dashboard filter (state.type=unstarted + priority<=2) is retired.
_BLOCKED_STATUS_NAME = "Pi-Dev: Blocked"
_BLOCKED_REASON_SESSION_LOST = "pi-dev:blocked-reason:session-lost"

# RA-2209 (empire-overview board memo 2026-05-10 · E3 phase 2). Founder-ruled
# scope tighten: poller only claims tickets carrying one of the labels listed in
# PI_CEO_AUTONOMY_PRIORITY_FILTER. Empty/unset (the code default) preserves the
# pre-RA-2209 behaviour — the filter is opt-in at deploy time so existing tests
# don't break and the operator decides explicitly when to scope the poller.
#
# Production setting at this commit (per founder ruling 2026-05-10):
#   PI_CEO_AUTONOMY_PRIORITY_FILTER="q2-priority-1,q2-priority-2"
# in the Railway / Vercel env config. 14-day window aligning autonomy with
# Q2 priorities #1 (CCW) and #2 (RA App Store). Remove the env var (or set
# empty) to revert to all-priorities behaviour.
_PRIORITY_FILTER_RAW = os.environ.get("PI_CEO_AUTONOMY_PRIORITY_FILTER", "").strip()
_PRIORITY_FILTER: set[str] = {
    s.strip() for s in _PRIORITY_FILTER_RAW.split(",") if s.strip()
}

_TODO_ISSUES_QUERY = _aq.TODO_ISSUES_QUERY  # W1b: paginated, carries the claim-guard fields


def fetch_todo_issues(api_key: str, *, fail_on_error: bool = False,
                      refused: list | None = None) -> list[dict]:
    """Claimable queue, every page. Repeat-claim refusals go to ``refused``."""
    projects = _load_portfolio_projects()
    seen: set[str] = set()
    merged: list[dict] = []
    for p in projects:
        for label in (_AUTONOMY_LABEL, _MACHINE_SHIP_LABEL):
            try:
                nodes = list(_aq.issue_pages(_gql, api_key, {
                    "projectId": p["project_id"],
                    "statusName": _READY_STATUS_NAME,
                    "autonomyLabel": label,
                }))
            except LinearRateLimitError:
                raise
            except Exception as exc:
                if fail_on_error:
                    raise RuntimeError("Linear portfolio scan failed") from None
                log.warning("Autonomy: project %s label %s fetch failed: %s", p["name"], label, exc)
                continue
            for issue in nodes:
                iid = issue.get("id")
                if not iid or iid in seen:
                    continue
                seen.add(iid)
                issue["_repo_url"] = p["repo_url"]
                issue["_team_id"] = p["team_id"]
                issue["_project_name"] = p["name"]
                issue["_project_id"] = p["project_id"]
                merged.append(issue)
    merged = _aq.claimable_or_refused(
        merged, refused,
        registered_project_ids={p["project_id"] for p in projects},
        priority_labels=_PRIORITY_FILTER,
    )
    merged.sort(key=lambda i: i.get("priority", 3))
    return merged


def _resolve_state_id(api_key: str, state_name: str, team_id: str = _TEAM_ID) -> str:
    """Resolve a human-readable state name to a Linear state ID for a given team.

    RA-1289 — accepts `team_id` so transitions work on any portfolio team, not
    just Pi-Dev-Ops. Defaults to `_TEAM_ID` for backwards compat with any caller
    still operating on the Pi-Dev-Ops board.
    """
    query = """
    query TeamStates($teamId: String!) {
        team(id: $teamId) {
            states { nodes { id name } }
        }
    }
    """
    data = _gql(api_key, query, {"teamId": team_id})
    states = (data.get("team") or {}).get("states", {}).get("nodes", [])
    target = next((s for s in states if s["name"].lower() == state_name.lower()), None)
    if not target:
        raise RuntimeError(f"State '{state_name}' not found in team {team_id} workflow")
    return target["id"]


def transition_issue(api_key: str, issue_id: str, state_name: str, team_id: str = _TEAM_ID) -> None:
    """Move a Linear issue to the named state (e.g. 'In Progress', 'Todo').

    RA-1289 — `team_id` defaults to Pi-Dev-Ops for compat; poller passes the
    issue's mapped team so cross-project tickets transition correctly.
    """
    state_id = _resolve_state_id(api_key, state_name, team_id=team_id)
    mutation = """
    mutation UpdateIssue($id: String!, $stateId: String!) {
        issueUpdate(id: $id, input: { stateId: $stateId }) { success }
    }
    """
    _gql(api_key, mutation, {"id": issue_id, "stateId": state_id})


def comment_on_issue(api_key: str, issue_id: str, body: str) -> None:
    """Post a comment on a Linear issue."""
    mutation = """
    mutation CreateComment($issueId: String!, $body: String!) {
        commentCreate(input: { issueId: $issueId, body: $body }) { success }
    }
    """
    _gql(api_key, mutation, {"issueId": issue_id, "body": body})


def _resolve_or_create_label(api_key: str, team_id: str, label_name: str) -> str | None:
    """Resolve a label name to a label id on the given team; create if missing.

    Returns the label id or None on failure (caller logs and continues — we do
    NOT block the transition just because label creation fails).
    """
    query = """
    query TeamLabels($teamId: String!) {
        team(id: $teamId) { labels { nodes { id name } } }
    }
    """
    try:
        data   = _gql(api_key, query, {"teamId": team_id})
        labels = (data.get("team") or {}).get("labels", {}).get("nodes", [])
        for lb in labels:
            if lb.get("name", "").lower() == label_name.lower():
                return lb.get("id")
        # Not found — create it.
        mutation = """
        mutation CreateLabel($teamId: String!, $name: String!, $color: String!) {
            issueLabelCreate(input: { teamId: $teamId, name: $name, color: $color })
            { issueLabel { id } }
        }
        """
        created = _gql(api_key, mutation,
                       {"teamId": team_id, "name": label_name, "color": "#EF4444"})
        return (created.get("issueLabelCreate", {})
                       .get("issueLabel", {}) or {}).get("id")
    except LinearRateLimitError:
        raise
    except Exception as exc:
        log.warning("label resolve/create failed (team=%s name=%s): %s",
                    team_id, label_name, exc)
        return None


def add_label_to_issue(api_key: str, issue_id: str, team_id: str, label_name: str) -> bool:
    """Add `label_name` to the issue's existing label set. Returns True on success.

    Reads current labels first so existing labels are preserved (issueUpdate
    replaces the full set).
    """
    label_id = _resolve_or_create_label(api_key, team_id, label_name)
    if not label_id:
        return False
    # Fetch existing label ids so we preserve them.
    fetch = """
    query IssueLabels($id: String!) {
        issue(id: $id) { labels { nodes { id } } }
    }
    """
    try:
        data     = _gql(api_key, fetch, {"id": issue_id})
        existing = [n.get("id") for n in
                    ((data.get("issue") or {}).get("labels", {}).get("nodes", []))
                    if n.get("id")]
        merged   = sorted(set(existing + [label_id]))
        mutation = """
        mutation AddLabel($id: String!, $labelIds: [String!]!) {
            issueUpdate(id: $id, input: { labelIds: $labelIds }) { success }
        }
        """
        _gql(api_key, mutation, {"id": issue_id, "labelIds": merged})
        return True
    except LinearRateLimitError:
        raise
    except Exception as exc:
        log.warning("add_label_to_issue failed (issue=%s label=%s): %s",
                    issue_id, label_name, exc)
        return False


# ---------------------------------------------------------------------------
# Brief construction
# ---------------------------------------------------------------------------

def _extract_repo_url(issue: dict) -> str:
    """Resolve repo URL for an issue.

    Priority (highest first):
      1. `repo:` label (explicit override on the ticket)
      2. `repo:` line in the description (legacy override)
      3. RA-1289 — mapped `_repo_url` annotation from `fetch_todo_issues`
         (picked up from `config/harness/projects.json` for the issue's project)
      4. Pi-Dev-Ops default

    Overrides 1+2 still win because some cross-project tickets target a
    different repo than their Linear project's default (e.g. a ticket in the
    Pi-Dev-Ops project that asks for a fix in a sibling repo).
    """
    labels = [ln["name"] for ln in (issue.get("labels") or {}).get("nodes", [])]
    for label in labels:
        if label.startswith("repo:"):
            return label.replace("repo:", "").strip()
    desc = issue.get("description", "") or ""
    for line in desc.splitlines():
        if line.startswith("repo:"):
            return line.replace("repo:", "").strip()
    mapped = issue.get("_repo_url")
    if mapped:
        return mapped
    return _DEFAULT_REPO_URL


def _build_brief(issue: dict) -> str:
    """Build a structured brief from a Linear issue dict."""
    priority_map = {1: "URGENT", 2: "HIGH", 3: "NORMAL", 4: "LOW"}
    priority_label = priority_map.get(issue.get("priority", 3), "NORMAL")
    title = issue.get("title", "Untitled")
    desc = (issue.get("description") or "").strip()
    brief = f"[{priority_label}] {title}\n\n"
    if desc:
        brief += f"Description:\n{desc}\n\n"
    brief += (
        f"Linear ticket: {issue.get('identifier')} — {issue.get('url')}\n"
        "Triggered automatically by Pi-CEO autonomous poller.\n"
    )
    return brief


# RA-1373 — intent + scope inference from Linear labels
# ---------------------------------------------------------------------------
# session_phases.py only calls classify_intent(brief) when `intent` is empty
# and the classifier defaults to BUG when signals are ambiguous. That's wrong
# for UI/UX tickets (SYN-753 first run logged Intent=BUG, plan_confidence=20%).
# Linear labels carry the truth — read them in the poller and pass through.

# Label → intent mapping. First match wins; extend as the portfolio grows.
_INTENT_BY_LABEL = {
    "ui-ux":             "refactor",
    "ui":                "refactor",
    "design-tokens":     "refactor",
    "foundation":        "feature",
    "feature":           "feature",
    "enhancement":       "feature",
    "bug":               "bug",
    "regression":        "bug",
    "security":          "bug",
    "performance":       "refactor",
    "refactor":          "refactor",
    "docs":              "docs",
    "test":              "test",
    "ci":                "bug",
    "dependencies":      "chore",
    "chore":             "chore",
}


def _infer_intent(issue: dict) -> str:
    """Derive generator intent from Linear labels. Empty string = let classifier decide."""
    labels = [ln.get("name", "") for ln in (issue.get("labels") or {}).get("nodes", [])]
    for label in labels:
        normalised = label.lower().strip()
        if normalised in _INTENT_BY_LABEL:
            return _INTENT_BY_LABEL[normalised]
    return ""


# RA-1495 — autonomous poller filter for non-code tickets.
# DR-535 (a legal-process escalation explicitly tagged "not a code change")
# was picked up by the poller in 2026-04-20 and triggered a 28%-confidence
# planner session against non-existent files. Time + tokens wasted with no
# code committed. The fix: skip tickets that are:
#   1. Labelled `no-code` / `manual-action` / `legal`
#   2. Body contains the phrase "not a code change" or "manual escalation"
# These tickets stay in the operator's view but the engineering pipeline
# never claims them.
_NO_CODE_LABELS = frozenset({"no-code", "manual-action", "legal"})
_NO_CODE_PHRASES = ("not a code change", "manual escalation")


def _should_skip_no_code(issue: dict) -> tuple[bool, str | None]:
    """Return (skip, reason) — skip=True if this ticket isn't engineering work.

    Reason is a short tag suitable for log + jsonl: "label:legal", "phrase:..."
    or None when not skipped.
    """
    label_nodes = (issue.get("labels") or {}).get("nodes") or []
    label_names = {(n.get("name") or "").strip().lower() for n in label_nodes}
    matched = label_names & _NO_CODE_LABELS
    if matched:
        return True, f"label:{sorted(matched)[0]}"

    haystack_parts = [
        issue.get("title") or "",
        issue.get("description") or "",
    ]
    haystack = " ".join(haystack_parts).lower()
    for phrase in _NO_CODE_PHRASES:
        if phrase in haystack:
            return True, f"phrase:{phrase}"

    return False, None


_TERMINAL_SESSION_STATUSES = frozenset({
    "complete", "done", "failed", "error", "killed", "interrupted", "blocked",
})


def _live_session_ids(sessions: dict) -> set[str]:
    """Session IDs that are still actively running (not terminal).

    Interrupted sessions restored from disk must not block orphan recovery —
    otherwise tickets like RA-1691 stay stuck In Progress forever after a
    failed evaluator pass.
    """
    out: set[str] = set()
    for sid, sess in sessions.items():
        status = (getattr(sess, "status", None) or "").lower()
        if status in _TERMINAL_SESSION_STATUSES:
            continue
        out.add(sid[:12])
    return out


def _is_pi_ceo_orphan(issue: dict, live_session_ids: set[str]) -> bool:
    """True when no referenced Pi-CEO session remains live."""
    comments = (issue.get("comments") or {}).get("nodes", [])
    referenced_ids: list[str] = []
    for c in comments:
        body = c.get("body", "")
        # Match `Session ID: `<12hex>`` (our session-started comment format)
        import re
        for m in re.finditer(r"Session ID:\s*`([0-9a-f]{8,})`", body):
            referenced_ids.append(m.group(1)[:12])
    if not referenced_ids:
        return False
    # Orphan if NONE of the referenced sessions are currently live
    return not any(sid in live_session_ids for sid in referenced_ids)


def _orphan_recovery_blocking(api_key: str) -> None:
    """Keep the poller's recovery entry point on a worker thread (RA-7845)."""
    asyncio.run(_orphan_recovery(api_key))


_ORPHAN_COMMENT_MARKER = "Pi-CEO orphan recovery — session lost."
_logged_orphan_recoveries: set[str] = set()


def _orphan_completion(issue: dict) -> tuple[bool, bool]:
    return orphan_completion(issue, _BLOCKED_REASON_SESSION_LOST, _ORPHAN_COMMENT_MARKER)


def _comment_on_orphan(api_key: str, iid: str, target_state: str,
                       issue: dict, label_ok: bool) -> bool:
    changed = False
    if not recovery_comment_present(issue, _gql, api_key, _ORPHAN_COMMENT_MARKER):
        comment_on_issue(
            api_key, iid,
            "🤖 **Pi-CEO orphan recovery — session lost.**\n\n"
            "The previous Pi-CEO session claimed this ticket but is no "
            "longer running (likely a Railway restart or process crash "
            "— in-memory session state did not survive).\n\n"
            f"- Transitioned to `{target_state}`.\n"
            f"- Label `{_BLOCKED_REASON_SESSION_LOST}` attached "
            f"({'OK' if label_ok else 'attach failed — see server log'}).\n\n"
            "A human (or the next contract-audit pass) should confirm "
            "state, remove the blocked-reason label, then move back to `Ready for Pi-Dev`.",
        )
        changed = True
    return changed


def _recover_orphan_issue(api_key: str, project: dict, issue: dict) -> int:
    iid, ident, team_id = issue["id"], issue.get("identifier", "?"), project["team_id"]
    target_state = _recovery_state_for(team_id)
    already_target = (issue.get("state") or {}).get("name", "").lower() == target_state.lower()
    if already_target and all(_orphan_completion(issue)):
        if needs_recovery_success(_AUTONOMY_LOG, _logged_orphan_recoveries, iid, ident):
            record_recovery_success(_log_event, _logged_orphan_recoveries, iid, ident,
                                    target_state, _BLOCKED_REASON_SESSION_LOST, True)
            return 1
        return 0
    try:
        if not already_target:
            record_recovery_attempt(_log_event, _logged_orphan_recoveries,
                                    iid, ident, target_state)
        labelled, _ = _orphan_completion(issue)
        label_ok = labelled or add_label_to_issue(api_key, iid, team_id,
                                                  _BLOCKED_REASON_SESSION_LOST)
        if not already_target and not transition_orphan_issue(
                transition_issue, _log_event, log, api_key, iid, ident, team_id, target_state):
            return 0
        changed = _comment_on_orphan(api_key, iid, target_state, issue, label_ok)
        if (not already_target or (not labelled and label_ok) or changed
                or needs_recovery_success(_AUTONOMY_LOG, _logged_orphan_recoveries, iid, ident)):
            log.info("orphan-recovery: transitioned %s to %s (session-lost)", ident, target_state)
            record_recovery_success(_log_event, _logged_orphan_recoveries, iid, ident,
                                    target_state, _BLOCKED_REASON_SESSION_LOST, label_ok)
            return 1
        return 0
    except LinearRateLimitError as exc:
        _logged_orphan_recoveries.discard(iid)
        _log_event({"action": "orphan_recovery_error", "ticket": ident,
                    "error": str(exc), "transition": target_state})
        raise
    except Exception as exc:
        log.warning("orphan-recovery: block %s failed: %s", ident, exc)
        _log_event({"action": "orphan_recovery_error", "ticket": ident, "error": str(exc)})
        return 0


def _orphan_recovery_sync(api_key: str) -> None:
    """Block session-lost tickets once at startup, off the ASGI event loop."""
    from .sessions import _sessions  # late import to avoid circular
    live_ids = _live_session_ids(_sessions)

    projects = _load_portfolio_projects()
    reverted = 0
    checked  = 0

    for p in projects:
        seen: set[str] = set()
        queries = (
            (_RECOVERY_TARGET_QUERY, {"projectId": p["project_id"],
                                      "targetState": _recovery_state_for(p["team_id"])}),
            (_IN_PROGRESS_QUERY, {"projectId": p["project_id"]}),
        )
        for query, variables in queries:
            try:
                for nodes in issue_pages(_gql, api_key, query, variables,
                                         paginate=query == _RECOVERY_TARGET_QUERY):
                    for issue in nodes:
                        if issue["id"] in seen:
                            continue
                        checked += 1
                        if not _is_pi_ceo_orphan(issue, live_ids):
                            continue
                        if (query == _RECOVERY_TARGET_QUERY
                                and not _orphan_completion(issue)[0]
                                and not recovery_comment_present(
                                    issue, _gql, api_key, _ORPHAN_COMMENT_MARKER)):
                            continue
                        seen.add(issue["id"])
                        reverted += _recover_orphan_issue(api_key, p, issue)
            except LinearRateLimitError:
                raise
            except Exception as exc:
                log.warning("orphan-recovery: project %s fetch failed: %s", p["name"], exc)

    log.info("orphan-recovery complete: checked=%d blocked=%d live_sessions=%d",
             checked, reverted, len(live_ids))


async def _orphan_recovery(api_key: str) -> None:
    """Keep startup Linear reconciliation off the ASGI event loop."""
    await asyncio.to_thread(_orphan_recovery_sync, api_key)


def _infer_scope(issue: dict) -> dict:
    """Default scope contract for autonomy sessions.

    Without a scope contract the evaluator has no file-count ceiling and a
    session can produce a sprawling 40-file diff that never gets reviewed
    properly. Derive from Linear estimate when available; otherwise cap at
    15 files (conservative default for autonomous work).

    Linear `estimate` semantics vary team-to-team but the convention inside
    this workspace is roughly 1 point = 1–3 files of touching. 3x gives a
    generous ceiling; cap at 30 to keep catastrophic blast radius impossible.
    """
    estimate = issue.get("estimate")
    try:
        pts = int(estimate) if estimate else 0
    except (TypeError, ValueError):
        pts = 0
    max_files = min(max(pts * 3, 15), 30)
    return {"type": "auto-routine", "max_files_modified": max_files}


# ---------------------------------------------------------------------------
# Poller
# ---------------------------------------------------------------------------

async def linear_todo_poller() -> None:
    """
    Background coroutine. Every TAO_AUTONOMY_POLL_INTERVAL seconds:
      - fetch Urgent/High Todo issues from Linear
      - for each one with a repo URL, fire a build session
    """
    from . import config  # late import to avoid circular
    from .sessions import create_session

    global _last_poll_at, _poll_count

    interval = int(os.environ.get("TAO_AUTONOMY_POLL_INTERVAL", "300"))
    # Startup delay — small grace period so the API is fully up before poll #1,
    # but NOT a full interval. Previously this was `await asyncio.sleep(interval)`
    # which meant after every Railway restart the poller sat idle for 5 full
    # minutes before its first fetch. That bootstrap delay is what made the
    # system look "stuck" and required a manual prompt to kick it back into life.
    startup_delay = int(os.environ.get("TAO_AUTONOMY_STARTUP_DELAY", "10"))
    log.info(
        "Autonomy poller started (interval=%ds, startup_delay=%ds, enabled=%s)",
        interval, startup_delay, config.AUTONOMY_ENABLED,
    )

    # Do-while: first iteration fires after `startup_delay` seconds, subsequent
    # iterations wait the full `interval`.
    first_iter = True
    orphan_recovery_done = False  # RA-1373 — run once per process lifetime
    # RA-1973 — watchdog: wrap the iteration body in try/except so an unhandled
    # exception in any single cycle does NOT kill the asyncio task. Prior to
    # this, a single stack trace silently terminated the poller and /health
    # kept returning 200. Outer loop structure (do-while + sleep) is preserved.
    while True:
        await asyncio.sleep(startup_delay if first_iter else interval)
        first_iter = False
        try:
            orphan_recovery_done = await _run_poller_iteration(
                config, create_session, orphan_recovery_done,
            )
        except Exception as exc:  # pragma: no cover — defense in depth
            _record_iteration_error(exc)
            continue


async def _ensure_orphan_recovery(config: Any, done: bool) -> bool:
    if done or not config.AUTONOMY_ENABLED or not config.LINEAR_API_KEY or linear_rate_limited():
        return done
    try:
        await asyncio.to_thread(_orphan_recovery_blocking, config.LINEAR_API_KEY)
    except LinearRateLimitError as exc:
        log.warning("orphan-recovery rate limited; pausing Linear reads")
        _log_event({"action": "poll_error", "error": str(exc)})
        return False
    except Exception as exc:
        log.error("orphan-recovery crashed: %s", exc)
    return True


async def _run_poller_iteration(
    config: Any,
    create_session: Any,
    orphan_recovery_done: bool,
) -> bool:
    """RA-1973 — single iteration body, extracted so the watchdog can wrap it.

    Returns the (possibly updated) `orphan_recovery_done` flag so the caller
    keeps the once-per-process semantic.
    """
    global _last_poll_at, _poll_count

    # RA-1373 — orphan-transition recovery, once at startup. Any ticket
    # left In Progress by a previous process instance (Railway restart /
    # crash) with no live session gets reverted to Todo + explanatory
    # comment, so the next poll reclaims it instead of it sitting stuck.
    orphan_recovery_done = await _ensure_orphan_recovery(config, orphan_recovery_done)

    if not config.AUTONOMY_ENABLED:
        log.debug("Autonomy poller: disabled (TAO_AUTONOMY_ENABLED=0)")
        return orphan_recovery_done

    # RA-1966 — TAO hard-stop file aborts the autonomy poller too. Operator
    # touches TAO_HARD_STOP_FILE → next poll exits with reason="HARD_STOP",
    # surfaced loudly so /health goes degraded.
    try:
        from . import kill_switch as _ks  # noqa: PLC0415
        _ks.check_hard_stop()
    except _ks.KillSwitchAbort as abort:
        log.warning("Autonomy poller: hard-stop file detected — pausing (%s)", abort.snapshot)
        return orphan_recovery_done

    if linear_rate_limited():
        return orphan_recovery_done

    if not config.LINEAR_API_KEY:
        # Warn loudly EVERY poll, not just once — this was the silent-failure
        # mode that made Pi-Dev-Ops look healthy while nothing was happening.
        log.warning(
            "Autonomy poller: LINEAR_API_KEY not set — skipping poll #%d (check Railway env vars)",
            _poll_count + 1,
        )
        return orphan_recovery_done

    _last_poll_at = time.time()
    _poll_count += 1
    log.info("Autonomy poll #%d", _poll_count)

    try:
        issues = await asyncio.to_thread(fetch_todo_issues, config.LINEAR_API_KEY)
        await asyncio.to_thread(_aq.block_repeat_claims, config.LINEAR_API_KEY, _aq.drain_repeat_claims())
    except Exception as exc:
        log.error("Autonomy poll #%d: fetch failed: %s", _poll_count, exc)
        _log_event({"action": "poll_error", "poll": _poll_count, "error": str(exc)})
        return orphan_recovery_done

    log.info("Autonomy poll #%d: %d todo issues found", _poll_count, len(issues))
    _log_event({"action": "poll", "poll": _poll_count, "found": len(issues)})
    for issue in issues:
        await _process_autonomy_issue(config, create_session, issue)
    return orphan_recovery_done


async def _process_autonomy_issue(
    config: Any,
    create_session: Any,
    issue: dict,
) -> None:
    """Process one issue; record ticket failures without stopping the queue."""
    issue_id   = issue["id"]
    identifier = issue.get("identifier", "?")
    title      = issue.get("title", "?")
    repo_url   = _extract_repo_url(issue)
    team_id    = issue.get("_team_id", _TEAM_ID)  # RA-1289 — mapped team

    log.info(
        "Autonomy: processing %s '%s' repo=%s team=%s",
        identifier, title, repo_url, team_id,
    )

    # RA-1495 — skip manual-escalation / non-engineering tickets.
    skip_no_code, skip_reason = _should_skip_no_code(issue)
    if skip_no_code:
        log.info(
            "Autonomy: skipping %s '%s' — non-code ticket (reason=%s)",
            identifier, title, skip_reason,
        )
        _log_event({
            "action": "skip_no_code",
            "ticket": identifier,
            "title": title,
            "reason": skip_reason,
        })
        return

    if generation_blocked(identifier, _log_event):
        return
    if _aq.token_cap_refusal(config, issue_id, identifier, team_id):
        return  # W1b: at its cumulative token cap across retries — parked, never claimed

    label_names = {
        n.get("name", "")
        for n in (issue.get("labels") or {}).get("nodes", [])
        if isinstance(n, dict)
    }
    if _MACHINE_SHIP_LABEL in label_names and os.environ.get("TAO_MACHINE_SHIP_MODE", "0") == "1":
        from app.server.spec_pipeline import run_pipeline  # noqa: PLC0415

        transitioned_to = _transition_to_in_progress(
            config, issue_id, identifier, title, team_id,
        )
        if transitioned_to is None:
            return
        proposal = f"{title}\n\n{issue.get('description') or ''}"
        try:
            result = await run_pipeline(
                proposal,
                trigger="linear",
                issue_id=issue_id,
                dry_run=False,
            )
            _log_event({
                "action": "machine_spec_pipeline",
                "ticket": identifier,
                "pipeline_id": result.pipeline_id,
                "status": result.status,
                "pr_url": result.pr_url,
            })
        except Exception as exc:  # noqa: BLE001
            log.exception("Autonomy machine-ship failed for %s", identifier)
            _log_event({"action": "machine_spec_pipeline_error", "ticket": identifier, "error": str(exc)})
        session_lease.release_linear_ticket(identifier, "done")  # W1b: never hold a finished claim
        return

    transitioned_to = _transition_to_in_progress(config, issue_id, identifier, title, team_id)
    if transitioned_to is None:
        return
    _aq.remember_claim(issue_id, identifier)

    _log_event({
        "action": "transition_to_in_progress",
        "ticket": identifier,
        "title": title,
        "repo_url": repo_url,
        "target_state": transitioned_to,
    })

    brief = _build_brief(issue)
    inferred_intent = _infer_intent(issue)
    inferred_scope  = _infer_scope(issue)
    try:
        session = await create_session(
            repo_url=repo_url,
            brief=brief,
            model="sonnet",
            intent=inferred_intent,
            scope=inferred_scope,
            linear_issue_id=issue_id,
            autonomy_triggered=True,
        )
        log.info("Autonomy: session %s started for %s", session.id, identifier)
        _log_event({
            "action": "session_started",
            "ticket": identifier,
            "title": title,
            "session_id": session.id,
            "repo_url": repo_url,
        })
        try:
            comment_on_issue(
                config.LINEAR_API_KEY,
                issue_id,
                (
                    f"🤖 **Pi-CEO autonomous session started**\n\n"
                    f"- Session ID: `{session.id}`\n"
                    f"- Repo: {repo_url}\n"
                    f"- Triggered by: autonomy poller (poll #{_poll_count})"
                ),
            )
        except Exception as exc:
            log.warning("Autonomy: comment post failed for %s: %s", identifier, exc)

    except Exception as exc:
        # W1b: a failed start is parked Blocked and its claim released. Reverting
        # it to Ready is what let RA-7785 be claimed 14 times in one day.
        _aq.fail_start(config.LINEAR_API_KEY, issue_id, identifier, team_id, exc)


def _transition_error(identifier: str, title: str, exc: BaseException) -> None:
    """Log + ring-record one failed Linear transition, and give back the claim it won."""
    log.error("Autonomy: transition failed for %s: %s", identifier, exc)
    _log_event({"action": "transition_error", "ticket": identifier,
                "title": title, "error": str(exc)})
    session_lease.release_linear_ticket(identifier, "released")  # W1b: nothing started


def _transition_to_in_progress(
    config: Any,
    issue_id: str,
    identifier: str,
    title: str,
    team_id: str,
) -> str | None:
    """Claim the ticket fleet-wide, then move it to 'Pi-Dev: In Progress'.

    The claim is the same `mesh_work_claims` INSERT the mesh dispatcher and a
    runner's `claim/self` use, guarded by the `mesh_work_claims_one_open`
    partial unique index — one lock, all claimants. Linear's own state is not a
    lock: the poll and the transition are two round trips, so every replica saw
    the same Ready ticket and each started its own session on it. A 409 means
    another worker owns it — return None and let the caller skip the ticket.
    """
    if not session_lease.claim_linear_ticket(identifier):
        log.info("Autonomy: %s claimed by another worker — skipping", identifier)
        return None
    try:
        transition_issue(config.LINEAR_API_KEY, issue_id,
                         "Pi-Dev: In Progress", team_id=team_id)
        return "Pi-Dev: In Progress"
    except RuntimeError as exc:
        if "not found" in str(exc).lower():
            log.info(
                "Autonomy: 'Pi-Dev: In Progress' not configured for team %s — "
                "falling back to 'In Progress' (RA-1298 workspace-setup pending)",
                team_id,
            )
            try:
                transition_issue(config.LINEAR_API_KEY, issue_id,
                                 "In Progress", team_id=team_id)
                return "In Progress"
            except Exception as inner:
                _transition_error(identifier, title, inner)
                return None
        _transition_error(identifier, title, exc)
        return None
    except Exception as exc:
        _transition_error(identifier, title, exc)
        return None


def _record_iteration_error(exc: BaseException) -> None:
    """RA-1973 — watchdog: log + count + alert on iteration crash."""
    global _poller_iteration_errors, _last_iteration_error
    log.exception("autonomy poller iteration crashed: %s", exc)
    _poller_iteration_errors += 1
    iso_now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _last_iteration_error = {
        "error": str(exc),
        "type":  type(exc).__name__,
        "ts":    iso_now,
        "count": _poller_iteration_errors,
    }
    _log_event({
        "action": "poller_iteration_error",
        "error":  str(exc),
        "count":  _poller_iteration_errors,
    })
    # First failure (1) → wake-up alert; tenth (10) → escalation.
    if _poller_iteration_errors in (1, 10):
        _send_watchdog_telegram(
            f"Pi-CEO autonomy poller crashed (count={_poller_iteration_errors})\n"
            f"Type: {type(exc).__name__}\n"
            f"Error: {exc}\n"
            f"Loop survived; investigate Railway logs."
        )


# ---------------------------------------------------------------------------
# Status (for /api/autonomy/status endpoint)
# ---------------------------------------------------------------------------


def autonomy_status() -> dict:
    """Return poller heartbeat + recent events for the status endpoint."""
    from . import config
    from .machine_ship_readiness import machine_ship_readiness
    from .session_sdk import generation_readiness

    now = time.time()
    age = round(now - _last_poll_at) if _last_poll_at else None
    return {
        "enabled": config.AUTONOMY_ENABLED,
        "poll_interval_s": int(os.environ.get("TAO_AUTONOMY_POLL_INTERVAL", "300")),
        "last_poll_at": _last_poll_at or None,
        "last_poll_ago_s": age,
        "stale": age is not None and age > 900,
        "poll_count": _poll_count,
        # RA-1973 — watchdog diagnostic surface for /health + dashboard.
        "poller_iteration_errors": _poller_iteration_errors,
        "last_iteration_error": _last_iteration_error,
        "effective_autonomy": _calc_effective_autonomy(_recent_events),  # RA-626
        "machine_ship": machine_ship_readiness(),  # RA-6885
        "generation": generation_readiness(),
        "planner": _planner_runtime_status(),  # OM-1 lookahead
        "recent_events": _recent_events,
    }


def _planner_runtime_status() -> dict:
    from .tao_planner import planner_runtime_status
    return planner_runtime_status()
