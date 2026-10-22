"""get_health_summary carries the scan date and the last recorded deploy check.

A card that shows an undated score reads as current. The summary must say when
the scans behind the score finished, and pass through the deployment_health
record the scanner already writes, without making any new HTTP call.
"""

import json

import pytest

from app.server import scanner as scanner_mod
from app.server.scanner import ProjectScanner

PROJECT = {"id": "demo", "repo": "CleanExpo/Demo", "deployments": {"frontend": "https://demo.example"}}


def _write(root, name, body):
    path = root / "demo" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body if isinstance(body, str) else json.dumps(body))


@pytest.fixture
def summary(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner_mod, "_RESULTS_ROOT", tmp_path)
    monkeypatch.setattr(ProjectScanner, "load_projects", lambda self: [PROJECT])

    def run():
        return ProjectScanner().get_health_summary()[0]

    return tmp_path, run


def test_finished_at_is_the_oldest_scan_behind_the_score(summary):
    root, run = summary
    _write(root, "2026-10-20-security.json", {"finished_at": "2026-10-20T01:00:00+00:00", "findings": []})
    _write(root, "2026-10-21-code_quality.json", {"finished_at": "2026-10-21T01:00:00+00:00", "findings": []})
    row = run()
    assert row["finished_at"] == "2026-10-20T01:00:00+00:00"


def test_finished_at_is_none_when_no_scan_exists(summary):
    _, run = summary
    row = run()
    assert row["finished_at"] is None
    assert row["deploy_check"] is None


def test_finished_at_is_none_when_a_scan_behind_the_score_is_undated(summary):
    root, run = summary
    _write(root, "2026-10-20-security.json", {"finished_at": "2026-10-20T01:00:00+00:00", "findings": []})
    _write(root, "2026-10-21-dependencies.json", {"findings": []})
    assert run()["finished_at"] is None


def test_deploy_check_passes_through_the_recorded_findings(summary):
    root, run = summary
    _write(root, "2026-10-21-deployment_health.json", {
        "finished_at": "2026-10-21T02:00:00+00:00", "error": "",
        "findings": [{"severity": "critical", "title": "Deployment 5xx: frontend", "description": "x"}],
    })
    check = run()["deploy_check"]
    assert check == {
        "finished_at": "2026-10-21T02:00:00+00:00", "error": "",
        "findings": [{"severity": "critical", "title": "Deployment 5xx: frontend"}],
    }


def test_deploy_check_reports_an_unreadable_record_as_an_error(summary):
    root, run = summary
    _write(root, "2026-10-21-deployment_health.json", "{not json")
    check = run()["deploy_check"]
    assert check["error"] == "deploy check record unreadable"
    assert check["finished_at"] is None


def test_a_crashed_scan_is_not_scored_and_its_error_is_reported(summary):
    root, run = summary
    _write(root, "2026-10-20-security.json", {"finished_at": "2026-10-20T01:00:00+00:00", "findings": [], "error": "git clone failed"})
    _write(root, "2026-10-21-code_quality.json", {"finished_at": "2026-10-21T01:00:00+00:00", "findings": []})
    row = run()
    assert "security" not in row["scores"]
    assert row["scan_errors"] == {"security": "git clone failed"}
    assert row["finished_at"] == "2026-10-21T01:00:00+00:00"


def test_no_scan_errors_is_an_empty_map(summary):
    root, run = summary
    _write(root, "2026-10-20-security.json", {"finished_at": "2026-10-20T01:00:00+00:00", "findings": [], "error": ""})
    assert run()["scan_errors"] == {}
