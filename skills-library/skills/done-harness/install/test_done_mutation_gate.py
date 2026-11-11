"""Controls for the proposed Done mutation-gate hook (20/10/2026, weakness #2).
    python3 skills/done-harness/install/test_done_mutation_gate.py   (exit 1 on any failure)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE_DIR = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "done_mutation_gate.py")
# The hook loads donectl from ~/.claude/skills/done-harness. Point HOME at a throwaway home whose
# done-harness IS this checkout, so the run tests this branch (not the installed copy) and works
# on a CI runner that has no ~/.claude at all (the kill switch also lands in this home's state).
_HOME = tempfile.mkdtemp(prefix="gate-home-")
os.makedirs(os.path.join(_HOME, ".claude", "skills"))
os.symlink(os.path.dirname(HERE_DIR), os.path.join(_HOME, ".claude", "skills", "done-harness"))
os.environ["HOME"] = _HOME
DONECTL = os.path.join(_HOME, ".claude", "skills", "done-harness", "scripts", "donectl.py")


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def hook(tool, tool_input, cwd, env=None):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(
        {"tool_name": tool, "tool_input": tool_input, "cwd": cwd}), capture_output=True, text=True,
        env=env)
    return p.returncode


def preflight_rc(tool, tool_input, cwd):
    """2 if THIS checkout's donectl.preflight denies, else 0 (the hook loads the installed copy)."""
    code = ("import sys,json; sys.path.insert(0, %r); import donectl; "
            "r = donectl.preflight(%r, json.loads(%r), cwd=%r); sys.exit(2 if r['decision'] != 'ALLOW' else 0)"
            % (os.path.join(os.path.dirname(HERE_DIR), "scripts"), tool, json.dumps(tool_input), cwd))
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).returncode


