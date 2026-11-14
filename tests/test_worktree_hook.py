"""RA-8375: starting Claude Code in worktree mode must work from this repository.

Claude Code sends the WorktreeCreate / WorktreeRemove event as JSON on standard input ({"name": ...} and
{"worktree_path": ...}) and reads the new folder from the last line of standard output. It sets no WORKTREE_DIR or
WORKTREE_BRANCH. The hook lines added by RA-547 read those two variables, so git was handed an empty branch name and
every worktree-mode start failed. The lines now call .claude/hooks/worktree_hook.py.

Every test runs the command exactly as .claude/settings.json registers it, in a throwaway repository, so the wiring
and the script are checked together. The two `old_hook_lines` tests keep the original failure reproducible.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = "worktree_hook.py"
SCRIPT = REPO / ".claude" / "hooks" / HOOK
SHELLS = ["/bin/bash", "/bin/sh"] + (["/bin/dash"] if Path("/bin/dash").exists() else [])
# The lines origin/main carried before RA-8375, byte for byte.
OLD_CREATE = 'git -C "$CLAUDE_PROJECT_DIR" worktree add "$WORKTREE_DIR" -b "$WORKTREE_BRANCH" 2>&1'
OLD_REMOVE = 'git -C "$CLAUDE_PROJECT_DIR" worktree remove "$WORKTREE_DIR" --force 2>&1'


def _command(event: str) -> str:
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    found = [hook["command"] for group in settings["hooks"][event] for hook in group["hooks"]]
    assert len(found) == 1, found
    return found[0]


def _env(project: Path, path: str | None = None) -> dict[str, str]:
    """What Claude Code gives a hook, and nothing it does not: no WORKTREE_DIR, no WORKTREE_BRANCH."""
    return {"HOME": str(project.parent / "home"), "CLAUDE_PROJECT_DIR": str(project),
            "PATH": path or f"{Path(sys.executable).parent}:/usr/bin:/bin",
            "GIT_CEILING_DIRECTORIES": str(project.parent), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def _git(project: Path, where: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True, env=_env(project),
                          timeout=60)


def _project(tmp_path: Path, name: str = "project", install: bool = True) -> Path:
    project = tmp_path / name
    project.mkdir()
    assert _git(project, project, "init", "-q").returncode == 0
    assert _git(project, project, "commit", "-q", "--allow-empty", "-m", "first").returncode == 0
    if install:
        (project / ".claude" / "hooks").mkdir(parents=True)
        shutil.copy(SCRIPT, project / ".claude" / "hooks" / HOOK)
    return project


def _event(event: str, **fields: object) -> str:
    return json.dumps({"session_id": "abc123", "transcript_path": "/x/t.jsonl", "cwd": "/x",
                       "hook_event_name": event, **fields})


def _run(command: str, project: Path, payload: str, shell: str = "/bin/bash",
         path: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([shell, "-c", command], input=payload, capture_output=True, text=True, cwd=project,
                          env=_env(project, path), timeout=60)


def _create(project: Path, name: object, shell: str = "/bin/bash") -> subprocess.CompletedProcess:
    return _run(_command("WorktreeCreate"), project, _event("WorktreeCreate", name=name), shell)


def _remove(project: Path, target: Path, shell: str = "/bin/bash") -> subprocess.CompletedProcess:
    return _run(_command("WorktreeRemove"), project, _event("WorktreeRemove", worktree_path=str(target)), shell)


def _worktrees(project: Path) -> int:
    listing = _git(project, project, "worktree", "list", "--porcelain").stdout
    return sum(1 for line in listing.splitlines() if line.startswith("worktree "))


def _has_branch(project: Path, branch: str) -> bool:
    return _git(project, project, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0


@pytest.mark.parametrize("shell", SHELLS)
def test_old_hook_lines_cannot_create_from_claude_code_input(tmp_path: Path, shell: str) -> None:
    project = _project(tmp_path)
    result = _run(OLD_CREATE, project, _event("WorktreeCreate", name="feature-auth"), shell)
    assert result.returncode != 0, result.stdout
    assert _worktrees(project) == 1  # only the main checkout


@pytest.mark.parametrize("shell", SHELLS)
def test_old_hook_lines_cannot_remove_from_claude_code_input(tmp_path: Path, shell: str) -> None:
    project = _project(tmp_path)
    target = project / ".claude" / "worktrees" / "feature-auth"
    assert _git(project, project, "worktree", "add", "-q", str(target), "-b", "made-by-hand").returncode == 0
    result = _run(OLD_REMOVE, project, _event("WorktreeRemove", worktree_path=str(target)), shell)
    assert result.returncode != 0, result.stdout
    assert target.is_dir()


def test_settings_register_the_script_for_both_events() -> None:
    assert SCRIPT.is_file()
    for event, mode in (("WorktreeCreate", "create"), ("WorktreeRemove", "remove")):
        command = _command(event)
        assert f".claude/hooks/{HOOK}" in command and f'"$f" {mode}' in command, command
        assert "WORKTREE_DIR" not in command and "WORKTREE_BRANCH" not in command, command


def test_the_repository_ignores_the_folder_the_hook_writes_to() -> None:
    """Read from the file, not `git check-ignore`: a machine's own .git/info/exclude would make that pass anyway."""
    assert ".claude/worktrees/" in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("folder", ["project", "my project folder"])
