"""Controls for the Done mutation-gate kill switch (~/.claude/state/proof-loop.disabled).
    python3 skills/done-harness/install/test_kill_switch.py   (exit 1 on any failure)

Each case runs the gate as a subprocess with a throwaway HOME whose .claude/skills/done-harness
is a symlink to this worktree's harness, so the code under test is the code in this checkout.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "done_mutation_gate.py")
HARNESS = os.path.dirname(HERE)


def run(cmd, cwd, env=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)


def gate(home, tool, tool_input, cwd):
    env = dict(os.environ, HOME=home, PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(
        {"tool_name": tool, "tool_input": tool_input, "cwd": cwd}), capture_output=True,
        text=True, env=env)
    return p.returncode, p.stderr


def audit_lines(home):
    path = os.path.join(home, ".claude", "state", "proof-loop-audit.jsonl")
    if not os.path.exists(path):
        return []
    return [json.loads(x) for x in open(path).read().splitlines() if x.strip()]


def main():
    results = []
    with tempfile.TemporaryDirectory() as t:
        t = os.path.realpath(t)
        home = os.path.join(t, "home")
        os.makedirs(os.path.join(home, ".claude", "skills"))
        os.makedirs(os.path.join(home, ".claude", "state"))
        os.symlink(HARNESS, os.path.join(home, ".claude", "skills", "done-harness"))
        marker = os.path.join(home, ".claude", "state", "proof-loop.disabled")
        plain = os.path.join(t, "plain")
        os.makedirs(plain)
        repo = os.path.join(t, "repo")
        os.makedirs(repo)
        for c in (["git", "init", "-q", "-b", "main"], ["git", "config", "user.email", "t@t"],
                  ["git", "config", "user.name", "t"]):
            run(c, repo)
        open(os.path.join(repo, "a.txt"), "w").write("a\n")
        run(["git", "add", "-A"], repo)
        run(["git", "commit", "-q", "-m", "i"], repo)
        env = dict(os.environ, HOME=home)
        run([sys.executable, os.path.join(HARNESS, "scripts", "donectl.py"), "init"], repo, env)
        run(["git", "add", "-A"], repo)
        run(["git", "commit", "-q", "-m", "done tree"], repo)
        product = os.path.join(repo, "src", "new.py")
        touch = "touch ~/.claude/state/proof-loop.disabled"

        # --- switch absent ---
        rc, _ = gate(home, "Write", {"file_path": os.path.join(plain, "x")}, plain)
        results.append(("off: Write in a non-repo dir is allowed (out of scope)", rc, 0))
        rc, _ = gate(home, "Write", {"file_path": product}, repo)
        results.append(("off: Write in a repo with no locked contract is denied (gate unchanged)", rc, 2))
        rc, err = gate(home, "Write", {"file_path": marker}, plain)
        results.append(("off: Write to the marker path is denied", rc, 2))
        results.append(("off: marker-write denial says Phill creates it from Terminal",
                        int("not by an agent" in err), 1))
        rc, _ = gate(home, "Bash", {"command": touch}, plain)
        results.append(("off: Bash touching the marker is denied", rc, 2))
        results.append(("off: no audit line written", len(audit_lines(home)), 0))

        # --- switch present ---
        open(marker, "w").close()
        rc, err = gate(home, "Write", {"file_path": product}, repo)
        results.append(("on: Write in a no-contract repo is allowed", rc, 0))
        results.append(("on: stderr announces the gate is DISABLED", int("DISABLED" in err), 1))
        lines = audit_lines(home)
        results.append(("on: exactly one audit line", len(lines), 1))
        if lines:
            ln = lines[0]
            results.append(("on: audit line decision ALLOW, reason 'kill switch present'",
                            int(ln.get("decision") == "ALLOW"
                                and ln.get("reason") == "kill switch present"
                                and ln.get("tool") == "Write" and ln.get("cwd") == repo
                                and bool(ln.get("ts"))), 1))
        rc, _ = gate(home, "Bash", {"command": touch}, plain)
        results.append(("on: the same marker Bash command is allowed", rc, 0))
        os.remove(marker)
        rc, _ = gate(home, "Write", {"file_path": product}, repo)
        results.append(("removing the marker restores the gate", rc, 2))

    failed = 0
    for name, got, want in results:
        ok = got == want
        failed += not ok
        print("%s %s (got %s, want %s)" % ("PASS" if ok else "FAIL", name, got, want))
    print("%d/%d passed" % (len(results) - failed, len(results)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
