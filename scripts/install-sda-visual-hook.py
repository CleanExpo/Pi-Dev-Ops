#!/usr/bin/env python3
"""Fail-safe opt-in installation of SDA advisory routing in a separate file.

Never rewrites any pre-existing Claude settings file. If the selected target
exists with unrelated hooks, stop and leave it byte-for-byte unchanged. The
new file is made with an atomic hardlink of a fully flushed same-dir temp
file; concurrent writers cannot be overwritten even without shared locks.
"""
import argparse
import json
import os
import shlex
import tempfile
from pathlib import Path

COMMAND = "/usr/bin/env python3 $HOME/.claude/hooks/sda_visual_router.py"


def _router_registration(events, hook_file):
    """Return match, conflict or absent by resolved actual script path."""
    if not isinstance(events, list):
        return "absent"
    target = hook_file.resolve(strict=True)
    for event in events:
        hooks = event.get("hooks", []) if isinstance(event, dict) else []
        if not isinstance(hooks, list):
            continue
        for hook in hooks:
            command = hook.get("command") if isinstance(hook, dict) else None
            if not isinstance(command, str):
                continue
            try:
                argv = shlex.split(command)
            except ValueError:
                continue
            if (len(argv) == 3 and argv[:2] == ["/usr/bin/env", "python3"]):
                script = argv[2]
            elif len(argv) == 2 and Path(argv[0]).name.startswith("python3"):
                script = argv[1]
            else:
                continue
            resolved = Path(os.path.expandvars(os.path.expanduser(script))).resolve()
            if resolved == target:
                return "match"
            if resolved.name in (target.name, "sda_visual_router.py"):
                return "conflict"
    return "absent"


def _existing_parent_registration(settings, hook_file):
    """Do not create a project hook when its user already registered SDA."""
    if settings.name != "settings.local.json":
        return None
    candidates = (Path.home() / ".claude/settings.json",
                  settings.with_name("settings.json"))
    for primary in dict.fromkeys(candidates):
        if not primary.is_file():
            continue
        data = json.loads(primary.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        hooks = data.get("hooks") or {}
        events = hooks.get("UserPromptSubmit", []) if isinstance(hooks, dict) else []
        status = _router_registration(events, hook_file)
        if status == "match":
            return data
        if status == "conflict":
            raise FileExistsError(
                "Existing SDA router points to different file; no duplicate installed"
            )
    return None


def prepare(settings, hook_file):
    if not hook_file.is_file():
        raise FileNotFoundError("SDA routing hook missing: " + str(hook_file))
    # Only execute the exact router file we verified before registration.
    hook_command = "/usr/bin/env python3 " + shlex.quote(str(hook_file.resolve(strict=True)))
    # Deduplicate against both user-wide and project-local hook registrations.
    existing = _existing_parent_registration(settings, hook_file)
    if existing is not None:
        return existing, False
    if settings.exists():
        current = json.loads(settings.read_text(encoding="utf-8"))
        if not isinstance(current, dict):
            raise ValueError("settings must be an object")
        hooks = current.get("hooks", {})
        entries = hooks.get("UserPromptSubmit", []) if isinstance(hooks, dict) else []
        if _router_registration(entries, hook_file) == "match":
            return current, False
        raise FileExistsError(
            "Refusing to replace existing settings: " + str(settings) +
            "; use the established authorised settings editor to append the hook"
        )
    return {"hooks": {"UserPromptSubmit": [
        {"hooks": [{"type": "command", "command": hook_command, "timeout": 5}]}
    ]}}, True


def install(settings, hook_file):
    data, changed = prepare(settings, hook_file)
    if not changed:
        return "ALREADY INSTALLED"
    settings.parent.mkdir(parents=True, exist_ok=True)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=settings.parent,
            prefix=".sda-hook-", suffix=".tmp", delete=False
        ) as temp:
            pending = Path(temp.name)
            json.dump(data, temp, indent=2)
            temp.write("\n")
            temp.flush()
            os.fsync(temp.fileno())
        # Atomic create ONLY when destination does not exist, no TOCTOU
        # check-then-replace race. Works even if another writer ignores us.
        try:
            os.link(pending, settings)
        except FileExistsError as exc:
            raise FileExistsError(
                "Settings created concurrently; no existing file was overwritten"
            ) from exc
        return "INSTALLED"
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--settings", type=Path,
        default=Path.home() / ".claude/settings.json",
        help="loaded user settings file; existing files are NEVER overwritten"
    )
    parser.add_argument(
        "--hook", type=Path,
        default=Path.home() / ".claude/hooks/sda_visual_router.py"
    )
    parser.add_argument("--install", action="store_true", help="create only if absent")
    args = parser.parse_args()
    data, changed = prepare(args.settings, args.hook)
    if args.install:
        print(install(args.settings, args.hook))
    else:
        print("NEEDS INSTALL" if changed else "ALREADY INSTALLED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
