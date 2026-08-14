"""
test_ra7216_outcome_events.py — RA-7216 gap 2, phases 2-6.

Spec: .spm/RA-7216-completion.md. Covers the three detectors, the outcome_events
writer, the filter escaping (RA-7219), and C1's re-point.

All Supabase HTTP is mocked. No live network in CI.
"""
import importlib.util
from types import SimpleNamespace
from unittest.mock import patch


def _load_scorer():
    spec = importlib.util.spec_from_file_location("zte_v2_score", "scripts/zte_v2_score.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _attributed(n):
    return [{"gate_check_id": i} for i in range(n)]


def _unattributed(n):
    return [{"gate_check_id": None} for _ in range(n)]


def _merged(n):
    return [{"merge_sha": f"sha{i}", "shipped": True} for i in range(n)]


# ── RA-7219: filter escaping ──────────────────────────────────────────────────

def test_filter_values_are_percent_encoded():
    """MUTATION CONTROL: drop _q() from the filters → this fails.

    An unescaped `&` starts a new filter parameter, silently BROADENING a PATCH
    so it updates rows it was never meant to touch. `_patch` only checks the
    HTTP status, so the wrong-row update is invisible.
    """
    from app.server import supabase_log

    captured = {}
    with patch.object(supabase_log, "_patch",
                      side_effect=lambda t, f, b: captured.update(filter=f) or True):
        supabase_log.record_acceptance(
            linear_issue_id="evil&accepted_at=is.null&id",
            state_name="Done", state_type="completed",
        )
    assert "&accepted_at=is.null&id" not in captured["filter"].split("linear_issue_id=eq.")[1].split("&")[0]
    assert "%26" in captured["filter"]


def test_repo_name_slash_is_encoded():
    from app.server import supabase_log

    captured = {}
    with patch.object(supabase_log, "_patch",
                      side_effect=lambda t, f, b: captured.update(filter=f) or True):
        supabase_log.record_merge(repo_name="CleanExpo/Pi-Dev-Ops", pr_number=7, merge_sha="abc")
    assert "CleanExpo%2FPi-Dev-Ops" in captured["filter"]


# ── revert parsing ────────────────────────────────────────────────────────────

def test_revert_commit_shas_are_extracted():
    from app.server.webhook import parse_revert_commit

    assert parse_revert_commit(
        'Revert "feat: thing"\n\nThis reverts commit a1b2c3d4e5f6789012345678901234567890abcd.'
    ) == "a1b2c3d4e5f6789012345678901234567890abcd"
    assert parse_revert_commit('Revert "feat: thing"\n\nThis reverts commit a1b2c3d.') == "a1b2c3d"


def test_non_reverts_are_not_matched():
    """NEGATIVE CONTROL. Without this, 'always return a SHA' passes the case
    above and every ordinary push would record a rollback."""
    from app.server.webhook import parse_revert_commit

    assert parse_revert_commit("feat: do not revert this\n\nThis reverts commit a1b2c3d.") is None
    assert parse_revert_commit('Revert "feat: thing"\n\nno sha here') is None
    assert parse_revert_commit("chore: discuss revert policy") is None
    assert parse_revert_commit("") is None


# ── Detector A ────────────────────────────────────────────────────────────────

def _push_event(ref="refs/heads/main", default_branch="main", message=None, sha="deadbeef1234"):
    return {
        "source": "github", "event": "push", "repo_url": "https://github.com/CleanExpo/X",
        "repo_name": "CleanExpo/X", "default_branch": default_branch, "ref": ref,
        "head_commit_sha": sha,
        "head_commit_message": message or 'Revert "feat: x"\n\nThis reverts commit abc1234.',
        "head_commit_timestamp": "2026-08-14T05:00:00Z",
        "commits": [],
    }


def test_revert_on_default_branch_is_recorded():
    """MUTATION CONTROL: remove the detector call → this fails."""
    from app.server.routes import webhooks as wh

    calls = []
    with patch.object(wh, "record_outcome_event", side_effect=lambda **kw: calls.append(kw) or True), \
         patch.object(wh, "find_gate_check_by_merge_sha", return_value=42), \
         patch.object(wh, "is_recorded_revert", return_value=False):
        kinds = wh._record_reverts_in_push(_push_event())

    assert kinds == ["revert"]
    assert calls[0]["kind"] == "revert"
    assert calls[0]["gate_check_id"] == 42
    assert calls[0]["merge_sha"] == "abc1234"


def test_revert_on_feature_branch_is_ignored():
    """MUTATION CONTROL: drop the default-branch guard → this fails.

    A revert on a feature branch reverts something that never shipped, so it is
    not a rollback of anything Pi-CEO delivered.
    """
    from app.server.routes import webhooks as wh

    calls = []
    with patch.object(wh, "record_outcome_event", side_effect=lambda **kw: calls.append(kw) or True):
        kinds = wh._record_reverts_in_push(_push_event(ref="refs/heads/feature/x"))
    assert kinds == []
    assert calls == []


def test_ordinary_push_records_nothing():
    from app.server.routes import webhooks as wh

    calls = []
    with patch.object(wh, "record_outcome_event", side_effect=lambda **kw: calls.append(kw) or True):
        kinds = wh._record_reverts_in_push(_push_event(message="feat: add a thing"))
    assert kinds == [] and calls == []


def test_revert_of_a_revert_is_classified_as_re_land():
    """MUTATION CONTROL: drop the is_recorded_revert branch → this fails.

    A revert of a revert re-lands the original change. Counting it as a second
    rollback would double-penalise the recovery.
    """
    from app.server.routes import webhooks as wh

    calls = []
    with patch.object(wh, "record_outcome_event", side_effect=lambda **kw: calls.append(kw) or True), \
         patch.object(wh, "find_gate_check_by_merge_sha", return_value=None), \
         patch.object(wh, "is_recorded_revert", return_value=True):
        kinds = wh._record_reverts_in_push(_push_event())
    assert kinds == ["re_land"]


def test_unattributable_revert_is_still_recorded():
    """MUTATION CONTROL: skip recording when the lookup misses → this fails.

    Dropping it would rebuild the survivorship bias slice 2 removed. Per the §9
    decision these are counted separately, never discarded.
    """
    from app.server.routes import webhooks as wh

    calls = []
    with patch.object(wh, "record_outcome_event", side_effect=lambda **kw: calls.append(kw) or True), \
         patch.object(wh, "find_gate_check_by_merge_sha", return_value=None), \
         patch.object(wh, "is_recorded_revert", return_value=False):
        wh._record_reverts_in_push(_push_event())
    assert calls[0]["gate_check_id"] is None


def test_head_commit_is_not_double_recorded():
    """head_commit is normally also present in commits[]; one delivery must not
    produce two rows for the same SHA."""
    from app.server.routes import webhooks as wh

    ev = _push_event()
    ev["commits"] = [{"id": ev["head_commit_sha"], "message": ev["head_commit_message"],
                      "timestamp": "2026-08-14T05:00:00Z"}]
    calls = []
    with patch.object(wh, "record_outcome_event", side_effect=lambda **kw: calls.append(kw) or True), \
         patch.object(wh, "find_gate_check_by_merge_sha", return_value=1), \
         patch.object(wh, "is_recorded_revert", return_value=False):
        wh._record_reverts_in_push(ev)
    assert len(calls) == 1


# ── attribution lookups ───────────────────────────────────────────────────────

def test_ambiguous_sha_prefix_is_not_guessed():
    """MUTATION CONTROL: accept the first of several matches → this fails.

    Attributing a revert to the WRONG session is worse than not attributing it.
    """
    from app.server import supabase_log

    with patch.object(supabase_log, "_select", return_value=[{"id": 1}, {"id": 2}]):
        assert supabase_log.find_gate_check_by_merge_sha("abc1234") is None


def test_single_match_attributes():
    from app.server import supabase_log

    with patch.object(supabase_log, "_select", return_value=[{"id": 7}]):
        assert supabase_log.find_gate_check_by_merge_sha("abc1234") == 7


def test_reopen_lookup_requires_an_accepted_row():
    """Detector B's basis: the filter must demand accepted_at is not null, or a
    never-accepted issue would read as a reopen."""
    from app.server import supabase_log

    captured = {}
    with patch.object(supabase_log, "_select",
                      side_effect=lambda t, p: captured.update(params=p) or []):
        supabase_log.find_accepted_gate_check("issue-1")
    assert "accepted_at=not.is.null" in captured["params"]


# ── outcome_events writer ─────────────────────────────────────────────────────

def test_record_outcome_event_rejects_incomplete_rows():
    from app.server import supabase_log

    with patch.object(supabase_log, "_insert") as ins:
        assert supabase_log.record_outcome_event(
            kind="", repo_name="r", occurred_at="t", detected_by="d") is False
        assert supabase_log.record_outcome_event(
            kind="revert", repo_name="", occurred_at="t", detected_by="d") is False
    ins.assert_not_called()


# ── C1 re-point ───────────────────────────────────────────────────────────────

def test_c1_reports_rate_unattributed_and_coverage():
    """MUTATION CONTROL: fold unattributed into the rate → this fails."""
    z = _load_scorer()
    z._fetch_outcome_events = lambda k, d: _attributed(6) + _unattributed(2) if k == "revert" else []
    score, note = z.score_c1_deployment_success(_merged(100), 30)
    assert "observed_rollback_rate=6/100" in note
    assert "unattributed_reverts=2" in note
    assert "attribution_coverage=75%" in note
    assert score == 3


def test_c1_degrades_when_coverage_collapses():
    """MUTATION CONTROL: delete the coverage floor → this fails.

    A rate over 6 attributed reverts while 40 went unattributed reads as
    reassurance when it is the opposite.
    """
    z = _load_scorer()
    z._fetch_outcome_events = lambda k, d: _attributed(6) + _unattributed(40) if k == "revert" else []
    score, note = z.score_c1_deployment_success(_merged(100), 30)
    assert score == 1
    assert "needs_data" in note and "coverage" in note


def test_c1_degrades_below_the_attributed_floor():
    z = _load_scorer()
    z._fetch_outcome_events = lambda k, d: _attributed(4) if k == "revert" else []
    score, note = z.score_c1_deployment_success(_merged(100), 30)
    assert score == 1 and "needs_data" in note


def test_c1_is_never_a_ship_rate():
    """MUTATION CONTROL: restore shipped/total → this fails.

    With zero reverts recorded, a perfect ship rate must NOT produce a score.
    """
    z = _load_scorer()
    z._fetch_outcome_events = lambda k, d: []
    score, note = z.score_c1_deployment_success(_merged(50), 30)
    assert score == 1
    assert "needs_data" in note


# ── the seven metrics ─────────────────────────────────────────────────────────

def _accepted_row(**kw):
    base = {"accepted_at": "2026-08-14T05:00:00Z", "accepted_state_type": "completed",
            "push_timestamp": "2026-08-14T03:00:00Z",
            "session_started_at": "2026-08-14T02:00:00Z", "merge_sha": "a"}
    base.update(kw)
    return base


def test_metrics_derive_latency_and_trigger_to_accepted():
    z = _load_scorer()
    z._fetch_outcome_events = lambda k, d: []
    m = z.compute_ra7216_metrics([_accepted_row()], 30)
    assert m["review_latency"]["value"] == 120.0
    assert m["trigger_to_accepted_outcome"]["value"] == 180.0
    assert "QUEUE time" in m["review_latency"]["provenance"]


def test_metric_2_is_needs_data_with_a_reason():
    """MUTATION CONTROL: derive human_correction_count from reopens → fails.

    A reopen is not a correction. Inventing the number is what the ticket's
    first guardrail forbids.
    """
    z = _load_scorer()
    z._fetch_outcome_events = lambda k, d: [{"gate_check_id": 1}] * 5
    m = z.compute_ra7216_metrics([_accepted_row()], 30)
    assert m["human_correction_count"]["state"] == "needs_data"
    assert m["human_correction_count"]["value"] is None
    assert "no source" in m["human_correction_count"]["reason"]


def test_every_metric_is_measured_or_needs_data():
    """The goal's completion condition, asserted directly."""
    z = _load_scorer()
    z._fetch_outcome_events = lambda k, d: []
    m = z.compute_ra7216_metrics([_accepted_row()], 30)
    assert len(m) == 7
    for name, entry in m.items():
        assert entry["state"] in ("measured", "needs_data"), name
        if entry["state"] == "needs_data":
            assert entry["reason"], f"{name} has no reason"
        else:
            assert entry["value"] is not None, name
