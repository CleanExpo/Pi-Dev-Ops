"""tests/swarm/test_tmux_validator_home.py — the cd sandbox must not depend on HOME.

`skills/terminal-orchestrator/policy/allowlist.yaml` lists `~` among
`verbs.cd.safe_path_prefixes`, meaning "anywhere under the operator's home".
That entry is load-bearing: without it `cd ~/Pi-CEO` would be denied on every
machine whose home is not literally `/Users/phillmcgurk`.

It was also the hole. `Path("~").expanduser()` is `/` whenever `HOME=/`, and the
old check asked `target.startswith(exp.rstrip("/") + "/")` — with `exp` of `/`
that is `target.startswith("/")`, true for EVERY absolute path. The allowlist
stopped constraining anything, silently, on a security control.

WHY THIS FILE EXISTS SEPARATELY FROM test_tmux_validator.py: that suite runs
under whatever HOME the runner happens to have. On CI that is `/home/runner`, so
the bug is invisible there — the suite was fully green on `main` while the hole
was open. A test that pins this behaviour has to set HOME itself, and assert
across several values rather than trusting the one it inherited.

The bug reached `main` and survived because no test controlled this variable.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from swarm.tmux_validator import validate_command  # noqa: E402

# Real homes plus the degenerate one. `/` is not hypothetical: it is what this
# repo's own dev container runs with, which is how the defect was found.
HOMES = ["/Users/phillmcgurk", "/home/runner", "/root", "/"]

# Paths no cd allowlist should ever admit, whatever HOME says.
OUTSIDE = ["/etc", "/etc/ssh", "/var/log", "/usr/bin", "/"]


@pytest.mark.parametrize("home", HOMES)
@pytest.mark.parametrize("target", OUTSIDE)
def test_cd_outside_the_allowlist_is_denied_under_every_home(monkeypatch, home, target):
    """THE REGRESSION TEST.

    Under `HOME=/` every one of these was ALLOWED before the fix, because the
    `~` prefix expanded to `/` and matched the whole filesystem. The other three
    homes are the green control in the same parametrisation: they proved nothing
    was broken by the fix, and they are also why CI never caught the original.
    """
    monkeypatch.setenv("HOME", home)
    assert validate_command(f"cd {target} && ls").allowed is False
    assert validate_command(f"cd {target}").allowed is False


@pytest.mark.parametrize("home", ["/Users/phillmcgurk", "/home/runner", "/root"])
def test_the_home_prefix_still_works_where_home_is_a_real_directory(monkeypatch, home):
    """GREEN CONTROL, and the reason the fix skips `/` rather than dropping `~`.

    `~` must keep meaning "anywhere under my home" on a normal machine. A fix
    that removed the entry outright, or that rejected every prefix, would pass
    the test above while denying the operator their own working directories.
    """
    monkeypatch.setenv("HOME", home)
    assert validate_command("cd ~/Pi-CEO && git status").allowed is True
    assert validate_command("cd ~").allowed is True


def test_a_root_home_costs_the_home_prefix_rather_than_the_sandbox(monkeypatch):
    """The accepted trade-off, written down so it is not mistaken for a bug.

    With `HOME=/`, "under my home" is "the entire filesystem", so the entry
    cannot be honoured without voiding the sandbox. It is skipped, which means
    `cd ~/anything` is refused in that environment. That is the correct
    direction: a visible denial an operator can act on, rather than a silent
    hole nothing reports.
    """
    monkeypatch.setenv("HOME", "/")
    assert validate_command("cd ~/Pi-CEO && git status").allowed is False
    # An explicitly listed absolute prefix still works — only `~` is lost.
    assert validate_command("cd /tmp && ls").allowed is True


@pytest.mark.parametrize("home", HOMES)
def test_explicit_prefixes_are_unaffected_by_home(monkeypatch, home):
    """`/tmp` is in the allowlist literally and must behave identically
    everywhere — proof the fix touched only `~`-derived prefixes."""
    monkeypatch.setenv("HOME", home)
    assert validate_command("cd /tmp && ls").allowed is True
    assert validate_command("cd /tmp/sub && ls").allowed is True


@pytest.mark.parametrize("home", HOMES)
def test_prefix_matching_is_not_a_bare_string_prefix(monkeypatch, home):
    """`/tmpevil` must not pass because it starts with the characters `/tmp`.

    The check appends a separator before comparing, so a sibling directory whose
    name merely begins with an allowed one is still outside. Independent of the
    HOME bug, and cheap to pin while this file is being written.
    """
    monkeypatch.setenv("HOME", home)
    assert validate_command("cd /tmpevil && ls").allowed is False
