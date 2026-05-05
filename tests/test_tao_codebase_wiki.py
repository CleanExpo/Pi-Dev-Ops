"""tests/test_tao_codebase_wiki.py — RA-1968 unit tests.

Cover the public API of `app.server.tao_codebase_wiki.update_wiki`:
  * happy path with mocked SDK + real tiny git repo
  * cost-budget guard
  * kill-switch precedence (HARD_STOP env)
  * dry-run mode
  * idempotency (same git state -> same WIKI.md modulo timestamp)
  * empty-diff case

Real git is invoked via `subprocess.run(["git", "init"], ...)` in tmp_path.
SDK is mocked via `unittest.mock.patch("app.server.tao_codebase_wiki._run_scribe_sync")`.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from unittest.mock import patch

from app.server import tao_codebase_wiki as tcw


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _run_git(repo, "init", "-q", "-b", "main")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test")
    _run_git(repo, "config", "commit.gpgsign", "false")


def _commit(repo: Path, files: dict[str, str], message: str) -> str:
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        _run_git(repo, "add", rel)
    _run_git(repo, "commit", "-q", "-m", message)
    return _run_git(repo, "rev-parse", "HEAD").strip()


_FAKE_BODY = (
    "## Architecture (current)\n"
    "Mocked summary paragraph.\n\n"
    "## Files of interest\n"
    "- src/foo.py — entry point"
)


# ── 1. Happy path ─────────────────────────────────────────────────────────────

def test_happy_path_writes_wiki_per_directory(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit(repo, {"README.md": "init\n"}, "chore: init")
    _commit(repo, {"app/server/foo.py": "x = 1\n"}, "feat(app): add foo")
    _commit(repo, {"dashboard/page.tsx": "export default null\n"}, "feat(dashboard): add page")
    _commit(repo, {"tests/test_x.py": "def test_x(): pass\n"}, "test(tests): add test")

    with patch.object(tcw, "_run_scribe_sync", return_value=_FAKE_BODY) as scribe:
        result = tcw.update_wiki(str(repo), since_ref=base, max_cost_usd=1.0)

    assert scribe.called
    assert set(result.directories_updated) == {"app", "dashboard", "tests"}
    assert len(result.files_written) == 3
    assert result.commits_summarized == 3
    assert result.bypassed is False
    # WIKI.md content sanity
    text = (repo / "app" / "WIKI.md").read_text(encoding="utf-8")
    assert "# app — Wiki" in text
    assert "## Recent changes" in text
    assert "Mocked summary paragraph" in text
    assert re.search(r"_Last updated: \S+ \(commits [0-9a-f]+\.\.[0-9a-f]+\)_", text)


# ── 2. Cost-budget guard ──────────────────────────────────────────────────────

def test_cost_budget_exceeded_bypasses_before_sdk(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit(repo, {"README.md": "init\n"}, "chore: init")
    _commit(repo, {"app/server/foo.py": "x = 1\n"}, "feat(app): add foo")

    with patch.object(tcw, "_run_scribe_sync", return_value=_FAKE_BODY) as scribe:
        # max_cost_usd=0 forces guard to trip on the first directory.
        result = tcw.update_wiki(str(repo), since_ref=base, max_cost_usd=0.0)

    assert result.bypassed is True
    assert result.bypass_reason == "cost_budget_exceeded"
    assert result.directories_updated == []
    assert scribe.called is False


# ── 3. Kill-switch precedence ─────────────────────────────────────────────────

def test_hard_stop_aborts_before_sdk(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit(repo, {"README.md": "init\n"}, "chore: init")
    _commit(repo, {"app/foo.py": "x = 1\n"}, "feat(app): add foo")
    hard_stop = tmp_path / "HARD_STOP"
    hard_stop.write_text("stop", encoding="utf-8")
    monkeypatch.setenv("TAO_HARD_STOP_FILE", str(hard_stop))

    with patch.object(tcw, "_run_scribe_sync", return_value=_FAKE_BODY) as scribe:
        result = tcw.update_wiki(str(repo), since_ref=base, max_cost_usd=1.0)

    assert result.bypassed is True
    assert result.bypass_reason == "kill_switch:HARD_STOP"
    assert scribe.called is False


# ── 4. Dry-run mode ───────────────────────────────────────────────────────────

def test_dry_run_does_not_call_sdk_or_write_files(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit(repo, {"README.md": "init\n"}, "chore: init")
    _commit(repo, {"app/foo.py": "x = 1\n"}, "feat(app): add foo")
    _commit(repo, {"dashboard/x.tsx": "export {}\n"}, "feat(dash): add")

    with patch.object(tcw, "_run_scribe_sync", return_value=_FAKE_BODY) as scribe:
        result = tcw.update_wiki(str(repo), since_ref=base, max_cost_usd=1.0, dry_run=True)

    assert scribe.called is False
    assert set(result.directories_updated) == {"app", "dashboard"}
    assert result.files_written == []
    assert not (repo / "app" / "WIKI.md").exists()
    assert not (repo / "dashboard" / "WIKI.md").exists()


# ── 5. Idempotency ────────────────────────────────────────────────────────────

def test_idempotent_run_yields_same_body(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit(repo, {"README.md": "init\n"}, "chore: init")
    _commit(repo, {"app/foo.py": "x = 1\n"}, "feat(app): add foo")

    with patch.object(tcw, "_run_scribe_sync", return_value=_FAKE_BODY):
        tcw.update_wiki(str(repo), since_ref=base, max_cost_usd=1.0)
    first = (repo / "app" / "WIKI.md").read_text(encoding="utf-8")

    with patch.object(tcw, "_run_scribe_sync", return_value=_FAKE_BODY):
        tcw.update_wiki(str(repo), since_ref=base, max_cost_usd=1.0)
    second = (repo / "app" / "WIKI.md").read_text(encoding="utf-8")

    # Strip the timestamp line; everything else must match.
    def norm(s: str) -> str:
        return re.sub(r"_Last updated: \S+ \(", "_Last updated: T (", s)
    assert norm(first) == norm(second)


# ── 6. Empty diff ─────────────────────────────────────────────────────────────

def test_empty_diff_returns_no_directories(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    head = _commit(repo, {"README.md": "init\n"}, "chore: init")

    with patch.object(tcw, "_run_scribe_sync", return_value=_FAKE_BODY) as scribe:
        result = tcw.update_wiki(str(repo), since_ref=head, max_cost_usd=1.0)

    assert result.directories_updated == []
    assert result.files_written == []
    assert result.commits_summarized == 0
    assert scribe.called is False


# ── 7. Directories filter ─────────────────────────────────────────────────────

def test_directories_filter_restricts_scope(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit(repo, {"README.md": "init\n"}, "chore: init")
    _commit(repo, {"app/foo.py": "x = 1\n"}, "feat(app): add foo")
    _commit(repo, {"dashboard/x.tsx": "export {}\n"}, "feat(dash): add")
    _commit(repo, {"swarm/bot.py": "y = 2\n"}, "feat(swarm): add")

    with patch.object(tcw, "_run_scribe_sync", return_value=_FAKE_BODY):
        result = tcw.update_wiki(
            str(repo),
            since_ref=base,
            max_cost_usd=1.0,
            directories=["app", "swarm"],
        )

    assert set(result.directories_updated) == {"app", "swarm"}
    assert not (repo / "dashboard" / "WIKI.md").exists()


# ── 8. SDK failure stub fallback ──────────────────────────────────────────────

def test_sdk_returns_empty_uses_stub_body(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit(repo, {"README.md": "init\n"}, "chore: init")
    _commit(repo, {"app/foo.py": "x = 1\n"}, "feat(app): add foo")

    with patch.object(tcw, "_run_scribe_sync", return_value=""):
        result = tcw.update_wiki(str(repo), since_ref=base, max_cost_usd=1.0)

    assert "app" in result.directories_updated
    text = (repo / "app" / "WIKI.md").read_text(encoding="utf-8")
    assert "Auto-stub" in text
    assert "## Files of interest" in text


# ── 9. RA-1996 regressions ────────────────────────────────────────────────────


def test_ra1996_default_budget_admits_typical_prompt(tmp_path):
    """RA-1996 — `_DEFAULT_COMPLETION_TOKENS=1500` used to cost $0.0225 alone,
    exceeding the $0.02 default budget on EVERY call. Default budget is the
    one hit by `.github/workflows/codebase-wiki.yml`'s CLI invocation when the
    env override is absent. Regression-guard: default budget must admit a
    realistic single-directory prompt (1-2KB) without bypass."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit(repo, {"README.md": "init\n"}, "chore: init")
    _commit(repo, {"app/foo.py": "x = 1\n"}, "feat(app): add foo")

    with patch.object(tcw, "_run_scribe_sync", return_value=_FAKE_BODY):
        # 0.02 is the documented CLI default; this MUST succeed.
        result = tcw.update_wiki(str(repo), since_ref=base, max_cost_usd=0.02)

    assert result.bypassed is False, (
        f"Default $0.02 budget tripped — bypass_reason={result.bypass_reason}"
    )
    assert "app" in result.directories_updated


