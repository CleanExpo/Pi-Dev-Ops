#!/usr/bin/env python3
"""Controls for check_freeze.py hook mode. Each runs the real script under a temp HOME."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).with_name("check_freeze.py")
SESSION = "test-session"


def run(home: Path, file_path: str) -> str:
    payload = {"session_id": SESSION, "cwd": str(home),
               "tool_input": {"file_path": file_path}}
    out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                         capture_output=True, text=True, env={**os.environ, "HOME": str(home)})
    body = json.loads(out.stdout or "{}")
    return body.get("hookSpecificOutput", {}).get("permissionDecision", "allow")


def main() -> int:
    fails = []
    with tempfile.TemporaryDirectory() as raw:
        home = Path(raw).resolve()
        safe = home / "safe"
        safe.mkdir()
        state = home / ".local/state/gs/freeze" / f"{SESSION}.txt"
        state.parent.mkdir(parents=True)
        cases = []
        state.write_text(f"{safe}\n")
        cases.append(("inside the boundary", run(home, str(safe / "a.txt")), "allow"))
        cases.append(("outside the boundary", run(home, str(home / "b.txt")), "deny"))
        cases.append(("`..` escape", run(home, str(safe / ".." / "c.txt")), "deny"))
        state.write_text("")
        cases.append(("empty state file (corrupt)", run(home, str(home / "d.txt")), "deny"))
        state.unlink()
        cases.append(("no freeze set", run(home, str(home / "e.txt")), "allow"))
        for label, got, want in cases:
            ok = got == want
            print(f"{'ok  ' if ok else 'FAIL'} {want:5} {label}" + ("" if ok else f" -> {got}"))
            if not ok:
                fails.append(label)
    print(f"\n{len(cases) - len(fails)}/{len(cases)} controls held")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
