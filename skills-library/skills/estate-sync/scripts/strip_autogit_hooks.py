#!/usr/bin/env python3
"""Remove autogit hooks from a Claude Code settings.json (RA-7802).

autogit commits and pushes from every Claude session. It was disarmed on the
MacBook under RA-7038 as a hazard, but nothing removed it anywhere else: on
28/09/2026 the Mac Mini still ran it on three hook events, and it was the Mini's
autogit, not the mesh runner, that committed RA-7794. bootstrap.sh runs this on
every machine so the removal cannot drift again.

Only hooks that RUN autogit, in their command or args, are removed: the same
test check-enforcement-wiring.py reports on. A hook whose name merely contains
the word, such as check-autogit-status, is left alone. A gate sharing an entry with autogit
stays; an entry is dropped only when nothing but autogit was in it. Every other
setting is left exactly as it was. A backup is written before any change.
Exit 0 always: a machine without the file, or with unreadable JSON, is left alone.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import time
from pathlib import Path


AUTOGIT = re.compile(r"""(?:^|[\s;&|({/"'`])autogit(?=$|[\s;&|)}"'`])""")  # autogit run as a program, quoted or not; not a word in a name


def _is_autogit(hook: dict) -> bool:
    """Same test as check-enforcement-wiring.py. `check-autogit-status` is not autogit."""
    return bool(AUTOGIT.search(" ".join([str(hook.get("command", "")), *map(str, hook.get("args", []) or [])])))


def strip(settings: Path) -> int:
    """Remove autogit hooks; return how many hooks were removed."""
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return 0
    removed = 0
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            continue
        kept = []
        for e in entries:
            inner = e.get("hooks") if isinstance(e, dict) else None
            if not isinstance(inner, list):
                kept.append(e)
                continue
            left = [h for h in inner if not (isinstance(h, dict) and _is_autogit(h))]
            removed += len(inner) - len(left)
            if left or not inner:
                kept.append({**e, "hooks": left} if len(left) != len(inner) else e)
        hooks[event] = kept
    if removed:
        shutil.copy2(settings, settings.with_name(settings.name + time.strftime(".bak-autogit-%Y%m%d%H%M%S")))
        settings.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return removed


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".claude" / "settings.json"
    n = strip(path)
    print(f"removed {n} autogit hook{'' if n == 1 else 's'} from {path}" if n
          else f"no autogit hooks in {path}")
