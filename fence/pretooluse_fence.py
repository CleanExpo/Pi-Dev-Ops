#!/usr/bin/env python3
"""pretooluse_fence.py — the fence. PreToolUse classifier for Claude Code.

Stops exactly two classes of action: SPENDING MONEY and TOUCHING PRODUCTION.
Everything else passes silently. See docs/orchestrator/01-decision-rights.md.

R3 — A DENIED ACTION IS TERMINAL. The agent may not retry it, may not reach the
same outcome by another route, may not weaken or disable the fence, and may not
escalate its own permissions. A second attempt trips HARD_STOP and freezes the
agent until a human releases it.

FAIL-CLOSED BY CONSTRUCTION. The Claude Code hook mechanism fails *open* — a
crashed hook or invalid JSON on exit 0 lets the tool call proceed. So this script
never relies on the harness: every path that is not a proven ALLOW exits 2, the
only exit code that blocks regardless of JSON validity.

Contract (verified against code.claude.com/docs/en/hooks, 2026-08-01):
  stdin  : {"tool_name":..., "tool_input":{...}, "cwd":...}
  block  : exit 2, reason on stderr (stdout JSON also emitted, belt-and-braces)
  allow  : exit 0, no output

Scope honesty: a GUARDRAIL, not a sandbox. It stops well-intentioned mistakes and
makes a determined bypass loud and terminal. It cannot stop a hostile process with
filesystem access — which is why the fence's own files are terminal-on-touch.

Emergency bypass: CLAUDE_FENCE_BYPASS=1 (founder-only; every use is logged).
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FENCE_DIR = Path(os.environ.get("CLAUDE_FENCE_DIR", Path.home() / ".claude" / "fence"))
FENCE_FILE = FENCE_DIR / "fence.json"
DENIALS = FENCE_DIR / "denials.jsonl"
AUDIT = FENCE_DIR / "fence.jsonl"
SHADOW = FENCE_DIR / "shadow.jsonl"
INCIDENTS = FENCE_DIR / "incidents"
HARD_STOP = Path(os.environ.get("CLAUDE_HARD_STOP", Path.home() / ".claude" / "HARD_STOP"))


def _read_mode() -> str:
    """Best-effort, at import time, so even the crash handler knows whether it is
    allowed to block. Unknown => 'enforce' (fail closed on the safety question)."""
    try:
        m = json.loads(FENCE_FILE.read_text(encoding="utf-8")).get("mode", "enforce")
        return "shadow" if str(m).lower() == "shadow" else "enforce"
    except Exception:
        return "enforce"


MODE = _read_mode()
SHADOWING = MODE == "shadow"


# ---------------------------------------------------------------- plumbing

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(path: Path, row: dict) -> None:
    """Append-only audit. Never allowed to break the decision path."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        row.setdefault("ts", _now())
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def fp(*parts: str) -> str:
    norm = re.sub(r"\s+", " ", "|".join(p for p in parts if p)).strip().lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def load_denials() -> list[dict]:
    try:
        if not DENIALS.exists():
            return []
        rows = []
        for line in DENIALS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if not r.get("cleared_by_founder"):
                rows.append(r)
        return rows
    except Exception:
        return []


# ---------------------------------------------------------------- outcomes

def write_incident(title: str, attempted: str, rule_hit: str,
                   why_terminal: str, options: list[str]) -> Path | None:
    """Plain English. A human reads this cold, possibly on a phone, possibly angry."""
    body = (
        f"FENCE INCIDENT — {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}\n"
        f"{'=' * 60}\n\n"
        f"{title}\n\n"
        f"WHAT WAS ATTEMPTED\n  {attempted}\n\n"
        f"WHICH RULE WAS HIT\n  {rule_hit}\n\n"
        f"WHAT MADE IT TERMINAL\n  {why_terminal}\n\n"
        f"THE AGENT IS NOW FROZEN.\n"
        f"  Nothing else will run until a person releases it. This is deliberate.\n\n"
        f"YOUR OPTIONS\n"
        + "".join(f"  {i}. {o}\n" for i, o in enumerate(options, 1))
        + f"\nRelease is a desktop action. It cannot be done from a phone or a chat message.\n"
    )
    try:
        INCIDENTS.mkdir(parents=True, exist_ok=True)
        p = INCIDENTS / f"incident-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.txt"
        p.write_text(body, encoding="utf-8")
        return p
    except Exception:
        return None