def darwin_temp():
    """The per-user temp dir the runner uses; None off macOS."""
    p = subprocess.run(["getconf", "DARWIN_USER_TEMP_DIR"], capture_output=True, text=True)
    return os.path.realpath(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip() else None


def repair_cases(t):
    """donectl.preflight RAISES (broken gate). Only a Write-family tool whose own path field really
    resolves inside the done-harness folder may pass; a forged extra file_path must not."""
    home = os.path.join(t, "repair-home")
    harness = os.path.join(home, ".claude", "skills", "done-harness")
    os.makedirs(os.path.join(harness, "scripts"))
    with open(os.path.join(harness, "scripts", "donectl.py"), "w") as f:
        f.write("def preflight(*a, **k):\n    raise RuntimeError('boom')\n")
    outside = os.path.join(t, "repair-outside")
    os.makedirs(outside)
    link = os.path.join(harness, "escape")
    os.symlink(outside, link)
    inside = os.path.join(harness, "scripts", "x.py")
    env = dict(os.environ, HOME=home, PYTHONDONTWRITEBYTECODE="1")
    marker = os.path.join(outside, "marker")
    return [
        ("repair: forged Bash payload (extra file_path in harness) is denied",
         hook("Bash", {"command": "touch " + marker, "file_path": inside}, t, env=env), 2),
        ("repair: Bash without file_path is denied",
         hook("Bash", {"command": "touch " + marker}, t, env=env), 2),
        ("repair: Write inside the harness is still allowed",
         hook("Write", {"file_path": inside}, t, env=env), 0),
        ("repair: Edit inside the harness is still allowed",
         hook("Edit", {"file_path": inside}, t, env=env), 0),
        ("repair: NotebookEdit notebook_path inside the harness is allowed",
         hook("NotebookEdit", {"notebook_path": inside}, t, env=env), 0),
        ("repair: Write through a harness symlink to outside is denied",
         hook("Write", {"file_path": os.path.join(link, "evil.py")}, t, env=env), 2),
        ("repair: Write outside the harness is denied",
         hook("Write", {"file_path": marker}, t, env=env), 2),
        ("repair: Write whose notebook_path is in the harness but file_path is outside is denied",
         hook("Write", {"file_path": marker, "notebook_path": inside}, t, env=env), 2),
    ]


def main():
    failed = 0
    with tempfile.TemporaryDirectory() as t:
        # the source repo sits under a path with a space so every git-dir the mesh probe reads
        # holds one, wherever the temp root is (review r4: a space only in the worktree path
        # never reached the probe output, so a split() regression passed off the Mini)
        repo = os.path.join(t, "src repo")
        os.makedirs(repo)
        for c in (["git", "init", "-q", "-b", "main"], ["git", "config", "user.email", "t@t"],
                  ["git", "config", "user.name", "t"]):
            run(c, repo)
        open(os.path.join(repo, "a.txt"), "w").write("a\n")
        run(["git", "add", "-A"], repo)
        run(["git", "commit", "-q", "-m", "i"], repo)
        run([sys.executable, DONECTL, "init"], repo)
        out = json.loads(run([sys.executable, DONECTL, "start", "gate test"], repo).stdout)
        product = os.path.join(repo, "src", "new.py")
        cases = [
            ("DRAFT: Write to a product file is denied", hook("Write", {"file_path": product}, repo), 2),
            ("DRAFT: Write inside .claude/done is allowed",
             hook("Write", {"file_path": out["contract_path"]}, repo), 0),
            ("DRAFT: a mutating Bash command is denied", hook("Bash", {"command": "rm a.txt"}, repo), 2),
            ("DRAFT: Bash carrying a forged file_path inside .claude/done is still denied",
             preflight_rc("Bash", {"command": "rm a.txt", "file_path": out["contract_path"]}, repo), 2),
            ("DRAFT: a MultiEdit to a product file is denied",
             preflight_rc("MultiEdit", {"file_path": product}, repo), 2),
            ("DRAFT: a read-only Bash command is allowed", hook("Bash", {"command": "ls"}, repo), 0),
            ("DRAFT: judged by the TARGET repo, not the session cwd",
             hook("Write", {"file_path": product}, t), 2),
            ("non-repo: out of scope, allowed", hook("Write", {"file_path": os.path.join(t, "x")}, t), 0),
            ("DRAFT: Bash with a forged file_path in a non-repo dir is still judged by cwd",
             hook("Bash", {"command": "rm a.txt", "file_path": os.path.join(t, "x")}, repo), 2),
        ]
        # mesh runner (21/10): its probe and run worktrees sit directly under the system temp dir as
        # mesh-*; they hold no contract, so the gate refused every write and the runner stalled.
        run(["git", "add", "-A"], repo)
        run(["git", "commit", "-q", "-m", "done tree"], repo)
        root = os.path.realpath(tempfile.gettempdir())
        made = [tempfile.mkdtemp(prefix="mesh-preflight-wt-", dir=root), tempfile.mkdtemp(prefix="meshy-", dir=root)]
        try:
            probe_wt = os.path.join(made[0], "wt")
            run_wt = os.path.join(root, "mesh-RA-0000-%s" % os.path.basename(made[0])[-8:])
            look_wt = os.path.join(made[1], "wt")
            nested_wt = os.path.join(t, "mesh-nested")
            for w in (probe_wt, run_wt, look_wt, nested_wt):
                run(["git", "worktree", "add", "-q", "--detach", w, "HEAD"], repo)
            made.append(run_wt)
            cases += [
                ("mesh: runner probe write in its temp worktree is allowed",
                 hook("Write", {"file_path": os.path.join(probe_wt, "mesh-preflight-x.txt")}, probe_wt), 0),
                ("mesh: a mutating Bash command in a run worktree is allowed",
                 hook("Bash", {"command": "git commit -qam x"}, run_wt), 0),
                ("mesh: a look-alike <temp>/meshy-* worktree is still denied",
                 hook("Write", {"file_path": os.path.join(look_wt, "x.txt")}, look_wt), 2),
                ("mesh: a mesh-* folder not directly under the temp dir is still denied",
                 hook("Write", {"file_path": os.path.join(nested_wt, "x.txt")}, nested_wt), 2),
            ]
            # review 26/10: a name alone is forgeable. A fresh `git init` named <temp>/mesh-* with a
            # .claude/done tree and no lock is not a runner worktree (the runner only ever uses
            # `git worktree add`), so it must stay gated.
            fake = tempfile.mkdtemp(prefix="mesh-fake-review-", dir=root)
            made.append(fake)
            run(["git", "init", "-q"], fake)
            os.makedirs(os.path.join(fake, ".claude", "done"))
            plain = tempfile.mkdtemp(prefix="mesh-plain-", dir=root)
            made.append(plain)
            # the live runner's temp root is on "/Volumes/Storage Unit": a space in the path must not
            # break the linked-worktree check.
            spaced = os.path.join(t, "with space")
            os.makedirs(spaced)
            sp_wt = os.path.join(spaced, "mesh-RA-0001-space")
            run(["git", "worktree", "add", "-q", "--detach", sp_wt, "HEAD"], repo)
            sp_env = dict(os.environ, TMPDIR=spaced, TMP=spaced, TEMP=spaced)
            sp_gitdir = run(["git", "rev-parse", "--path-format=absolute", "--git-dir"], sp_wt).stdout.strip()
            probe = run(["git", "rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir"],
                        sp_wt).stdout.splitlines()
            assert len(probe) == 2 and all(" " in d for d in probe), probe  # the fixture must exercise it
            git_env = dict(os.environ, GIT_DIR=sp_gitdir, GIT_WORK_TREE=sp_wt)
            # review r2: copy only a real linked worktree's .git pointer into a fresh mesh-* folder
            copied = tempfile.mkdtemp(prefix="mesh-forged-", dir=root)
            made.append(copied)
            shutil.copy(os.path.join(sp_wt, ".git"), os.path.join(copied, ".git"))
            os.makedirs(os.path.join(copied, ".claude", "done"))
            # review r5: a back-reference naming any other file in the fake folder is not a registration
            sib = tempfile.mkdtemp(prefix="mesh-sibling-", dir=root)
            made.append(sib)
            shutil.copy(os.path.join(sp_wt, ".git"), os.path.join(sib, ".git"))
            os.makedirs(os.path.join(sib, ".claude", "done"))
            back_file = os.path.join(sp_gitdir, "gitdir")
            real_back = open(back_file).read()
            os.makedirs(os.path.join(sp_wt, "src"), exist_ok=True)
            cases += [
                ("mesh: a write in a folder below a real run worktree's root is allowed",
                 hook("Write", {"file_path": os.path.join(sp_wt, "src", "nested.txt")},
                      os.path.join(sp_wt, "src"), env=sp_env), 0),
            ]
            with open(back_file, "w") as f:
                f.write(os.path.join(sib, "not.git") + "\n")
            try:
                cases.append(("mesh: a back-reference naming a sibling file of a copied pointer is denied",
                              hook("Bash", {"command": "touch product.txt"}, sib), 2))
            finally:
                with open(back_file, "w") as f:
                    f.write(real_back)
            cases += [
                ("mesh: a real run worktree stays allowed when the hook inherits another repo's GIT_DIR",
                 hook("Bash", {"command": "git commit -qam x"}, sp_wt,
                      env=dict(sp_env, GIT_DIR=os.path.join(repo, ".git"), GIT_WORK_TREE=repo)), 0),
                ("mesh: a copied linked-worktree .git pointer is still denied",
                 hook("Bash", {"command": "touch product.txt"}, copied), 2),
                ("mesh: a run worktree under a temp root with a space is allowed",
                 hook("Bash", {"command": "git commit -qam x"}, sp_wt, env=sp_env), 0),
                ("mesh: a fresh git init named mesh-* is still denied (Bash)",
                 hook("Bash", {"command": "touch product.txt"}, fake), 2),
                ("mesh: a fresh git init named mesh-* is still denied (Write)",
                 hook("Write", {"file_path": os.path.join(fake, "product.txt")}, fake), 2),
                ("mesh: an inherited GIT_DIR naming a real worktree does not exempt a fresh git init",
                 hook("Write", {"file_path": os.path.join(fake, "product.txt")}, fake, env=git_env), 2),
                ("mesh: a plain non-repo mesh-* folder stays out of scope",
                 hook("Write", {"file_path": os.path.join(plain, "x.txt")}, plain), 0),
            ]
            # 21/10 live failure: ~/.zprofile points the hook's TMPDIR at the SSD while the runner's
            # worktrees sit in the macOS per-user temp dir. The exemption must not depend on TMPDIR.
            dt = darwin_temp()
            if dt:
                d_parent = tempfile.mkdtemp(prefix="mesh-preflight-wt-", dir=dt)
                made.append(d_parent)
                d_wt = os.path.join(d_parent, "wt")
                run(["git", "worktree", "add", "-q", "--detach", d_wt, "HEAD"], repo)
                other = dict(os.environ, TMPDIR=t, TMP=t, TEMP=t)
                cases += [
                    ("mesh: probe write allowed when the hook's TMPDIR points elsewhere",
                     hook("Write", {"file_path": os.path.join(d_wt, "p.txt")}, d_wt, env=other), 0),
                    ("mesh: an ordinary repo is still denied when TMPDIR points elsewhere",
                     hook("Write", {"file_path": product}, repo, env=other), 2),
                ]
        finally:
            for m in made:
                shutil.rmtree(m, ignore_errors=True)
            run(["git", "worktree", "prune"], repo)
        c = json.load(open(out["contract_path"]))
        c["criteria"] = [{"id": "C1", "text": "holds", "recipe": "true"}]
        json.dump(c, open(out["contract_path"], "w"))
        run([sys.executable, DONECTL, "lock"], repo)
        cases.append(("LOCKED: Write to a product file is allowed",
                      hook("Write", {"file_path": product}, repo), 0))
        cases += repair_cases(t)
        bad = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True, text=True)
        cases.append(("unreadable payload fails closed", bad.returncode, 2))
        for name, got, want in cases:
            ok = got == want
            failed += not ok
            print("%s %s (rc=%s, want %s)" % ("PASS" if ok else "FAIL", name, got, want))
    print("%d/%d passed" % (len(cases) - failed, len(cases)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
