"""
feedback_loop.py — RA-689: Outcome Feedback Loop (analyzing-customer-patterns)

Reads shipped feature records, collects post-ship signals from Linear,
detects outcome patterns, writes lessons back to lessons.jsonl, flags
stale features, and returns BVI "features delivered" contribution data.

Runs monthly via cron (1st of month, 08:00 UTC).
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger("pi-ceo.agents.feedback-loop")

_HARNESS_ROOT = Path(__file__).resolve().parents[3] / ".harness"
_SHIPPED_FEATURES_FILE = _HARNESS_ROOT / "shipped-features.jsonl"
_LESSONS_FILE = _HARNESS_ROOT / "lessons.jsonl"
_FEEDBACK_CACHE_FILE = _HARNESS_ROOT / "feedback-cache.json"

# How many days before a feature is considered stale (no outcome signal)
_STALE_DAYS = 30

# Linear API config
_LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")
_LINEAR_TEAM_ID = "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673"

# Positive/negative signal keywords in Linear comments
_POSITIVE_KEYWORDS = frozenset([
    "working", "works", "shipped", "live", "deployed", "done", "complete",
    "client happy", "looks good", "all good", "confirmed", "verified",
    "in production", "prod", "merged",
])
_NEGATIVE_KEYWORDS = frozenset([
    "broken", "broke", "reverted", "revert", "rollback", "regression",
    "client complaint", "not working", "failing", "failed", "hotfix",
    "emergency", "incident", "bug", "crash",
])


# ── Shipped features I/O ──────────────────────────────────────────────────────

def load_shipped_features() -> list[dict[str, Any]]:
    """Read all entries from shipped-features.jsonl."""
    if not _SHIPPED_FEATURES_FILE.exists():
        return []
    features = []
    for line in _SHIPPED_FEATURES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            features.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return features


def append_shipped_feature(
    pipeline_id: str,
    idea: str,
    review_score: float,
    linear_ticket_id: str | None = None,
) -> None:
    """Record a newly shipped feature. Called by pipeline.py after successful ship."""
    entry = {
        "pipeline_id": pipeline_id,
        "linear_ticket_id": linear_ticket_id or pipeline_id,
        "idea": idea,
        "review_score": review_score,
        "shipped_at": datetime.now(timezone.utc).isoformat(),
        "outcome_signal": None,  # filled in by feedback cycle
        "outcome_analysed_at": None,
    }
    try:
        with open(_SHIPPED_FEATURES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        log.info("Shipped feature recorded: pipeline=%s", pipeline_id)
    except OSError as exc:
        log.warning("Could not record shipped feature: %s", exc)


# ── Linear API helpers ────────────────────────────────────────────────────────

def _linear_gql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a Linear GraphQL query."""
    if not _LINEAR_API_KEY:
        raise RuntimeError("LINEAR_API_KEY not set")
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        "https://api.linear.app/graphql",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": _LINEAR_API_KEY,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    if "errors" in data:
        raise RuntimeError(f"Linear GraphQL errors: {data['errors']}")
    return data.get("data", {})


def _fetch_issue_comments(linear_id: str) -> list[str]:
    """Fetch comment bodies for a Linear issue. Returns list of lowercase strings."""
    try:
        data = _linear_gql(
            """
            query IssueComments($id: String!) {
              issue(id: $id) {
                comments { nodes { body } }
              }
            }
            """,
            {"id": linear_id},
        )
        nodes = data.get("issue", {}).get("comments", {}).get("nodes", [])
        return [n.get("body", "").lower() for n in nodes]
    except Exception as exc:
        log.warning("Could not fetch comments for %s: %s", linear_id, exc)
        return []


def _fetch_issue_state(linear_id: str) -> str:
    """Return the state name for a Linear issue (e.g. 'Done', 'In Progress')."""
    try:
        data = _linear_gql(
            """
            query IssueState($id: String!) {
              issue(id: $id) { state { name type } }
            }
            """,
            {"id": linear_id},
        )
        state = data.get("issue", {}).get("state", {})
        return state.get("name", "unknown")
    except Exception as exc:
        log.warning("Could not fetch state for %s: %s", linear_id, exc)
        return "unknown"