def shadow_record(would: str, rule: str, tool: str, target: str, reason: str) -> None:
    """Shadow mode: record what WOULD have happened, then get out of the way."""
    _log(SHADOW, {"would": would, "rule": rule, "tool": tool,
                  "target": target[:400], "reason": reason})
    sys.exit(0)


def trip_hard_stop(title: str, attempted: str, rule_hit: str,
                   why_terminal: str, options: list[str], tool: str, target: str) -> None:
    """Freeze the agent. Writes HARD_STOP + a plain-English incident note."""
    if SHADOWING:
        shadow_record("FREEZE", rule_hit, tool, target, title)
    note = write_incident(title, attempted, rule_hit, why_terminal, options)
    try:
        HARD_STOP.parent.mkdir(parents=True, exist_ok=True)
        HARD_STOP.write_text(
            f"Frozen {_now()} by the fence.\n{title}\n"
            f"Incident: {note or '(note could not be written)'}\n"
            f"Delete this file to release the agent.\n", encoding="utf-8")
    except Exception:
        pass
    _log(AUDIT, {"decision": "HARD_STOP", "rule": rule_hit, "tool": tool,
                 "target": target[:400], "incident": str(note)})
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": f"{title} The agent is frozen pending human release.",
    }}))
    sys.stderr.write(
        f"\n[FENCE] *** HARD STOP ***\n{title}\n"
        f"Incident note: {note}\n"
        f"The agent is frozen. A person must delete {HARD_STOP} to release it.\n"
        f"Do not attempt further actions.\n")
    sys.exit(2)


def block(reason: str, rule: str, tool: str, target: str,
          resource: str = "") -> None:
    """Deny, and make the denial terminal by recording both fingerprints."""
    if SHADOWING:
        # No denial recorded: a shadow run must not seed terminal denials that
        # would freeze the first real session the moment enforcement is switched on.
        shadow_record("BLOCK", rule, tool, target, reason)
    _log(DENIALS, {
        "action_fp": fp(tool, target),
        "target_fp": fp(resource) if resource else "",
        "tool": tool, "target": target[:400], "resource": resource,
        "rule": rule, "reason": reason, "cleared_by_founder": False,
    })
    _log(AUDIT, {"decision": "STOP", "rule": rule, "tool": tool,
                 "target": target[:400], "reason": reason})
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason + " This refusal is final — do not retry it, "
                                             "and do not try to reach the same result another way. "
                                             "A second attempt freezes the agent.",
    }}))
    sys.stderr.write(f"[FENCE] BLOCKED ({rule}): {reason}\n"
                     f"[FENCE] This is terminal. Retrying, or routing around it, trips a hard stop.\n")
    sys.exit(2)


def allow() -> None:
    sys.exit(0)


# ---------------------------------------------------------------- helpers

def mcp_leaf(tool_name: str) -> str:
    return tool_name.rsplit("__", 1)[-1] if tool_name.startswith("mcp__") else tool_name


def target_preview(ti: dict) -> str:
    return str(ti.get("command") or ti.get("file_path") or ti.get("path") or "")[:200]


# Tools that carry a file_path but cannot change the file. Everything else that
# names a path is treated as mutating (unknown tool => assume it writes).
READ_ONLY_TOOLS = {"Read", "Glob", "Grep", "NotebookRead", "LS"}


def mutates(tool: str) -> bool:
    return mcp_leaf(tool) not in READ_ONLY_TOOLS and tool not in READ_ONLY_TOOLS


def any_re(patterns, text: str):
    for p in patterns:
        if not isinstance(p, str) or p.startswith("_"):
            continue
        try:
            if re.search(p, text, re.I):
                return p
        except re.error:
            return f"<malformed:{p}>"
    return None


def path_fenced(path: str, globs) -> str | None:
    norm = str(path).replace("\\", "/")
    for g in globs:
        if not isinstance(g, str) or g.startswith("_"):
            continue
        if (fnmatch.fnmatch(norm, g) or fnmatch.fnmatch(norm, g.lstrip("*/"))
                or fnmatch.fnmatch("/" + norm.lstrip("/"), g)):
            return g
    return None


