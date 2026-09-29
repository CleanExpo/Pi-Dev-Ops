#!/usr/bin/env python3
"""Tests for estate-sync.sh — the unattended 15-minute auto-sync to origin/main.

WHY. This script runs `git add --ignore-removal .` then commits and pushes to
main, unattended, every 15 minutes. Whatever a session happens to have on disk at
minute 15 becomes a commit on main. That was tolerable while the synced surface
was inert markdown. It stopped being tolerable on 2026-07-16 when .github/ was
unignored to add CI: files under .github/workflows/ EXECUTE on push. A workflow
caught half-written by the timer would run, and a transient broken state would
land red on main — with no human having decided it was ready.

These tests drive the REAL script against a throwaway bare remote (via
ESTATE_SYNC_REPO), so the push path is genuinely exercised without touching
origin.

T2 is the positive control and is NOT optional: it proves the sync still pushes
ordinary work. Without it, a script that pushed NOTHING would satisfy T1
vacuously — "the workflow wasn't pushed" is trivially true of a broken sync.

Stdlib only, no pytest. Requires git plus zsh on POSIX or Windows PowerShell.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import shutil
import unittest
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).parent / "estate-sync.sh"
POWERSHELL_SCRIPT = Path(__file__).parent / "estate-sync.ps1"


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, timeout=60)
    return (r.stdout + r.stderr).strip()


def _make_estate(tmp: Path) -> tuple[Path, Path]:
    """A repo wired to a local bare 'origin', shaped like skills-library."""
    origin = tmp / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", "-b", "main", str(origin)], check=True)

    repo = tmp / "estate"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    _git(repo, "remote", "add", "origin", str(origin))

    # deny-all + allowlist, mirroring the real .gitignore
    (repo / ".gitignore").write_text("*\n!.gitignore\n!.github/\n!.github/**\n!skills/\n!skills/**\nlogs/\n")
    (repo / "logs").mkdir()
    (repo / "skills" / "demo").mkdir(parents=True)
    (repo / "skills" / "demo" / "SKILL.md").write_text("# demo\n")
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text("name: ci\non: [push]\n")

    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    # Seed origin by CLONING rather than pushing. pr-release-gate installs a global
    # pre-push hook (~/.config/git/hooks/pre-push) that runs `verify` for every push to
    # refs/heads/* in ANY repository, including these throwaway remotes. The setup push
    # therefore failed, origin stayed empty, the script's own `git fetch origin main`
    # then failed at line 16, and every test died before reaching the behaviour it was
    # written to exercise -- while t1 passed vacuously throughout. Clone does not fire
    # pre-push. See t15, which asserts this situation rather than hiding it.
    shutil.rmtree(origin)
    subprocess.run(["git", "clone", "--bare", "-q", str(repo), str(origin)], check=True)
    _git(repo, "fetch", "-q", "origin")
    _git(repo, "branch", "--set-upstream-to=origin/main", "main")
    return repo, origin


def _seed_origin(repo: Path, origin: Path) -> None:
    """Advance origin/main to the repo's HEAD without pushing.

    A push from the test repo fires pr-release-gate's global pre-push hook and fails.
    Fetching from the origin side achieves the same setup and runs no push hook.
    """
    subprocess.run(["git", "--git-dir", str(origin), "fetch", "-q", str(repo),
                    "main:refs/heads/main"], check=True)


def _run_sync(repo: Path) -> str:
    r = _run_sync_result(repo)
    return r.stdout + r.stderr


def _run_sync_result(repo: Path, path: str = "", quiet_secs: str = "0",
                     hold_max_secs: str = "3600",
                     receipt_max_secs: str = "3600") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({"HOME": str(repo.parent), "ESTATE_SYNC_REPO": str(repo),
                # Tests write a file then sync in the same second, which the quiescence
                # guard is designed to skip. Default it off so every pre-existing test
                # still exercises what it was written to exercise; t13/t14 set it back on.
                "ESTATE_SYNC_QUIET_SECS": quiet_secs,
                "ESTATE_SYNC_HOLD_MAX_SECS": hold_max_secs,
                # Expiry is off by default for the same reason: every other test writes
                # its receipt seconds before syncing. t26 sets it to 0 to make every
                # receipt stale deterministically, rather than sleeping.
                "ESTATE_SYNC_RECEIPT_MAX_SECS": receipt_max_secs})
    if os.name == "nt":
        if path:
            env["PATH"] = path
        command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                   "-File", str(POWERSHELL_SCRIPT)]
    else:
        # Resolve zsh rather than hardcoding /bin/zsh. On a Linux CI runner or a
        # container it lives at /usr/bin/zsh, and the hardcoded path made 15 of these
        # 22 tests raise FileNotFoundError — reported as ERROR, indistinguishable in
        # a summary from the script being broken. A platform gap rendering as a
        # failure is the fault class this repo keeps paying for, and the suite that
        # guards the sync was committing it.
        zsh = shutil.which("zsh") or "/bin/zsh"
        if not os.path.exists(zsh):
            raise unittest.SkipTest(
                "zsh is not installed on this host, so the POSIX sync path cannot be "
                "exercised here. This is NOT a pass: the tests did not run. Install "
                "zsh (CI does) or run this suite on macOS.")
        command = [zsh, str(SCRIPT)]
        env["PATH"] = path or "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
    return subprocess.run(command,
                          capture_output=True, text=True, timeout=120,
                          env=env)


def _receipt(repo: Path, *paths: str) -> None:
    """Write the gate receipt that authorises the sync to publish these exact files.

    Deliberately an INDEPENDENT implementation of the receipt format rather than a call
    to `estate-sync.ps1 -Receipt`: a test that produced its input with the code under
    test would pass just as happily if both sides agreed on the wrong thing.
    """
    lines = ["# test receipt"]
    for p in paths:
        digest = hashlib.sha256((repo / p).read_bytes()).hexdigest()
        lines.append(f"{digest}  {p}")
    (repo / ".estate-sync-receipt").write_text("\n".join(lines) + "\n")


def _pushed_files(origin: Path) -> set[str]:
    out = subprocess.run(["git", "--git-dir", str(origin), "ls-tree", "-r",
                          "--name-only", "main"],
                         capture_output=True, text=True, timeout=60).stdout
    return set(out.split())


def _origin_content(origin: Path, path: str) -> str:
    return subprocess.run(["git", "--git-dir", str(origin), "show", f"main:{path}"],
                          capture_output=True, text=True, timeout=60).stdout


def t1_workflow_edit_is_not_auto_pushed(tmp: Path) -> None:
    """THE FIX. A mid-edit workflow must never be auto-committed to main.

    Simulates the real hazard: a session is halfway through editing a workflow
    when the 15-minute timer fires.
    """
    repo, origin = _make_estate(tmp)
    broken = "name: ci\non: [push]\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n        BROKEN"
    (repo / ".github" / "workflows" / "ci.yml").write_text(broken)
    (repo / ".github" / "workflows" / "brand-new.yml").write_text("name: half-written\n")

    _run_sync(repo)

    assert "BROKEN" not in _origin_content(origin, ".github/workflows/ci.yml"), (
        "T1: a half-edited workflow was auto-pushed to main — it would EXECUTE there")
    assert ".github/workflows/brand-new.yml" not in _pushed_files(origin), (
        "T1: a brand-new half-written workflow was auto-pushed to main")


def t2_ordinary_work_still_syncs(tmp: Path) -> None:
    """POSITIVE CONTROL. The sync must still do its job.

    Without this, a totally broken sync that pushes nothing would pass T1.
    """
    repo, origin = _make_estate(tmp)
    (repo / "skills" / "demo" / "NEW.md").write_text("# new skill\n")
    (repo / "skills" / "demo" / "SKILL.md").write_text("# demo edited\n")
    _receipt(repo, "skills/demo/NEW.md", "skills/demo/SKILL.md")

    out = _run_sync(repo)

    pushed = _pushed_files(origin)
    assert "skills/demo/NEW.md" in pushed, (
        f"T2: estate-sync no longer pushes ordinary skill work — the sync is broken, "
        f"and T1's green is meaningless. out={out[-400:]}")
    assert "edited" in _origin_content(origin, "skills/demo/SKILL.md"), (
        "T2: edits to existing skills stopped propagating")


def t3_mixed_edit_pushes_skill_not_workflow(tmp: Path) -> None:
    """The discriminating case: both dirty at once, only the skill goes."""
    repo, origin = _make_estate(tmp)
    (repo / "skills" / "demo" / "SKILL.md").write_text("# demo edited\n")
    (repo / ".github" / "workflows" / "ci.yml").write_text("name: ci\non: [push]\n# WIP\n")
    _receipt(repo, "skills/demo/SKILL.md")

    _run_sync(repo)

    assert "edited" in _origin_content(origin, "skills/demo/SKILL.md"), (
        "T3: skill work was blocked — the .github guard is over-reaching")
    assert "WIP" not in _origin_content(origin, ".github/workflows/ci.yml"), (
        "T3: workflow edit leaked to main alongside the skill edit")


def t4_skip_is_logged_not_silent(tmp: Path) -> None:
    """A skipped .github edit must be explained, or it sits dirty forever."""
    repo, _ = _make_estate(tmp)
    (repo / ".github" / "workflows" / "ci.yml").write_text("name: ci\non: [push]\n# WIP\n")

    _run_sync(repo)

    log = (repo / "logs" / "estate-sync.log").read_text()
    assert ".github" in log, f"T4: the skip was silent. log={log[-300:]}"


def t5_deleted_tracked_skill_is_non_green_and_not_pushed(tmp: Path) -> None:
    """A deleted tracked symlink must block all pushes and never report in-sync."""
    repo, origin = _make_estate(tmp)
    blob = subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
                          input="../../Pi-Dev-Ops/skills/design-audit",
                          capture_output=True, text=True, check=True).stdout.strip()
    _git(repo, "update-index", "--add", "--cacheinfo",
         f"120000,{blob},skills/design-link")
    _git(repo, "commit", "-qm", "track relative skill symlink")
    _seed_origin(repo, origin)
    (repo / "skills" / "demo" / "SKILL.md").write_text("# must not push\n")

    result = _run_sync_result(repo)

    log = (repo / "logs" / "estate-sync.log").read_text()
    assert result.returncode != 0, "T5: a tracked deletion returned green"
    assert "tracked deletion" in log.lower(), f"T5: deletion was not reported. log={log[-300:]}"
    assert "ok: in sync" not in log, f"T5: deletion was falsely reported in-sync. log={log[-300:]}"
    assert "skills/design-link" in _pushed_files(origin), (
        "T5: tracked deletion propagated to origin")
    assert "must not push" not in _origin_content(origin, "skills/demo/SKILL.md"), (
        "T5: ordinary edits were pushed despite unresolved deletion")


def t6_powershell_checks_deletions_before_staging(tmp: Path) -> None:
    """Windows must fail closed on tracked deletions before its staging path."""
    del tmp  # source-order contract; native execution is run on Windows
    source = POWERSHELL_SCRIPT.read_text()
    deletion_guard = source.find("--diff-filter=D")
    staging = source.find("git add --ignore-removal")
    assert 0 <= deletion_guard < staging, (
        "T6: PowerShell does not check tracked deletions before staging")


def t7_powershell_suppresses_github_before_commit(tmp: Path) -> None:
    """Windows must not auto-commit executable GitHub configuration."""
    del tmp  # source-order contract; native execution is run on Windows
    source = POWERSHELL_SCRIPT.read_text()
    # As of 16/08/2026 the dedicated `git restore --staged .github` was generalised into a
    # never-sync sweep that runs over everything staged. The guarantee this test exists for
    # is unchanged — executable CI config must be unstaged before any commit — so assert the
    # mechanism that now provides it, and that .github is still one of its members.
    listed = source.find("'.github/'")
    sweep = source.find("REFUSED: unstaged never-sync path")
    commit = source.find("git commit --quiet")
    assert 0 <= listed, "T7: .github is not in the PowerShell never-sync list"
    assert 0 <= sweep < commit, (
        "T7: PowerShell does not sweep never-sync paths out of the index before auto-commit")


def t8_powershell_supports_throwaway_repo_override(tmp: Path) -> None:
    """Windows regression tests must not exercise the canonical estate."""
    del tmp
    source = POWERSHELL_SCRIPT.read_text()
    assert "ESTATE_SYNC_REPO" in source, (
        "T8: PowerShell cannot be exercised against a throwaway remote")


def t9_test_harness_selects_powershell_on_windows(tmp: Path) -> None:
    """The same throwaway-remote suite must exercise PowerShell on Windows."""
    del tmp
    source = inspect.getsource(_run_sync_result)
    assert 'os.name == "nt"' in source and "powershell.exe" in source, (
        "T9: test harness cannot execute the Windows implementation")


def t10_deletion_probe_failure_is_non_green(tmp: Path) -> None:
    """A failed deletion classifier must not degrade to an empty, green result."""
    repo, origin = _make_estate(tmp)
    (repo / "skills" / "demo" / "SKILL.md").write_text("# must not push\n")
    bindir = tmp / "bin"
    bindir.mkdir()
    real_git = shutil.which("git")
    assert real_git
    if os.name == "nt":
        wrapper = bindir / "git.cmd"
        wrapper.write_text(
            "@echo off\n"
            "echo %* | %SystemRoot%\\System32\\findstr.exe /C:\"--diff-filter=D\" >nul\n"
            "if not errorlevel 1 exit /b 128\n"
            f'"{real_git}" %*\n')
        path = f"{bindir}{os.pathsep}{os.environ['PATH']}"
    else:
        wrapper = bindir / "git"
        wrapper.write_text(
            "#!/bin/sh\n"
            "case \" $* \" in *' --diff-filter=D '*) exit 128;; esac\n"
            f'exec "{real_git}" "$@"\n')
        wrapper.chmod(0o755)
        path = f"{bindir}:/usr/bin:/bin"

    local_head_before = _git(repo, "rev-parse", "HEAD")
    result = _run_sync_result(repo, path)

    log = (repo / "logs" / "estate-sync.log").read_text()
    assert _git(repo, "rev-parse", "HEAD") == local_head_before, (
        "T10: ordinary edits were committed locally after deletion probe failure")
    assert result.returncode != 0, "T10: failed deletion probe returned green"
    assert "ok: in sync" not in log, "T10: failed deletion probe reported in-sync"
    assert "must not push" not in _origin_content(origin, "skills/demo/SKILL.md"), (
        "T10: ordinary edits were pushed after deletion probe failure")


def t11_powershell_fails_closed_when_deletion_probe_fails(tmp: Path) -> None:
    """Windows must check the classifier exit code before trusting its output."""
    del tmp
    source = POWERSHELL_SCRIPT.read_text()
    probe = source.index("$deleted =")
    result_use = source.index("$deleted.Count", probe)
    assert "$LASTEXITCODE" in source[probe:result_use], (
        "T11: PowerShell treats a failed deletion probe as an empty result")


def t12_github_unstage_failure_is_non_green(tmp: Path) -> None:
    """A failed .github unstage must stop before any commit or push."""
    repo, origin = _make_estate(tmp)
    (repo / "skills" / "demo" / "SKILL.md").write_text("# must not push\n")
    (repo / ".github" / "workflows" / "ci.yml").write_text(
        "name: WIP-BYPASS\non: [push]\n")
    # Force the workflow into the index first. Since 16/08/2026 the Windows gate refuses to
    # STAGE a never-sync path at all, so the unstage branch this test exists to exercise is
    # only reachable if something else put it there — which is exactly the corruption the
    # branch is defence against. Harmless on POSIX, where `git add .` stages it anyway.
    _git(repo, "add", "-f", ".github")
    bindir = tmp / "bin"
    bindir.mkdir()
    real_git = shutil.which("git")
    assert real_git
    if os.name == "nt":
        wrapper = bindir / "git.cmd"
        wrapper.write_text(
            "@echo off\n"
            "echo %* | %SystemRoot%\\System32\\findstr.exe "
            "/C:\"restore --staged\" >nul\n"
            "if not errorlevel 1 exit /b 128\n"
            f'"{real_git}" %*\n')
        path = f"{bindir}{os.pathsep}{os.environ['PATH']}"
    else:
        wrapper = bindir / "git"
        wrapper.write_text(
            "#!/bin/sh\n"
            "case \" $* \" in *' restore --staged '*) exit 128;; esac\n"
            f'exec "{real_git}" "$@"\n')
        wrapper.chmod(0o755)
        path = f"{bindir}:/usr/bin:/bin"

    local_head_before = _git(repo, "rev-parse", "HEAD")
    origin_head_before = _git(origin, "rev-parse", "main")
    result = _run_sync_result(repo, path)

    log = (repo / "logs" / "estate-sync.log").read_text()
    assert result.returncode != 0, "T12: failed .github unstage returned green"
    assert _git(repo, "rev-parse", "HEAD") == local_head_before, (
        "T12: failed .github unstage still created a local commit")
    assert _git(origin, "rev-parse", "main") == origin_head_before, (
        "T12: failed .github unstage still pushed to origin")
    assert "ok: in sync" not in log, (
        "T12: failed .github unstage was falsely reported in-sync")


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


def t13_recent_edit_is_not_swept_into_a_sync_commit(tmp: Path) -> None:
    """The bug this guard exists for, reproduced.

    On 2026-07-29 the timer fired at 14:35:43 and 14:50:56 while an agent was midway
    through committing. Both times `git add .` swept the work into a chore(sync) commit,
    so the change landed under a message that explains nothing and the author's own
    commit found nothing left to record.

    Asserts on the COMMIT, not the push: the guard's job is to leave the working tree
    alone, and the push path is separately blocked on this machine by the global
    pr-release-gate pre-push hook (see t15).

    The first half is the positive control. Without it a guard that skipped every cycle
    would satisfy the second half trivially.
    """
    repo, _ = _make_estate(tmp)
    (repo / "skills" / "fresh.md").write_text("an agent is still writing this\n")
    _receipt(repo, "skills/fresh.md")  # control arm: the gate must not be what blocks it
    before = _head(repo)
    _run_sync_result(repo, quiet_secs="0")
    assert _head(repo) != before, (
        "T13 control: with the guard off the edit must be committed, else this test proves "
        "nothing about the guard")

    repo2, _ = _make_estate(tmp / "second")
    (repo2 / "skills" / "fresh.md").write_text("an agent is still writing this\n")
    before2 = _head(repo2)
    _run_sync_result(repo2, quiet_secs="300")
    assert _head(repo2) == before2, (
        "T13: a file written seconds ago was still swept into a sync commit")
    log = (repo2 / "logs" / "estate-sync.log").read_text()
    assert "session may be mid-edit" in log, f"T13: the skip was silent. log={log}"


def t14_hold_stops_the_sync_and_a_stale_hold_does_not_wedge_it(tmp: Path) -> None:
    """An explicit hold beats a heuristic; a forgotten hold must not block sync forever."""
    repo, _ = _make_estate(tmp)
    (repo / ".estate-sync-hold").write_text("")
    (repo / "skills" / "held.md").write_text("work in progress\n")
    _receipt(repo, "skills/held.md")  # so the stale-hold arm is testing the HOLD, not the gate
    before = _head(repo)

    _run_sync_result(repo, quiet_secs="0", hold_max_secs="3600")
    assert _head(repo) == before, "T14: the hold did not stop the sync"
    log = (repo / "logs" / "estate-sync.log").read_text()
    assert "session working" in log, f"T14: the hold skip was silent. log={log}"

    # Same hold, now past its cap: the sync must proceed rather than block indefinitely.
    _run_sync_result(repo, quiet_secs="0", hold_max_secs="0")
    assert _head(repo) != before, "T14: a stale hold blocked the sync forever"
    log = (repo / "logs" / "estate-sync.log").read_text()
    assert "hold is stale" in log, f"T14: the stale-hold override was silent. log={log}"


def t15_global_pre_push_hook_blocks_the_test_remote(tmp: Path) -> None:
    """Documents why t2-t5 are red on this machine, so the cause is not rediscovered.

    ~/.config/git/hooks/pre-push is installed globally by pr-release-gate and runs
    `pr_release_gate.py verify` for every push to any refs/heads/* in ANY repository,
    including the throwaway bare remotes this suite creates. The setup push in
    _make_estate therefore fails, origin stays empty, and every assertion phrased as
    "was it pushed" is vacuous -- t1 passes for the wrong reason.

    This test asserts the situation rather than working around it. It fails, loudly and
    on purpose, if someone narrows the hook to exempt temp-directory remotes -- at which
    point t2-t5 can be restored to push-based assertions and this test deleted.
    """
    hook = Path.home() / ".config" / "git" / "hooks" / "pre-push"
    if not hook.exists():
        return  # nothing installed here; the suite's push path is unobstructed
    body = hook.read_text()
    assert "pr_release_gate.py" in body, (
        "T15: a global pre-push hook exists but is not the pr-release-gate one -- "
        "re-establish why pushes are intercepted before trusting this suite")
    repo, origin = _make_estate(tmp)
    (repo / "skills" / "pushprobe.md").write_text("probe\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "probe")
    out = _git(repo, "push", "-q", "origin", "main")
    assert "pushprobe.md" not in _pushed_files(origin), (
        f"T15: a direct push from a throwaway repo now succeeds -- the pre-push hook has been "
        f"narrowed. Restore the fixture to push-based seeding and delete this test. out={out}")


def t16_foreign_commit_on_main_is_not_auto_pushed(tmp: Path) -> None:
    """The bug this guard exists for, reproduced.

    On 06/08/2026 an interactive session's `git commit` landed directly on local
    main (should have gone to a feature branch) and the next 15-minute cycle
    pushed it to origin unattended, with zero review, before the session had
    decided how to release it. skills-library is exempt from the receipt-based
    pr-release-gate itself (deliberately, per pr_release_gate.py) — but that
    exemption is about not requiring the heavyweight PR machinery for routine
    housekeeping, not a licence for this cron to ship any commit it happens to
    find sitting on main. Only the script's own chore(sync) commits may be
    auto-pushed; anything else must wait for a human/session to push it.
    """
    repo, origin = _make_estate(tmp)
    origin_head_before = _git(origin, "rev-parse", "main")
    (repo / "skills" / "demo" / "SKILL.md").write_text("# a session's deliberate change\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "feat(demo): a deliberate change a session made directly on main")

    result = _run_sync_result(repo)

    log = (repo / "logs" / "estate-sync.log").read_text()
    assert result.returncode == 0, f"T16: guard should skip cleanly, not fail. log={log[-400:]}"
    assert _git(origin, "rev-parse", "main") == origin_head_before, (
        "T16: a non-sync commit on local main was auto-pushed to origin unattended")
    assert "non-sync commit" in log, f"T16: the skip was silent. log={log[-400:]}"
    assert "ok: in sync" not in log, (
        f"T16: a held foreign commit was falsely reported in-sync. log={log[-400:]}")


def t17_own_sync_commit_still_pushes(tmp: Path) -> None:
    """POSITIVE CONTROL for T16. Without it, a guard that skips every push would pass T16
    trivially — this proves the guard still lets the script's own housekeeping through."""
    repo, origin = _make_estate(tmp)
    (repo / "skills" / "demo" / "NEW.md").write_text("# new skill\n")
    _receipt(repo, "skills/demo/NEW.md")

    _run_sync(repo)

    assert "skills/demo/NEW.md" in _pushed_files(origin), (
        "T17: the foreign-commit guard is over-reaching and blocked the script's own sync commit")


def t18_powershell_holds_foreign_commits_before_pushing(tmp: Path) -> None:
    """Windows must carry the same non-sync-commit guard as macOS/Linux.

    No live Windows box is reachable from this environment (no pwsh, no
    Task Scheduler host, no documented remote access in connections.md), so
    this is a structural proof, same contract as T6/T7/T11: the guard that
    matches commit subjects against the chore(sync) pattern and skips before
    ever reaching `git push` must exist and be correctly ordered relative to
    the push line. Native end-to-end execution is run on Windows itself.
    """
    del tmp
    source = POWERSHELL_SCRIPT.read_text()
    guard = source.find(r"-notmatch '^chore\(sync\): .* auto-sync '")
    held_skip = source.find("non-sync commit(s) ahead of origin/main")
    push = source.find("git push origin main")
    assert 0 <= guard < held_skip < push, (
        "T18: PowerShell's foreign-commit guard is missing or does not "
        "precede the push line — a non-sync commit on main could still ship")


GATED_SCRIPT = POWERSHELL_SCRIPT if os.name == "nt" else SCRIPT


def _require_gate() -> None:
    """t19-t22 test the receipt gate. Fail loudly where it is not implemented.

    This is deliberately NOT a skip. estate-sync.sh on the Mac Mini pushes to the same
    PUBLIC origin and has not been gated (16/08/2026); a skip here would render green and
    the estate would carry a hole it had a passing test suite for. Delete this shim when
    the .sh carries the gate.
    """
    if ".estate-sync-receipt" not in GATED_SCRIPT.read_text():
        raise AssertionError(
            f"{GATED_SCRIPT.name} has no receipt gate — this machine can still publish "
            "unreceipted third-party edits to the PUBLIC origin. Founder item, 16/08/2026.")


def t19_unreceipted_edit_is_refused_not_published(tmp: Path) -> None:
    """THE FIX. An edit this script did not author must never become a public commit.

    Reproduces 16/08/2026: an agent edited skills/session-handoff/SKILL.md at ~14:53 and
    deliberately did not commit it; the 15:09:49 cycle published it as aac5efe.
    """
    _require_gate()
    repo, origin = _make_estate(tmp)
    origin_head_before = _git(origin, "rev-parse", "main")
    before = _head(repo)
    (repo / "skills" / "demo" / "SKILL.md").write_text("# edited by someone else, uncommitted\n")

    result = _run_sync_result(repo)

    log = (repo / "logs" / "estate-sync.log").read_text()
    assert _head(repo) == before, "T19: an unreceipted foreign edit was committed"
    assert _git(origin, "rev-parse", "main") == origin_head_before, (
        "T19: an unreceipted foreign edit was PUBLISHED")
    assert "REFUSED: skills/demo/SKILL.md" in log, (
        f"T19: the refusal was silent — an operator cannot tell edits are piling up. log={log[-400:]}")
    assert result.returncode == 0, "T19: a refusal is a normal steady state, not a failure"


def t20_receipt_is_one_shot_and_content_bound(tmp: Path) -> None:
    """A receipt authorises a VERSION, not a filename.

    Without the hash binding, an author could receipt a file a foreign process then
    rewrites before the timer fires — the exact race the gate exists to close.
    """
    _require_gate()
    repo, origin = _make_estate(tmp)
    origin_head_before = _git(origin, "rev-parse", "main")
    (repo / "skills" / "demo" / "SKILL.md").write_text("# the content the author signed\n")
    _receipt(repo, "skills/demo/SKILL.md")
    (repo / "skills" / "demo" / "SKILL.md").write_text("# SWAPPED after signing\n")

    _run_sync_result(repo)

    log = (repo / "logs" / "estate-sync.log").read_text()
    assert "SWAPPED" not in _origin_content(origin, "skills/demo/SKILL.md"), (
        "T20: content swapped after the receipt was written was still published")
    assert _git(origin, "rev-parse", "main") == origin_head_before, "T20: the swap was published"
    assert "changed after the receipt" in log, f"T20: the refusal was silent. log={log[-400:]}"


def t21_session_handoffs_are_never_published(tmp: Path) -> None:
    """Handoffs are transcripts of private estate work and origin is PUBLIC.

    Asserts the TRACKED case specifically: 23 handoffs are already committed, and git
    never ignores a tracked path, so .gitignore alone cannot hold this line.
    """
    _require_gate()
    repo, origin = _make_estate(tmp)
    handoff = repo / "docs" / "session-handoffs" / "old.md"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text("# an already-tracked handoff\n")
    _git(repo, "add", "-f", "docs/session-handoffs/old.md")
    _git(repo, "commit", "-qm", "seed a tracked handoff")
    _seed_origin(repo, origin)
    origin_head_before = _git(origin, "rev-parse", "main")
    handoff.write_text("# prod db identities and what is unguarded\n")
    _receipt(repo, "docs/session-handoffs/old.md")  # even WITH a receipt

    _run_sync_result(repo)

    log = (repo / "logs" / "estate-sync.log").read_text()
    assert "unguarded" not in _origin_content(origin, "docs/session-handoffs/old.md"), (
        "T21: an edit to a tracked session handoff was published to the public origin")
    assert _git(origin, "rev-parse", "main") == origin_head_before, "T21: the handoff edit shipped"
    assert "never-sync path" in log, f"T21: the refusal was silent. log={log[-400:]}"


def t22_secret_in_the_payload_refuses_the_whole_push(tmp: Path) -> None:
    """A receipt proves someone named the file, not that they read every line of it.

    The planted value is AWS's own published example key, never a live credential.
    """
    _require_gate()
    repo, origin = _make_estate(tmp)
    origin_head_before = _git(origin, "rev-parse", "main")
    (repo / "skills" / "demo" / "notes.md").write_text(
        "aws_access_key_id = AKIA" + "IOSFODNN7EXAMPLE\n")
    _receipt(repo, "skills/demo/notes.md")

    result = _run_sync_result(repo)

    log = (repo / "logs" / "estate-sync.log").read_text()
    assert _git(origin, "rev-parse", "main") == origin_head_before, (
        "T22: a credential-shaped value was pushed to the public origin")
    assert "SECRET-SCAN" in log, f"T22: the scan did not fire. log={log[-400:]}"
    assert "AKIA" + "IOSFODNN7EXAMPLE" not in log, (
        "T22: the scanner logged the secret it found — the log is not a safe place for it")
    assert result.returncode != 0, "T22: a blocked push reported green"


def _write_receipt_via_script(repo: Path, *paths: str) -> subprocess.CompletedProcess[str]:
    """Invoke the script's OWN receipt-writing mode, unlike _receipt() above.

    _receipt() reimplements the format independently, which is right for t19-t22: a test
    that produced its input with the code under test would pass just as happily if both
    sides agreed on the wrong thing. But that independence means nothing in this suite has
    ever run the mode a HUMAN types. An unusable receipt writer is not a cosmetic defect —
    it is the whole gate, because an operator who cannot publish deliberately will disable
    the gate rather than stop publishing.
    """
    env = os.environ.copy()
    env.update({"HOME": str(repo.parent), "ESTATE_SYNC_REPO": str(repo),
                "ESTATE_SYNC_QUIET_SECS": "0"})
    if os.name == "nt":
        command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                   "-File", str(POWERSHELL_SCRIPT), "-Receipt", "-Path", ",".join(paths)]
    else:
        zsh = shutil.which("zsh") or "/bin/zsh"
        if not os.path.exists(zsh):
            raise unittest.SkipTest(
                "zsh is not installed on this host, so the POSIX receipt writer cannot be "
                "exercised here. This is NOT a pass: the test did not run.")
        command = [zsh, str(SCRIPT), "--receipt", *paths]
        env["PATH"] = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
    return subprocess.run(command, capture_output=True, text=True, timeout=120, env=env)


def t23_the_receipt_writer_produces_a_receipt_the_gate_accepts(tmp: Path) -> None:
    """End-to-end on the human path: write the receipt with the script, then sync.

    The two halves of the gate were written from the same description but are separate
    code. If the writer emits `sha  path` and the reader expects `path  sha`, every test
    above still passes — they all bypass the writer — and every real publish silently
    refuses. This is the only test that makes the two halves meet.
    """
    _require_gate()
    repo, origin = _make_estate(tmp)
    (repo / "skills" / "demo" / "NEW.md").write_text("# written by a human who meant it\n")

    written = _write_receipt_via_script(repo, "skills/demo/NEW.md")
    assert written.returncode == 0, (
        f"T23: the receipt writer failed. out={written.stdout} err={written.stderr}")
    assert "receipt written" in written.stdout, (
        f"T23: the writer said nothing an operator could act on. out={written.stdout}")

    # The hash it recorded must be the real one, computed here without the script.
    body = (repo / ".estate-sync-receipt").read_text()
    digest = hashlib.sha256((repo / "skills" / "demo" / "NEW.md").read_bytes()).hexdigest()
    assert digest in body.lower(), (
        f"T23: the receipt does not carry the file's actual sha256. receipt={body!r}")

    _run_sync(repo)

    assert "skills/demo/NEW.md" in _pushed_files(origin), (
        "T23: a receipt written by the script itself was not accepted by the script's own "
        "gate — the publish path a human uses does not work")
    assert not (repo / ".estate-sync-receipt").exists(), (
        "T23: the receipt was not consumed — it is a standing licence, not a one-shot, and "
        "tomorrow's unrelated edit to the same file would publish itself")


def t24_the_receipt_writer_fails_closed_on_a_partial_request(tmp: Path) -> None:
    """One refused path must refuse the whole request.

    A partial receipt is the worst outcome: the author is told some paths were rejected and
    reasonably assumes nothing was authorised, while the subset that passed publishes on
    the next cycle.
    """
    _require_gate()
    repo, _ = _make_estate(tmp)
    (repo / "skills" / "demo" / "NEW.md").write_text("# fine\n")
    (repo / ".github" / "workflows" / "ci.yml").write_text("name: ci\n# WIP\n")

    written = _write_receipt_via_script(repo, "skills/demo/NEW.md",
                                        ".github/workflows/ci.yml")

    assert written.returncode != 0, "T24: a refused path still returned success"
    assert not (repo / ".estate-sync-receipt").exists(), (
        f"T24: a PARTIAL receipt was written — skills/demo/NEW.md would publish while the "
        f"author believes the request was refused. out={written.stdout}")
    assert "never-sync" in written.stdout, (
        f"T24: the refusal did not say why. out={written.stdout}")


def t25_the_receipt_writer_refuses_a_path_that_is_not_a_file(tmp: Path) -> None:
    """A typo must be reported, not receipted.

    Receipting a non-existent path would put an entry in the file that can never match,
    which reads to an operator exactly like the gate being broken.
    """
    _require_gate()
    repo, _ = _make_estate(tmp)

    written = _write_receipt_via_script(repo, "skills/demo/TYPO.md")

    assert written.returncode != 0, "T25: a non-existent path was receipted successfully"
    assert not (repo / ".estate-sync-receipt").exists(), "T25: a receipt was still written"
    assert "not a file" in written.stdout, (
        f"T25: the refusal did not name the cause. out={written.stdout}")


def t26_a_stale_receipt_authorises_nothing(tmp: Path) -> None:
    """Expiry is the difference between a permit and a standing licence.

    Found by mutation, not by review: setting the staleness branch to `if false` left the
    whole suite green, so nothing here had ever proved that a receipt stops working. A
    receipt that never expires means a file named once in August is publishable in
    December, including by whatever process happens to have rewritten it since.

    Both arms run with the same receipt and the same edit; only the lifetime differs, so
    a gate that refused everything could not pass this.
    """
    _require_gate()
    repo, origin = _make_estate(tmp)
    (repo / "skills" / "demo" / "NEW.md").write_text("# authorised in August\n")
    _receipt(repo, "skills/demo/NEW.md")

    _run_sync_result(repo, receipt_max_secs="0")

    log = (repo / "logs" / "estate-sync.log").read_text()
    assert "skills/demo/NEW.md" not in _pushed_files(origin), (
        "T26: a receipt past its lifetime still authorised a publish")
    assert "receipt stale" in log, (
        f"T26: the expiry was silent — an operator cannot tell why nothing published. "
        f"log={log[-400:]}")

    # Positive control: the same receipt, same file, within its lifetime. Without this a
    # gate that refused every receipt would pass the first half.
    _run_sync_result(repo, receipt_max_secs="3600")
    assert "skills/demo/NEW.md" in _pushed_files(origin), (
        "T26 control: a receipt inside its lifetime was refused — expiry is over-reaching "
        "and the gate cannot be used at all")


TESTS = (t1_workflow_edit_is_not_auto_pushed, t2_ordinary_work_still_syncs,
         t3_mixed_edit_pushes_skill_not_workflow, t4_skip_is_logged_not_silent,
         t5_deleted_tracked_skill_is_non_green_and_not_pushed,
         t6_powershell_checks_deletions_before_staging,
         t7_powershell_suppresses_github_before_commit,
         t8_powershell_supports_throwaway_repo_override,
         t9_test_harness_selects_powershell_on_windows,
         t10_deletion_probe_failure_is_non_green,
         t11_powershell_fails_closed_when_deletion_probe_fails,
         t12_github_unstage_failure_is_non_green,
         t13_recent_edit_is_not_swept_into_a_sync_commit,
         t14_hold_stops_the_sync_and_a_stale_hold_does_not_wedge_it,
         t15_global_pre_push_hook_blocks_the_test_remote,
         t16_foreign_commit_on_main_is_not_auto_pushed,
         t17_own_sync_commit_still_pushes,
         t18_powershell_holds_foreign_commits_before_pushing,
         t19_unreceipted_edit_is_refused_not_published,
         t20_receipt_is_one_shot_and_content_bound,
         t21_session_handoffs_are_never_published,
         t22_secret_in_the_payload_refuses_the_whole_push,
         t23_the_receipt_writer_produces_a_receipt_the_gate_accepts,
         t24_the_receipt_writer_fails_closed_on_a_partial_request,
         t25_the_receipt_writer_refuses_a_path_that_is_not_a_file,
         t26_a_stale_receipt_authorises_nothing)



def main() -> int:
    failures, skipped = [], []
    for t in TESTS:
        with tempfile.TemporaryDirectory() as d:
            try:
                t(Path(d))
                print(f"PASS  {t.__name__}")
            except unittest.SkipTest as e:
                # A test that COULD NOT RUN is not a test that failed, and it is not
                # a test that passed either. Reporting a missing interpreter as ERROR
                # made 15 of these 22 read as breakage in the sync script — a
                # platform gap wearing a defect's clothes, in the suite guarding the
                # bus. Reporting it as PASS would be worse. It gets its own bucket
                # and the tally names it, so "7/22 passed" can never again be read as
                # "15 things are broken".
                print(f"SKIP  {t.__name__}: {e}")
                skipped.append(t.__name__)
            except AssertionError as e:
                print(f"FAIL  {t.__name__}: {e}")
                failures.append(t.__name__)
            except Exception as e:  # noqa: BLE001
                print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
                failures.append(t.__name__)
    ran = len(TESTS) - len(skipped)
    print(f"\n{ran - len(failures)}/{ran} passed"
          + (f", {len(skipped)} SKIPPED (did not run)" if skipped else ""))
    if skipped:
        print("  skipped: " + ", ".join(skipped))
        print("  A skip is NOT a pass. Install the missing dependency or run this")
        print("  suite on a host that has it.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
