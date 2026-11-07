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
    "git merge -X theirs origin/main && git status",
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
