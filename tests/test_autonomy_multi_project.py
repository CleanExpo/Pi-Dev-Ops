"""
test_autonomy_multi_project.py — RA-1289 regression tests.

Locks the behavior of the multi-project autonomy poller:
  - `_load_portfolio_projects()` parses `.harness/projects.json` and emits
    well-formed entries, skipping projects without a `linear_project_id`.
  - `_load_portfolio_projects()` falls back to the Pi-Dev-Ops singleton when
    `projects.json` is missing or malformed.
  - `fetch_todo_issues()` iterates every project, annotates issues with
    `_repo_url` + `_team_id` + `_project_name`, and dedupes by issue id.
  - `fetch_todo_issues()` keeps going when one project's fetch fails.
  - `_extract_repo_url()` prioritises explicit `repo:` labels over the
    mapped annotation, and the mapped annotation over the Pi-Dev-Ops default.
"""
import json
from pathlib import Path
from unittest.mock import patch

from app.server import autonomy


def _write_registry(tmp_path: Path, projects: list[dict]) -> Path:
    path = tmp_path / "projects.json"
    path.write_text(json.dumps({"version": "1.0", "projects": projects}))
    return path


def test_load_portfolio_projects_well_formed(tmp_path):
    registry = _write_registry(tmp_path, [
        {
            "id": "alpha",
            "repo": "acme/alpha",
            "linear_project_id": "proj-alpha",
            "linear_project_name": "Alpha",
            "linear_team_id": "team-alpha",
        },
        {
            "id": "beta",
            "repo": "acme/beta",
            "linear_project_id": "proj-beta",
            "linear_project_name": "Beta",
            "linear_team_id": "team-beta",
        },
    ])
    with patch.object(autonomy, "_PROJECTS_JSON", registry):
        out = autonomy._load_portfolio_projects()
    assert len(out) == 2
    assert out[0] == {
        "project_id": "proj-alpha",
        "team_id": "team-alpha",
        "repo_url": "https://github.com/acme/alpha",
        "name": "Alpha",
    }


def test_load_portfolio_projects_skips_entries_without_project_id(tmp_path):
    registry = _write_registry(tmp_path, [
        {
            "id": "alpha",
            "repo": "acme/alpha",
            "linear_project_id": "proj-alpha",
            "linear_team_id": "team-alpha",
        },
        # oh-my-codex pattern — no linear_project_id, should be skipped
        {
            "id": "orphan",
            "repo": "acme/orphan",
            "linear_project_id": None,
            "linear_team_id": "team-alpha",
        },
    ])
    with patch.object(autonomy, "_PROJECTS_JSON", registry):
        out = autonomy._load_portfolio_projects()
    assert len(out) == 1
    assert out[0]["project_id"] == "proj-alpha"