def push_target_branch(cmd: str, cwd: str) -> str | None:
    m = re.search(r"git\s+push\s+(?:--\S+\s+)*(\S+)\s+(?:HEAD:)?(\S+)", cmd, re.I)
    if m:
        return m.group(2).split(":")[-1].strip()
    if re.search(r"git\s+push\s*(?:--\S+\s*)*$", cmd.strip(), re.I):
        try:
            out = subprocess.run(
                ["git", "-C", cwd or ".", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                return out.stdout.strip()
        except Exception:
            return "UNRESOLVED"
        return "UNRESOLVED"
    return None


# ---------------------------------------------------------------- main

def main() -> None:
    payload = json.loads(sys.stdin.read())   # unparseable -> exception -> fail closed
    tool = payload.get("tool_name") or ""
    ti = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or ""

    if os.environ.get("CLAUDE_FENCE_BYPASS") == "1":
        _log(AUDIT, {"decision": "BYPASS", "tool": tool, "note": "CLAUDE_FENCE_BYPASS=1"})
        allow()

    # --- already frozen? nothing runs. ---
    if HARD_STOP.exists():
        if SHADOWING:
            shadow_record("FREEZE-ACTIVE", "hard-stop-exists", tool, target_preview(ti),
                          "HARD_STOP present; in enforce mode this call would be refused")
        sys.stderr.write(
            f"[FENCE] The agent is frozen ({HARD_STOP} exists). A person must release it. "
            f"Do not continue; do not attempt to remove the file.\n")
        sys.exit(2)

    if not FENCE_FILE.exists():
        block(f"No fence file at {FENCE_FILE}. An agent without a fence is stopped, not free.",
              "no-fence", tool, "startup")
    fence = json.loads(FENCE_FILE.read_text(encoding="utf-8"))
    spend, prod, outb = fence.get("spend", {}), fence.get("prod", {}), fence.get("outbound", {})

    cmd = str(ti.get("command") or "")
    fpath = str(ti.get("file_path") or ti.get("path") or ti.get("notebook_path") or "")
    leaf = mcp_leaf(tool)
    target = cmd or fpath or json.dumps(ti)[:300]
    action_fp = fp(tool, target)

    # ================= R3: a denied action is terminal =================
    # Checked BEFORE any classification, so quality of reasoning is never an input.
    for d in load_denials():
        same_action = d.get("action_fp") == action_fp
        same_target = bool(d.get("target_fp")) and any(
            d.get("resource", "").lower() in s.lower()
            for s in (cmd, fpath, json.dumps(ti)) if s)
        if same_action or same_target:
            kind = ("the same action again" if same_action
                    else f"the same protected thing ({d.get('resource')}) by a different route")
            trip_hard_stop(
                title=f"A refused action was attempted a second time.",
                attempted=(f"{'Retrying' if same_action else 'Routing around'} a refusal from "
                           f"{d.get('ts', 'earlier')}. The agent tried {kind}.\n  "
                           f"Tool: {tool}\n  Request: {target[:300]}"),
                rule_hit="A denied action is terminal. It cannot be retried, and it cannot be "
                         "reached by another route.",
                why_terminal=(f"The first attempt was refused because: {d.get('reason', '(no reason recorded)')} "
                              f"Once something is refused, trying again is itself a stop condition — "
                              f"however good the new argument is. That rule exists so a refusal cannot "
                              f"be worn down by persistence."),
                options=[
                    f"Release the agent — delete {HARD_STOP} on the desktop, then tell it to do something else.",
                    f"Do the action yourself, if you actually want it done.",
                    f"Authorise it properly — mark the denial cleared in {DENIALS}; this creates a new "
                    f"record and leaves the original refusal in place.",
                    "Leave it frozen — if this looks wrong, nothing happens until you decide.",
                ],
                tool=tool, target=target)

    # ================= self-modification: terminal on FIRST attempt =================
    # Editing the fence, the hook, or the permission settings is not an honest mistake.
    # Reading the constitution, the fence, or settings.json is always fine — the
    # agent is meant to know what binds it. Only changing them is the offence.
    if fpath and mutates(tool):
        selfmod = path_fenced(fpath, prod.get("self_modification_globs", []))
        if selfmod:
            trip_hard_stop(
                title="The agent tried to edit the thing that limits it.",
                attempted=f"A write to {fpath}\n  Tool: {tool}",
                rule_hit="The agent may not weaken or disable the fence, or escalate its own permissions.",
                why_terminal=("This file is what decides whether the agent may spend money or touch "
                              "production. Changing it is not a normal edit — it is the agent expanding "
                              "its own authority, so it stops on the first attempt rather than the second."),
                options=[
                    f"Release the agent — delete {HARD_STOP} on the desktop.",
                    "Make the change yourself, if the fence genuinely needs updating.",
                    "Check what it was trying to do first — this is the one incident worth reading closely.",
                ],
                tool=tool, target=fpath)

    # ================= spend =================
    if leaf in set(spend.get("mcp_tools", [])):
        block(f"'{leaf}' spends money or consumes paid credits.", "spend-mcp", tool, leaf, leaf)
    # a Bash write to a rule file bypasses the file_path check above
    if cmd:
        hit = any_re(prod.get("self_modification_bash_patterns", []), cmd)
        if hit:
            trip_hard_stop(
                title="The agent tried to change the thing that limits it, via a shell command.",
                attempted=f"A shell command that writes to a fence rule file.\n  Command: {cmd[:300]}",
                rule_hit="The agent may not weaken or disable the fence, or escalate its own permissions.",
                why_terminal=("Doing it through the shell instead of a file edit is the same act. "
                              "It stops on the first attempt, not the second."),
                options=[f"Release the agent — delete {HARD_STOP} on the desktop.",
                         "Make the change yourself if the fence genuinely needs updating.",
                         "Read the command first — this is the incident worth reading closely."],
                tool=tool, target=cmd)

    if cmd:
        hit = any_re(spend.get("bash_patterns", []), cmd)
        if hit:
            block(f"That command spends money (matched {hit}).", "spend-bash", tool, cmd, hit)

    # ================= production =================
    if leaf in set(prod.get("mcp_tools", [])):
        block(f"'{leaf}' changes production.", "prod-mcp", tool, leaf, leaf)
    if leaf in set(outb.get("mcp_tools", [])):
        block(f"'{leaf}' sends something to a real person or public account.",
              "outbound-mcp", tool, leaf, leaf)

    prod_dbs = {d.lower() for d in prod.get("databases", []) if isinstance(d, str)}

    if leaf in set(prod.get("mcp_tools_target_scoped", [])):
        ref = str(ti.get("project_id") or ti.get("project_ref") or ti.get("ref") or "")
        if not ref:
            block(f"'{leaf}' names no project, so it cannot be shown to be aimed at a "
                  f"non-production database.", "prod-db-unresolved", tool, leaf, leaf)
        if ref.lower() in prod_dbs:
            block(f"'{leaf}' is aimed at the live database '{ref}'.", "prod-db", tool, target, ref)
        allow()   # an explicit preview branch — the intended safe workspace

    blob = json.dumps(ti).lower()
    for db in prod_dbs:
        if db in blob:
            block(f"That request names the live database '{db}'.", "prod-db", tool, target, db)

    if fpath and mutates(tool):
        hit = path_fenced(fpath, prod.get("path_globs", []))
        if hit:
            block(f"'{fpath}' holds secrets or production configuration.",
                  "prod-path", tool, fpath, fpath)

    if cmd:
        for host in prod.get("hosts", []):
            if isinstance(host, str) and host.lower() in cmd.lower() and re.search(
                    r"\b(curl|wget|http|deploy|push|psql)\b", cmd, re.I):
                block(f"That command reaches the live site '{host}'.", "prod-host", tool, cmd, host)

        if re.search(r"\bgit\s+push\b", cmd, re.I):
            br = push_target_branch(cmd, cwd)
            if br == "UNRESOLVED":
                block("A bare `git push` here cannot be shown to be aimed away from a "
                      "protected branch.", "prod-branch-unresolved", tool, cmd, "unresolved-branch")
            if br and br.lower() in {b.lower() for b in prod.get("branches", [])}:
                block(f"That push targets the protected branch '{br}'.",
                      "prod-branch", tool, cmd, br)

        hit = any_re(prod.get("bash_patterns", []), cmd)
        if hit:
            block(f"That command changes production (matched {hit}).", "prod-bash", tool, cmd, hit)

        hit = any_re(outb.get("bash_patterns", []), cmd)
        if hit:
            block(f"That command sends something outward to a real recipient (matched {hit}).",
                  "outbound-bash", tool, cmd, hit)

    allow()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        if SHADOWING:
            # FAIL OPEN — the inverse of enforce, and deliberately so. A shadow
            # observer that crashes must never stop a session it was only watching.
            _log(SHADOW, {"would": "ERROR", "rule": "internal-error",
                          "reason": f"{type(exc).__name__}: {exc}"})
            sys.exit(0)
        sys.stderr.write(                          # FAIL CLOSED
            f"[FENCE] BLOCKED (internal-error): the fence could not judge this request "
            f"({type(exc).__name__}: {exc}). Something it cannot judge, it does not allow. "
            f"If the fence itself is broken, the founder can set CLAUDE_FENCE_BYPASS=1.\n")
        sys.exit(2)