def test_ra1996_root_level_files_skipped_not_treated_as_top_dir(tmp_path):
    """RA-1996 — root-level files (CLAUDE.md, Dockerfile, README.md) used to
    appear as "top dirs" via naive `f.split('/', 1)[0]`. A live run then tried
    `mkdir(parents=True, exist_ok=True)` on a path already occupied by a file
    → NotADirectoryError. Now filtered before the loop."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit(repo, {"README.md": "init\n"}, "chore: init")
    _commit(
        repo,
        {
            "CLAUDE.md": "root-file change\n",
            "Dockerfile": "FROM python:3.11\n",
            "app/foo.py": "x = 1\n",
        },
        "feat: mixed root + subdir change",
    )

    with patch.object(tcw, "_run_scribe_sync", return_value=_FAKE_BODY):
        result = tcw.update_wiki(str(repo), since_ref=base, max_cost_usd=1.0)

    # Only `app/` should be in the output — `CLAUDE.md` and `Dockerfile` are
    # root-level files, not directories.
    assert result.directories_updated == ["app"]
    assert "CLAUDE.md" not in result.directories_updated
    assert "Dockerfile" not in result.directories_updated
    # Confirm no spurious WIKI.md was attempted under file-paths.
    assert not (repo / "CLAUDE.md" / "WIKI.md").exists()


def test_ra1996_commits_summarized_set_before_early_return(tmp_path):
    """RA-1996 — `commits_summarized` was assigned only at the very end of the
    loop, so any early-return path returned 0 even when commits were collected.
    Verify a budget-bypass path now reports the truthful commit count."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit(repo, {"README.md": "init\n"}, "chore: init")
    _commit(repo, {"app/foo.py": "x = 1\n"}, "feat(app): one")
    _commit(repo, {"app/bar.py": "y = 2\n"}, "feat(app): two")
    _commit(repo, {"docs/r.md": "doc\n"}, "docs: r")

    # Force budget-exceeded on the first iteration via an absurdly-low budget.
    result = tcw.update_wiki(str(repo), since_ref=base, max_cost_usd=0.0)

    assert result.bypassed is True
    assert result.bypass_reason == "cost_budget_exceeded"
    # 3 distinct commits collected pre-bypass → must NOT be 0 anymore.
    assert result.commits_summarized == 3