@pytest.mark.parametrize("shell", SHELLS)
def test_create_makes_the_worktree_and_prints_only_its_path(tmp_path: Path, shell: str, folder: str) -> None:
    project = _project(tmp_path, name=folder)
    result = _create(project, "feat_auth-1", shell)
    target = project / ".claude" / "worktrees" / "feat_auth-1"
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [str(target)]  # Claude Code reads the last line; git's noise is on stderr
    assert (target / ".git").exists()
    assert _has_branch(project, "worktree-feat_auth-1") and _worktrees(project) == 2


@pytest.mark.parametrize("name", ["", "../escape", "a/b", "-rf", "has space", ".hidden", "x" * 65, "a\nb", "abc\n", 5, None])
def test_create_refuses_a_name_that_is_not_a_plain_slug(tmp_path: Path, name: object) -> None:
    project = _project(tmp_path)
    result = _create(project, name)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert result.stdout == ""  # no path line, so Claude Code cannot adopt a folder
    assert _worktrees(project) == 1 and not (tmp_path / "escape").exists()
    assert "refusing to create: worktree name" in result.stderr


def test_create_refuses_a_name_already_in_use(tmp_path: Path) -> None:
    project = _project(tmp_path)
    assert _create(project, "taken").returncode == 0
    again = _create(project, "taken")
    assert again.returncode == 1 and again.stdout == "", again.stderr
    assert "already exists" in again.stderr and _worktrees(project) == 2


@pytest.mark.parametrize("shell", SHELLS)
def test_remove_takes_the_worktree_and_its_merged_branch(tmp_path: Path, shell: str) -> None:
    project = _project(tmp_path)
    target = Path(_create(project, "done-work").stdout.strip())
    result = _remove(project, target, shell)
    assert result.returncode == 0, result.stderr
    assert not target.exists() and _worktrees(project) == 1
    assert not _has_branch(project, "worktree-done-work")


def test_remove_keeps_a_branch_that_holds_unmerged_commits(tmp_path: Path) -> None:
    project = _project(tmp_path)
    target = Path(_create(project, "open-work").stdout.strip())
    assert _git(project, target, "commit", "-q", "--allow-empty", "-m", "work not merged yet").returncode == 0
    result = _remove(project, target)
    assert result.returncode == 0, result.stderr
    assert not target.exists()
    assert _has_branch(project, "worktree-open-work")  # the commits stay reachable


@pytest.mark.parametrize("kind", ["untracked", "staged", "modified"])
def test_remove_refuses_a_worktree_that_holds_unsaved_files(tmp_path: Path, kind: str) -> None:
    """Codex round 1: the script passed --force, so files that existed nowhere else were deleted with exit 0."""
    project = _project(tmp_path)
    target = Path(_create(project, "dirty").stdout.strip())
    note = target / "unsaved.txt"
    note.write_text("first")
    if kind != "untracked":
        assert _git(project, target, "add", "unsaved.txt").returncode == 0
    if kind == "modified":
        assert _git(project, target, "commit", "-q", "-m", "tracked").returncode == 0
        note.write_text("edited, not committed")
    result = _remove(project, target)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert note.read_text() in ("first", "edited, not committed") and _worktrees(project) == 2
    assert _has_branch(project, "worktree-dirty") and "was not removed" in result.stderr


@pytest.mark.parametrize("loose", [True, False])
def test_remove_of_a_detached_head_depends_on_a_branch_holding_its_commits(tmp_path: Path, loose: bool) -> None:
    """Same class: a clean worktree can still hold the only copy of a commit. On a branch, it is safe to take."""
    project = _project(tmp_path)
    target = Path(_create(project, "parked").stdout.strip())
    assert _git(project, target, "checkout", "-q", "--detach").returncode == 0
    if loose:
        assert _git(project, target, "commit", "-q", "--allow-empty", "-m", "on no branch").returncode == 0
    result = _remove(project, target)
    assert result.returncode == (1 if loose else 0), (result.stdout, result.stderr)
    assert target.is_dir() == loose and ("on no branch" in result.stderr) == loose


def _link_out(project: Path, outside: Path, link: str) -> Path:
    """Turn one step of <project>/.claude/worktrees/one into a symlink out of the project; return where `one` lands."""
    claude = project / ".claude"
    if link == "claude":
        shutil.move(str(claude), str(outside / "claude"))
    at, to, landing = {"claude": (claude, outside / "claude", outside / "claude" / "worktrees" / "one"),
                       "worktrees": (claude / "worktrees", outside, outside / "one"),
                       "name": (claude / "worktrees" / "one", outside / "one", outside / "one")}[link]
    at.parent.mkdir(exist_ok=True)
    at.symlink_to(to, target_is_directory=True)  # for "name" the link dangles until something is made at its far end
    return landing


