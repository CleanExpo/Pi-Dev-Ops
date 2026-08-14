"""
webhook.py — GitHub and Linear webhook verification + event parsing.

Verifies HMAC-SHA256 signatures (timing-safe) and extracts repo_url
and metadata from webhook payloads.

GitHub: x-hub-signature-256 header, sha256=<hex> format
Linear: Linear-Signature header, raw hex format
"""
import hashlib
import hmac


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


# RA-7216: Linear state types that terminate an issue. "completed" is an
# acceptance; "canceled" is a rejection. Both end the founder-review window, so
# both must be captured — the distinction is carried in `state_type` rather than
# by dropping one, because a scorer that only ever sees acceptances measures
# nothing (that is exactly how C2 came to score 5/5 by construction).
_TERMINAL_STATE_TYPES = ("completed", "canceled")


def parse_linear_event(payload: dict) -> dict | None:
    """Extract issue data from Linear webhook events.

    Handles three triggers:
      - action=update + state→started  → issue moved to In Progress
      - action=update + state→terminal → issue accepted or cancelled (RA-7216)
      - action=create + priority≤2 + state=unstarted → Urgent/High issue created (RA-888)

    Returns a normalised dict for all three cases, or None to skip the event.
    """
    action = payload.get("action")
    event_type = payload.get("type")
    if event_type != "Issue":
        return None
    data = payload.get("data") or {}

    if action == "update":
        updated = payload.get("updatedFrom") or {}
        if "stateId" not in updated:
            return None
        state = (data.get("state") or {})
        state_type = state.get("type")
        if state_type == "started":
            event_name = "issue_started"
        elif state_type in _TERMINAL_STATE_TYPES:
            # RA-7216: the acceptance event. Before this, the only "acceptance"
            # signal written anywhere was the literal string "In Review",
            # hardcoded at push time in session_linear.py and never revisited —
            # so no terminal outcome was observable and `accepted_at` had no
            # source. This is that source.
            event_name = "issue_completed"
        else:
            return None

    elif action == "create":
        # RA-888: instant trigger — fire on Urgent (1) or High (2) new issues in unstarted state
        priority = data.get("priority", 0)
        if priority not in (1, 2):
            return None
        state = (data.get("state") or {})
        if state.get("type") != "unstarted":
            return None
        event_name = "issue_created"

    else:
        return None

    title = data.get("title", "")
    description = data.get("description", "")
    labels = [lbl.get("name", "") for lbl in (data.get("labels") or [])]
    priority = data.get("priority", 0)

    # Extract repo URL from labels first, then description lines
    repo_url = ""
    for label in labels:
        if label.startswith("repo:"):
            repo_url = label.replace("repo:", "").strip()
    if not repo_url:
        for line in description.splitlines():
            if line.startswith("repo:"):
                repo_url = line.replace("repo:", "").strip()
                break

    return {
        "source": "linear",
        "event": event_name,
        "issue_id": data.get("id", ""),
        "title": title,
        "description": description[:2000],
        "labels": labels,
        "priority": priority,
        "repo_url": repo_url,
        # RA-7216: carried on every event, not just terminal ones, so a caller
        # never has to infer state from the event name. `state_type` is the
        # field that separates an acceptance ("completed") from a rejection
        # ("canceled") — the event name deliberately does not.
        "state_name": state.get("name", ""),
        "state_type": state.get("type", ""),
        # Linear sets completedAt on terminal transitions. updatedAt is the
        # fallback so a cancelled issue (which may carry no completedAt) still
        # yields a timestamp; without one the review-latency arithmetic has no
        # end point and the row would be silently unmeasurable.
        "occurred_at": data.get("completedAt") or data.get("updatedAt") or "",
    }


def linear_issue_to_brief(issue_data: dict) -> str:
    """Convert a Linear issue event into a structured build brief."""
    title = issue_data.get("title", "Untitled")
    desc = issue_data.get("description", "")
    priority = issue_data.get("priority", 0)
    priority_label = {1: "URGENT", 2: "HIGH", 3: "NORMAL", 4: "LOW"}.get(priority, "NORMAL")
    event = issue_data.get("event", "issue_started")

    if event == "issue_created":
        trigger_line = "Triggered automatically: Urgent/High Linear issue created (RA-888 instant webhook)."
    else:
        trigger_line = "Triggered automatically from Linear issue moving to In Progress."

    brief = f"[{priority_label}] {title}\n\n"
    if desc:
        brief += f"Description:\n{desc}\n\n"
    brief += trigger_line
    return brief
