#!/usr/bin/env python3
"""Install Claude and global Git PR interlocks without discarding prior hooks."""

from __future__ import annotations

import json
import os
import secrets
import shlex
import stat
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
SETTINGS = HOME / ".claude" / "settings.json"
GATE = HOME / ".claude" / "skills" / "pr-release-gate" / "scripts" / "pr_release_gate.py"
DEFAULT_HOOKS = HOME / ".config" / "git" / "hooks"
KEY = HOME / ".local" / "state" / "pr-release-gate" / "attestation.key"
MARKER = "# pr-release-gate-managed"


def install_key() -> None:
    KEY.parent.mkdir(parents=True, exist_ok=True)
    if not KEY.exists():
        fd = os.open(KEY, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(secrets.token_bytes(32))


def hook_command() -> str:
    """The PreToolUse command string.

    GATE is quoted because a home directory may contain spaces. Unquoted, an installed
    hook on such a host shatters on the first space -- `C:\\Users\\Disaster Recovery 4\\...`
    reached python as `C:\\Users\\Disaster`, which resolved against the process CWD and
    failed with "can't open file". The hook then returned non-zero on EVERY Bash call,
    so it blocked all shell use while adjudicating no push at all: a control that fails
    closed on everything is indistinguishable from a control that works, until you look.
    Observed 2026-08-16 on PHILL_DESKTOP. Line 117 of this file already quoted GATE for
    the `verify` command; this one did not.

    On Windows `/usr/bin/env python3` also resolves to the WindowsApps stub, so the
    interpreter is chosen per-platform rather than assumed POSIX.
    """
    if os.name == "nt":
        return f'"{sys.executable}" "{GATE}" hook'
    return f'/usr/bin/env python3 "{GATE}" hook'


def command_argv(command: str) -> list[str]:
    """A hook command as the shell would split it, so quoted and unquoted GATE compare equal.

    An entry installed before GATE was quoted (`... python3 /Users/.../pr_release_gate.py
    hook`) did not string-match hook_command(), so a re-install appended a second entry
    and the gate ran twice per Bash call (RA-7791)."""
    try:
        return [token.strip('"') for token in shlex.split(command, posix=os.name != "nt")]
    except ValueError:
        return []


def install_claude_hook() -> None:
    data = json.loads(SETTINGS.read_text(encoding="utf-8")) if SETTINGS.exists() else {}
    command = hook_command()
    entry = {"matcher": "Bash", "hooks": [{"type": "command", "command": command}]}
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    wanted = command_argv(command)
    if not any(any(command_argv(str(h.get("command", ""))) == wanted for h in item.get("hooks", []))
               for item in pre if item.get("matcher") == "Bash"):
        pre.append(entry)
    # ensure_ascii=False: the default rewrote every "—" in the user's settings as "\u2014".
    SETTINGS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def configured_hooks_path() -> Path | None:
    result = subprocess.run(
        ["git", "config", "--global", "--get", "core.hooksPath"],
        text=True, capture_output=True, check=False,
    )
    if result.returncode or not result.stdout.strip():
        return None
    path = Path(result.stdout.strip()).expanduser()
    if not path.is_absolute():
        raise RuntimeError(
            "relative global core.hooksPath cannot be safely wrapped; configure an absolute path"
        )
    return path


def active_hooks_path() -> Path:
    return configured_hooks_path() or DEFAULT_HOOKS


def preserve_existing_hook(pre_push: Path, previous: Path) -> None:
    if not pre_push.exists():
        return
    content = pre_push.read_text(errors="replace")
    if MARKER in content or "pr_release_gate.py" in content:
        return
    if not previous.exists():
        previous.write_bytes(pre_push.read_bytes())
        previous.chmod(pre_push.stat().st_mode)


def render_hook(previous: Path) -> str:
    return f'''#!/bin/sh
{MARKER}
set -eu

payload="$(mktemp "${{TMPDIR:-/tmp}}/pr-release-gate.XXXXXX")"
trap 'rm -f "$payload"' EXIT HUP INT TERM
cat > "$payload"

if [ -x "{previous}" ]; then
  "{previous}" "$@" < "$payload"
fi

repo_hook="$(git rev-parse --git-dir 2>/dev/null)/hooks/pre-push"
if [ -x "$repo_hook" ] && [ "$repo_hook" != "$0" ]; then
  "$repo_hook" "$@" < "$payload"
fi

# BRANCH-DELETION EXEMPTION, mirrored from pr_release_gate.py.
# Deleting a merged branch publishes nothing, and the Python gate exempts it
# (DELETION_PROTECTED_REFS / DELETION_DISQUALIFYING_FLAGS). But that exemption
# parses a COMMAND LINE, and a pre-push hook never sees one -- it gets refs on
# stdin. So the gate's own exemption was unreachable from here and every
# post-merge `git push --delete` was refused for a missing receipt, which is
# what happened cleaning up a merged branch on 25/08/2026.
#
# Pointing this hook at the `hook` subcommand does NOT fix that: hook() does
# json.load(sys.stdin) expecting Claude Code's tool_input schema, so git's ref
# lines would raise and block EVERY push. The exemption has to be mirrored here,
# against the refs this hook actually receives.
#
# Of the refs this loop gates -- refs/heads/* only -- exactly one is waved
# through: a deletion (all-zero local sha) of a non-protected branch. A real
# update, a protected branch, or a mixed push carrying both a deletion and an
# update all still set needs_gate and demand the receipt.
#
# PRE-EXISTING GAP, deliberately not closed here: refs outside refs/heads/*
# never set needs_gate, so a tag-only push has always bypassed this hook. That
# predates this exemption -- the original loop was
#   case "$remote_ref" in refs/heads/*) needs_gate=1 ;; esac
# -- and closing it would gate every tag push in every repo on this machine,
# which is a separate decision from post-merge branch cleanup. Named here so the
# next reader does not mistake this loop for tag coverage it has never had.
#
# MESH RUNNER EXEMPTION, founder ruling 28/09/2026 (RA-7789). A mesh runner ships each
# run by pushing its own `mesh/<host>/<ticket>-<run>` work branch, unattended. That push
# is not a release: it cannot merge anything, and opening, readying or merging a PR from
# it still runs through `pr_release_gate.py hook`, which this does not touch. Without it
# every Mac node refused its own work ("missing exact-SHA PR release receipt"), and the
# node still on older runner code reported those unshipped runs as done.
# Deliberately narrow: only refs/heads/mesh/*, only a new branch or a fast-forward (a
# history rewrite, or a remote tip this clone cannot see, still needs a receipt), and a
# push that also touches any other branch is gated whole. It announces on stderr.
needs_gate=0
mesh_waived=0
other_ref=0
while read local_ref local_sha remote_ref remote_sha; do
  case "$remote_ref" in
    refs/heads/*) ;;
    *) continue ;;
  esac
  case "$remote_ref" in
    refs/heads/mesh/*) ;;
    *) other_ref=1 ;;
  esac
  if [ "$local_sha" = "0000000000000000000000000000000000000000" ]; then
    # Last path component, as pr_release_gate.py reads it: `foo/main` is protected too.
    case "${{remote_ref##*/}}" in
      main|master|develop|trunk|release|HEAD) needs_gate=1 ;;
      *) ;;
    esac
  else
    case "$remote_ref" in
      refs/heads/mesh/*)
        if [ "$remote_sha" = "0000000000000000000000000000000000000000" ] \\
           || git merge-base --is-ancestor "$remote_sha" "$local_sha" 2>/dev/null; then
          mesh_waived=1
        else
          needs_gate=1
        fi
        ;;
      *) needs_gate=1 ;;
    esac
  fi
done < "$payload"
# A mesh waiver never carries another branch with it, not even a deletion.
[ "$mesh_waived" -eq 1 ] && [ "$other_ref" -eq 1 ] && needs_gate=1
if [ "$needs_gate" -eq 0 ]; then
  [ "$mesh_waived" -eq 1 ] && echo "pr-release-gate: mesh runner branch, gate skipped (RA-7789)" >&2
  exit 0
fi

# Throwaway remotes under the OS temp directory are not releases. This hook is global -- it
# runs for every push to refs/heads/* in EVERY repository on the machine -- so without this
# exemption no test suite anywhere can exercise a push path. The estate-sync suite sat at
# 8/12 for exactly this reason, with its own control test red and t1 passing vacuously
# because nothing pushed at all. A gate that silently breaks unrelated test suites teaches
# people to distrust test results, which costs more than it protects.
#
# Deliberately narrow: LOCAL filesystem paths under a temp root only. A network remote is
# never exempt regardless of what its path looks like, so this cannot be used to slip a real
# release past the gate -- reaching a shared remote still requires a receipt.
remote_url="${{2:-}}"
case "$remote_url" in
  *://*|*@*:*) ;;                                  # scheme or scp-style: never exempt
  *)
    case "$remote_url" in
      "${{TMPDIR:-/tmp}}"*|/tmp/*|/private/tmp/*|/var/folders/*|/private/var/folders/*)
        echo "pr-release-gate: temp remote, gate skipped ($remote_url)" >&2
        exit 0
        ;;
    esac
    ;;
esac

[ "${{PR_RELEASE_GATE_HUMAN_OVERRIDE:-0}}" = "1" ] && exit 0
/usr/bin/env python3 "{GATE}" verify
'''


def install_git_hook() -> None:
    hooks = active_hooks_path()
    hooks.mkdir(parents=True, exist_ok=True)
    pre_push = hooks / "pre-push"
    previous = hooks / "pre-push.before-pr-release-gate"
    preserve_existing_hook(pre_push, previous)
    pre_push.write_text(render_hook(previous))
    pre_push.chmod(pre_push.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if configured_hooks_path() is None:
        subprocess.run(["git", "config", "--global", "core.hooksPath", str(hooks)], check=True)


def main() -> None:
    if not GATE.exists():
        raise SystemExit(f"missing gate: {GATE}")
    install_key()
    install_claude_hook()
    install_git_hook()
    print("pr-release-gate: Claude and global Git interlocks installed")


if __name__ == "__main__":
    main()
