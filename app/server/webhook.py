"""
webhook.py — GitHub and Linear webhook verification + event parsing.

Verifies HMAC-SHA256 signatures (timing-safe) and extracts repo_url
and metadata from webhook payloads.

GitHub: x-hub-signature-256 header, sha256=<hex> format
Linear: Linear-Signature header, raw hex format
"""
import hashlib, hmac, json


def verify_github_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature (timing-safe)."""
    if not secret or not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def verify_linear_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Verify Linear webhook HMAC-SHA256 signature (timing-safe)."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def parse_github_event(event_type: str, payload: dict) -> dict | None:
    """Extract repo_url, ref, and action from GitHub push/pull_request events.
    Returns None for unsupported events."""
    if event_type not in ("push", "pull_request"):
        return None
    repo_url = (payload.get("repository") or {}).get("html_url")
    if not repo_url:
        return None
    result = {"source": "github", "event": event_type, "repo_url": repo_url}
    if event_type == "push":
        result["ref"] = payload.get("ref", "")
    elif event_type == "pull_request":
        result["action"] = payload.get("action", "")
        pr = payload.get("pull_request") or {}
        result["ref"] = (pr.get("head") or {}).get("ref", "")
    return result


def parse_linear_event(payload: dict) -> dict | None:
    """Extract issue data from Linear Issue.update webhook events.
    Only triggers when an issue moves to 'started' (In Progress)."""
    action = payload.get("action")
    event_type = payload.get("type")
    if event_type != "Issue" or action != "update":
        return None
    data = payload.get("data") or {}
    # Check if state changed to started
    updated = payload.get("updatedFrom") or {}
    # Linear sends updatedFrom.stateId when state changed
    if "stateId" not in updated:
        return None
    state = (data.get("state") or {})
    if state.get("type") != "started":
        return None
    title = data.get("title", "")
    description = data.get("description", "")
    labels = [l.get("name", "") for l in (data.get("labels") or [])]
    priority = data.get("priority", 0)
    # Try to extract repo URL from issue labels or description
    repo_url = ""
    for label in labels:
        if label.startswith("repo:"):
            repo_url = label.replace("repo:", "").strip()
    return {
        "source": "linear",
        "event": "issue_started",
        "title": title,
        "description": description[:2000],
        "labels": labels,
        "priority": priority,
        "repo_url": repo_url,
    }


def linear_issue_to_brief(issue_data: dict) -> str:
    """Convert a Linear issue into a structured build brief."""
    title = issue_data.get("title", "Untitled")
    desc = issue_data.get("description", "")
    priority = issue_data.get("priority", 0)
    priority_label = {1: "URGENT", 2: "HIGH", 3: "NORMAL", 4: "LOW"}.get(priority, "NORMAL")

    brief = f"[{priority_label}] {title}\n\n"
    if desc:
        brief += f"Description:\n{desc}\n\n"
    brief += "Triggered automatically from Linear issue moving to In Progress."
    return brief