def _get_or_create_feedback_label() -> str | None:
    """Get or create a 'feedback' label in Linear. Returns label ID or None."""
    if not _LINEAR_API_KEY:
        return None
    try:
        data = _linear_gql(
            """
            query Labels($teamId: ID!) {
              issueLabels(filter: { team: { id: { eq: $teamId } } }) {
                nodes { id name }
              }
            }
            """,
            {"teamId": _LINEAR_TEAM_ID},
        )
        for label in data.get("issueLabels", {}).get("nodes", []):
            if label.get("name", "").lower() == "feedback":
                return label["id"]
        # Create it
        create = _linear_gql(
            """
            mutation CreateLabel($teamId: String!, $name: String!, $color: String!) {
              issueLabelCreate(input: { teamId: $teamId, name: $name, color: $color }) {
                issueLabel { id }
              }
            }
            """,
            {"teamId": _LINEAR_TEAM_ID, "name": "feedback", "color": "#8B5CF6"},
        )
        return create.get("issueLabelCreate", {}).get("issueLabel", {}).get("id")
    except Exception as exc:
        log.warning("Could not get/create feedback label: %s", exc)
        return None


def _create_stale_review_issue(feature: dict[str, Any], label_id: str | None, dry_run: bool) -> str | None:
    """Create a Linear [FEEDBACK] review issue for a stale shipped feature."""
    shipped_at = feature.get("shipped_at", "unknown")
    pipeline_id = feature.get("pipeline_id", "?")
    idea = feature.get("idea", "unknown feature")
    score = feature.get("review_score", 0)

    try:
        shipped_dt = datetime.fromisoformat(shipped_at.replace("Z", "+00:00"))
        days_ago = (datetime.now(timezone.utc) - shipped_dt).days
    except Exception:
        days_ago = "unknown"

    title = f"[FEEDBACK] {pipeline_id} — 30-day outcome check needed"
    body = (
        f"Feature \"{idea}\" was shipped {days_ago} days ago (review score: {score}/10).\n\n"
        f"No outcome signal detected in {_STALE_DAYS} days.\n\n"
        f"**Actions:**\n"
        f"1. Confirm the feature is live in production\n"
        f"2. Verify with client/user that it is working as intended\n"
        f"3. Add an outcome note (comment or update this issue)\n"
        f"4. If the feature has problems, create a remediation ticket\n\n"
        f"_Auto-raised by Pi-CEO feedback loop (RA-689). Shipped: {shipped_at}_"
    )

    if dry_run:
        log.info("[DRY RUN] Would create stale review issue: %s", title)
        return f"dry-run-{pipeline_id}"

    if not _LINEAR_API_KEY:
        log.warning("Cannot create Linear issue — LINEAR_API_KEY not set")
        return None

    try:
        variables: dict[str, Any] = {
            "teamId": _LINEAR_TEAM_ID,
            "title": title,
            "description": body,
            "priority": 3,  # Normal
        }
        if label_id:
            variables["labelIds"] = [label_id]

        data = _linear_gql(
            """
            mutation CreateIssue(
              $teamId: String!, $title: String!, $description: String!,
              $priority: Int!, $labelIds: [String!]
            ) {
              issueCreate(input: {
                teamId: $teamId, title: $title, description: $description,
                priority: $priority, labelIds: $labelIds
              }) {
                issue { identifier }
              }
            }
            """,
            variables,
        )
        identifier = data.get("issueCreate", {}).get("issue", {}).get("identifier")
        log.info("Created stale review issue: %s for %s", identifier, pipeline_id)
        return identifier
    except Exception as exc:
        log.warning("Could not create stale review issue for %s: %s", pipeline_id, exc)
        return None


# ── Signal detection ──────────────────────────────────────────────────────────

def _detect_signal(comments: list[str], state: str) -> str:
    """
    Analyse comments and issue state to determine outcome signal.
    Returns: 'positive' | 'negative' | 'neutral'
    """
    combined = " ".join(comments)
    has_positive = any(kw in combined for kw in _POSITIVE_KEYWORDS)
    has_negative = any(kw in combined for kw in _NEGATIVE_KEYWORDS)

    if has_negative:
        return "negative"
    if has_positive:
        return "positive"
    if state.lower() in ("done", "completed", "closed"):
        return "neutral"
    return "neutral"


# ── Pattern analysis ──────────────────────────────────────────────────────────

