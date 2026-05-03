"""tests/test_portfolio_pulse_linear.py — RA-1890.

Coverage:
  * register() replaces the foundation's placeholder linear_movement provider
  * Provider returns "_(linear: no API key)_" when LINEAR_API_KEY is missing
  * Provider returns missing-projects-json error when project not in mapping
  * _render_section() formats opened/closed/blocked/stale into expected markdown
  * _classify_closed splits Done vs Canceled/Duplicate by state.type
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import portfolio_pulse  # noqa: E402
from swarm import portfolio_pulse_linear as ppl  # noqa: E402


def test_provider_self_registers_on_import():
    """Importing portfolio_pulse_linear replaces the placeholder."""
    provider = portfolio_pulse._SECTION_PROVIDERS.get("linear_movement")
    assert provider is ppl.linear_section_provider


def test_provider_no_api_key(monkeypatch, tmp_path):
    """Missing LINEAR_API_KEY → graceful fallback body."""
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    body, error = ppl.linear_section_provider("pi-ceo", tmp_path)
    assert "no API key" in body
    assert error == "no_api_key"


def test_provider_missing_project_in_mapping(monkeypatch, tmp_path):
    """project_id not in projects.json → graceful fallback body."""
    monkeypatch.setenv("LINEAR_API_KEY", "fake-key")
    # tmp_path doesn't have .harness/projects.json
    body, error = ppl.linear_section_provider("nonexistent-project", tmp_path)
    assert "not in" in body or "no linear_project_id" in body
    assert error in ("missing_projects_json_entry", "no_linear_project_id")


def test_render_section_formats_movement():
    """_render_section produces markdown with all 4 buckets."""
    movement = {
        "opened": [
            {"identifier": "RA-1", "title": "Test ticket", "priority": 1,
             "state": {"name": "Backlog"}},
        ],
        "closed": [
            {"identifier": "RA-2", "title": "Done ticket",
             "state": {"name": "Done", "type": "completed"}},
            {"identifier": "RA-3", "title": "Canceled ticket",
             "state": {"name": "Canceled", "type": "canceled"}},
        ],
        "blocked": [
            {"identifier": "RA-4", "title": "Blocked ticket",
             "state": {"name": "Pi-Dev: Blocked"},
             "labels": {"nodes": [
                 {"name": "pi-dev:blocked-reason:credentials"},
             ]}},
        ],
        "stale": [
            {"identifier": "RA-5", "title": "Stale", "priority": 3,
             "updatedAt": "2026-04-15T00:00:00Z"},
        ],
    }
    md = ppl._render_section(movement)
    assert "Opened (last 24h):** 1" in md
    assert "RA-1" in md and "Urgent" in md
    assert "Closed (last 24h):** 2" in md
    assert "Done 1" in md and "Canceled/Duplicate 1" in md
    assert "Currently blocked:** 1" in md
    assert "RA-4" in md and "credentials" in md
    assert "Stale" in md and "RA-5" in md


def test_render_section_zero_movement():
    """Empty movement renders zero counts cleanly without crashing."""
    movement = {"opened": [], "closed": [], "blocked": [], "stale": []}
    md = ppl._render_section(movement)
    assert "Opened (last 24h):** 0" in md
    assert "Closed (last 24h):** 0" in md
    assert "Currently blocked:** 0" in md
    assert "Stale" in md and ":** 0" in md


def test_render_section_error_passthrough():
    """{'error': ...} produces a graceful body."""
    md = ppl._render_section({"error": "request_failed"})
    assert "(linear:" in md
    assert "request_failed" in md


def test_classify_closed_splits_state_types():
    """Done (state.type=completed) vs Canceled (canceled) split correctly."""
    closed = [
        {"state": {"type": "completed"}},
        {"state": {"type": "canceled"}},
        {"state": {"type": "canceled"}},  # Duplicate is also type=canceled
    ]
    out = ppl._classify_closed(closed)
    assert len(out["done"]) == 1
    assert len(out["canceled"]) == 2


def test_load_projects_reads_json(tmp_path):
    """_load_projects parses .harness/projects.json into id-keyed dict."""
    harness = tmp_path / ".harness"
    harness.mkdir()
    (harness / "projects.json").write_text(
        '{"projects": [{"id": "abc", "linear_project_id": "uuid-1"}]}',
    )
    out = ppl._load_projects(tmp_path)
    assert "abc" in out
    assert out["abc"]["linear_project_id"] == "uuid-1"


def test_load_projects_missing_file(tmp_path):
    """Missing projects.json → empty dict, no exception."""
    out = ppl._load_projects(tmp_path)
    assert out == {}