def test_load_portfolio_projects_missing_file_falls_back(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    with patch.object(autonomy, "_PROJECTS_JSON", missing):
        out = autonomy._load_portfolio_projects()
    assert len(out) == 1
    assert out[0]["project_id"] == autonomy._PROJECT_ID
    assert out[0]["team_id"] == autonomy._TEAM_ID


def test_fetch_todo_issues_iterates_and_annotates(tmp_path):
    registry = _write_registry(tmp_path, [
        {"id": "alpha", "repo": "acme/alpha",
         "linear_project_id": "proj-alpha", "linear_team_id": "team-alpha",
         "linear_project_name": "Alpha"},
        {"id": "beta", "repo": "acme/beta",
         "linear_project_id": "proj-beta", "linear_team_id": "team-beta",
         "linear_project_name": "Beta"},
    ])

    def fake_gql(api_key, query, variables):
        project_id = variables["projectId"]
        if project_id == "proj-alpha":
            return {"project": {"issues": {"nodes": [
                {"id": "a1", "identifier": "A-1", "title": "A one", "priority": 2},
            ]}}}
        if project_id == "proj-beta":
            return {"project": {"issues": {"nodes": [
                {"id": "b1", "identifier": "B-1", "title": "B one", "priority": 1},
            ]}}}
        return {"project": None}

    with patch.object(autonomy, "_PROJECTS_JSON", registry), \
         patch.object(autonomy, "_gql", side_effect=fake_gql):
        issues = autonomy.fetch_todo_issues("fake-key")

    ids = [i["identifier"] for i in issues]
    assert set(ids) == {"A-1", "B-1"}
    # Urgent (priority=1) sorts before High (priority=2)
    assert issues[0]["identifier"] == "B-1"

    by_id = {i["identifier"]: i for i in issues}
    assert by_id["A-1"]["_repo_url"] == "https://github.com/acme/alpha"
    assert by_id["A-1"]["_team_id"] == "team-alpha"
    assert by_id["A-1"]["_project_name"] == "Alpha"
    assert by_id["B-1"]["_team_id"] == "team-beta"


def test_fetch_todo_issues_survives_single_project_failure(tmp_path):
    registry = _write_registry(tmp_path, [
        {"id": "alpha", "repo": "acme/alpha",
         "linear_project_id": "proj-alpha", "linear_team_id": "team-alpha"},
        {"id": "beta", "repo": "acme/beta",
         "linear_project_id": "proj-beta", "linear_team_id": "team-beta"},
    ])

    def fake_gql(api_key, query, variables):
        if variables["projectId"] == "proj-alpha":
            raise RuntimeError("Linear HTTP 500")
        return {"project": {"issues": {"nodes": [
            {"id": "b1", "identifier": "B-1", "title": "B one", "priority": 2},
        ]}}}

    with patch.object(autonomy, "_PROJECTS_JSON", registry), \
         patch.object(autonomy, "_gql", side_effect=fake_gql):
        issues = autonomy.fetch_todo_issues("fake-key")

    # Alpha failed but Beta still returned
    assert [i["identifier"] for i in issues] == ["B-1"]


def test_fetch_todo_issues_dedupes_cross_project(tmp_path):
    """Same issue ID across two project results should appear once."""
    registry = _write_registry(tmp_path, [
        {"id": "alpha", "repo": "acme/alpha",
         "linear_project_id": "proj-alpha", "linear_team_id": "team-alpha"},
        {"id": "beta", "repo": "acme/beta",
         "linear_project_id": "proj-beta", "linear_team_id": "team-beta"},
    ])
    shared = {"id": "shared-1", "identifier": "X-1", "title": "Shared", "priority": 2}

    def fake_gql(api_key, query, variables):
        return {"project": {"issues": {"nodes": [shared]}}}

    with patch.object(autonomy, "_PROJECTS_JSON", registry), \
         patch.object(autonomy, "_gql", side_effect=fake_gql):
        issues = autonomy.fetch_todo_issues("fake-key")

    assert len(issues) == 1
    # First-seen wins — Alpha was iterated first
    assert issues[0]["_team_id"] == "team-alpha"


def test_extract_repo_url_priority():
    # 1. Explicit `repo:` label wins over everything
    issue = {
        "labels": {"nodes": [{"name": "repo:https://github.com/override/one"}]},
        "description": "",
        "_repo_url": "https://github.com/mapped/two",
    }
    assert autonomy._extract_repo_url(issue) == "https://github.com/override/one"

    # 2. `repo:` description line wins over mapped annotation
    issue = {
        "labels": {"nodes": []},
        "description": "repo:https://github.com/override/two\nsome body",
        "_repo_url": "https://github.com/mapped/two",
    }
    assert autonomy._extract_repo_url(issue) == "https://github.com/override/two"

    # 3. Mapped annotation (RA-1289) wins over Pi-Dev-Ops default
    issue = {
        "labels": {"nodes": []},
        "description": "no repo override here",
        "_repo_url": "https://github.com/mapped/three",
    }
    assert autonomy._extract_repo_url(issue) == "https://github.com/mapped/three"

    # 4. Nothing → Pi-Dev-Ops default
    issue = {"labels": {"nodes": []}, "description": ""}
    assert autonomy._extract_repo_url(issue) == autonomy._DEFAULT_REPO_URL
