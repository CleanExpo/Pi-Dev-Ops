"""Where the size gates get their file list.

TRACKED **AND** UNTRACKED. The two size linters used to enumerate `git ls-files`
alone, which made them blind to precisely the file a session had just written: git
cannot see a new file until `git add`, so the gate printed "passed" locally and CI
then failed on it. Three files reached main that way — `file_length_lint.py`'s own
`main()`, `mesh_dispatch_service.py`, and `gate_parity_lint.py::main`, whose 51
lines were declared green by a run that could not see the file it was judging. A
gate whose blind spot is "new code" is not a gate, and CLAUDE.md's advice to run
the gates after `git add` put the fix in the hands of whoever forgot. It is here
instead.

`--exclude-standard` honours .gitignore, so scratch output and build artefacts stay
out. In CI everything is committed, so this changes nothing there — the whole
effect is local, which is exactly where the blindness was.
"""
from __future__ import annotations

import subprocess


def _ls(flags: list[str], suffixes: tuple[str, ...]) -> list[str]:
    return subprocess.run(
        ["git", "ls-files", *flags, *suffixes],
        capture_output=True, text=True, check=True,
    ).stdout.split("\n")


def source_paths(*suffixes: str) -> list[str]:
    """Every source path git knows about that it is not ignoring."""
    return _ls([], suffixes) + _ls(["--others", "--exclude-standard"], suffixes)
