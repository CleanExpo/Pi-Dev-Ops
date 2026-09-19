"""Complete GitHub CI evidence for one immutable commit; no network fallback."""
from __future__ import annotations


class CIVerificationError(RuntimeError):
    """CI policy or evidence cannot safely authorize a merge."""


def all_pages(request, path: str, *, key: str | None = None) -> list[dict]:
    items, expected = [], None
    for page in range(1, 101):
        separator = "&" if "?" in path else "?"
        payload = request("GET", f"{path}{separator}per_page=100&page={page}")
        if key is not None:
            if not isinstance(payload, dict) or type(payload.get("total_count")) is not int:
                raise CIVerificationError("Malformed CI pagination metadata")
            total = payload["total_count"]
            if total < 0 or total > 10000 or (expected is not None and total != expected):
                raise CIVerificationError("CI evidence changed or exceeds pagination limit")
            expected, batch = total, payload.get(key)
        else:
            batch = payload
        if not isinstance(batch, list) or len(batch) > 100 or any(not isinstance(row, dict) for row in batch):
            raise CIVerificationError("Malformed GitHub evidence page")
        items.extend(batch)
        if len(batch) < 100:
            if expected is not None and len(items) != expected:
                raise CIVerificationError("Incomplete CI evidence pagination")
            return items
    raise CIVerificationError("GitHub evidence pagination limit exceeded")


def _latest(rows, *, check_runs: bool, candidate_sha: str) -> dict:
    latest, seen = {}, set()
    for row in rows:
        ident = row.get("id")
        name = row.get("name" if check_runs else "context")
        if type(ident) is not int or ident <= 0 or ident in seen or not isinstance(name, str) or not name:
            raise CIVerificationError("Ambiguous or malformed CI evidence")
        seen.add(ident)
        if check_runs:
            app = row.get("app")
            if row.get("head_sha") != candidate_sha or not isinstance(app, dict) or type(app.get("id")) is not int:
                raise CIVerificationError("CI evidence is not bound to candidate and app")
            key = (name, app["id"])
        else:
            key = name
        # GitHub run/status IDs identify creation order, including newer reruns
        # that have no completed_at timestamp yet. Never prefer an older success.
        if key not in latest or ident > latest[key]["id"]:
            latest[key] = row
    return latest


def candidate_evidence(request, repo: str, candidate_sha: str) -> tuple[dict, dict]:
    root = f"/repos/{repo}/commits/{candidate_sha}"
    suites = request("GET", f"{root}/check-suites?per_page=1&page=1")
    # GitHub truncates the ref's check-runs endpoint above 1000 suites. Do not
    # mistake a completely paginated truncated response for complete evidence.
    if (not isinstance(suites, dict) or type(suites.get("total_count")) is not int
            or not 0 <= suites["total_count"] <= 1000):
        raise CIVerificationError("Candidate check-suite count is unknown or exceeds complete-evidence limit")
    runs = all_pages(request, f"{root}/check-runs?filter=all", key="check_runs")
    statuses = all_pages(request, f"{root}/statuses")
    return (_latest(runs, check_runs=True, candidate_sha=candidate_sha),
            _latest(statuses, check_runs=False, candidate_sha=candidate_sha))


def required_result(required: frozenset, runs: dict, statuses: dict) -> str:
    pending = False
    for context, app in required:
        matches = [row for (name, ident), row in runs.items() if name == context and (app is None or ident == app)]
        status = statuses.get(context)
        # A legacy status has no app identity. It cannot satisfy an app-bound
        # requirement, and when both surfaces exist both must report success.
        if not matches and (status is None or app is not None):
            pending = True
        for row in matches:
            state = row.get("status")
            if state not in {"queued", "in_progress", "requested", "waiting", "pending", "completed"}:
                raise CIVerificationError("Unknown check-run state")
            if state != "completed":
                pending = True
            elif row.get("conclusion") != "success":
                return "failed"
        if status is not None:
            state = status.get("state")
            if state not in {"error", "failure", "pending", "success"}:
                raise CIVerificationError("Unknown legacy status state")
            if state in {"error", "failure"}:
                return "failed"
            pending |= state == "pending"
    return "pending" if pending else "passed"
