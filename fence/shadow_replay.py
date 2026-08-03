#!/usr/bin/env python3
"""shadow_replay.py — replay real workflow commands through the fence, offline.

WHY THIS EXISTS, STATED PLAINLY: the scheduled workflows run in GitHub Actions.
They never pass through the PreToolUse hook, which only sees this machine's Claude
Code tool calls. So "run the workflows in shadow" cannot produce hook data — the
two never meet.

What this does instead is real evidence, not a simulation: it extracts every shell
command from the scheduled workflow YAMLs and classifies each one exactly as the
fence would if an agent had typed it locally. That answers the actual question —
which of our routine automated work would the fence stop?

Output: shadow-replay.csv + a summary split into REAL GAP vs LEGITIMATE WORK.
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

WF = Path(r"D:\Pi-Dev-Ops\.github\workflows")
FENCE = Path(r"D:\Pi-Dev-Ops\fence\pretooluse_fence.py")
SANDBOX = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "_replay"
OUT = Path(r"D:\Pi-Dev-Ops\fence\shadow-replay.csv")


def scheduled_workflows() -> list[Path]:
    out = []
    for f in sorted(WF.glob("*.yml")):
        t = f.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^\s*schedule:", t, re.M):
            out.append(f)
    return out


def commands(text: str) -> list[str]:
    """Every line under a `run:` block. Crude on purpose — over-collecting is fine,
    under-collecting would hide a command the fence would have stopped."""
    cmds, in_run, indent = [], False, 0
    for line in text.splitlines():
        m = re.match(r"^(\s*)-?\s*run:\s*(\|.*)?$", line)
        if m:
            in_run, indent = True, len(m.group(1))
            continue
        m1 = re.match(r"^(\s*)-?\s*run:\s*(\S.*)$", line)
        if m1:
            cmds.append(m1.group(2).strip())
            in_run = False
            continue
        if in_run:
            if line.strip() and (len(line) - len(line.lstrip())) <= indent:
                in_run = False
            elif line.strip() and not line.strip().startswith("#"):
                cmds.append(line.strip())
    return cmds


def classify(cmd: str) -> tuple[str, str]:
    """Run the real fence in enforce mode against a synthetic Bash tool call."""
    payload = json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": cmd},
                          "cwd": str(SANDBOX)})
    r = subprocess.run([sys.executable, str(FENCE)], input=payload, text=True,
                       capture_output=True,
                       env={**dict(__import__("os").environ),
                            "CLAUDE_FENCE_DIR": str(SANDBOX),
                            "CLAUDE_HARD_STOP": str(SANDBOX / "HARD_STOP")})
    if r.returncode == 0:
        return "ALLOW", ""
    m = re.search(r"\[FENCE\] (?:BLOCKED \((\S+?)\)|\*\*\* HARD STOP)", r.stderr)
    return ("BLOCK", m.group(1) if m and m.group(1) else "self-modification")


def main() -> int:
    SANDBOX.mkdir(parents=True, exist_ok=True)
    fj = json.loads((Path(r"D:\Pi-Dev-Ops\fence\fence.json")).read_text(encoding="utf-8"))
    fj["mode"] = "enforce"          # classify as if enforcing, without enforcing anything
    (SANDBOX / "fence.json").write_text(json.dumps(fj), encoding="utf-8")

    rows = []
    for wf in scheduled_workflows():
        for cmd in commands(wf.read_text(encoding="utf-8", errors="replace")):
            if not cmd or cmd.startswith(("uses:", "with:", "env:", "name:")):
                continue
            (SANDBOX / "HARD_STOP").unlink(missing_ok=True)
            (SANDBOX / "denials.jsonl").unlink(missing_ok=True)
            verdict, rule = classify(cmd)
            rows.append({"workflow": wf.name, "verdict": verdict,
                         "rule": rule, "command": cmd[:220]})

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["workflow", "verdict", "rule", "command"])
        w.writeheader()
        w.writerows(rows)

    blocked = [r for r in rows if r["verdict"] == "BLOCK"]
    print(f"scheduled workflows replayed : {len(scheduled_workflows())}")
    print(f"commands classified          : {len(rows)}")
    print(f"WOULD BE BLOCKED             : {len(blocked)}")
    print(f"would pass                   : {len(rows) - len(blocked)}")
    if blocked:
        print("\n-- every command the fence would have stopped --")
        for r in blocked:
            print(f"  [{r['rule']:<22}] {r['workflow'][:30]:<30} {r['command'][:80]}")
    print(f"\nwritten: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
