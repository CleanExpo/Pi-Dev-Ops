"""Classify one PreToolUse hook reply from its RAW stdout bytes (C6, contract v6).

usage: hook_verdict.py <stdout-file> <hook-exit-code>   prints: deny | allow | error:<why>

Reads the file as bytes, so nothing is stripped before validation (v4 captured stdout with
shell command substitution, which silently drops NUL bytes: P1-DONE-C6-MALFORMED-OUTPUT-ACCEPTED).
The reply must be strict JSON twice over (v5 accepted NaN/Infinity, which Python's json module
allows and JSON.parse rejects: P1-DONE-C6-NONSTANDARD-JSON-ACCEPTED):
  1. Python json with the non-standard constants NaN, Infinity, -Infinity refused, and
  2. Node's JSON.parse - the parser family Claude Code itself uses - on the same bytes.
  allow = exit 0 and zero bytes of output (the hook's "no decision" path), or exactly one
          well-formed object below whose permissionDecision is "allow"
  deny  = exit 0 and the whole output is exactly one JSON object
          {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", ...}}
Anything else, including a missing node binary, is an error, never a pass.
"""
import json
import subprocess
import sys

NODE_PARSE = (
    "const b=require('fs').readFileSync(0);"
    "const s=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(b);"
    "JSON.parse(s);"
)


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-standard JSON constant {name}")


def _node_accepts(raw: bytes) -> bool:
    try:
        r = subprocess.run(["node", "-e", NODE_PARSE], input=raw, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def classify(raw: bytes, rc: int) -> str:
    if rc != 0:
        return f"error:exit{rc}"
    if raw == b"":
        return "allow"
    if b"\x00" in raw:
        return "error:nul"
    try:
        obj = json.loads(raw.decode("utf-8", errors="strict"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError):
        return "error:not-one-json-object"
    if not _node_accepts(raw):
        return "error:json-parse-rejects"
    if not isinstance(obj, dict) or set(obj) != {"hookSpecificOutput"}:
        return "error:shape"
    hso = obj["hookSpecificOutput"]
    if not isinstance(hso, dict) or hso.get("hookEventName") != "PreToolUse":
        return "error:shape"
    decision = hso.get("permissionDecision")
    return decision if decision in ("deny", "allow") else "error:decision"


def main() -> None:
    with open(sys.argv[1], "rb") as f:
        print(classify(f.read(), int(sys.argv[2])))


if __name__ == "__main__":
    main()