def _analyse_patterns(features_with_signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Detect recurring outcome patterns across shipped features.
    Returns list of pattern dicts.
    """
    patterns: list[dict[str, Any]] = []

    # Count negative features — surface if > 1
    negative = [f for f in features_with_signals if f.get("outcome_signal") == "negative"]
    if len(negative) > 1:
        patterns.append({
            "pattern": "recurring_post_ship_issues",
            "frequency": len(negative),
            "severity": "high" if len(negative) >= 3 else "medium",
            "description": f"{len(negative)} features had negative post-ship signals",
            "recommendation": "Review pre-ship test coverage; consider adding post-ship smoke tests",
        })

    # High-score features with negative outcomes — review gate may be too lenient
    high_score_negative = [
        f for f in negative
        if (f.get("review_score") or 0) >= 9
    ]
    if high_score_negative:
        patterns.append({
            "pattern": "high_score_negative_outcome",
            "frequency": len(high_score_negative),
            "severity": "high",
            "description": f"{len(high_score_negative)} features scored ≥9/10 in review but had negative outcomes",
            "recommendation": "Review gate may be over-scoring. Add production smoke tests to acceptance criteria.",
        })

    # Stale features — no signal at all
    stale = [f for f in features_with_signals if f.get("outcome_signal") == "stale"]
    if len(stale) >= 3:
        patterns.append({
            "pattern": "high_stale_rate",
            "frequency": len(stale),
            "severity": "medium",
            "description": f"{len(stale)} features have no outcome signal after {_STALE_DAYS} days",
            "recommendation": "Establish post-ship feedback protocol — Telegram confirmation or Linear comment within 7 days of deploy",
        })

    return patterns


# ── Lesson writing ────────────────────────────────────────────────────────────

def _write_outcome_lesson(feature: dict[str, Any], signal: str) -> None:
    """Append an outcome lesson to lessons.jsonl."""
    shipped_at = feature.get("shipped_at", "")
    try:
        shipped_dt = datetime.fromisoformat(shipped_at.replace("Z", "+00:00"))
        days_since = (datetime.now(timezone.utc) - shipped_dt).days
    except Exception:
        days_since = 0

    severity_map = {"positive": "info", "negative": "warn", "neutral": "info", "stale": "warn"}
    lesson_map = {
        "positive": f"Feature delivered successfully with positive outcome signal at {days_since} days post-ship.",
        "negative": f"Feature had negative post-ship signal at {days_since} days — investigate regression or client issue.",
        "neutral": f"Feature shipped {days_since} days ago with no explicit outcome signal. Mark confirmed or investigate.",
        "stale": f"Feature shipped {days_since} days ago with zero outcome signal — follow up with client/user.",
    }

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "analyzing-customer-patterns",
        "category": "outcome",
        "pipeline_id": feature.get("pipeline_id", "unknown"),
        "shipped_at": shipped_at,
        "days_since_ship": days_since,
        "outcome_signal": signal,
        "lesson": lesson_map.get(signal, "Unknown outcome."),
        "severity": severity_map.get(signal, "info"),
    }
    try:
        with open(_LESSONS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as exc:
        log.warning("Could not write outcome lesson: %s", exc)


# ── Cache helpers (avoid re-analysing features each run) ─────────────────────

def _load_cache() -> dict[str, Any]:
    if _FEEDBACK_CACHE_FILE.exists():
        try:
            return json.loads(_FEEDBACK_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(cache: dict[str, Any]) -> None:
    tmp = _FEEDBACK_CACHE_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        tmp.replace(_FEEDBACK_CACHE_FILE)
    except OSError as exc:
        log.warning("Could not save feedback cache: %s", exc)


# ── Main entry point ──────────────────────────────────────────────────────────

def run_feedback_cycle(dry_run: bool = False) -> dict[str, Any]:
    """
    Run the outcome feedback analysis cycle.

    1. Load shipped features from .harness/shipped-features.jsonl
    2. For each: fetch Linear signals (comments, state)
    3. Classify outcome: positive / negative / neutral / stale
    4. Write outcome lessons to lessons.jsonl
    5. Create stale review issues in Linear
    6. Return BVI contribution data

    Returns dict with: features_analysed, patterns, bvi_contribution, stale_issues_created
    """
    log.info("Feedback cycle starting (dry_run=%s)", dry_run)
    start = time.time()

    features = load_shipped_features()
    if not features:
        log.info("No shipped features found — nothing to analyse")
        return {
            "features_analysed": 0,
            "patterns": [],
            "bvi_contribution": {
                "features_with_positive_outcome": 0,
                "features_with_negative_outcome": 0,
                "features_stale": 0,
                "features_pending_signal": 0,
            },
            "stale_issues_created": [],
            "duration_s": round(time.time() - start, 2),
        }

    now = datetime.now(timezone.utc)
    cache = _load_cache()
    label_id: str | None = None
    features_with_signals: list[dict[str, Any]] = []
    stale_issues_created: list[str] = []
    outcome_lessons: list[dict[str, Any]] = []

    for feature in features:
        pipeline_id = feature.get("pipeline_id", "?")
        linear_id = feature.get("linear_ticket_id") or pipeline_id
        shipped_at_str = feature.get("shipped_at", "")

        # Calculate age
        try:
            shipped_dt = datetime.fromisoformat(shipped_at_str.replace("Z", "+00:00"))
            age_days = (now - shipped_dt).days
        except Exception:
            age_days = 0

        # Already analysed and cached with a final signal? Skip unless stale check needed
        cached = cache.get(pipeline_id, {})
        if cached.get("outcome_signal") in ("positive", "negative") and not cached.get("stale_issue_raised"):
            feature["outcome_signal"] = cached["outcome_signal"]
            features_with_signals.append(feature)
            continue

        # Stale: shipped > STALE_DAYS with no signal
        if age_days >= _STALE_DAYS and not cached.get("stale_issue_raised"):
            feature["outcome_signal"] = "stale"
            features_with_signals.append(feature)

            # Create Linear review issue
            if label_id is None:
                label_id = _get_or_create_feedback_label()
            issue_id = _create_stale_review_issue(feature, label_id, dry_run)
            if issue_id:
                stale_issues_created.append(issue_id)
                cache[pipeline_id] = {**cached, "stale_issue_raised": issue_id, "outcome_signal": "stale"}

            if not dry_run:
                _write_outcome_lesson(feature, "stale")
            continue

        # Fetch signals from Linear
        comments = _fetch_issue_comments(linear_id)
        state = _fetch_issue_state(linear_id)
        signal = _detect_signal(comments, state)

        feature["outcome_signal"] = signal
        features_with_signals.append(feature)

        # Cache and write lesson for non-neutral signals (or neutral after 7+ days)
        if signal in ("positive", "negative") or age_days >= 7:
            cache[pipeline_id] = {**cached, "outcome_signal": signal, "analysed_at": now.isoformat()}
            if not dry_run:
                _write_outcome_lesson(feature, signal)

    # Save updated cache
    if not dry_run:
        _save_cache(cache)

    # Analyse patterns
    patterns = _analyse_patterns(features_with_signals)

    # BVI contribution
    counts = {
        "features_with_positive_outcome": sum(1 for f in features_with_signals if f.get("outcome_signal") == "positive"),
        "features_with_negative_outcome": sum(1 for f in features_with_signals if f.get("outcome_signal") == "negative"),
        "features_stale": sum(1 for f in features_with_signals if f.get("outcome_signal") == "stale"),
        "features_pending_signal": sum(1 for f in features_with_signals if f.get("outcome_signal") == "neutral"),
    }

    elapsed = round(time.time() - start, 2)
    log.info(
        "Feedback cycle complete: features=%d positive=%d negative=%d stale=%d stale_issues=%d elapsed=%.1fs",
        len(features_with_signals),
        counts["features_with_positive_outcome"],
        counts["features_with_negative_outcome"],
        counts["features_stale"],
        len(stale_issues_created),
        elapsed,
    )

    return {
        "features_analysed": len(features_with_signals),
        "patterns": patterns,
        "outcome_lessons": outcome_lessons,
        "bvi_contribution": counts,
        "stale_issues_created": stale_issues_created,
        "duration_s": elapsed,
    }


# ── Board meeting summary helper ──────────────────────────────────────────────

def get_feedback_summary() -> dict[str, Any]:
    """
    Return a lightweight summary for board meeting Phase 1 STATUS.
    Reads shipped features + cache without making API calls.
    """
    features = load_shipped_features()
    if not features:
        return {"available": False, "reason": "No shipped features recorded yet"}

    cache = _load_cache()
    now = datetime.now(timezone.utc)

    positive = negative = stale = neutral = pending = 0
    for feature in features:
        pipeline_id = feature.get("pipeline_id", "?")
        cached = cache.get(pipeline_id, {})
        signal = cached.get("outcome_signal") or feature.get("outcome_signal")

        if not signal:
            # Check age
            try:
                shipped_dt = datetime.fromisoformat(
                    (feature.get("shipped_at") or "").replace("Z", "+00:00")
                )
                age_days = (now - shipped_dt).days
            except Exception:
                age_days = 0

            if age_days >= _STALE_DAYS:
                stale += 1
            else:
                pending += 1
        elif signal == "positive":
            positive += 1
        elif signal == "negative":
            negative += 1
        elif signal == "stale":
            stale += 1
        else:
            neutral += 1

    # Recent patterns from last feedback run
    recent_patterns: list[str] = []
    try:
        feedback_log_path = _HARNESS_ROOT / "feedback-cache.json"
        if feedback_log_path.exists():
            # Patterns not stored in cache — would need separate store; skip for now
            pass
    except Exception:
        pass

    return {
        "available": True,
        "total_shipped": len(features),
        "positive": positive,
        "negative": negative,
        "stale": stale,
        "neutral": neutral,
        "pending_signal": pending,
        "last_analysis": None,  # could add timestamp to cache header
    }
