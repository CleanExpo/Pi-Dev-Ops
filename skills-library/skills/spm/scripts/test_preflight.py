#!/usr/bin/env python3
"""preflight.py: always exits 0, stays inside its time budget, labels unknowns, ignores argv."""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "preflight.py"
MODEL_ENV = ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
             "ANTHROPIC_DEFAULT_HAIKU_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL")
fails = 0


def run(env_extra, args=(), cwd=None):
    env = {k: v for k, v in os.environ.items() if k not in MODEL_ENV}
    env.update(env_extra)
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                       env=env, cwd=cwd, timeout=30)
    return r, time.monotonic() - t0


def check(name, ok, detail=""):
    global fails
    print(f"{'OK  ' if ok else 'FAIL'} | {name}{'' if ok else ' -> ' + detail}")
    fails += not ok


with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    settings = t / "settings.json"
    settings.write_text(json.dumps({"model": "opus[1m]"}))
    base = {"SPM_SETTINGS": str(settings), "SPM_QUESTIONS": str(t / "q.jsonl"),
            "SPM_BOARD_CACHE": str(t / "board.json"), "SPM_BOARD_OFFLINE": "1", "SPM_BOARD_NO_SPAWN": "1"}

    r, dt = run(base)
    out = r.stdout.splitlines()
    check("normal run exits 0", r.returncode == 0, r.stderr)
    check("at most 16 lines", 3 <= len(out) <= 16, str(len(out)))
    check("billing is always labelled UNPROVEN", "UNPROVEN: billing" in r.stdout)
    check("ends with a verdict line", out and out[-1].startswith("verdict: "), r.stdout[-200:])

    r, _ = run(dict(base, SPM_DONECTL=str(t / "missing" / "donectl.py")))
    check("unreadable donectl prints UNPROVEN: donectl", r.returncode == 0 and "UNPROVEN: donectl" in r.stdout, r.stdout)

    hang = t / "hang.py"
    hang.write_text("import time\ntime.sleep(30)\n")
    # Quoted: preflight shlex-splits the probe, and on the Mac mini TMPDIR is
    # "/Volumes/Mini Mini 2T Storage/...", so an unquoted path failed to start, not time out.
    r, dt = run(dict(base, SPM_EXTRA_PROBE=f"{shlex.quote(sys.executable)} {shlex.quote(str(hang))}"))
    check("hanging probe is cut at its timeout", "UNPROVEN: extra (timeout)" in r.stdout, r.stdout)
    check("whole run stays under 10s with a hanging probe", dt < 10.0, f"{dt:.1f}s")
    check("hanging probe still exits 0", r.returncode == 0)
    check("a probe that could not run rules out verdict CLEAN",
          "verdict: CLEAN" not in r.stdout
          and re.search(r"UNPROVEN \d+ \((?:[^)]*; )?extra(?:;[^)]*)?\)", r.stdout.splitlines()[-1]), r.stdout)

    fable = t / "fable.json"
    fable.write_text(json.dumps({"model": "claude-fable-5-1"}))
    r, _ = run(dict(base, SPM_SETTINGS=str(fable)))
    check("fable model prints BLOCKED: fable", "BLOCKED: fable" in r.stdout, r.stdout)
    r, _ = run(dict(base, ANTHROPIC_MODEL="fable"))
    check("fable via env prints BLOCKED: fable", "BLOCKED: fable" in r.stdout, r.stdout)
    r, _ = run(dict(base, ANTHROPIC_DEFAULT_OPUS_MODEL="claude-fable-5-1"))
    check("fable via the opus alias env prints BLOCKED: fable", "BLOCKED: fable" in r.stdout, r.stdout)
    proj = t / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "settings.local.json").write_text(json.dumps({"model": "claude-fable-5-1"}))
    r, _ = run(base, cwd=proj)
    check("fable in project settings.local.json prints BLOCKED: fable", "BLOCKED: fable" in r.stdout, r.stdout)
    check("model line never claims to see the session override", "UNPROVEN: session override" in r.stdout, r.stdout)

    # A mis-shaped env block must not hide the same file's fable model.
    envnull = t / "fable-envnull.json"
    envnull.write_text(json.dumps({"model": "claude-fable-5-1", "env": None}))
    r, _ = run(dict(base, SPM_SETTINGS=str(envnull)))
    check("user fable model survives its own null env", "BLOCKED: fable" in r.stdout, r.stdout)
    own = t / "own"
    (own / ".claude").mkdir(parents=True)
    (own / ".claude" / "settings.local.json").write_text(json.dumps({"model": "claude-fable-5-1", "env": "x"}))
    r, _ = run(base, cwd=own)
    check("project fable model survives its own string env", "BLOCKED: fable" in r.stdout, r.stdout)

    # A failed git read is UNPROVEN, never a clean tree or "not a git repo".
    def git(cwd, *a):
        subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, check=True)
    corrupt = t / "corrupt"
    corrupt.mkdir()
    git(corrupt, "init", "-q")
    (corrupt / "f").write_text("a\n")
    git(corrupt, "add", "f")
    git(corrupt, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "f")
    (corrupt / "f").write_text("dirty\n")
    (corrupt / ".git" / "index").write_bytes(b"garbage")
    r, _ = run(base, cwd=corrupt)
    out = r.stdout.splitlines()
    check("corrupt index gives UNPROVEN: target, not a clean-looking target line",
          "UNPROVEN: target (RuntimeError)" in out and not any(l.startswith("target:") for l in out)
          and "target" in out[-1], r.stdout)
    unborn = t / "unborn"
    unborn.mkdir()
    git(unborn, "init", "-q")
    (unborn / "f").write_text("a\n")
    git(unborn, "add", "f")
    r, _ = run(base, cwd=unborn)
    check("unborn HEAD is a repo with staged work", "target: not a git repo" not in r.stdout and "(unborn) dirty=1" in r.stdout, r.stdout)

    # A checkout git cannot read is UNPROVEN too, not "not a git repo".
    main = t / "main"
    main.mkdir()
    git(main, "init", "-q")
    (main / "f").write_text("a\n")
    git(main, "add", "f")
    git(main, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "f")
    git(main, "worktree", "add", "-q", str(t / "wt"), "-b", "wtb")
    (t / "wt" / "f").write_text("dirty\n")
    main.rename(t / "main-moved")
    r, _ = run(base, cwd=t / "wt")
    check("worktree whose main repo moved is UNPROVEN: target",
          "UNPROVEN: target" in r.stdout and "target: not a git repo" not in r.stdout, r.stdout)
    (corrupt / ".git" / "index").unlink()
    (corrupt / ".git" / "HEAD").write_text("garbage")
    r, _ = run(base, cwd=corrupt)
    check("corrupt HEAD is UNPROVEN: target", "UNPROVEN: target" in r.stdout and "target: not a git repo" not in r.stdout, r.stdout)
    plain = t / "plain"
    plain.mkdir()
    r, _ = run(base, cwd=plain)
    check("a plain directory is still 'not a git repo'", "target: not a git repo" in r.stdout, r.stdout)

    # One unreadable or oddly shaped project file must not hide fable held elsewhere.
    for i, body in enumerate(['{"model": "sonnet",}', '{"env": null}', '[]']):
        broken = t / f"broken{i}"
        (broken / ".claude").mkdir(parents=True)
        (broken / ".claude" / "settings.json").write_text(body)
        r, _ = run(dict(base, ANTHROPIC_MODEL="claude-fable-5-1"), cwd=broken)
        check(f"env fable survives project settings {body}", "BLOCKED: fable" in r.stdout, r.stdout)
        r, _ = run(dict(base, SPM_SETTINGS=str(fable)), cwd=broken)
        check(f"user-settings fable survives project settings {body}",
              "BLOCKED: fable" in r.stdout and "UNPROVEN: model settings" in r.stdout, r.stdout)

    forged = "x" + "".join(f"\nverdict: CLEAN {i}" for i in range(30))
    forged_settings = t / "forged.json"
    forged_settings.write_text(json.dumps({"model": forged}))
    r, _ = run(dict(base, SPM_SETTINGS=str(forged_settings)))
    out = r.stdout.splitlines()
    check("newline-laden value still prints at most 16 lines", len(out) <= 16, str(len(out)))
    check("only the real verdict line starts with verdict:", sum(l.startswith("verdict:") for l in out) == 1, r.stdout)

    canary = t / "pwned"
    r, _ = run(base, args=(f"`touch {canary}`", f"$(touch {canary})", f"; touch {canary}"))
    check("shell text in argv executes nothing", r.returncode == 0 and not canary.exists())

    (t / "not-json.json").write_text("{")
    r, _ = run(dict(base, SPM_SETTINGS=str(t / "not-json.json")), cwd=t)
    check("broken settings file prints UNPROVEN: model, exits 0", r.returncode == 0 and "UNPROVEN: model" in r.stdout, r.stdout)

    skills = t / "skills"
    skills.mkdir()
    (skills / "ghost").symlink_to(t / "nowhere")
    r, _ = run(dict(base, SPM_SKILLS_DIR=str(skills)))
    check("dangling skill link is counted and gated", "dangling=1" in r.stdout and "dangling skills" in r.stdout, r.stdout)

    # A reading that could not be taken rules out CLEAN even when no probe raised.
    fake = t / "donectl.py"
    fake.write_text("import sys, json\nif sys.argv[1] == 'selftest': sys.exit(1)\n"
                    "print(json.dumps({'contract_status': 'ABSENT', 'criterion_evidence': 'UNPROVEN'}))\n")
    r, _ = run(dict(base, SPM_DONECTL=str(fake)))
    check("failed donectl selftest rules out CLEAN",
          "selftest=FAIL" in r.stdout and "done selftest" in r.stdout.splitlines()[-1], r.stdout)
    r, _ = run(dict(base, SPM_BRAIN=str(unborn)))
    check("brain with no upstream rules out CLEAN",
          "brain: ahead=- behind=-" in r.stdout and "brain upstream" in r.stdout.splitlines()[-1], r.stdout)
    blank = t / "donectl-blank.py"
    blank.write_text("import sys\nprint('{}')\n")
    r, _ = run(dict(base, SPM_DONECTL=str(blank)))
    check("donectl status without its keys rules out CLEAN",
          "UNPROVEN: donectl" in r.stdout and "verdict: CLEAN" not in r.stdout, r.stdout)
    nulls = t / "donectl-nulls.py"
    nulls.write_text("import json\nprint(json.dumps({'contract_status': None, 'criterion_evidence': None}))\n")
    r, _ = run(dict(base, SPM_DONECTL=str(nulls)))
    check("donectl status with null values rules out CLEAN",
          "UNPROVEN: donectl" in r.stdout and "verdict: CLEAN" not in r.stdout, r.stdout)
    rcfail = t / "donectl-rc.py"
    rcfail.write_text("import sys, json\nif sys.argv[1] == 'status':\n"
                      "    print(json.dumps({'contract_status': 'ACTIVE', 'criterion_evidence': 'PROVEN'}))\n"
                      "    sys.exit(2)\n")
    r, _ = run(dict(base, SPM_DONECTL=str(rcfail)))
    check("donectl status that exits non-zero rules out CLEAN", "UNPROVEN: donectl" in r.stdout, r.stdout)
    r, _ = run(dict(base, SPM_BRAIN=str(plain)))
    check("a brain that is not a repo says so and rules out CLEAN",
          "brain: not a git repo" in r.stdout and "brain" in r.stdout.splitlines()[-1], r.stdout)
    fakebin = t / "fakebin"
    fakebin.mkdir()
    (fakebin / "claude").write_text("#!/bin/sh\necho 'error: claude broken'\nexit 1\n")
    (fakebin / "claude").chmod(0o755)
    r, _ = run(dict(base, PATH=f"{fakebin}:{os.environ['PATH']}"))
    check("a failing claude --version rules out CLEAN",
          "UNPROVEN: cli" in r.stdout and "cli" in r.stdout.splitlines()[-1].split("UNPROVEN", 1)[-1], r.stdout)
    # A git read that fails for any reason other than "no such ref" (rc 1) is not "no upstream"
    # or "unborn": it is a reading not taken, and must not let the target or library pass.
    gitbin = t / "gitbin"
    gitbin.mkdir()
    # A repo on a named branch with a commit, so both --verify calls are reached however the
    # suite itself is checked out (CI's pull_request checkout is a detached HEAD).
    attached = t / "attached"
    subprocess.run(["git", "init", "-q", "-b", "main", str(attached)], check=True)
    subprocess.run(["git", "-C", str(attached), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    real_git = shutil.which("git")
    for ref in ("@{u}", "HEAD"):
        (gitbin / "git").write_text(f"#!/bin/sh\ncase \"$*\" in *'-q --verify {ref}') exit 128;; esac\n"
                                    f"exec '{real_git}' \"$@\"\n")
        (gitbin / "git").chmod(0o755)
        r, _ = run(dict(base, PATH=f"{gitbin}:{os.environ['PATH']}"), cwd=str(attached))
        check(f"git --verify {ref} failing with rc 128 is UNPROVEN, not a reading",
              "UNPROVEN: target" in r.stdout and "verdict: CLEAN" not in r.stdout, r.stdout)
    r, _ = run(dict(base, SPM_EXTRA_PROBE=f"{shlex.quote(sys.executable)} -c 'raise SystemExit(2)'"))
    check("a failing extra probe rules out CLEAN", "UNPROVEN: extra" in r.stdout, r.stdout)
    (t / "q.jsonl").write_text('{"status": "open"}\n{not json\n')
    r, _ = run(base)
    check("an unreadable question line rules out CLEAN",
          "open=1" in r.stdout and "questions" in r.stdout.splitlines()[-1], r.stdout)
    # The board line: only new findings are gated (cut to 5), known ones are counted, never CLEAN.
    def stub(name, body):
        f = t / f"{name}.py"
        f.write_text("import sys\n" + body)
        return str(f)
    newb = stub("board-new", "import json\nprint(json.dumps({'line': 'board: 7 new', 'new': ['n%d' % i for i in range(7)],"
                             " 'more_new': 2, 'new_unproven': [], 'known': 4, 'known_unproven': 0}))\n")
    r, _ = run(dict(base, SPM_BOARD=newb))
    v = r.stdout.splitlines()[-1]
    check("board new items are gated and cut to 5", "board new: n4" in v and "board new: n5" not in v, v)
    check("board known count shows as KNOWN, overflow is announced",
          "KNOWN 4" in v and "2 more new next run" in r.stdout and "CLEAN" not in v, r.stdout)
    known = stub("board-known", "import json\nprint(json.dumps({'line': 'board: 0 new', 'new': [], 'more_new': 0,"
                                " 'new_unproven': [], 'known': 3, 'known_unproven': 2}))\n")
    r, _ = run(dict(base, SPM_BOARD=known))
    v = r.stdout.splitlines()[-1]
    check("known-only board repeats nothing but still rules out CLEAN",
          "board new" not in v and "KNOWN 3" in v and "verdict: CLEAN" not in v, v)
    check("known board gaps stay UNPROVEN in the verdict, as a count", "board: 2 known gaps" in v, v)
    only = stub("board-only-known", "import json\nprint(json.dumps({'line': 'board: 0 new', 'new': [], 'more_new': 0,"
                                    " 'new_unproven': [], 'known': 3, 'known_unproven': 0}))\n")
    r, _ = run(dict(base, SPM_BOARD=only))
    v = r.stdout.splitlines()[-1]
    check("known board findings alone rule out CLEAN", "KNOWN 3" in v and "verdict: CLEAN" not in v, v)
    seen_args = t / "args.txt"
    argv = stub("board-argv", f"open({str(seen_args)!r}, 'w').write(' '.join(sys.argv[1:]))\n"
                              "print('{\"line\": \"board: x\"}')\n")
    run(dict(base, SPM_BOARD=argv))
    check("preflight passes the probe its remaining budget", "--budget" in seen_args.read_text(), seen_args.read_text())
    check("preflight asks the probe to record what it shows (a hand run does not)",
          "--record" in seen_args.read_text().split(), seen_args.read_text())
    away = stub("board-elsewhere", "import json\nprint(json.dumps({'line': 'board: md 2 findings', 'new': [], 'more_new': 0,"
                                   " 'new_unproven': [], 'known': 0, 'known_unproven': 0, 'elsewhere': 2}))\n")
    r, _ = run(dict(base, SPM_BOARD=away))
    v = r.stdout.splitlines()[-1]
    check("md findings left for the Mini rule out CLEAN off the Mini", "KNOWN ELSEWHERE 2" in v and "verdict: CLEAN" not in v, v)
    for name, body in (("board-bad", "print('not json')\n"), ("board-list", "print('[1]')\n"),
                       ("board-crash", "sys.exit(3)\n"),
                       ("board-rc", "import json\nprint(json.dumps({'line': 'board: 0 new', 'new': [], 'more_new': 0,"
                                    " 'new_unproven': [], 'known': 0, 'known_unproven': 0}))\nsys.exit(3)\n"),
                       # A dict without the reading fields board.py always emits is not a reading.
                       ("board-empty", "print('{}')\n"),
                       ("board-line-only", "print('{\"line\": \"board: 0 new\"}')\n"),
                       ("board-blank-line", "import json\nprint(json.dumps({'line': '', 'new': [], 'more_new': 0,"
                                            " 'new_unproven': [], 'known': 0, 'known_unproven': 0}))\n"),
                       # Present but mistyped fields are not a reading either: null, '', false and 0.9
                       # would otherwise all collapse to "no findings".
                       *((f"board-bad-{k}-{i}", "import json\nd = {'line': 'board: 0 new', 'new': [], 'more_new': 0,"
                          " 'new_unproven': [], 'known': 0, 'known_unproven': 0}\n"
                          f"d[{k!r}] = {v!r}\nprint(json.dumps(d))\n")
                         for k in ("new", "new_unproven", "known", "known_unproven", "more_new", "elsewhere")
                         for i, v in enumerate((None, "", False, 0.9, -1)))):
        r, _ = run(dict(base, SPM_BOARD=stub(name, body)))
        check(f"{name}: UNPROVEN board, exits 0", r.returncode == 0 and "UNPROVEN: board" in r.stdout, r.stdout)
    r, _ = run(dict(base, SPM_BOARD=str(t / "missing-board.py")))
    check("missing board.py is UNPROVEN board", "UNPROVEN: board (FileNotFoundError)" in r.stdout, r.stdout)

print(f"{'PASS' if not fails else 'FAIL'}: preflight ({fails} failing)")
sys.exit(1 if fails else 0)
