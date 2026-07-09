"""Regression coverage for ZTE Framework v2 Section C scoring (RA-2161 / RA-672).

The Section C scorers in scripts/zte_v2_score.py are pure functions over
gate_check / scanner / lessons rows. Before this file there was no automated
test asserting their band boundaries, so a regression in the scoring maths would
have silently shifted the board-meeting ZTE score. These tests pin the C1–C5
bands, the v2 band thresholds, and the compute_v2_score assembly.

Import convention matches tests/test_plaud_actions.py: insert scripts/ so the
bare `import zte_v2_score` resolves.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import zte_v2_score as z


# ─── _band thresholds ────────────────────────────────────────────────────────

def test_band_boundaries():
    assert z._band(33) == "Manual"
    assert z._band(34) == "Assisted"
    assert z._band(55) == "Assisted"
    assert z._band(56) == "Autonomous"
    assert z._band(79) == "Autonomous"
    assert z._band(80) == "Zero Touch"
    assert z._band(94) == "Zero Touch"
    assert z._band(95) == "Zero Touch Elite"


# ─── C1 deployment success ───────────────────────────────────────────────────

def test_c1_no_data_floor():
    score, note = z.score_c1_deployment_success([])
    assert score == 1
    assert "no deployment data" in note


def test_c1_all_shipped_is_max():
    rows = [{"shipped": True} for _ in range(10)]
    score, _ = z.score_c1_deployment_success(rows)
    assert score == 5


def test_c1_band_steps():
    # 6/10 shipped = 0.60 → falls in the >=0.50 band → 2
    rows = [{"shipped": True}] * 6 + [{"shipped": False}] * 4
    assert z.score_c1_deployment_success(rows)[0] == 2
    # 8/10 = 0.80 → >=0.70 band → 3
    rows = [{"shipped": True}] * 8 + [{"shipped": False}] * 2
    assert z.score_c1_deployment_success(rows)[0] == 3


# ─── C3 mean time to value ───────────────────────────────────────────────────

def test_c3_no_durations_floor():
    score, note = z.score_c3_mean_time_to_value([{"shipped": False}])
    assert score == 1
    assert "needs_data" in note


def test_c3_fast_median_is_max():
    rows = [
        {
            "shipped": True,
            "session_started_at": "2026-07-01T00:00:00Z",
            "push_timestamp": "2026-07-01T00:10:00Z",  # 10 min
        }
        for _ in range(3)
    ]
    score, _ = z.score_c3_mean_time_to_value(rows)
    assert score == 5  # median 10 min <= 20


def test_c3_slow_median_low_band():
    rows = [
        {
            "shipped": True,
            "session_started_at": "2026-07-01T00:00:00Z",
            "push_timestamp": "2026-07-01T02:30:00Z",  # 150 min
        }
    ]
    score, _ = z.score_c3_mean_time_to_value(rows)
    assert score == 2  # 150 min <= 180 band


# ─── C4 security posture ─────────────────────────────────────────────────────

def test_c4_no_projects_floor():
    assert z.score_c4_security_posture([])[0] == 1


def test_c4_all_high_is_max():
    projects = [{"scores": {"security": 90}}, {"scores": {"security": 85}}]
    assert z.score_c4_security_posture(projects)[0] == 5


def test_c4_mixed_avg_band():
    # avg (90+30)/2 = 60 → >=60 band → 4 (not all >=80, so not 5)
    projects = [{"scores": {"security": 90}}, {"scores": {"security": 30}}]
    assert z.score_c4_security_posture(projects)[0] == 4


# ─── C5 knowledge velocity ───────────────────────────────────────────────────

def test_c5_high_velocity_and_eval_is_max():
    rows = [{"review_score": 8.0}, {"review_score": 8.0}]
    score, _ = z.score_c5_knowledge_velocity(6.0, rows)
    assert score == 5  # lpw>=5 and eval_avg>=7.5


def test_c5_no_lessons_floor():
    score, note = z.score_c5_knowledge_velocity(0.0, [])
    assert score == 1
    assert "no lessons" in note


def test_c5_low_velocity_band():
    # lpw between 0 and 1, no eval scores → falls to lpw>0 band → 2
    assert z.score_c5_knowledge_velocity(0.5, [])[0] == 2


# ─── C2 output acceptance (primary Supabase path, monkeypatched) ─────────────

def test_c2_accepted_states_score_high(monkeypatch):
    accepted = [{"linear_state_after": "Done"} for _ in range(9)]
    accepted.append({"linear_state_after": "Backlog"})  # 9/10 accepted = 0.90
    monkeypatch.setattr(z, "_supabase_query", lambda *a, **k: accepted)
    score, note = z.score_c2_output_acceptance(days=30)
    assert score == 5
    assert "supabase" in note


def test_c2_no_data_falls_through_to_floor(monkeypatch, tmp_path):
    # No Supabase rows and no local outcomes file → floor of 1.
    monkeypatch.setattr(z, "_supabase_query", lambda *a, **k: [])
    monkeypatch.setattr(z, "_HARNESS", tmp_path)  # session-outcomes.jsonl absent here
    score, note = z.score_c2_output_acceptance(days=30)
    assert score == 1
    assert "needs_data" in note


# ─── compute_v2_score assembly ───────────────────────────────────────────────

def test_compute_v2_score_assembles_section_c(monkeypatch, tmp_path):
    monkeypatch.setattr(z, "_supabase_query", lambda *a, **k: [{"shipped": True}] * 10)
    monkeypatch.setattr(z, "_load_scanner_summary", lambda: [{"scores": {"security": 90}}])
    monkeypatch.setattr(z, "_lessons_per_week", lambda days=30: 6.0)
    monkeypatch.setattr(z, "_load_v1_score", lambda: (73, 75))
    monkeypatch.setattr(z, "_HARNESS", tmp_path)
    monkeypatch.setattr(z, "_OUTPUT", tmp_path / "zte-v2-score.json")

    r = z.compute_v2_score(days=30)

    sc = r["section_c"]
    # total is the sum of the five component scores, capped at 25
    assert sc["total"] == sum(
        sc[k]["score"] for k in (
            "C1_deployment_success",
            "C2_output_acceptance",
            "C3_mean_time_to_value",
            "C4_security_posture",
            "C5_knowledge_velocity",
        )
    )
    assert sc["max"] == 25
    assert r["v2_total"] == r["v1_score"] + sc["total"]
    assert r["v2_max"] == 100
    assert r["band"] == z._band(r["v2_total"])
    # output persisted
    assert (tmp_path / "zte-v2-score.json").exists()
