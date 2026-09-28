"""Classify one PreToolUse hook reply from its RAW stdout bytes (C6, contract v5).

usage: hook_verdict.py <stdout-file> <hook-exit-code>   prints: deny | allow | error:<why>

Reads the file as bytes, so nothing is stripped before validation (v4 captured stdout with
shell command substitution, which silently drops NUL bytes: P1-DONE-C6-MALFORMED-OUTPUT-ACCEPTED).
  allow = exit 0 and zero bytes of output (the hook's "no decision" path), or exactly one
          well-formed object below whose permissionDecision is "allow"
  deny  = exit 0 and the whole output is exactly one JSON object
          {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", ...}}
Anything else is an error, never a pass.
"""
import json
import sys


def classify(raw: bytes, rc: int) -> str:
    if rc != 0:
        return f"error:exit{rc}"
    if raw == b"":
        return "allow"
    if b"\x00" in raw:
        return "error:nul"
    try:
        obj = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "error:not-one-json-object"
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
