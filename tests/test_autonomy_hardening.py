"""
test_autonomy_hardening.py — RA-1373 regression tests.

Locks:
  - _infer_intent() returns correct string per label, "" on unknown.
  - _infer_scope() computes max_files from estimate with clamps.
  - _is_pi_ceo_orphan() detects orphaned tickets correctly.
"""
from app.server import autonomy


# ── intent inference ─────────────────────────────────────────────────────────
def _issue_with_labels(*names):
    return {"labels": {"nodes": [{"name": n} for n in names]}}


def test_infer_intent_ui_ux_label():
    assert autonomy._infer_intent(_issue_with_labels("ui-ux")) == "refactor"


def test_infer_intent_bug_wins_first_match():
    # First label match wins; bug comes first so returns bug even though
    # ui-ux would also match.
    assert autonomy._infer_intent(_issue_with_labels("bug", "ui-ux")) == "bug"


def test_infer_intent_case_insensitive():
    assert autonomy._infer_intent(_issue_with_labels("UI-UX")) == "refactor"
    assert autonomy._infer_intent(_issue_with_labels("  Bug  ")) == "bug"


def test_infer_intent_no_match_returns_empty():
    assert autonomy._infer_intent(_issue_with_labels("purple", "whimsy")) == ""
    assert autonomy._infer_intent({"labels": {"nodes": []}}) == ""
    assert autonomy._infer_intent({}) == ""


# ── scope inference ──────────────────────────────────────────────────────────
def test_infer_scope_default_no_estimate():
    s = autonomy._infer_scope({})
    assert s == {"type": "auto-routine", "max_files_modified": 15}


def test_infer_scope_estimate_scales_by_three():
    # estimate 4 → 12 → clamped up to floor 15
    assert autonomy._infer_scope({"estimate": 4})["max_files_modified"] == 15
    # estimate 6 → 18
    assert autonomy._infer_scope({"estimate": 6})["max_files_modified"] == 18
    # estimate 20 → 60 → clamped down to ceiling 30
    assert autonomy._infer_scope({"estimate": 20})["max_files_modified"] == 30


def test_infer_scope_bad_estimate_falls_back():
    assert autonomy._infer_scope({"estimate": "abc"})["max_files_modified"] == 15
    assert autonomy._infer_scope({"estimate": None})["max_files_modified"] == 15


# ── orphan detection ─────────────────────────────────────────────────────────
def test_is_pi_ceo_orphan_session_alive():
    """Ticket has session_id in comment and that session is live → NOT orphan."""
    issue = {
        "comments": {"nodes": [
            {"body": "🤖 **Pi-CEO autonomous session started**\n\n- Session ID: `abc123def456`\n- Repo: x"},
        ]}
    }
    live_ids = {"abc123def456"}
    assert autonomy._is_pi_ceo_orphan(issue, live_ids) is False


def test_is_pi_ceo_orphan_session_dead():
    """Ticket references a session_id that's NOT in live set → orphan."""
    issue = {
        "comments": {"nodes": [
            {"body": "🤖 **Pi-CEO autonomous session started**\n\n- Session ID: `deadbeef1234`\n"},
        ]}
    }
    assert autonomy._is_pi_ceo_orphan(issue, {"otherlivesession"}) is True


def test_is_pi_ceo_orphan_no_comments():
    """No Pi-CEO session comment at all → NOT an orphan (it was never claimed by us)."""
    issue = {"comments": {"nodes": []}}
    assert autonomy._is_pi_ceo_orphan(issue, set()) is False


def test_is_pi_ceo_orphan_multiple_comments_latest_session_dead():
    """Multiple session comments; ANY live match → NOT orphan; none live → orphan."""
    issue = {
        "comments": {"nodes": [
            {"body": "Session ID: `aaaa11112222`"},
            {"body": "Session ID: `bbbb33334444`"},
        ]}
    }
    # one live → not orphan
    assert autonomy._is_pi_ceo_orphan(issue, {"bbbb33334444"}) is False
    # none live → orphan
    assert autonomy._is_pi_ceo_orphan(issue, {"zzzz99998888"}) is True
