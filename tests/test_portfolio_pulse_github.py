"""tests/test_portfolio_pulse_github.py — RA-1889.

Coverage:
  * register() replaces the foundation's placeholder providers for
    deploys / ci / prs slots on import
  * No GITHUB_TOKEN → synthetic placeholder body for each provider
  * recent_deploys / ci_summary / pr_summary happy-path render with
    mocked urllib.request.urlopen
  * Empty-repo case (no commits / runs / PRs) renders cleanly
  * urllib HTTPError swallowed → empty section, no exception
"""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import portfolio_pulse  # noqa: E402
from swarm import portfolio_pulse_github as ppg  # noqa: E402


# ── Fixtures helpers ────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _route(routes: dict[str, object]):
    """Return a urlopen replacement that dispatches by URL substring."""

    def fake_urlopen(req, timeout=None):  # noqa: ARG001
        url = getattr(req, "full_url", None) or req
        for needle, payload in routes.items():
            if needle in url:
                if isinstance(payload, Exception):
                    raise payload
                return _FakeResponse(
                    json.dumps(payload).encode("utf-8")
                )
        raise AssertionError(f"unexpected URL: {url}")

    return fake_urlopen


def _write_projects(repo_root: Path, project_id: str, repo: str) -> None:
    harness = repo_root / ".harness"
    harness.mkdir(exist_ok=True)
    (harness / "projects.json").write_text(
        json.dumps({"projects": [
            {"id": project_id, "repo": repo},
        ]})
    )


# ── Self-registration ──────────────────────────────────────────────────────


def test_providers_self_register_on_import():
    """Importing portfolio_pulse_github replaces the placeholders."""
    for slot, fn in (
        ("deploys", ppg.deploys_provider),
        ("ci", ppg.ci_provider),
        ("prs", ppg.prs_provider),
    ):
        assert portfolio_pulse._SECTION_PROVIDERS.get(slot) is fn


# ── No-token fallback ───────────────────────────────────────────────────────


