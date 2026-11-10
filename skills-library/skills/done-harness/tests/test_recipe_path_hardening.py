#!/usr/bin/env python3
r"""A recipe runs with a system PATH, not the caller's - and on Windows it must still
be able to find node.

This is the file the comment above `_run`'s PATH allowlist in donectl.py names. Its POSIX
half (planted interpreters, hostile HOME, the owner's ~/.local/bin staying LAST) was
written 02/09-05/09/2026 and lives at 9f1534c9 on feat/gauntlet-loop-v2; it never reached
main. What is here is the Windows half of the same defect.

Found 17/10/2026 on Synthex work w_700ccb6f54bf. The Windows branch of `_run` sets PATH
to System32, the Windows directory, Wbem and WindowsPowerShell and nothing else, so a
recipe written as `node ...` fails with "'node' is not recognized" and the criterion reads
FAILED for a tooling reason that looks exactly like a real failure. All three criteria at
b5e5bb369 did, until the contract was revised to name C:\nvm\nodejs\node.exe by absolute
path. The POSIX branch had the same gap closed on 05/09/2026 by appending the owner's
~/.local/bin LAST; the Windows branch never got the analogue.

Asserted by capturing the env handed to Popen with os.name and os.path.isdir patched, so
the suite runs on every platform CI has - an untested branch is how this gap survived.
Three things are held: the node directories come AFTER every system directory (position
is what makes them safe), a directory that is not present is not added, and nothing the
caller puts in the environment can add a directory. A fourth test runs bare
`node --version` through a real recipe on a Windows host that has node in one of the fixed
locations, and skips - saying so - everywhere else.

Run: python3 skills/done-harness/tests/test_recipe_path_hardening.py
"""
import importlib.util
import os
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
DONECTL = HERE.parent / "scripts" / "donectl.py"

# The fixed install directories `_run` may append, in the order it appends them: the
# standard installer's location, then nvm-windows's symlink. Neither is read from the
# caller - not from NVM_SYMLINK, not from ProgramFiles.
NODE_DIRS = (r"C:\Program Files\nodejs", r"C:\nvm\nodejs")


