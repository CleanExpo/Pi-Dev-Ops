"""mesh/repo_guard.py — is this runner's default repo actually this project?

`mesh/runner.py` resolves every claim without an explicit `repo_dir` against
`DEFAULT_REPO_DIR`, which is `MESH_REPO_DIR` or, failing that, the checkout the
runner ships in. Honouring the variable is deliberate: `bootstrap.sh` sets it in
the launchd plist, and a relocated runner needs it.

Silently INHERITING it is the failure mode (RA-7375). On one node it was
exported into the ambient session pointing at a foreign Codex worktree on an
external volume, so every default-routed claim would have run there — and until
RA-7394 was fixed, been claimed, failed, and never reported.

RUNTIME CANNOT TELL DELIBERATE FROM INHERITED. That was established while fixing
RA-7370, and no test can separate them either: the process sees one environment
variable with no provenance. What it CAN tell is whether the path is a checkout
of the same project the runner itself ships in, and that stands in for intent —
a deliberate relocation points at a clone of this repo; an inherited path
usually does not.

The authority is the runner's own checkout's `origin`, not a hardcoded name, so
the check is self-describing and keeps working on a fork or a rename.

Extracted from runner.py rather than added to it: that file was under the
300-line convention and this would have pushed it over, and the repo's rule is
to extract rather than baseline a new offender.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def git_origin(repo: Path) -> str:
    """The `origin` URL of a checkout, or "" when there is none to read."""
    out = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"],
                         capture_output=True, text=True, check=False)
    if getattr(out, "returncode", 1) != 0:
        return ""
    return (getattr(out, "stdout", "") or "").strip()


def repo_dir_problem(default_repo_dir: Path, own_repo: Path) -> str:
    """Why `default_repo_dir` must not be trusted, or "" when it is sound.

    Takes both paths rather than reading module state, so it can be reasoned
    about and tested without loading the runner.
    """
    target = Path(default_repo_dir).expanduser().resolve()
    own = Path(own_repo).resolve()
    if target == own:
        return ""
    if not (target / ".git").exists():
        return f"MESH_REPO_DIR={target} is not a git checkout"
    mine = git_origin(own)
    if not mine:
        return f"cannot read this checkout's origin at {own}, so {target} cannot be validated"
    theirs = git_origin(target)
    if theirs != mine:
        return f"MESH_REPO_DIR={target} has origin {theirs or '(none)'}, expected {mine}"
    return ""