def test_provider_no_token(monkeypatch, tmp_path):
    """Missing GITHUB_TOKEN → synthetic placeholder for every section."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    for fn in (ppg.deploys_provider, ppg.ci_provider, ppg.prs_provider):
        body, error = fn("pi-ceo", tmp_path)
        assert "GitHub token not configured" in body
        assert error == "no_token"


def test_provider_missing_repo_mapping(monkeypatch, tmp_path):
    """Token set but project_id has no repo → graceful fallback."""
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    # tmp_path has no .harness/projects.json
    body, error = ppg.deploys_provider("ghost-project", tmp_path)
    assert "no `repo` mapping" in body
    assert error == "no_repo_mapping"


# ── Happy path ──────────────────────────────────────────────────────────────


def test_happy_path_renders_all_sections(monkeypatch, tmp_path):
    """2 deploys, 1 pass + 1 fail, 2 open PRs (1 stale) renders cleanly."""
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    _write_projects(tmp_path, "pi-ceo", "octocat/hello")

    now = datetime.now(timezone.utc)
    fresh_iso = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    stale_iso = (now - timedelta(days=5)).isoformat().replace("+00:00", "Z")

    routes = {
        "/repos/octocat/hello/commits": [
            {"sha": "abc1234deadbeef",
             "html_url": "https://github.com/octocat/hello/commit/abc",
             "commit": {"message": "feat: add thing\n\nbody",
                          "author": {"name": "alice", "date": fresh_iso}}},
            {"sha": "def5678cafebabe",
             "html_url": "https://github.com/octocat/hello/commit/def",
             "commit": {"message": "fix: bug",
                          "author": {"name": "bob", "date": fresh_iso}}},
        ],
        "/repos/octocat/hello/actions/runs": {"workflow_runs": [
            {"name": "ci", "status": "completed", "conclusion": "success",
             "created_at": fresh_iso, "head_sha": "abc1234deadbeef",
             "html_url": "https://github.com/octocat/hello/actions/runs/1"},
            {"name": "deploy", "status": "completed", "conclusion": "failure",
             "created_at": fresh_iso, "head_sha": "def5678cafebabe",
             "html_url": "https://github.com/octocat/hello/actions/runs/2"},
        ]},
        "/repos/octocat/hello/pulls": [
            {"number": 11, "title": "Old PR",
             "html_url": "https://github.com/octocat/hello/pull/11",
             "user": {"login": "carol"},
             "created_at": stale_iso, "updated_at": stale_iso},
            {"number": 12, "title": "Fresh PR",
             "html_url": "https://github.com/octocat/hello/pull/12",
             "user": {"login": "dave"},
             "created_at": fresh_iso, "updated_at": fresh_iso},
        ],
    }

    monkeypatch.setattr(ppg, "urlopen", _route(routes))

    deploy_body, deploy_err = ppg.deploys_provider("pi-ceo", tmp_path)
    ci_body, ci_err = ppg.ci_provider("pi-ceo", tmp_path)
    pr_body, pr_err = ppg.prs_provider("pi-ceo", tmp_path)

    assert deploy_err is None and ci_err is None and pr_err is None

    assert "Commits to main (last 24h):** 2" in deploy_body
    assert "abc1234" in deploy_body and "alice" in deploy_body
    assert "[unknown]" in deploy_body  # placeholder deploy_status

    assert "1 passed" in ci_body and "1 failed" in ci_body
    assert "deploy" in ci_body  # failure name surfaces

    assert "Open PRs:** 2" in pr_body
    assert "Oldest:" in pr_body and "#11" in pr_body
    assert "Stale (no update >3d):** 1" in pr_body
    assert "carol" in pr_body  # stale PR author surfaces


def test_composite_provider_returns_pulse_section(monkeypatch, tmp_path):
    """provider() returns a single PulseSection with combined body."""
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    _write_projects(tmp_path, "pi-ceo", "octocat/hello")
    monkeypatch.setattr(ppg, "urlopen", _route({
        "/repos/octocat/hello/commits": [],
        "/repos/octocat/hello/actions/runs": {"workflow_runs": []},
        "/repos/octocat/hello/pulls": [],
    }))
    section = ppg.provider("pi-ceo", tmp_path)
    assert isinstance(section, portfolio_pulse.PulseSection)
    assert section.name == "github"
    assert "### Deploys" in section.body_md
    assert "### CI" in section.body_md
    assert "### PRs" in section.body_md


# ── Empty repo ──────────────────────────────────────────────────────────────


def test_empty_repo_renders_cleanly(monkeypatch, tmp_path):
    """No commits / runs / PRs → zero-counts body, no crash."""
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    _write_projects(tmp_path, "pi-ceo", "octocat/empty")
    monkeypatch.setattr(ppg, "urlopen", _route({
        "/repos/octocat/empty/commits": [],
        "/repos/octocat/empty/actions/runs": {"workflow_runs": []},
        "/repos/octocat/empty/pulls": [],
    }))

    deploy_body, _ = ppg.deploys_provider("pi-ceo", tmp_path)
    ci_body, _ = ppg.ci_provider("pi-ceo", tmp_path)
    pr_body, _ = ppg.prs_provider("pi-ceo", tmp_path)

    assert "no main-branch commits" in deploy_body
    assert "0 passed" in ci_body and "0 failed" in ci_body
    assert "Open PRs:** 0" in pr_body
    assert "Stale (no update >3d):** 0" in pr_body


# ── HTTPError swallowing ────────────────────────────────────────────────────


def test_http_error_swallowed(monkeypatch, tmp_path):
    """HTTPError from urlopen → empty section data, never raises."""
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    _write_projects(tmp_path, "pi-ceo", "octocat/down")

    err = HTTPError(
        "https://api.github.com/x", 503, "Service Unavailable",
        hdrs=None, fp=io.BytesIO(b""),
    )
    monkeypatch.setattr(ppg, "urlopen", _route({
        "/repos/octocat/down/commits": err,
        "/repos/octocat/down/actions/runs": err,
        "/repos/octocat/down/pulls": err,
    }))

    # Each fetcher returns a sentinel-empty value, never raises
    deploys = ppg.recent_deploys("octocat/down", "2026-05-01T00:00:00Z",
                                  token="fake-token")
    assert deploys == []
    ci = ppg.ci_summary("octocat/down", "2026-05-01T00:00:00Z",
                          token="fake-token")
    assert ci == {"pass_count": 0, "fail_count": 0, "recent_failures": []}
    prs = ppg.pr_summary("octocat/down", token="fake-token")
    assert prs == {"open_count": 0, "oldest_pr": None, "stale_prs": []}

    # Provider-level call also returns a body without raising
    body, error = ppg.deploys_provider("pi-ceo", tmp_path)
    assert "no main-branch commits" in body
    assert error is None


# ── Helpers ─────────────────────────────────────────────────────────────────


def test_load_projects_reads_repo_field(tmp_path):
    _write_projects(tmp_path, "abc", "owner/name")
    out = ppg._load_projects(tmp_path)
    assert "abc" in out and out["abc"]["repo"] == "owner/name"


def test_load_projects_missing_file(tmp_path):
    out = ppg._load_projects(tmp_path)
    assert out == {}
