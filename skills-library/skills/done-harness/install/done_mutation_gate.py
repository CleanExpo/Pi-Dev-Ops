#!/usr/bin/env python3
"""PreToolUse hook: consult `donectl preflight` before any mutation-capable tool call.

INSTALLED on the Mini since 20/10/2026 (harness weakness #2). donectl has always computed a
DENY for a Write while the contract is DRAFT; this hook is the caller that asks it.

Registration is one PreToolUse entry (installing a forcing hook is founder-gated):
    matcher: "Write|Edit|NotebookEdit|Bash"
    command: /opt/homebrew/bin/python3 ~/.claude/skills/done-harness/install/done_mutation_gate.py

Kill switch: if ~/.claude/state/proof-loop.disabled exists the gate is OFF - every call is
allowed, one JSON line is appended to ~/.claude/state/proof-loop-audit.jsonl and one stderr line
says so. Creating that file is Phill's act, from Terminal. While the switch is off, an agent's
Write/Edit/NotebookEdit to that path, or any Bash command naming "proof-loop.disabled", is
denied before donectl is consulted, so the gate cannot be disabled by the agent it constrains.
RESIDUAL (recorded, not solved): the Bash check is a plain substring match. A command that
builds the name at run time (quotes split inside it, a variable, printf) is not caught, and an
agent with arbitrary Bash can do anything the user can. So this stops the obvious and the
accidental, not a determined bypass. Detection covers the rest: every allowed call while the
switch is on writes an audit line, and the Proof Loop deadman reports a present switch as an
alert (spec Wiki/ops/false-positive-controls-2026-10-26, Stage 1).

Decisions taken here, each fail-closed:
- A Write/Edit is judged against the repository that holds the TARGET file, not the session
  cwd: a session started in ~ that edits ~/repo/x must meet ~/repo's contract.
- An internal error (donectl missing, unreadable payload) DENIES - except a Write/Edit inside
  the done-harness skill itself, so a broken gate can still be repaired instead of locking
  the machine out of its own fix.
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

KILL_NAME = "proof-loop.disabled"

HARNESS = os.path.join(os.path.expanduser("~"), ".claude", "skills", "done-harness")
REPAIR_SCOPE = os.path.realpath(HARNESS) + os.sep


def _mesh_scratch(path) -> bool:
    """A mesh runner worktree: directly under the system temp dir and named mesh-* (21/10/2026).

    The runner's probe (`mesh-preflight-wt-*/wt`) and run worktrees (`mesh-<ID>-<run>`) hold no
    Done contract, so the gate refused every write and the Mini runner stalled. Only the first
    path component below the temp dir counts: <temp>/meshy-* or <temp>/x/mesh-* stay gated.

    The hook's own TMPDIR is not enough: ~/.zprofile points it at the SSD while the runner's
    worktrees sit in the macOS per-user temp dir, so that dir is checked too."""
    p = os.path.realpath(path)
    if os.sep + "mesh-" not in p:
        return False  # the common case: no getconf call on every gated tool use
    for root in _temp_roots():
        if p.startswith(root) and p[len(root):].split(os.sep, 1)[0].startswith("mesh-"):
            return _linked_worktree(p)
    return False


def _linked_worktree(path) -> bool:
    """The name alone is forgeable (review 26/10): the runner only ever makes these with
    `git worktree add`, so a mesh-* folder counts only when it is a LINKED worktree (its git dir
    differs from the common dir). A fresh `git init` there stays gated; any git failure fails closed."""
    try:
        # an inherited GIT_DIR / GIT_WORK_TREE would make git answer for a different repository
        # (review 26/10), so the probe sees only the folder itself
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        r = subprocess.run(["git", "-C", path, "rev-parse", "--path-format=absolute",
                            "--git-dir", "--git-common-dir", "--show-toplevel"],
                           capture_output=True, text=True, timeout=5, env=env)
    except Exception:  # noqa: BLE001
        return False
    dirs = r.stdout.splitlines()  # never split(): runner temp roots such as /Volumes/Storage Unit hold spaces
    if r.returncode != 0 or len(dirs) != 3:
        return False
    git_dir, common_dir, top = dirs
    if os.path.realpath(git_dir) == os.path.realpath(common_dir):
        return False
    # a copied .git pointer also yields two different dirs (review 26/10 r2): the source repo must
    # have registered this worktree, i.e. <git-dir>/gitdir names exactly <top>/.git. The judged
    # path may be a folder below the worktree root (review r5), so compare against the root.
    try:
        with open(os.path.join(git_dir, "gitdir")) as f:
            back = f.read().strip()
    except OSError:
        return False
    return os.path.realpath(back) == os.path.realpath(os.path.join(top, ".git"))


def _temp_roots():
    roots = [tempfile.gettempdir()]
    try:
        out = subprocess.run(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], capture_output=True,
                             text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            roots.append(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass  # off macOS or getconf missing: only the TMPDIR root counts (fails closed)
    return {os.path.realpath(r) + os.sep for r in roots}


def _state_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "state")  # call time: tests change HOME


def _kill_switch_on() -> bool:
    KILL_SWITCH = os.path.join(_state_dir(), KILL_NAME)
    return os.path.exists(KILL_SWITCH)


def _audit_allow(tool, cwd):
    """Append one audit line; a failed write must never block."""
    try:
        d = _state_dir()
        os.makedirs(d, exist_ok=True)
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "tool": tool, "cwd": cwd,
               "decision": "ALLOW", "reason": "kill switch present"}
        with open(os.path.join(d, "proof-loop-audit.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def _tool_path(tool, ti):
    """The path a tool really writes: its OWN field only. Any other tool's file_path is untrusted
    noise (a Bash payload can carry one), so it names no target."""
    if tool not in WRITE_TOOLS or not isinstance(ti, dict):
        return None
    target = ti.get("notebook_path" if tool == "NotebookEdit" else "file_path")
    return target if isinstance(target, str) and target else None


def _touches_kill_switch(tool, ti, cwd) -> bool:
    if tool == "Bash":
        return KILL_NAME in (ti.get("command") or "")
    target = _tool_path(tool, ti)
    if target:
        if not os.path.isabs(target):
            target = os.path.join(cwd, target)
        return os.path.realpath(target) == os.path.realpath(os.path.join(_state_dir(), KILL_NAME))
    return False


def _repair_target(payload) -> bool:
    """Repair exemption: only a Write-family tool whose own path field resolves (symlinks
    followed) inside the harness. Bash and every other tool are denied when the gate is broken."""
    p = payload if isinstance(payload, dict) else {}
    target = _tool_path(p.get("tool_name"), p.get("tool_input") or {})
    if not target:
        return False
    if not os.path.isabs(target):
        target = os.path.join(p.get("cwd") or os.getcwd(), target)
    return os.path.realpath(target).startswith(REPAIR_SCOPE)


def main() -> int:
    payload = None
    try:
        payload = json.load(sys.stdin)
        k_tool = payload.get("tool_name", "")
        k_ti = payload.get("tool_input") or {}
        k_cwd = payload.get("cwd") or os.getcwd()
        if _kill_switch_on():
            _audit_allow(k_tool, k_cwd)
            sys.stderr.write("Done gate DISABLED by kill switch ~/.claude/state/proof-loop.disabled "
                             "(audit logged)\n")
            return 0
        if _touches_kill_switch(k_tool, k_ti, k_cwd):
            sys.stderr.write("Done gate BLOCKED: the proof-loop kill switch is created by Phill "
                             "from Terminal, not by an agent\n")
            return 2
        sys.path.insert(0, os.path.join(HARNESS, "scripts"))
        import donectl  # noqa: E402

        tool = payload.get("tool_name", "")
        ti = payload.get("tool_input") or {}
        cwd = payload.get("cwd") or os.getcwd()
        target = _tool_path(tool, ti)
        if target:
            if not os.path.isabs(target):
                target = os.path.join(cwd, target)
            d = os.path.dirname(os.path.realpath(target))
            while d and not os.path.isdir(d) and d != os.path.dirname(d):
                d = os.path.dirname(d)  # a new file in a new directory: nearest that exists
            cwd = d or cwd
        if _mesh_scratch(cwd):
            return 0
        res = donectl.preflight(tool, ti, cwd=cwd)
    except Exception as e:  # noqa: BLE001
        if _repair_target(payload):
            return 0
        sys.stderr.write("Done gate BLOCKED: ENFORCEMENT_UNPROVEN - the gate could not "
                         "decide (%s: %s); failing closed\n" % (type(e).__name__, e))
        return 2
    if res.get("decision") == "ALLOW":
        return 0
    sys.stderr.write("Done gate BLOCKED: %s. Only read-only recon and writes under "
                     ".claude/done are allowed until the contract is LOCKED "
                     "(donectl status / start / lock).\n" % res.get("reason"))
    return 2


if __name__ == "__main__":
    sys.exit(main())