@pytest.mark.parametrize("link", ["worktrees", "claude", "name"])
def test_a_symlink_out_of_the_project_stops_both_create_and_remove(tmp_path: Path, link: str) -> None:
    """Codex round 1 (P2): create built the worktree outside the project. Codex round 2 (P1): remove then deleted an
    outside worktree and its ignored file, exit 0. One rule, owned_target(), now decides for both."""
    project, outside = _project(tmp_path), tmp_path / "outside"
    outside.mkdir()
    landing = _link_out(project, outside, link)
    made = _create(project, "one")
    assert made.returncode == 1 and made.stdout == "" and "through a symlink" in made.stderr, made.stderr
    assert not landing.exists() and _worktrees(project) == 1
    assert _git(project, project, "worktree", "add", "-q", str(landing), "-b", "external").returncode == 0
    (project / ".git" / "info" / "exclude").write_text("*.cache\n")
    (landing / "only-copy.cache").write_text("ignored by git, exists nowhere else")
    gone = _remove(project, project / ".claude" / "worktrees" / "one")
    assert gone.returncode == 1 and "refusing to remove" in gone.stderr, (gone.stdout, gone.stderr)
    assert (landing / "only-copy.cache").is_file() and _worktrees(project) == 2


@pytest.mark.parametrize("kind", ["project", "sibling", "worktrees-root", "symlink-out", "nested", "alias"])
def test_remove_refuses_anything_but_a_folder_create_could_have_made(tmp_path: Path, kind: str) -> None:
    project = _project(tmp_path)
    real = Path(_create(project, "real").stdout.strip())
    root, sibling = real.parent, tmp_path / "sibling"
    (root / "a" / "b").mkdir(parents=True)
    sibling.mkdir()
    (sibling / "keep.txt").write_text("keep")
    (root / "link").symlink_to(sibling, target_is_directory=True)
    (root / "alias").symlink_to(real, target_is_directory=True)  # a link to a real worktree must not remove that one
    target = {"project": project, "sibling": sibling, "worktrees-root": root, "symlink-out": root / "link",
              "nested": root / "a" / "b", "alias": root / "alias"}[kind]
    result = _remove(project, target)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "refusing to remove" in result.stderr and real.is_dir() and _worktrees(project) == 2
    assert project.is_dir() and (root / "a" / "b").is_dir() and (sibling / "keep.txt").read_text() == "keep"


def test_remove_of_a_folder_already_gone_succeeds(tmp_path: Path) -> None:
    project = _project(tmp_path)
    result = _remove(project, project / ".claude" / "worktrees" / "never-made")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("event", ["WorktreeCreate", "WorktreeRemove"])
@pytest.mark.parametrize("payload", ["", "not json", "[]", "null", "{}", '{"name": {}, "worktree_path": 7}'])
def test_input_the_script_cannot_use_fails_closed(tmp_path: Path, event: str, payload: str) -> None:
    project = _project(tmp_path)
    result = _run(_command(event), project, payload)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert result.stdout == "" and _worktrees(project) == 1


@pytest.mark.parametrize("project_dir", [None, "/no/such/folder"])
@pytest.mark.parametrize("mode", ["create", "remove", "bogus"])
def test_the_script_fails_closed_without_a_project_folder_or_mode(tmp_path: Path, project_dir: str | None,
                                                                  mode: str) -> None:
    env = {"PATH": "/usr/bin:/bin", **({"CLAUDE_PROJECT_DIR": project_dir} if project_dir else {})}
    if mode == "bogus":
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    result = subprocess.run([sys.executable, str(SCRIPT), mode], input=_event("WorktreeCreate", name="x"),
                            capture_output=True, text=True, cwd=tmp_path, env=env, timeout=60)
    assert result.returncode == 1 and result.stdout == "", result.stderr
    assert "worktree_hook:" in result.stderr


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("event", ["WorktreeCreate", "WorktreeRemove"])
def test_a_missing_script_fails_with_a_reason_and_never_exits_2(tmp_path: Path, shell: str, event: str) -> None:
    """RA-8340: a session whose project folder is not this repository has no copy of the script. The line must say
    so and exit 1. `python3 <missing file>` exits 2, which Claude Code reads as "block" for other events."""
    project = _project(tmp_path, install=False)
    result = _run(_command(event), project, _event(event, name="x", worktree_path=str(project / "x")), shell)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert result.stdout == "" and _worktrees(project) == 1
    assert f"{project}/.claude/hooks/{HOOK}" in result.stderr and "RA-8375" in result.stderr


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("event", ["WorktreeCreate", "WorktreeRemove"])
def test_without_python3_the_line_exits_1_not_127(tmp_path: Path, shell: str, event: str) -> None:
    project = _project(tmp_path)
    result = _run(_command(event), project, _event(event, name="x"), shell, path=str(tmp_path / "no-such-bin"))
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert result.stdout == "" and not (project / ".claude" / "worktrees").exists()
