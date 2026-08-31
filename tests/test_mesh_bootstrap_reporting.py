"""tests/test_mesh_bootstrap_reporting.py — bootstrap must not claim what it did not do.

`mesh/bootstrap.sh` ends with an unconditional "Done. $HOST is enlisted with
visibility + work execution." It printed that line on a simulated Windows node
after warning three times: no `PI_CEO_API_KEY`, a heartbeat that returned
`{"published": false}`, and a platform branch that installed no daemon at all.
Exit code was 0, so automation reads it as success too.

That is the RA-1109 surface treatment the repo prohibits — a label overstating
what the action did — and it sits on the critical path of fleet-operations
switch #1. `docs/runbooks/fleet-operations.md` warns that "a machine that
silently failed to enlist looks identical to one that is merely idle"; this was
worse, because the script actively asserted the opposite.

WHY THIS FILE EXISTS SEPARATELY FROM test_mesh_runner_service.py: that suite
asserts on bootstrap.sh's TEXT (`bootstrap.read_text()`), which can confirm a
string is present but can never catch a message printed on a path that should
not print it. Catching this needs the script EXECUTED, with the platform and
the heartbeat outcome controlled. Every external command is stubbed, so these
tests touch no network and install nothing.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = REPO_ROOT / "mesh" / "bootstrap.sh"

# `uname -s` as each fleet machine reports it. `phill-desktop` runs Git Bash,
# which reports MINGW64_NT-*, and matches neither Darwin nor Linux.
WINDOWS_UNAME = "MINGW64_NT-10.0-22631"

SUCCESS_CLAIM = "is enlisted with visibility + work execution"

# The two halves of "enlisted", as the script names them when one is missing.
# Tests assert the SPECIFIC gap: a script that merely failed somewhere would
# satisfy "did not claim success" without ever diagnosing anything.
NO_HEARTBEAT = "the first heartbeat did not publish"
NO_SUPERVISION = "no supervision installed"


def _write(path: Path, body: str) -> None:
    """Write an executable stub. Every fake binary here must be chmod +x."""
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _stub_bins(sandbox: Path, *, uname_s: str, heartbeat_ok: bool) -> Path:
    """A PATH where every command bootstrap shells out to is inert.

    The `python3` shim is the important one: it intercepts `heartbeat.py` so the
    publish outcome is a test parameter rather than a live HTTP call, and execs
    the real interpreter for everything else (bootstrap hardens agent hooks with
    an inline `python3 -` heredoc that must genuinely run).
    """
    binn = sandbox / "bin"
    binn.mkdir(parents=True, exist_ok=True)
    for name in ("node", "npm", "autogit", "launchctl", "systemctl"):
        _write(binn / name, "#!/bin/sh\nexit 0\n")
    _write(binn / "uname", f'#!/bin/sh\n[ "$1" = "-s" ] && echo "{uname_s}" || /usr/bin/uname "$@"\n')
    published = "true" if heartbeat_ok else "false"
    _write(
        binn / "python3",
        "#!/bin/sh\n"
        "for a in \"$@\"; do\n"
        "  case \"$a\" in *heartbeat.py)\n"
        f'    echo \'{{"published": {published}}}\'\n'
        f"    exit {0 if heartbeat_ok else 1} ;;\n"
        "  esac\n"
        "done\n"
        f'exec {sys.executable} "$@"\n',
    )
    return binn


def _run_bootstrap(sandbox: Path, *, uname_s: str, heartbeat_ok: bool) -> subprocess.CompletedProcess:
    """Run bootstrap.sh with the platform and heartbeat outcome controlled.

    `env -i`-style: only PATH, HOME and the API key are passed, so nothing
    leaks in from the runner and the two inputs under test are the only
    things that vary between cases.
    """
    binn = _stub_bins(sandbox, uname_s=uname_s, heartbeat_ok=heartbeat_ok)
    home = sandbox / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": f"{binn}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(home),
        "PI_CEO_API_KEY": "test-key-not-a-real-credential",
    }
    return subprocess.run(
        ["bash", str(BOOTSTRAP)],
        env=env, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
    )


# ── the regression ───────────────────────────────────────────────────────────


def test_windows_node_does_not_claim_enlistment_it_did_not_achieve(tmp_path):
    """THE REGRESSION TEST.

    The Windows branch installs no supervision — it prints a warning telling the
    operator to register Scheduled Tasks themselves. Until they do, the node
    sends the single bootstrap heartbeat and then goes silent, so dispatch skips
    it as stale forever. Claiming "enlisted with work execution" there is false.
    """
    proc = _run_bootstrap(tmp_path, uname_s=WINDOWS_UNAME, heartbeat_ok=True)
    combined = proc.stdout + proc.stderr
    assert SUCCESS_CLAIM not in combined
    # The heartbeat DID publish here, so only the supervision half may be named.
    # `!= 0` and "no success claim" were both satisfied by a script that died
    # before reaching the verdict at all — see the module docstring.
    assert NO_SUPERVISION in combined, combined
    assert NO_HEARTBEAT not in combined, combined
    assert proc.returncode == 1, f"exit {proc.returncode}: {proc.stderr}"


def test_a_failed_heartbeat_is_not_reported_as_enlisted(tmp_path):
    """A node whose heartbeat never published is not in the fleet.

    Supervision being installed is not sufficient: if nothing reached
    `/api/mesh/fleet`, the confirmation the runbook asks for cannot pass.
    """
    proc = _run_bootstrap(tmp_path, uname_s="Darwin", heartbeat_ok=False)
    combined = proc.stdout + proc.stderr
    assert SUCCESS_CLAIM not in combined
    # Mirror image of the case above: launchd loaded both services, so ONLY the
    # heartbeat half is missing. Asserting both directions is what stops a
    # blanket "NOT enlisted" from passing either test.
    assert NO_HEARTBEAT in combined, combined
    assert NO_SUPERVISION not in combined, combined
    assert proc.returncode == 1, f"exit {proc.returncode}: {proc.stderr}"


def test_the_operator_is_told_which_half_failed(tmp_path):
    """A denial an operator cannot act on is barely better than a false success.

    The two failure modes need different work — one is a platform port, the
    other is a credential or an endpoint — so the output must distinguish them.
    """
    proc = _run_bootstrap(tmp_path, uname_s=WINDOWS_UNAME, heartbeat_ok=True)
    combined = proc.stdout + proc.stderr
    assert "schtasks" in combined, "Windows needs the actual command, not prose"
    assert "NOT enlisted" in combined


# ── green controls ───────────────────────────────────────────────────────────


def test_a_fully_successful_darwin_run_still_reports_enlisted(tmp_path):
    """GREEN CONTROL, and the reason the tests above prove anything.

    A "fix" that deleted the success line, or that always exited non-zero, would
    satisfy every assertion above while telling an operator on a working Mac
    that their node failed. The happy path must still say so and exit 0.
    """
    proc = _run_bootstrap(tmp_path, uname_s="Darwin", heartbeat_ok=True)
    assert SUCCESS_CLAIM in proc.stdout, proc.stdout + proc.stderr
    assert proc.returncode == 0


def test_darwin_still_installs_both_launchd_services(tmp_path):
    """GREEN CONTROL for the supervision check itself.

    The verdict must be derived from work actually done, not asserted alongside
    it — so pin that the happy path really does write both plists.
    """
    proc = _run_bootstrap(tmp_path, uname_s="Darwin", heartbeat_ok=True)
    agents = tmp_path / "home" / "Library" / "LaunchAgents"
    assert (agents / "com.unite-group.mesh-heartbeat.plist").exists(), proc.stdout
    assert (agents / "com.unite-group.mesh-runner.plist").exists(), proc.stdout


@pytest.mark.parametrize("uname_s,enlisted,exit_code", [
    ("Darwin", True, 0),          # installs both launchd services
    ("Linux", False, 1),          # prints daemon commands, supervises nothing
    (WINDOWS_UNAME, False, 1),    # prints schtasks commands, supervises nothing
])
def test_every_platform_reaches_its_own_verdict(tmp_path, uname_s, enlisted, exit_code):
    """Each platform must arrive at its verdict deliberately, not fall out early.

    `set -euo pipefail` makes any failing command an exit, so a script that
    died on an unrelated line would still exit non-zero — which the two
    regression tests above would happily read as the fix working. Asserting the
    TERMINAL LINE, not just a tolerated exit code, is what separates "reached
    the verdict block and decided" from "died on the way there".

    Raised by CodeRabbit on this PR. The earlier version of this test accepted
    any exit of 0 or 1 once it saw the opening banner, and the banner prints on
    line 18. Verified by planting `false` right after it: the script died at
    line 20, never reached the verdict, and all three cases passed — the exact
    early exit the docstring claimed to guard.
    """
    proc = _run_bootstrap(tmp_path, uname_s=uname_s, heartbeat_ok=True)
    assert "Nexus Mesh bootstrap on" in proc.stdout
    combined = proc.stdout + proc.stderr
    if enlisted:
        assert SUCCESS_CLAIM in combined, combined
    else:
        assert "NOT enlisted" in combined, combined
    assert proc.returncode == exit_code, f"exit {proc.returncode}: {proc.stderr}"
