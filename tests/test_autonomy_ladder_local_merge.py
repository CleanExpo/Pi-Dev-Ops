"""RA-8245: a local merge is L1 only as plain local git; everything else keeps the old L3.

`git merge` was a blanket L3 signature. Lowering it to L1 for every command exposed
pushes that the blanket rule had been hiding: on a main checkout,
`git merge feature/x && git push origin HEAD` writes main and scored L2 (Codex round
1). Six rounds of trying to read every hidden push out of arbitrary Bash did not
converge, so the lowering is now an exact allowlist instead: plain `git` words, local
subcommands only, nothing that can push or run code. Each case below that contains a
merge and something else came from a Codex round, and must stay L3.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


LADDER = _load("autonomy_ladder_local_merge", "swarm/nexus/autonomy_ladder.py")


def tier(command: str) -> int:
    return LADDER.classify("Bash", {"command": command})


@pytest.mark.parametrize("command", [
    "git merge origin/main",
    "git merge --no-ff --no-edit origin/main",
    "git fetch origin && git merge origin/main",
    "git fetch origin; git merge --ff-only origin/main",
    "git -C /Users/x/repo merge origin/main",
    "git merge --abort",
    "git merge --no-edit origin/main && git status --short",
    "git switch feature/x && git merge origin/main && git log --oneline -3",
])
def test_plain_local_merge_is_below_l3(command: str) -> None:
    assert tier(command) < LADDER.TIER_IRREVERSIBLE, command


@pytest.mark.parametrize("command", [
    # Round 1: the reproduction that sent this branch back.
    "git merge feature/x && git push origin HEAD",
    "git merge feature/x && git push",
    "git merge feature/x && git push -u origin feature/x",
    # Rounds 2-6: hidden pushes, each chained after a merge.
    "git merge x && git push origin m'a'in",
    "git merge x && bash -c $'git push origin HEAD'",
    "git merge x && git pu''sh origin HEAD",
    "git merge x; p=push; git $p origin HEAD",
    "git merge x && printf 'gi%st pu%sh origin HEAD' t s | bash",
    "git merge x && git log `git push origin HEAD`",
    "git merge x\nalias g='git push origin HEAD'\ng",
    "git merge x && printf 'git push origin HEAD' > /tmp/g.sh && bash /tmp/g.sh",
    # Not plain git, so the old blanket L3 still applies.
    "git merge -m 'msg' origin/main",
    "git -c core.editor=true merge main",
    "git merge x & git status",
    "git merge x | cat",
    "cd /repo && git merge origin/main",
    # Round 7: plain words that still pick a program to run, write a file or discard work.
    "git merge -s localexec feature",
    "git merge --strategy=localexec feature",
    "git merge -slocalexec feature",
    "git merge -X theirs origin/main",
    "git merge HEAD && git fetch --upload-pack=/tmp/prog /tmp/bare.git",
    "git merge HEAD && git fetch --upload-pack /tmp/prog /tmp/bare.git",
    "git merge HEAD && git fetch ext::localexec",
    "git merge x && git diff --output=/tmp/f",
    "git merge x && git log --output=/tmp/f",
    "git merge x && git switch -f main",
    "git merge x && git checkout app.py",
    "git merge x && git branch -D old",
    "git merge x -- y",
])
def test_merge_inside_anything_else_keeps_the_old_l3(command: str) -> None:
    assert tier(command) == LADDER.TIER_IRREVERSIBLE, command


@pytest.mark.parametrize("command", [
    'echo "git push origin HEAD"',
    "echo X='git push origin HEAD'",
    "gh pr create --body='git push origin HEAD' --title x",
    "git commit --message='git push origin HEAD'",
])
def test_quoted_push_text_without_a_merge_is_not_raised_by_this_rule(command: str) -> None:
    """Round 5/6 false alarms came from the removed push reader; text is not L3 here."""
    assert tier(command) < LADDER.TIER_IRREVERSIBLE, command


def test_merge_strategy_really_runs_a_program_and_both_gates_deny_it(tmp_path: Path) -> None:
    """Positive control for round 7: `-s <name>` runs `git-merge-<name>` from PATH."""
    import os
    import subprocess

    import app.server.tool_gate as tool_gate
    import swarm.nexus.autonomy_gate as autonomy_gate

    repo, bindir, marker = tmp_path / "repo", tmp_path / "bin", tmp_path / "ran"
    bindir.mkdir()
    prog = bindir / "git-merge-localexec"
    prog.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 2\n")
    prog.chmod(0o755)
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", GIT_AUTHOR_NAME="t",
               GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    # Two diverged branches: an up-to-date merge never calls the strategy program.
    g = ["git", "-C", str(repo)]
    for cmd in (["git", "init", "-q", "-b", "trunk", str(repo)], g +["commit", "-q", "--allow-empty", "-m", "a"],
                g + ["branch", "feature"], g + ["commit", "-q", "--allow-empty", "-m", "b"],
                g + ["switch", "-q", "feature"], g + ["commit", "-q", "--allow-empty", "-m", "c"]):
        subprocess.run(cmd, check=True, env=env)
    command = "git merge -s localexec trunk"
    subprocess.run(command.split(), cwd=repo, env=env, capture_output=True)
    assert marker.exists(), "the strategy program did not run, so this control proves nothing"
    assert tier(command) == LADDER.TIER_IRREVERSIBLE
    assert tool_gate.decide("Bash", {"command": command}).allow is False
    assert autonomy_gate.decide("Bash", {"command": command}) is not None


@pytest.mark.parametrize("command", [
    "git fetch origin && git merge origin/main",
    "git -C /r merge HEAD && git -C /r fetch origin",
])
def test_a_plain_chain_is_no_higher_than_git_pull(command: str) -> None:
    """Round 8: a repo whose own config runs a program (an `ext::` remote, a hook) runs it
    for `git pull`, which is fetch plus merge and already L1 at base, and for a bare
    `git fetch origin` at L0. A plain chain may not rank above `git pull`; repository
    config is trusted by every git command and no text check can read it (RA-8248).
    """
    assert tier("git pull") < LADDER.TIER_IRREVERSIBLE
    assert tier(command) <= tier("git pull"), command