def load():
    spec = importlib.util.spec_from_file_location("_donectl_path", str(DONECTL))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TheWindowsRecipePathReachesNode(unittest.TestCase):
    def setUp(self):
        self.donectl = load()

    def _recipe_path(self, present, caller_env):
        """The PATH `_run` hands a Windows recipe when exactly `present` directories exist
        on disk and the caller's environment is exactly `caller_env`.

        Captured at Popen rather than by running a recipe, because this suite also runs
        on the POSIX hosts CI has, and because asserting on the string is what lets a
        hostile directory be "present" without creating it."""
        captured = {}

        class FakePopen:
            def __init__(self, *a, **kw):
                captured.update(kw.get("env") or {})
                self.pid = os.getpid()
                self.returncode = 0

            def communicate(self, timeout=None):
                return "", ""

        mod = self.donectl
        prev_name = mod.os.name
        prev_isdir = mod.os.path.isdir
        prev_popen = mod.subprocess.Popen
        prev_environ = dict(os.environ)
        mod.os.name = "nt"
        mod.os.path.isdir = lambda d: d in present
        mod.subprocess.Popen = FakePopen
        os.environ.clear()
        os.environ.update(caller_env)
        try:
            mod._run("node recipe.js", cwd=None)
        finally:
            mod.os.name = prev_name
            mod.os.path.isdir = prev_isdir
            mod.subprocess.Popen = prev_popen
            os.environ.clear()
            os.environ.update(prev_environ)
        return [p for p in captured.get("PATH", "").split(";") if p]

    def _system_path(self):
        """The PATH with no node directory present: the allowlist as it was, unchanged."""
        return self._recipe_path(present=(), caller_env={})

    # ------------------------------------------------------------------ the defect
    def test_the_node_directories_come_after_every_system_directory(self):
        """Membership alone would be the hole. If either directory came before System32,
        a file dropped in it would answer for cmd, where, or any other system tool in
        every recipe; LAST is what makes the append safe."""
        system = self._system_path()
        self.assertTrue(system, "positive control: the system allowlist must be non-empty")
        for d in NODE_DIRS:
            self.assertNotIn(d, system, "a node directory is in the system allowlist itself")

        path = self._recipe_path(present=NODE_DIRS, caller_env={})
        self.assertEqual(path[:len(system)], system,
                         "the system directories must stay first and unchanged: %r" % (path,))
        self.assertEqual(path[len(system):], list(NODE_DIRS),
                         "the node directories must be appended LAST, in their fixed order, "
                         "or a bare `node` recipe is still 'not recognized': %r" % (path,))

    def test_a_node_directory_that_is_not_present_is_not_added(self):
        """A PATH entry for a directory that does not exist is a place an attacker could
        later create. Only what is on disk now is appended."""
        system = self._system_path()
        path = self._recipe_path(present=(NODE_DIRS[1],), caller_env={})
        self.assertNotIn(NODE_DIRS[0], path, "an absent directory was added: %r" % (path,))
        self.assertEqual(path, system + [NODE_DIRS[1]],
                         "exactly the present directory, appended last: %r" % (path,))

    def test_nothing_in_the_callers_environment_can_add_a_directory(self):
        """The POSIX branch takes the owner's directory from the passwd database, never
        from HOME. There is no passwd database on Windows, so the locations are FIXED -
        and this holds that nothing the caller sets (NVM_SYMLINK, ProgramFiles, PATH, a
        variable nobody has listed) can move or add one. Every hostile directory is
        "present", so a branch that read the variable and checked isdir would be caught."""
        hostile = {
            "PATH": r"C:\ATTACKER\bin;C:\Windows\System32",
            "NVM_SYMLINK": r"C:\ATTACKER\nvm-symlink",
            "NVM_HOME": r"C:\ATTACKER\nvm",
            "ProgramFiles": r"C:\ATTACKER\Program Files",
            "ProgramW6432": r"C:\ATTACKER\Program Files",
            "ProgramFiles(x86)": r"C:\ATTACKER\Program Files (x86)",
            "NODE_HOME": r"C:\ATTACKER\node",
            "SYSTEMROOT": r"C:\ATTACKER",
            "SOMETHING_NOBODY_LISTED": r"C:\ATTACKER\anything",
        }
        present = set(NODE_DIRS)
        for v in hostile.values():
            present.update(p for p in v.split(";") if p)
            present.add(os.path.join(v, "nodejs"))

        clean = self._recipe_path(present=NODE_DIRS, caller_env={})
        path = self._recipe_path(present=present, caller_env=hostile)
        self.assertEqual(path, clean,
                         "the caller's environment changed the recipe PATH: %r" % (path,))
        self.assertFalse([p for p in path if "ATTACKER" in p.upper()],
                         "a caller-named directory reached the recipe PATH: %r" % (path,))

    # ------------------------------------------------------------- the behaviour
    def test_node_actually_runs_from_a_recipe_on_windows(self):
        """The behavioural case: bare `node` from a REAL recipe, under the real hardened
        environment. Only a Windows host with node in one of the fixed directories can
        prove it; everywhere else there is nothing to prove, and the skip says so rather
        than reading as a pass."""
        if os.name != "nt":
            self.skipTest("the Windows branch of _run runs only on Windows")
        installed = [d for d in NODE_DIRS if os.path.isfile(os.path.join(d, "node.exe"))]
        if not installed:
            self.skipTest("node.exe is in none of %r on this machine" % (NODE_DIRS,))
        rc, out = self.donectl._run("node --version", cwd=None)
        self.assertEqual(rc, 0,
                         "node is installed in %s but a recipe cannot run it: rc=%s out=%r"
                         % (installed[0], rc, out))
        self.assertRegex(out.strip(), r"^v\d+\.")

    # ------------------------------------------------------------- positive control
    def test_zz_an_ordinary_recipe_still_runs(self):
        """Without this, a _run that broke every recipe would satisfy the tests above
        while making every criterion permanently unprovable - the mirror defect."""
        rc, out = self.donectl._run("echo hello-from-recipe", cwd=None)
        self.assertEqual(rc, 0, out)
        self.assertIn("hello-from-recipe", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
