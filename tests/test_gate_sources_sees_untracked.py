"""The size gates must see a file that has not been `git add`ed yet.

WHY. Both size linters enumerated `git ls-files`, which lists tracked files only.
A file a session had just written was therefore invisible: the gate printed
"passed" locally and CI failed on that exact file. Three have reached main that
way — `file_length_lint.py`'s own `main()`, `mesh_dispatch_service.py`, and
`gate_parity_lint.py::main` at 51 lines, which a handoff recorded as
`pass=23 fail=0` because the run could not see the file it was judging.

CLAUDE.md's answer was "run the gates after `git add`". That puts the fix in the
hands of whoever forgot, which is why it recurred. These tests pin the mechanical
fix instead.

The negative half matters as much as the positive: an IGNORED file must stay out,
or the gate starts failing on build output and gets switched off.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "gate_sources.py"


def _load():
    spec = importlib.util.spec_from_file_location("gate_sources", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch) -> Path:
    r = tmp_path / "r"
    r.mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True, capture_output=True)
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "T")
    (r / ".gitignore").write_text("ignored/\n")
    (r / "tracked.py").write_text("x = 1\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "seed")
    monkeypatch.chdir(r)
    return r


def test_untracked_file_is_enumerated(repo: Path):
    (repo / "brand_new.py").write_text("y = 2\n")
    assert not subprocess.run(
        ["git", "-C", str(repo), "ls-files", "brand_new.py"],
        capture_output=True, text=True,
    ).stdout.strip(), "fixture is wrong — the file must be untracked for this to prove anything"

    assert "brand_new.py" in _load().source_paths("*.py")


def test_ignored_file_is_not_enumerated(repo: Path):
    (repo / "ignored").mkdir()
    (repo / "ignored" / "junk.py").write_text("z = 3\n")

    paths = _load().source_paths("*.py")
    assert "ignored/junk.py" not in paths
    assert "tracked.py" in paths, "positive control: tracked files must still appear"
