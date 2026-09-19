"""Constrain privileged Git to repository data, never candidate-supplied programs."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

_GIT = shutil.which("git")
_GIT = str(Path(_GIT).resolve()) if _GIT else ""
_SAFE_CONFIG = {
    "core.repositoryformatversion", "core.filemode", "core.bare", "core.logallrefupdates",
    "core.symlinks", "core.ignorecase", "core.precomposeunicode", "core.protectntfs",
    "core.protecthfs", "user.name", "user.email", "extensions.objectformat",
}
_OVERRIDES = (
    "core.hooksPath=/dev/null", "core.fsmonitor=false", "credential.helper=",
    "commit.gpgSign=false", "tag.gpgSign=false", "gc.auto=0", "maintenance.auto=false",
    "protocol.ext.allow=never",
)


def _configs(cwd: Path) -> list[Path]:
    marker = cwd / ".git"
    if marker.is_symlink():
        raise RuntimeError("Privileged Git refuses linked repository metadata")
    if marker.is_dir():
        return [marker / "config"]
    if not marker.exists():
        return []
    # A legitimate Git worktree has a reciprocal gitdir backlink and a common
    # repository directory. A candidate cannot redirect host Git to another repo.
    try:
        pointer = marker.read_text(encoding="utf-8").strip()
        if not pointer.startswith("gitdir: "):
            raise ValueError
        metadata = (cwd / pointer[8:]).resolve()
        backlink = (metadata / "gitdir").read_text(encoding="utf-8").strip()
        if (metadata / backlink).resolve() != marker.resolve():
            raise ValueError
        common = (metadata / (metadata / "commondir").read_text(encoding="utf-8").strip()).resolve()
        if metadata.parent != common / "worktrees":
            raise ValueError
        return [common / "config", metadata / "config.worktree"]
    except (OSError, ValueError):
        raise RuntimeError("Privileged Git refuses unverified worktree metadata") from None


def prepare_git(cwd: str, args, env: dict | None = None) -> tuple[list[str], dict[str, str]]:
    """Return a trusted command and process-only settings; never edit user config."""
    if not _GIT:
        raise RuntimeError("Trusted Git executable is unavailable")
    source = os.environ if env is None else env
    child = {key: value for key, value in source.items() if not key.upper().startswith("GIT_")}
    child.pop("SSH_ASKPASS", None)
    root = Path(cwd).resolve()
    child.update({
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0", "GIT_ALLOW_PROTOCOL": "https:http:file",
        "GIT_CEILING_DIRECTORIES": str(root.parent),
        "GIT_AUTHOR_NAME": source.get("GIT_AUTHOR_NAME", "Pi Mission Control"),
        "GIT_AUTHOR_EMAIL": source.get("GIT_AUTHOR_EMAIL", "mission-control@localhost"),
        "GIT_COMMITTER_NAME": source.get("GIT_COMMITTER_NAME", "Pi Mission Control"),
        "GIT_COMMITTER_EMAIL": source.get("GIT_COMMITTER_EMAIL", "mission-control@localhost"),
    })
    _authorization_header(env, child)
    command = [_GIT]
    for option in _OVERRIDES:
        command.extend(("-c", option))
    _validate_configs(root, command, child)
    return [*command, *args], child


def _authorization_header(env, child):
    # Only the caller's explicit GitHub authorization header is permitted.
    # Ambient command overrides and arbitrary extra config never cross this boundary.
    if env is not None:
        try:
            count = min(int(env.get("GIT_CONFIG_COUNT", "0")), 64)
        except ValueError:
            count = 0
        for index in range(count):
            key = env.get(f"GIT_CONFIG_KEY_{index}", "")
            value = env.get(f"GIT_CONFIG_VALUE_{index}", "")
            if key == "http.https://github.com/.extraheader" and re.fullmatch(r"AUTHORIZATION: basic [A-Za-z0-9+/]+=*", value):
                child.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": key, "GIT_CONFIG_VALUE_0": value})
                break


def _validate_configs(root, command, child):
    for config in _configs(root):
        if not config.exists():
            continue
        if config.is_symlink():
            raise RuntimeError("Privileged Git refuses linked configuration")
        try:
            result = subprocess.run(
                [*command, "config", "--file", str(config), "--no-includes", "--name-only", "--null", "--list"],
                cwd=str(root), env=child, capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except (OSError, subprocess.SubprocessError):
            raise RuntimeError("Repository Git configuration could not be verified") from None
        if result.returncode:
            raise RuntimeError("Repository Git configuration could not be verified")
        for key in result.stdout.split("\0"):
            key = key.strip().lower()
            if key and key not in _SAFE_CONFIG and not re.fullmatch(r"(?:remote\..+\.(?:url|fetch)|branch\..+\.(?:remote|merge))", key):
                # Never include configuration values, which can hold credentials.
                raise RuntimeError("Repository Git configuration is outside the privileged allowlist")
