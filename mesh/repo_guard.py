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

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

_SCP_REMOTE = re.compile(r"(?:[^/@]+@)?([^:/\s]+):(.+)")
_HOSTED_SCHEMES = {"http", "https", "ssh", "git"}


def git_origin(repo: Path) -> str:
    """The stored local `origin` URL, or "" when there is none to read.

    Reads `git config --local --get remote.origin.url`, not `git remote
    get-url`. get-url applies insteadOf, which can rewrite the spelling or
    inject a credential before the guard sees it (UNI-2644).
    """
    out = subprocess.run(
        ["git", "-C", str(repo), "config", "--local", "--get", "remote.origin.url"],
        capture_output=True, text=True, check=False,
    )
    if getattr(out, "returncode", 1) != 0:
        return ""
    return (getattr(out, "stdout", "") or "").strip()


def canonical_origin(value: str) -> str:
    """Same hosted repository, same identity — protocol and `.git` do not count.

    http(s), ssh://, and git@host:path collapse to host/owner/repo. file://
    and other local forms stay verbatim, so `.git` remains significant there.
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    return _hosted_identity(raw) or raw


def _strip_git_suffix(path: str) -> str:
    """Drop a trailing `.git` after trimming slashes. Local file paths skip this."""
    path = path.strip("/")
    return path[:-4] if path.endswith(".git") else path


def _hosted_identity(value: str) -> str:
    """host/owner/repo for a hosted remote, else '' so the raw spelling is kept."""
    return _scp_identity(value) or _url_identity(value)


def _scp_identity(value: str) -> str:
    """git@host:path / host:owner/repo → host/owner/repo. Else ''."""
    if "://" in value:
        return ""
    match = _SCP_REMOTE.fullmatch(value)
    if not match:
        return ""
    host, path = match.group(1).lower(), match.group(2)
    if "@" not in value and "/" not in path:
        return ""
    path = _strip_git_suffix(path)
    return f"{host}/{path}" if path else ""


def _url_identity(value: str) -> str:
    """http(s)/ssh/git URL → host/owner/repo. file:// and unknowns stay ''."""
    parsed = urlsplit(value)
    if parsed.scheme not in _HOSTED_SCHEMES or not parsed.hostname:
        return ""
    path = _strip_git_suffix(unquote(parsed.path))
    return f"{parsed.hostname.lower()}/{path}" if path else ""


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
    if canonical_origin(theirs) != canonical_origin(mine):
        return f"MESH_REPO_DIR={target} has origin {theirs or '(none)'}, expected {mine}"
    return ""
