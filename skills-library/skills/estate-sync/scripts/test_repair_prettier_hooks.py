#!/usr/bin/env python3
"""The post-edit Prettier hook guard must actually fire, and must be WIRED.

WHY THIS EXISTS. repair_prettier_hooks.py is a safety control, and on 2026-08-08
it was found in the state its own docstring warns about: tracked in the repo since
2026-07-29, present on every machine, invoked by none — the bootstrap.sh line that
calls it was sitting uncommitted in a working tree. A control nothing calls is
indistinguishable from a control that passes.

So this file tests two separable things, and the second is the one that was broken:

  1. THE REPAIR      does the script detect and rewrite the defective command
  2. THE WIRING      does bootstrap.sh actually invoke the script

The interesting test is t5. Everything else checks strings; t5 runs both command
variants through a real shell with an instrumented `npx` and asserts on whether
prettier was INVOKED. That is the only test here that could have caught the
original defect, because the defect is shell semantics, not text:

    npx prettier --write "$CLAUDE_FILE_PATH"

with the variable unset expands to a bare `prettier --write`, which formats the
whole working tree. `2>/dev/null || true` then hides it. Reading the string tells
you nothing; running it tells you everything.

Stdlib only, no pytest. Mirrors test_symlinks.py.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repair_prettier_hooks as R  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

# The exact defect, as found live in two worktrees on 2026-08-08.
UNGUARDED = 'npx prettier --write "$CLAUDE_FILE_PATH" 2>/dev/null || true'


@contextlib.contextmanager
def scan_root(path):
    """Declare `path` as a scan root for the duration.

    repair() refuses to write outside ROOTS (review 2026-08-09: resolving a symlink
    otherwise let it edit files beyond the declared surface). Fixtures live under
    TMPDIR, which is NOT under $HOME, so without this every repair() call returns 0 —
    and tests that merely assert "nothing was broken" would pass VACUOUSLY. Declaring
    the root keeps each test exercising the real write path.
    """
    original = R.ROOTS
    R.ROOTS = [Path(path)]
    try:
        yield
    finally:
        R.ROOTS = original


def hooks_doc(command: str) -> dict:
    """A minimal .codex/hooks.json carrying one PostToolUse hook plus a sibling.

    The sibling exists so a repair that clobbers unrelated hooks fails loudly.
    """
    return {
        "hooks": {
            "PostToolUse": [
                {"matcher": "Write|Edit",
                 "hooks": [{"type": "command", "command": command}]}
            ],
            "Stop": [
                {"hooks": [{"type": "command",
                            "command": "bash .codex/hooks/stop-verifier.sh"}]}
            ],
        }
    }


def t1_detects_the_defect() -> None:
    """POSITIVE CONTROL. The real defective command must be flagged."""
    assert R.needs_repair(UNGUARDED), (
        "t1: the live defective command was NOT flagged — needs_repair() is broken, "
        "so every 'clean' result from this script is vacuous")


def t2_does_not_flag_the_innocent() -> None:
    """NEGATIVE CONTROLS. A check that flags everything is not a check."""
    cases = {
        "already guarded": R.GUARDED,
        "not prettier": 'eslint --fix "$CLAUDE_FILE_PATH"',
        "no file variable": "npx prettier --write .",
        "read-only prettier": 'npx prettier --check "$CLAUDE_FILE_PATH"',
        "non-string command": None,
    }
    wrong = [name for name, cmd in cases.items() if R.needs_repair(cmd)]
    assert not wrong, f"t2: flagged commands that are not the defect: {wrong}"


def t3_repairs_and_preserves() -> None:
    """The rewrite must replace the defect and leave sibling hooks alone."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "hooks.json"
        path.write_text(json.dumps(hooks_doc(UNGUARDED), indent=2))

        changed = R.repair(path)
        assert changed == 1, f"t3: expected 1 repair, got {changed}"

        data = json.loads(path.read_text())
        got = data["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        assert got == R.GUARDED, f"t3: command not replaced with the guard, got: {got}"
        assert data["hooks"]["PostToolUse"][0]["matcher"] == "Write|Edit", \
            "t3: repair dropped the matcher"
        assert data["hooks"]["Stop"][0]["hooks"][0]["command"].startswith("bash "), \
            "t3: repair clobbered an unrelated hook — blast radius is wrong"


def t4_idempotent() -> None:
    """A second run must leave the file BYTE-identical.

    bootstrap runs on every sync; a non-idempotent repair would churn the file
    forever and mask real drift.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "hooks.json"
        path.write_text(json.dumps(hooks_doc(UNGUARDED), indent=2))
        R.repair(path)

        before = path.read_bytes()
        changed = R.repair(path)
        after = path.read_bytes()

        assert changed == 0, f"t4: re-run reported {changed} repair(s), expected 0"
        assert before == after, "t4: re-run rewrote an already-guarded file"


def t5_guard_actually_suppresses_invocation() -> None:
    """THE REAL TEST. Run both variants in a shell and see if prettier is called.

    Four inputs, because the defect has three distinct triggers (unset, empty,
    directory) and one case that must keep working (a real file). A guard that
    also suppressed the file case would be a silent regression, not a fix.
    """
    bash = shutil.which("bash")
    assert bash, "t5: no bash on PATH — cannot test shell semantics, refusing to pass"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "bin").mkdir()
        (tmp / "tree").mkdir()
        target = tmp / "tree" / "a.js"
        target.write_text("x\n")

        # An `npx` that records its arguments instead of formatting anything.
        fake = tmp / "bin" / "npx"
        fake.write_text('#!/bin/sh\necho "INVOKED $*" >> "$LOG"\n')
        fake.chmod(0o755)

        log = tmp / "npx.log"
        inputs = {
            "unset": None,
            "empty": "",
            "directory": str(tmp / "tree"),
            "real file": str(target),
        }
        # (variant, input) -> should prettier run?
        expected = {
            (UNGUARDED, "unset"): True,       # the defect: bare `prettier --write`
            (UNGUARDED, "empty"): True,
            (UNGUARDED, "directory"): True,   # the defect: formats a whole tree
            (UNGUARDED, "real file"): True,
            (R.GUARDED, "unset"): False,
            (R.GUARDED, "empty"): False,
            (R.GUARDED, "directory"): False,
            (R.GUARDED, "real file"): True,   # must still do its job
        }

        failures = []
        for (command, case), should_run in expected.items():
            log.write_text("")
            env = {"PATH": f"{tmp / 'bin'}:/usr/bin:/bin", "LOG": str(log)}
            if inputs[case] is not None:
                env["CLAUDE_FILE_PATH"] = inputs[case]
            subprocess.run([bash, "-c", command], env=env, timeout=30,
                           capture_output=True)
            did_run = "INVOKED" in log.read_text()
            if did_run is not should_run:
                variant = "guarded" if command == R.GUARDED else "unguarded"
                failures.append(
                    f"{variant}/{case}: prettier "
                    f"{'ran' if did_run else 'did not run'}, expected the opposite")

        assert not failures, "t5: shell semantics wrong:\n    " + "\n    ".join(failures)


def t6_malformed_json_is_left_alone() -> None:
    """A hooks.json that does not parse must survive untouched.

    Rewriting it would disable EVERY hook in that file, turning a formatting
    nuisance into a disabled safety gate.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "hooks.json"
        path.write_text("{ not json")
        assert R.repair(path) == 0, "t6: reported a repair on unparseable JSON"
        assert path.read_text() == "{ not json", "t6: rewrote unparseable JSON"


def t7_bootstrap_actually_invokes_it() -> None:
    """THE WIRING GATE. This is the check that was missing.

    The script shipped to every machine on 2026-07-29 and ran on none, because
    nothing called it. Tracked-and-uninvoked is the estate's recurring failure
    class; assert the call site exists rather than assuming it.

    Comments do not count. A plain substring search over the whole file passes on
    a bootstrap.sh where the invocation is commented out — the script name also
    appears in prose — so this strips comment lines first and requires the name to
    survive in EXECUTABLE text. Caught in independent review 2026-08-08: the
    original form of this test could not fail under the defect it names, which is
    the same could-not-fail class as the bug it guards.
    """
    bootstrap = REPO / "bootstrap.sh"
    assert bootstrap.is_file(), f"t7: no bootstrap.sh at {bootstrap}"

    executable = [ln for ln in bootstrap.read_text().splitlines()
                  if not ln.lstrip().startswith("#")]
    invocations = [ln for ln in executable if "repair_prettier_hooks.py" in ln]

    assert invocations, (
        "t7: bootstrap.sh does not INVOKE repair_prettier_hooks.py in any "
        "non-comment line. The guard is tracked on every machine and executes on "
        "none — exactly the wired-is-not-synced defect it was written to fix.")
    assert any("python3" in ln for ln in invocations), (
        "t7: repair_prettier_hooks.py appears in executable text but is never run "
        f"by an interpreter. Lines found: {invocations}")


def t8_symlink_is_preserved_and_canonical_repaired() -> None:
    """A symlinked hooks.json must stay a link, and the REAL file must get guarded.

    Independently reproduced 2026-08-08 (Codex P1 #1): `tmp.replace(path)` swapped the
    symlink for a regular file, so the link got a guarded copy and the script printed
    success while the canonical file every other tool reads stayed unguarded. A false
    green — the worst shape of this bug, because it reports the opposite of the truth.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        canonical = tmp / "real-hooks.json"
        canonical.write_text(json.dumps(hooks_doc(UNGUARDED)))
        link = tmp / "hooks.json"
        link.symlink_to(canonical)

        R.repair(link)

        def command_in(p):
            return json.loads(Path(p).read_text())["hooks"]["PostToolUse"][0]["hooks"][0]["command"]

        assert link.is_symlink(), "t8: repair replaced the symlink with a regular file"
        assert command_in(canonical) == R.GUARDED, (
            "t8: the CANONICAL target was left unguarded — the link may look repaired "
            "while the file everything actually reads is still defective")


def t9_file_mode_is_preserved() -> None:
    """0600 and 0444 must survive the repair.

    os.replace adopts the TEMP file's permissions, so both silently became 0644.
    The 0444 case is a permission DOWNGRADE: a read-only hooks file becomes writable.
    """
    for want in (0o600, 0o444):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hooks.json"
            path.write_text(json.dumps(hooks_doc(UNGUARDED)))
            os.chmod(path, want)

            R.repair(path)

            got = stat.S_IMODE(path.stat().st_mode)
            assert got == want, f"t9: mode {oct(want)} became {oct(got)}"


def t10_concurrent_write_is_not_clobbered() -> None:
    """A writer landing mid-repair must not be silently overwritten.

    repair() is a read-modify-write; without an identity check it writes its stale
    pre-image over whatever arrived in the gap, silently disabling whatever that
    process just configured. Declining is the correct outcome — the next bootstrap
    run retries. Injected at the tmp parse-check, i.e. before the pre-replace stat.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "hooks.json"
        path.write_text(json.dumps(hooks_doc(UNGUARDED)))

        real_loads = R.json.loads
        calls = {"n": 0}

        def loads_with_race(s, *a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                doc = json.loads(path.read_text())
                doc["CONCURRENT_MARKER"] = "another-process"
                path.write_text(json.dumps(doc))
            return real_loads(s, *a, **k)

        R.json.loads = loads_with_race
        try:
            changed = R.repair(path)
        finally:
            R.json.loads = real_loads

        final = json.loads(path.read_text())
        assert changed == 0, "t10: repair overwrote a file that changed under it"
        assert "CONCURRENT_MARKER" in final, (
            "t10: the concurrent writer's change was lost")


def _scan_over(paths):
    """Run main() against an explicit file list, restoring the real finder after."""
    real_finder = R.find_hook_files
    R.find_hook_files = lambda: iter(paths)
    try:
        return R.main()
    finally:
        R.find_hook_files = real_finder


def t11_wrong_shape_json_does_not_abort_the_scan() -> None:
    """Valid JSON that does not match the hooks schema must not end the scan.

    Codex P1 #2, reproduced 2026-08-08: an entry that was a string made
    `(entry or {}).get` raise AttributeError. main() had no per-file guard, so the
    whole scan died on the first such file — and the __main__ wrapper turned that
    abort into exit 0, so bootstrap reported success while every later file was
    never examined. t6 only covers SYNTACTICALLY invalid JSON and cannot see this.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shapes = {
            "a-entry-is-string.json": {"hooks": {"PostToolUse": ["not a dict"]}},
            "b-hook-is-string.json": {"hooks": {"PostToolUse": [{"hooks": ["not a dict"]}]}},
            "c-top-is-list.json": ["top level is a list"],
        }
        paths = []
        for name, doc in shapes.items():
            p = tmp / name
            p.write_text(json.dumps(doc))
            paths.append(p)
        defective = tmp / "z-defective.json"
        defective.write_text(json.dumps(hooks_doc(UNGUARDED)))
        paths.append(defective)

        _scan_over(paths)

        got = json.loads(defective.read_text())["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        assert got == R.GUARDED, (
            "t11: a malformed-but-valid hooks file aborted the scan, so the defective "
            "file after it was left unguarded while bootstrap reported success")


def t12_one_failing_file_does_not_end_the_scan() -> None:
    """An unexpected error on one file must cost that file only.

    Separate from t11: t11 proves the shapes no longer raise; this proves the
    fault-isolation itself works for anything that still does. Without it the
    `except` branch is never exercised and cannot be trusted.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        boom = tmp / "boom.json"
        boom.write_text(json.dumps(hooks_doc(UNGUARDED)))
        later = tmp / "later.json"
        later.write_text(json.dumps(hooks_doc(UNGUARDED)))

        real_repair = R.repair

        def repair_that_explodes(path):
            if path.name == "boom.json":
                raise RuntimeError("simulated unexpected failure")
            return real_repair(path)

        R.repair = repair_that_explodes
        try:
            _scan_over([boom, later])
        finally:
            R.repair = real_repair

        got = json.loads(later.read_text())["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        assert got == R.GUARDED, (
            "t12: a raising file ended the scan; the file after it was never repaired")


def t13_symlink_outside_scan_roots_is_declined() -> None:
    """Resolving a link must not let the scanner write beyond its declared surface.

    Review 2026-08-09: a hooks.json symlinked to ../outside-root.json was repaired
    even though the target lay outside ROOTS (outside_target_repaired=True,
    target_within_scan_root=False). Fixing the false-green of P1 #1 by resolving
    introduced an unannounced edit outside the scan surface.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        root = tmp / "scan-root"
        (root / "project" / ".codex").mkdir(parents=True)
        outside = tmp / "outside-root.json"
        outside.write_text(json.dumps(hooks_doc(UNGUARDED)))
        link = root / "project" / ".codex" / "hooks.json"
        link.symlink_to(outside)

        with scan_root(root):
            changed = R.repair(link)

        got = json.loads(outside.read_text())["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        assert changed == 0, "t13: repaired a target outside the scan roots"
        assert got == UNGUARDED, (
            "t13: a file OUTSIDE the declared scan roots was rewritten")


def t14_preexisting_temp_symlink_cannot_be_followed() -> None:
    """The temp file must not be a predictable, pre-emptable name.

    Review 2026-08-09: `hooks.json.tmp` pre-created as a symlink to an unrelated file
    was followed — victim_overwritten=True, hooks_points_to_victim=True. mkstemp
    creates O_CREAT|O_EXCL with an unpredictable name, so there is nothing to pre-empt.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        path = tmp / "hooks.json"
        path.write_text(json.dumps(hooks_doc(UNGUARDED)))
        victim = tmp / "outside-victim.txt"
        victim.write_text("PRECIOUS")
        (tmp / "hooks.json.tmp").symlink_to(victim)

        with scan_root(tmp):
            R.repair(path)

        assert victim.read_text() == "PRECIOUS", (
            "t14: the repair followed a pre-created temp symlink and destroyed an "
            "unrelated file")
        assert not path.is_symlink(), "t14: hooks.json was turned into a symlink"


def t15_concurrent_write_detected_even_if_mtime_is_restored() -> None:
    """Identity must be the CONTENT, not the metadata.

    Review 2026-08-09: a writer that changed four bytes and restored the exact
    original mtime defeated the (mtime_ns, size) check entirely, and a writer landing
    between read and stat was never seen at all.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        path = tmp / "hooks.json"
        doc = hooks_doc(UNGUARDED)
        doc["MARKER"] = "AAAA"
        path.write_text(json.dumps(doc))
        original = path.stat()

        real_loads = R.json.loads
        calls = {"n": 0}

        def loads_with_race(s, *a, **k):
            calls["n"] += 1
            if calls["n"] == 2:  # the tmp parse-check, before the pre-replace compare
                d = json.loads(path.read_text())
                d["MARKER"] = "BBBB"
                path.write_text(json.dumps(d))
                os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
            return real_loads(s, *a, **k)

        R.json.loads = loads_with_race
        try:
            with scan_root(tmp):
                changed = R.repair(path)
        finally:
            R.json.loads = real_loads

        assert changed == 0, "t15: overwrote a file whose CONTENT changed under it"
        assert json.loads(path.read_text())["MARKER"] == "BBBB", (
            "t15: the concurrent writer's change was lost because the check trusted "
            "mtime, which the writer restored")


def t16_chmod_failure_aborts_the_swap() -> None:
    """If the mode cannot be preserved, do not perform the destructive half.

    Review 2026-08-09: a PermissionError from chmod was printed and the swap happened
    anyway, leaving final_mode=0o644 on a file that was 0600.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        path = tmp / "hooks.json"
        path.write_text(json.dumps(hooks_doc(UNGUARDED)))
        os.chmod(path, 0o600)

        real_chmod = R.os.chmod

        def chmod_that_fails(*a, **k):
            raise PermissionError("simulated chmod failure")

        R.os.chmod = chmod_that_fails
        try:
            with scan_root(tmp):
                changed = R.repair(path)
        finally:
            R.os.chmod = real_chmod

        got_mode = stat.S_IMODE(path.stat().st_mode)
        got_cmd = json.loads(path.read_text())["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        assert changed == 0, "t16: swapped despite being unable to preserve the mode"
        assert got_mode == 0o600, f"t16: mode became {oct(got_mode)} after a chmod failure"
        assert got_cmd == UNGUARDED, "t16: content was swapped despite the abort"


def _strays(directory: Path) -> list[str]:
    return [p.name for p in directory.iterdir()
            if ".tmp" in p.name or p.name.startswith(".hooks-repair-")]


def t17_no_temp_files_are_left_behind() -> None:
    """Every exit path must clean up its temp file, INCLUDING the abort paths.

    Review 2026-08-09 (P0): the original t17 ran only a successful replacement and
    then a no-op. On success the rename transfers ownership and on the no-op no temp
    is ever created, so the cleanup branch this test names was never executed —
    deleting the unlink left t17 green. It could not fail under the defect it
    guards, which is the same could-not-fail class it was written to catch.

    Each case below reaches an abort with a temp file already on disk: the
    digest-mismatch abort and the chmod-failure abort.
    """
    # Case 1: success then no-op — the original coverage, kept.
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        path = tmp / "hooks.json"
        path.write_text(json.dumps(hooks_doc(UNGUARDED)))
        with scan_root(tmp):
            R.repair(path)
            R.repair(path)
        assert not _strays(tmp), f"t17: temp left after success/no-op: {_strays(tmp)}"

    # Case 2: the digest-mismatch abort, reached with a temp file on disk.
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        path = tmp / "hooks.json"
        path.write_text(json.dumps(hooks_doc(UNGUARDED)))
        real_loads, calls = R.json.loads, {"n": 0}

        def loads_then_race(s, *a, **k):
            calls["n"] += 1
            if calls["n"] == 2:  # the temp parse-check: the temp now exists
                doc = json.loads(path.read_text())
                doc["MARKER"] = "CHANGED"
                path.write_text(json.dumps(doc))
            return real_loads(s, *a, **k)

        R.json.loads = loads_then_race
        try:
            with scan_root(tmp):
                changed = R.repair(path)
        finally:
            R.json.loads = real_loads
        assert changed == 0, "t17: swapped despite a concurrent content change"
        assert not _strays(tmp), f"t17: temp left after the digest abort: {_strays(tmp)}"

    # Case 3: the chmod-failure abort, reached with a temp file on disk.
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        path = tmp / "hooks.json"
        path.write_text(json.dumps(hooks_doc(UNGUARDED)))
        real_chmod = R.os.chmod

        def chmod_that_fails(*a, **k):
            raise PermissionError("simulated chmod failure")

        R.os.chmod = chmod_that_fails
        try:
            with scan_root(tmp):
                changed = R.repair(path)
        finally:
            R.os.chmod = real_chmod
        assert changed == 0, "t17: swapped despite being unable to preserve the mode"
        assert not _strays(tmp), f"t17: temp left after the chmod abort: {_strays(tmp)}"


def t18_ancestor_swapped_after_the_check_cannot_redirect_the_repair() -> None:
    """Confinement must survive an ancestor being swapped mid-repair.

    Review 2026-08-09 (P1): confinement was checked on a PATHNAME and every later
    operation re-resolved that same name. Renaming an ancestor and dropping a symlink
    to an outside directory in its place redirected the read, the temp write and the
    swap outside ROOTS — outside_repaired=True, inside_untouched=True. The window
    spanned almost the whole of repair(), far wider than the accepted final
    re-read-to-rename residual.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        root, outside = tmp / "scan-root", tmp / "outside"
        (root / "project" / ".codex").mkdir(parents=True)
        (outside / ".codex").mkdir(parents=True)
        path = root / "project" / ".codex" / "hooks.json"
        decoy = outside / ".codex" / "hooks.json"
        path.write_text(json.dumps(hooks_doc(UNGUARDED)))
        decoy.write_text(json.dumps(hooks_doc(UNGUARDED)))

        real_loads, calls = R.json.loads, {"n": 0}

        def loads_then_swap(s, *a, **k):
            # Call 1 is the parse of the file just read — by then confinement has been
            # decided, so this is exactly the window the finding describes.
            calls["n"] += 1
            if calls["n"] == 1:
                os.rename(root / "project", root / "project-moved")
                (root / "project").symlink_to(outside)
            return real_loads(s, *a, **k)

        R.json.loads = loads_then_swap
        try:
            with scan_root(root):
                R.repair(path)
        finally:
            R.json.loads = real_loads

        outside_cmd = json.loads(decoy.read_text())["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        moved = root / "project-moved" / ".codex" / "hooks.json"
        moved_cmd = json.loads(moved.read_text())["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        assert outside_cmd == UNGUARDED, (
            "t18: an ancestor swapped after the confinement check redirected the "
            "repair onto a file outside the scan roots")
        assert moved_cmd == R.GUARDED, (
            "t18: the pinned directory was not the one repaired")


def t19_concurrent_permission_change_is_not_reverted() -> None:
    """A concurrent chmod is an edit, and must be declined like a content edit.

    Review 2026-08-09 (P1): the mode was snapshotted before the temp existed and then
    applied blind at swap time. A writer that hardened 0644 -> 0600 without touching a
    byte was silently reverted — the content digest sees bytes only, so nothing
    noticed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        path = tmp / "hooks.json"
        path.write_text(json.dumps(hooks_doc(UNGUARDED)))
        os.chmod(path, 0o644)

        real_loads, calls = R.json.loads, {"n": 0}

        def loads_then_chmod(s, *a, **k):
            calls["n"] += 1
            if calls["n"] == 2:  # the temp parse-check, before the pre-swap compare
                os.chmod(path, 0o600)
            return real_loads(s, *a, **k)

        R.json.loads = loads_then_chmod
        try:
            with scan_root(tmp):
                changed = R.repair(path)
        finally:
            R.json.loads = real_loads

        got_mode = stat.S_IMODE(path.stat().st_mode)
        assert changed == 0, "t19: swapped despite a concurrent permission change"
        assert got_mode == 0o600, (
            f"t19: concurrent hardening was reverted — mode is {oct(got_mode)}, "
            "the stale pre-repair snapshot")


def t20_scan_root_swapped_before_it_is_opened_is_refused() -> None:
    """The descent is only as trustworthy as the descriptor it starts from.

    Review 2026-08-09 (P1): t18 pinned the component descent, but the SCAN ROOT was
    still opened by name without O_NOFOLLOW. Renaming the root and dropping a symlink
    to an outside directory in its place redirected the whole repair off the declared
    surface in one move — race_fired=True, outside_repaired=True. Distinct from t18:
    that swap happens after the dirfd exists, this one before it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        root, outside = tmp / "scan-root", tmp / "outside"
        root.mkdir()
        outside.mkdir()
        path = root / "hooks.json"
        decoy = outside / "hooks.json"
        path.write_text(json.dumps(hooks_doc(UNGUARDED)))
        decoy.write_text(json.dumps(hooks_doc(UNGUARDED)))

        real_open, fired = R.os.open, {"n": 0}

        def open_after_swapping_the_root(*a, **k):
            # Swap immediately before the very first open — the root open, which is
            # what establishes the trusted descriptor.
            fired["n"] += 1
            if fired["n"] == 1:
                os.rename(root, tmp / "scan-root-moved")
                root.symlink_to(outside)
            return real_open(*a, **k)

        R.os.open = open_after_swapping_the_root
        try:
            with scan_root(root):
                R.repair(path)
        finally:
            R.os.open = real_open

        assert fired["n"] >= 1, "t20: the root open never happened; the race never fired"
        outside_cmd = json.loads(decoy.read_text())["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        assert outside_cmd == UNGUARDED, (
            "t20: a scan root swapped to a symlink before it was opened redirected the "
            "repair onto a file outside the scan roots")


def t21_scan_root_replaced_by_a_directory_is_refused() -> None:
    """A root swapped for an ordinary DIRECTORY, not a symlink.

    Review 2026-08-09 (P1): O_NOFOLLOW refuses a symlink, and the identity check that
    was supposed to catch the rest compared fstat(dfd) against a stat() taken
    AFTERWARDS — so a directory swapped in before the open was observed identically by
    both and the check agreed with itself. The repair then rewrote a hooks.json the
    scan had never discovered. The snapshot is now taken before the open, so the two
    observations straddle the swap instead of both landing after it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        root, impostor = tmp / "scan-root", tmp / "impostor"
        root.mkdir()
        impostor.mkdir()
        path = root / "hooks.json"
        path.write_text(json.dumps(hooks_doc(UNGUARDED)))
        (impostor / "hooks.json").write_text(json.dumps(hooks_doc(UNGUARDED)))

        real_open, fired = R.os.open, {"n": 0}

        def open_after_replacing_the_root(*a, **k):
            fired["n"] += 1
            if fired["n"] == 1:
                os.rename(root, tmp / "scan-root-moved")
                os.rename(impostor, root)  # a real directory, not a link
            return real_open(*a, **k)

        R.os.open = open_after_replacing_the_root
        try:
            with scan_root(root):
                R.repair(path)
        finally:
            R.os.open = real_open

        assert fired["n"] >= 1, "t21: the root open never happened; the race never fired"
        planted = json.loads((root / "hooks.json").read_text())
        planted_cmd = planted["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        assert planted_cmd == UNGUARDED, (
            "t21: a directory swapped in for the scan root was repaired — an "
            "unannounced edit of a file the scan never discovered")


TESTS = [
    t1_detects_the_defect,
    t2_does_not_flag_the_innocent,
    t3_repairs_and_preserves,
    t4_idempotent,
    t5_guard_actually_suppresses_invocation,
    t6_malformed_json_is_left_alone,
    t7_bootstrap_actually_invokes_it,
    t8_symlink_is_preserved_and_canonical_repaired,
    t9_file_mode_is_preserved,
    t10_concurrent_write_is_not_clobbered,
    t11_wrong_shape_json_does_not_abort_the_scan,
    t12_one_failing_file_does_not_end_the_scan,
    t13_symlink_outside_scan_roots_is_declined,
    t14_preexisting_temp_symlink_cannot_be_followed,
    t15_concurrent_write_detected_even_if_mtime_is_restored,
    t16_chmod_failure_aborts_the_swap,
    t17_no_temp_files_are_left_behind,
    t18_ancestor_swapped_after_the_check_cannot_redirect_the_repair,
    t19_concurrent_permission_change_is_not_reverted,
    t20_scan_root_swapped_before_it_is_opened_is_refused,
    t21_scan_root_replaced_by_a_directory_is_refused,
]


def main() -> int:
    # Declare TMPDIR as the scan surface for the whole suite. repair() refuses to
    # write outside ROOTS, and every fixture here lives under TMPDIR (not $HOME), so
    # without this every repair() returns 0 — and the tests that assert "nothing was
    # broken" would pass VACUOUSLY while exercising none of the write path. Tests
    # that need the boundary to FIRE set their own roots via scan_root().
    R.ROOTS = [Path(tempfile.gettempdir())]

    failures = []
    for t in TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failures.append(t.__name__)
    n = len(TESTS)
    print(f"\n{n - len(failures)}/{n} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
