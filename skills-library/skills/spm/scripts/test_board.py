#!/usr/bin/env python3
"""board.py: every md class fires on a planted defect and a clean library stays clean; nothing
unread is shown as clean or current; each case is new once, then known; an unread section never
forgets what was shown; the home check reads a real git fixture; probe never fails."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "board.py"
fails = 0
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main",
       "-c", "commit.gpgsign=false"]


def check(name, ok, detail=""):
    global fails
    print(f"{'OK  ' if ok else 'FAIL'} | {name}{'' if ok else ' -> ' + detail}")
    fails += not ok


def run(env_extra, *args):
    env = dict(os.environ, SPM_BOARD_OFFLINE="1", SPM_BOARD_NO_SPAWN="1", SPM_BOARD_GATE_REF="HEAD", SPM_BOARD_MD_NEW="1")
    env.update(env_extra)
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          env=env, timeout=120)


def probe(env, limit=50, record=True):
    r = run(env, "probe", *(["--record"] if record else []), "--limit", str(limit))
    return json.loads(r.stdout)


def git(*a, cwd):
    subprocess.run([*GIT, *a], cwd=cwd, check=True, capture_output=True)


def skill(root, name, body="Use me.\n", fm=True):
    d = root / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    head = f"---\nname: {name}\ndescription: a test skill\n---\n" if fm else ""
    (d / "SKILL.md").write_text(head + body)
    return d


GATE_STUB = '''
def substitution_near_git(command):
    return ("$(" in command or chr(96) in command) and ("git" in command or "gh" in command)
'''

spec = importlib.util.spec_from_file_location("board_mod", SCRIPT)
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)
check("compare: older installed is an update", board.compare("2.1.305", "2.1.308") == "update")
check("compare: newer installed is ahead, not update", board.compare("2.1.310", "2.1.308") == "ahead")
check("compare: numeric, not text (0.99.0 < 0.163.0)", board.compare("0.99.0", "0.163.0") == "update")
check("compare: dated builds", board.compare("2026.10.19-6bbf2c4", "2026.10.22-aaaa") == "update")
check("compare: same date, other hash is build-differs, not ahead", board.compare("2026.10.22-abc", "2026.10.22-def") == "build-differs")
check("forbidding word before the match exempts it", board.forbidden_before("Never use --no-verify", 10))
check("forbidding word in an earlier sentence does not", not board.forbidden_before("Never mind. Then --no-verify", 17))

with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    clean, dirty = t / "clean", t / "dirty"
    for lib in (clean, dirty):
        (lib / "skills").mkdir(parents=True)
        (lib / "scripts").mkdir()
        (lib / "scripts/retired-models.txt").write_text("claude-2.1-legacy-test\n")
        gate = lib / "skills/pr-release-gate/scripts"
        gate.mkdir(parents=True)
        (gate / "pr_release_gate.py").write_text(GATE_STUB)
        skill(lib, "pr-release-gate", "the gate\n")
        (lib / "skills/HOMES.json").write_text('{"homes": {}}\n')
        (lib / "CLAUDE.md").write_text("# rules\nNever run `git commit --no-verify`.\n"
                                       "Do not hard-code /Users/phill-mac/ paths.\nNo `--no-verify`, ever.\n")
    skill(clean, "good", "Run `git status` and see [ref](good.md).\n```\nsee [x](missing.md) in a fence\n```\n"
                         "cat .env.example\n```text\nchecklist (`gh secret list`) and $(git log)\n```\n")
    (clean / "skills/good/good.md").write_text("ok\n")

    skill(dirty, "abs", "Read /Users/phill-mac/notes.md first.\n")
    skill(dirty, "sub", "```bash\nX=$(git rev-parse HEAD)\n```\n")
    skill(dirty, "tick", "```bash\nY=" + chr(96) + "git log -1" + chr(96) + "\n```\n")  # only the real gate sees this
    skill(dirty, "bypass", "If the push is refused, stop. Then run `git commit --no-verify` to finish.\n")
    skill(dirty, "force", "Run `git push origin +main` when it is blocked.\n")
    skill(dirty, "secret", "```\ncat ~/.claude/skills/seo/.env\n```\n")
    skill(dirty, "link", "See [missing](nope/file.md).\n")
    skill(dirty, "nofm", "no frontmatter here\n", fm=False)
    (dirty / "skills/empty").mkdir()
    (dirty / "skills/ghost").symlink_to(t / "does-not-exist")
    skill(dirty, "old", "Model: claude-2.1-legacy-test\n")
    venv = dirty / "skills/abs/.venv/lib"
    venv.mkdir(parents=True)
    (venv / "README.md").write_text("/Users/phill-mac/inside-venv\n")
    for lib in (clean, dirty):
        git("init", "-q", cwd=lib)
        git("add", "-A", cwd=lib)
        git("commit", "-q", "-m", "fixture", cwd=lib)

    expected = {"abs-path": "abs", "gate-refused": "sub", "refused-cmd": "bypass", "env-read": "secret",
                "dead-link": "link", "frontmatter": "nofm", "no-skill-md": "empty",
                "dangling-skill": "ghost", "retired-model": "old"}

    for name, lib in (("clean", clean), ("dirty", dirty)):
        cache = t / f"{name}.json"
        env = {"SPM_BOARD_LIBRARY": str(lib), "SPM_BOARD_CACHE": str(cache),
               "SPM_BOARD_HOME": str(t / "no-canonical-here")}
        r = run(env, "refresh")
        check(f"{name}: refresh exits 0 offline", r.returncode == 0 and cache.is_file(), r.stdout + r.stderr[-300:])
        d = json.loads(cache.read_text())
        items = d["md"]["items"]
        check(f"{name}: the installed gate's own detector ran (not the fallback)", d["md"]["detector"] == "gate",
              d["md"]["detector"])
        if name == "clean":
            check("clean: zero md findings (forbidding lines, text fences, fenced links, .env.example)",
                  not items, json.dumps(items))
        else:
            for cls, where in expected.items():
                check(f"dirty: {cls} fires on skills/{where}",
                      any(i["cls"] == cls and f"skills/{where}" in i["where"] for i in items),
                      json.dumps([i for i in items if i["cls"] == cls]))
            check("dirty: refspec force push (+main) after 'blocked' is flagged",
                  any(i["cls"] == "refused-cmd" and "skills/force" in i["where"] for i in items))
            check("dirty: .venv under a skill is not scanned", not any(".venv" in i["where"] for i in items))
        check(f"{name}: offline never reports a version as current",
              all(v.get("status") != "current" for v in d["fresh"]["tools"].values()), json.dumps(d["fresh"]))
        j = probe(env)
        check(f"{name}: canonical clone missing is unproven, and the line never says clean",
              any("not on this host" in u for u in j["new_unproven"]) and " clean" not in j["line"], json.dumps(j))
        if name == "dirty":
            check("dirty: first probe lists md findings as new", any(n.startswith("md abs-path: 1 new") for n in j["new"]),
                  json.dumps(j["new"]))
            j2 = probe(env)
            check("dirty: second probe repeats nothing", not j2["new"] and not j2["new_unproven"] and j2["known"] > 0,
                  json.dumps(j2))
            skill(dirty, "abs2", "Also /Users/phillmcgurk/elsewhere.\n")
            run(env, "refresh")
            j3 = probe(env)
            check("dirty: one new case of a known class is reported as 1 new",
                  any(n.startswith("md abs-path: 1 new (skills/abs2") for n in j3["new"]), json.dumps(j3["new"]))
            (dirty / "skills/abs/SKILL.md").write_text("---\nname: abs\ndescription: fixed\n---\n")
            run(env, "refresh"); probe(env)
            (dirty / "skills/abs/SKILL.md").write_text("---\nname: abs\ndescription: x\n---\nRead /Users/phill-mac/notes.md first.\n")
            run(env, "refresh")
            j4 = probe(env)
            check("dirty: a case that cleared and came back is new again",
                  any("skills/abs/SKILL.md" in n for n in j4["new"]), json.dumps(j4["new"]))
            env_l = dict(env, SPM_BOARD_CACHE=str(t / "lim.json"))
            run(env_l, "refresh")
            a = probe(env_l, limit=3)
            b = probe(env_l, limit=50)
            check("limit: groups over the limit are not marked shown and come next run",
                  len(a["new"]) == 3 and len(a["new_unproven"]) == 3 and a["more_new"] > 0
                  and len(b["new"]) + len(b["new_unproven"]) == a["more_new"], json.dumps([a, b]))

    # md rule fixes: every match on a line, forbidding words after the match, forbidding list lead-ins,
    # conditionals are not prohibitions, untagged fences are not shell, .env variants, lease is refused too,
    # identical lines get distinct ids, unreadable folders are unproven
    rl = t / "rules"
    (rl / "skills").mkdir(parents=True)
    (rl / "scripts").mkdir()
    (rl / "scripts/retired-models.txt").write_text("claude-2.1-legacy-test\n")
    (rl / "skills/pr-release-gate/scripts").mkdir(parents=True)
    (rl / "skills/pr-release-gate/scripts/pr_release_gate.py").write_text(GATE_STUB)
    skill(rl, "pr-release-gate", "the gate\n")
    planted = {  # skill -> (body, class, flagged?)
        "multi-bad": ("Never use --no-verify. If stuck, `git commit --no-verify`.\n", "refused-cmd", True),
        "multi-ok": ("Never use --no-verify; never `git commit --no-verify` either.\n", "refused-cmd", False),
        "multi-model": ("Do not use claude-2.1-legacy-test; model: claude-2.1-legacy-test\n", "retired-model", True),
        "after-ok": ("`--no-verify` is forbidden. A force push (`git push --force`) is refused by the gate.\n"
                     "`--dangerously-skip-permissions` is never allowed.\n", "refused-cmd", False),
        "after-cond": ("Run `git commit --no-verify` if the push is refused.\n", "refused-cmd", True),
        "list-ok": ("Never do any of these:\n- `--no-verify`, force push, … Ever, for any reason.\n"
                    "- `git push --force origin main`\n", "refused-cmd", False),
        "list-gap": ("Never do any of these:\n- `--dangerously-skip-permissions`\n\n- `git commit --no-verify` to finish\n",
                     "refused-cmd", True),
        "list-plain": ("Steps:\n- `git commit --no-verify`\n", "refused-cmd", True),
        "list-cond": ("If the push is refused:\n- `git push --force`\n", "refused-cmd", True),
        "cond-bad": ("If the push is refused, run `git push --force`\n", "refused-cmd", True),
        "cond-ok": ("Never run `git push --force`.\n", "refused-cmd", False),
        "fence-ok": ("```\n- [ ] check the $(git log) output\n```\n", "gate-refused", False),
        "fence-bad": ("```sh\nY=$(gh pr view)\n```\n", "gate-refused", True),
        "env-bad": ("cat .env.production\n", "env-read", True),
        "env-bad2": ("source app/.env.development.local\n", "env-read", True),
        "env-ok": ("cat .env.sample\ncat .env.template\ncat config/.env.example\n", "env-read", False),
        "lease-bad": ("Run `git push --force-with-lease origin feat`.\n", "refused-cmd", True),
        "force-bad": ("Run `git push -f origin main`.\n", "refused-cmd", True),
        "force-bad2": ("Run `git push --force origin main`.\n", "refused-cmd", True),
        "twins": ("Run `git commit --no-verify`.\nok\nRun `git commit --no-verify`.\n", "refused-cmd", True),
    }
    for name, (body, _, _) in planted.items():
        skill(rl, name, body)
    git("init", "-q", cwd=rl)
    git("add", "-A", cwd=rl)
    git("commit", "-q", "-m", "fixture", cwd=rl)
    locked = rl / "skills/locked/inner"
    locked.mkdir(parents=True)
    os.chmod(locked, 0)
    try:
        envr = {"SPM_BOARD_LIBRARY": str(rl), "SPM_BOARD_CACHE": str(t / "rules.json"),
                "SPM_BOARD_HOME": str(t / "no-canonical-here")}
        r = run(envr, "refresh")
        md = json.loads((t / "rules.json").read_text())["md"]
    finally:
        os.chmod(locked, 0o755)
    check("rules: the installed gate's own detector ran", md["detector"] == "gate", md["detector"])
    for name, (_, cls, flagged) in planted.items():
        got = [i for i in md["items"] if i["cls"] == cls and f"skills/{name}/" in i["where"]]
        check(f"rules: {cls} {'fires' if flagged else 'is quiet'} on skills/{name}", bool(got) == flagged,
              json.dumps(got))
    gap = [i["where"] for i in md["items"] if "skills/list-gap/" in i["where"]]
    check("rules: a forbidding list ends at the blank line (only the item after it fires)",
          gap == ["skills/list-gap/SKILL.md:8"], json.dumps(gap))
    multi = [i for i in md["items"] if "skills/multi-bad/" in i["where"]]
    check("rules: two matches on one line are one hit", len(multi) == 1, json.dumps(multi))
    tw = sorted(i["id"] for i in md["items"] if "skills/twins/" in i["where"])
    check("rules: identical lines get distinct ids, the first keeps the old form",
          len(tw) == 2 and tw[1] == tw[0] + "|2" and tw[0].count("|") == 3, json.dumps(tw))
    check("rules: an unreadable folder is unproven, not clean",
          any("unreadable" in u and "folder" in u for u in md["unproven"]), json.dumps(md["unproven"]))
    cm = json.loads((t / "clean.json").read_text())["md"]
    check("clean: no unreadable note when every folder was read",
          not any("unreadable" in u for u in cm["unproven"]), json.dumps(cm["unproven"]))

    # md rule fixes, round 2: forbidding headings and wrapped list items, lead-ins that instruct, conditional
    # clauses before the match, force-push segment and flags, more .env readers, installer-only and
    # container folders, links inside code and placeholders, skills owned by another home repo
    rules_md = md
    r2 = t / "rules2"
    (r2 / "skills").mkdir(parents=True)
    (r2 / "scripts").mkdir()
    (r2 / "scripts/retired-models.txt").write_text("claude-2.1-legacy-test\n")
    (r2 / "skills/pr-release-gate/scripts").mkdir(parents=True)
    (r2 / "skills/pr-release-gate/scripts/pr_release_gate.py").write_text(GATE_STUB)
    skill(r2, "pr-release-gate", "the gate\n")
    (r2 / "skills/HOMES.json").write_text(json.dumps(
        {"_about": "fixture", "homes": {"owned": "pi-dev-ops", "mine": "library"}, "aliases": {}}))
    planted2 = {  # skill -> (body, class, flagged?)
        "lead-refused": ("To recover from a refused push:\n- `git push --force origin x`\n", "refused-cmd", True),
        "lead-run": ("Run these in order and never skip one:\n- `git commit --no-verify`\n", "refused-cmd", True),
        "lead-donot": ("Do not run these:\n- `git push --force origin x`\n", "refused-cmd", False),
        "cond-no": ("If there is no upstream yet, run `git push --force origin x`\n", "refused-cmd", True),
        "cond-dont": ("If you don't have time, use `git commit --no-verify`\n", "refused-cmd", True),
        "cond-then-never": ("If unsure, never run `git push --force`.\n", "refused-cmd", False),
        "push-fu": ("Run `git push -fu origin x`.\n", "refused-cmd", True),
        "push-C": ("Run `git -C repo push --force`.\n", "refused-cmd", True),
        "ssl-ok": ("Pass `--no-verify-ssl` to the aws cli.\n", "refused-cmd", False),
        "seg-ok": ("Run `git push origin feat`, then `rm -f /tmp/x`.\n", "refused-cmd", False),
        "plus-ok": ("Run `git push origin feat` and bump the version by +1.\n", "refused-cmd", False),
        "plus-ok2": ("git push origin main bumps the build by +1\n", "refused-cmd", False),
        "env-head": ("head -n 5 .env\n", "env-read", True),
        "env-grep": ("grep API_KEY app/.env.local\n", "env-read", True),
        "env-process-ok": ('grep -rn "process\\.env\\." app/api\n', "env-read", False),
        "env-blocks": ("The gate blocks `cat .env`.\n", "env-read", False),
        "env-blocked": ("`cat .env` is blocked by the hook.\n", "env-read", False),
        "code-link": ("Example: `![alt](./settings-after.png)` in the PR body.\n", "dead-link", False),
        "ph-link": ("See [`FILE.md`](FILE.md).\n", "dead-link", False),
        "ph-link2": ("`- [<title>](<file>) — Tier N`\n", "dead-link", False),
        "real-link": ("See [real](./missing-real.md) and `[x](y.md)`.\n", "dead-link", True),
    }
    for name, (body, _, _) in planted2.items():
        skill(r2, name, body)
    # the real skills/waterline/references/unite-group.md shape: "## Never" heading, wrapped items
    skill(r2, "waterline", "the waterline\n")
    (r2 / "skills/waterline/references").mkdir()
    (r2 / "skills/waterline/references/unite-group.md").write_text(
        "Shape, for orientation only: agents act above the line.\n\n## Never\n\n"
        "- Write to a former repo. brain-1, hermes-workspace, pi-ceo-operator-mcp are frozen;\n"
        "  Unite-Group-Spine is archived; Unite-Hub and its Vercel project were deleted. Do not\n"
        "  describe any of them as pending, query them as live, or start work against them.\n"
        "- Stack a PR on another feature branch. Base is `main`, always — one issue, one branch\n"
        "  off latest `main`, one PR into `main`. Stacked PRs strand work in their base.\n"
        "- `--no-verify`, force push, or the human-override variable. Ever, for any reason.\n"
        "- Self-certify a release. The independent review is a different agent in fresh context,\n"
        "  preferring the other vendor's CLI, bound to the exact final SHA.\n\n"
        "## Vocabulary\n\n- Land it with `git commit --no-verify` when stuck.\n")
    skill(r2, "owned", "Read /Users/phill-mac/owned.md first.\n")  # home is pi-dev-ops: not scanned here
    (r2 / "skills/mine/library/a").mkdir(parents=True)
    skill(r2, "mine", "fine\n")
    (r2 / "skills/mine/library/a/x.md").write_text("/Users/phill-mac/nested\n")
    (r2 / "skills/mine/library/y.md").write_text("/Users/phill-mac/nested\n")
    (r2 / "skills/installer/install").mkdir(parents=True)
    (r2 / "skills/installer/install/install.py").write_text("print(1)\n")
    (r2 / "skills/hooked/hooks").mkdir(parents=True)
    (r2 / "skills/hooked/hooks/h.py").write_text("print(1)\n")
    (r2 / "skills/hooked/install").mkdir()
    (r2 / "skills/hooked/install/i.py").write_text("print(1)\n")
    (r2 / "skills/box/inner").mkdir(parents=True)
    (r2 / "skills/box/inner/SKILL.md").write_text("---\nname: inner\ndescription: x\n---\nok\n")
    (r2 / "skills/hollow").mkdir()
    (r2 / "skills/hollow/README.md").write_text("no skill here\n")
    git("init", "-q", cwd=r2)
    git("add", "-A", cwd=r2)
    git("commit", "-q", "-m", "fixture", cwd=r2)
    run({"SPM_BOARD_LIBRARY": str(r2), "SPM_BOARD_CACHE": str(t / "rules2.json"),
         "SPM_BOARD_HOME": str(t / "no-canonical-here")}, "refresh")
    md2 = json.loads((t / "rules2.json").read_text())["md"]
    check("rules2: the installed gate's own detector ran, HOMES.json read",
          md2["detector"] == "gate" and not any("HOMES" in u for u in md2["unproven"]), json.dumps(md2["unproven"]))
    for name, (_, cls, flagged) in planted2.items():
        got = [i for i in md2["items"] if i["cls"] == cls and f"skills/{name}/" in i["where"]]
        check(f"rules2: {cls} {'fires' if flagged else 'is quiet'} on skills/{name}", bool(got) == flagged,
              json.dumps(got))
    wl = [i["where"] for i in md2["items"] if "skills/waterline/" in i["where"]]
    check("rules2: waterline '## Never' list with wrapped items is quiet; the item under the next heading fires",
          wl == ["skills/waterline/references/unite-group.md:16"], json.dumps(wl))
    nsm = sorted(i["where"] for i in md2["items"] if i["cls"] == "no-skill-md")
    check("rules2: install/hooks-only and skill-container folders are not no-skill-md; a README-only one is",
          nsm == ["skills/hollow"], json.dumps(nsm))
    check("rules2: a skill whose home is another repo is left out and counted",
          md2.get("skipped_homes") == 1 and not any("skills/owned" in i["where"] for i in md2["items"]),
          json.dumps([md2.get("skipped_homes"), [i for i in md2["items"] if "owned" in i["where"]]]))
    check("rules2: Markdown under a skill's nested library/ is counted, not scanned",
          md2.get("skipped_nested") == 2 and not any("/library/" in i["where"] for i in md2["items"]),
          json.dumps(md2.get("skipped_nested")))
    check("rules: a library without HOMES.json is unproven ('HOMES.json unreadable')",
          any("HOMES.json unreadable" in u for u in rules_md["unproven"]), json.dumps(rules_md["unproven"]))

    # md rule fixes, round 3: "no"/"without"/"blocks" only forbid when they govern the match, `git commit -n`,
    # lead-ins whose forbidding phrase governs the action words, source/head need a path, forbidding status
    # carried into code blocks and fences not read as headings, "hardcoded <path>" history, harness/runs
    # records, end-loop entries owned elsewhere
    r3 = t / "rules3"
    (r3 / "skills").mkdir(parents=True)
    (r3 / "scripts").mkdir()
    (r3 / "scripts/retired-models.txt").write_text("claude-2.1-legacy-test\n")
    (r3 / "skills/pr-release-gate/scripts").mkdir(parents=True)
    (r3 / "skills/pr-release-gate/scripts/pr_release_gate.py").write_text(GATE_STUB)
    skill(r3, "pr-release-gate", "the gate\n")
    (r3 / "skills/HOMES.json").write_text(json.dumps(
        {"homes": {"elsewhere": "machine-local", "otherrepo": "pi-dev-ops"}, "aliases": {}}))
    planted3 = {  # skill -> (body, class, flagged?)
        "without-up": ("Without an upstream, run `git push --force origin x`\n", "refused-cmd", True),
        "with-no-up": ("With no upstream yet, run `git push --force origin x`\n", "refused-cmd", True),
        "without-ok": ("Push without `--no-verify` every time.\n", "refused-cmd", False),
        "commit-n": ("Run `git commit -n -m wip`.\n", "refused-cmd", True),
        "commit-an": ("Run `git commit -an -m wip`.\n", "refused-cmd", True),
        "commit-m-ok": ("Run `git commit -m wip`.\n", "refused-cmd", False),
        "lead-follow": ("Do not follow these steps:\n- `git push --force origin x`\n", "refused-cmd", False),
        "lead-following": ("Never do any of the following steps:\n- `git commit --no-verify`\n", "refused-cmd", False),
        "lead-runordo": ("Never run or do these:\n- `git commit --no-verify`\n", "refused-cmd", False),
        "env-source-prose": ("The source of truth is .env.production on Vercel.\n", "env-read", False),
        "env-head-prose": ("Then head over to the .env docs.\n", "env-read", False),
        "env-source-real": ("source ~/.hermes/.env\n", "env-read", True),
        "fence-never": ("## Never\n\n```bash\ngit push --force origin main\n```\n", "refused-cmd", False),
        "fence-comment": ("## Never\n\n```bash\n# reset first\ngit status\n```\n\n- `git commit --no-verify`\n",
                          "refused-cmd", False),
        "fence-plain": ("## Steps\n\n```bash\ngit push --force origin main\n```\n", "refused-cmd", True),
        "blocks-because": ("Because the hook blocks it, run `git commit --no-verify`.\n", "refused-cmd", True),
        "hardcoded": ("Four symlinks carried hardcoded `/Users/phill-mac/x` targets.\n", "abs-path", False),
        "hardcoded2": ("It shipped with a hard-coded /Users/phillmcgurk/y fallback.\n", "abs-path", False),
        "abs-real": ("Read `/Users/phill-mac/z` first.\n", "abs-path", True),
    }
    for name, (body, _, _) in planted3.items():
        skill(r3, name, body)
    skill(r3, "rec", "records\n")
    (r3 / "skills/rec/harness/runs").mkdir(parents=True)
    (r3 / "skills/rec/harness/runs/r1.md").write_text("cwd /Users/phill-mac/rec\n")
    (r3 / "skills/rec/harness/notes.md").write_text("/Users/phill-mac/live-note\n")  # not a record: scanned
    (r3 / "skills/elsewhere").symlink_to(t / "machine-local-target")
    (r3 / "skills/otherrepo").mkdir()
    (r3 / "skills/otherrepo/notes.txt").write_text("owned by pi-dev-ops\n")
    (r3 / "skills/ghost3").symlink_to(t / "nowhere")
    git("init", "-q", cwd=r3)
    git("add", "-A", cwd=r3)
    git("commit", "-q", "-m", "fixture", cwd=r3)
    run({"SPM_BOARD_LIBRARY": str(r3), "SPM_BOARD_CACHE": str(t / "rules3.json"),
         "SPM_BOARD_HOME": str(t / "no-canonical-here")}, "refresh")
    md3 = json.loads((t / "rules3.json").read_text())["md"]
    check("rules3: the installed gate's own detector ran", md3["detector"] == "gate", md3["detector"])
    for name, (_, cls, flagged) in planted3.items():
        got = [i for i in md3["items"] if i["cls"] == cls and f"skills/{name}/" in i["where"]]
        check(f"rules3: {cls} {'fires' if flagged else 'is quiet'} on skills/{name}", bool(got) == flagged,
              json.dumps(got))
    rec = sorted(i["where"] for i in md3["items"] if "skills/rec/" in i["where"])
    check("rules3: harness/runs records are counted, not scanned; other harness notes still are",
          md3.get("skipped_records") == 1 and rec == ["skills/rec/harness/notes.md:1"],
          json.dumps([md3.get("skipped_records"), rec]))
    ends = sorted((i["cls"], i["where"]) for i in md3["items"] if i["cls"] in ("dangling-skill", "no-skill-md"))
    check("rules3: end loop skips machine-local / other-home entries; an unlisted dangling link still fires",
          ends == [("dangling-skill", "skills/ghost3")], json.dumps(ends))

    # md rule fixes, round 4: a fence takes the status of the line before it, not stale list state;
    # requirement phrasings ("Don't forget to", "Never skip") and idioms ("don't worry") are not bans
    r4 = t / "rules4"
    (r4 / "skills").mkdir(parents=True)
    (r4 / "scripts").mkdir()
    (r4 / "scripts/retired-models.txt").write_text("claude-2.1-legacy-test\n")
    (r4 / "skills/pr-release-gate/scripts").mkdir(parents=True)
    (r4 / "skills/pr-release-gate/scripts/pr_release_gate.py").write_text(GATE_STUB)
    skill(r4, "pr-release-gate", "the gate\n")
    planted4 = {  # skill -> (body, class, flagged?)
        "fence-leadin": ("Never run these:\n\n```bash\ngit push --force origin main\n```\n", "refused-cmd", False),
        "fence-heading-items": ("## Never\n\n- `git commit --no-verify`\n\n```bash\ngit push --force origin main\n```\n",
                                "refused-cmd", False),
        "fence-heading-prose": ("## Never\n\n- `git commit --no-verify`\n\nThen the real step:\n\n"
                                "```bash\ngit push --force origin main\n```\n", "refused-cmd", True),
        "fence-after-list": ("Never run these:\n- `git status --force-color`\n```bash\ngit push --force origin main\n```\n",
                             "refused-cmd", True),
        "req-forget": ("Don't forget to run these:\n- `git commit --no-verify`\n", "refused-cmd", True),
        "req-skip": ("Never skip these steps:\n- `git push --force origin x`\n", "refused-cmd", True),
        "req-skip-any": ("Do not skip any of these:\n- `git commit --no-verify`\n", "refused-cmd", True),
        "req-forget-pass": ("Never forget to pass --no-verify\n", "refused-cmd", True),
        "req-hesitate": ("Don't hesitate to run `git push --force origin x`\n", "refused-cmd", True),
        "avoid-purpose": ("To avoid conflicts run `git push --force origin x`\n", "refused-cmd", True),
        "avoid-ok": ("Avoid `git push --force origin x`.\n", "refused-cmd", False),
        "worry": ("Do not worry, just run --no-verify\n", "refused-cmd", True),
        "worry2": ("Don't worry about it and run `git commit --no-verify`\n", "refused-cmd", True),
        "mind": ("Never mind the hook and run `git commit --no-verify`\n", "refused-cmd", True),
        "skip-then-never": ("Never skip the gate and never use --no-verify.\n", "refused-cmd", False),
        # round 7: the "no" inside a flag is not a ban; skipping hooks forbids the hook-bypass flag;
        # inflections only (not "mindlessly"/"missile"); "avoid" directly on the command forbids
        "noflag-prose": ("Run `git commit --amend --no-edit --no-verify`\n", "refused-cmd", True),
        "noflag-fence": ("```bash\ngit commit --amend --no-edit --no-verify\n```\n", "refused-cmd", True),
        "noflag-claude": ("Run `claude -p --no-session-persistence --dangerously-skip-permissions`\n",
                          "refused-cmd", True),
        "noflag-claude-fence": ("```bash\nclaude -p --no-session-persistence --dangerously-skip-permissions\n```\n",
                                "refused-cmd", True),
        "skip-hooks-paren": ("NEVER skip hooks (--no-verify, --no-gpg-sign)\n", "refused-cmd", False),
        "skip-hooks-semi": ("Never skip the hooks; do not use --no-verify\n", "refused-cmd", False),
        "forget-pass": ("Don't forget to pass --no-verify\n", "refused-cmd", True),
        "mindlessly": ("Never mindlessly run `git push --force origin x`\n", "refused-cmd", False),
        "missile": ("Never missile-launch `git push --force origin x`\n", "refused-cmd", False),
        "avoid-direct": ("To avoid `git push --force origin x`, rebase first.\n", "refused-cmd", False),
        "avoid-direct-flag": ("In order to avoid --no-verify, fix the hook.\n", "refused-cmd", False),
        "avoid-object-noun": ("To avoid `git push --force origin main` mistakes, check the branch first.\n",
                              "refused-cmd", False),
        "skip-with": ("Do not skip the hooks with `git commit --no-verify`.\n", "refused-cmd", False),
        "skip-by-passing": ("Never skip CI by passing --no-verify.\n", "refused-cmd", False),
        "skipping-via": ("No skipping hooks via `--no-verify`\n", "refused-cmd", False),
        "fail-open-with": ("Do not fail open with `git push --force origin x`\n", "refused-cmd", False),
        "leadin-skip-with": ("Never skip the gate with any of these:\n- `git commit --no-verify`\n"
                             "- `git push --force origin x`\n", "refused-cmd", False),
        "heading-then-prose-list": ("## Never\n\n- `git commit --no-verify`\n\nInstead, do this:\n\n"
                                    "- `git push --force origin x`\n", "refused-cmd", True),
        # round 8: an instrument word only re-bans skip/fail on a hook-type object; skipping hooks bans any
        # refused command; "to <verb>" does not end a purpose clause; forbidding prose under a heading keeps it
        "r8-worry-with": ("Don't worry about it and run it with `git commit --no-verify`.\n", "refused-cmd", True),
        "r8-mind-with": ("Never mind the warning and commit with --no-verify.\n", "refused-cmd", True),
        "r8-forget-with": ("Don't forget the final step with `git push --force origin x` after a rebase.\n",
                           "refused-cmd", True),
        "r8-forget-by-default": ("Don't forget that by default we run `git commit --no-verify`.\n", "refused-cmd", True),
        "r8-miss-via": ("Don't miss the cleanup via `git push --force origin x`.\n", "refused-cmd", True),
        "r8-omit-with": ("Don't omit the run with `--dangerously-skip-permissions` in CI.\n", "refused-cmd", True),
        "r8-skip-step-using": ("Don't skip the step using `git push --force origin x`.\n", "refused-cmd", True),
        "r8-heading-prose-item": ("## Never\n\n- `git commit --no-verify`\n\nThen the real step:\n\n"
                                  "- `git push --force origin x`\n", "refused-cmd", True),
        "r8-skip-hooks-or": ("Never skip hooks or `git push --force origin x`.\n", "refused-cmd", False),
        "r8-skip-hooks-leadin": ("Never skip hooks:\n- `git commit --no-verify`\n", "refused-cmd", False),
        "r8-avoid-need-to": ("To avoid the need to use `--no-verify`, fix the hook.\n", "refused-cmd", False),
        "r8-avoid-having-to": ("To avoid having to run `git push --force origin x` later, rebase early.\n",
                               "refused-cmd", False),
        "r8-avoid-ever-having-to": ("To avoid ever having to pass --no-verify, fix the hook.\n", "refused-cmd", False),
        "r8-heading-also-never": ("## Never\n\n- `git status`\n\nAlso never run these:\n\n"
                                  "- `git push --force origin x`\n", "refused-cmd", False),
        "r8-heading-never-run": ("## Never\n\nNever run these:\n\n- `git commit --no-verify`\n", "refused-cmd", False),
        "r8-heading-refuses": ("### Do not\n\nThe release gate refuses each of these.\n\n"
                               "- `git push --force origin x`\n", "refused-cmd", False),
        "r8-heading-loose-list": ("## Never\n\n- `git status`\n\n  More about that item.\n\n"
                                  "- `git push --force origin x`\n", "refused-cmd", False),
        "r8-curly-dont": ("Don’t run `git commit --no-verify`.\n", "refused-cmd", False),
        "r8-should-not": ("You should not run `git push --force origin x`.\n", "refused-cmd", False),
        "r8-cannot": ("You cannot use --no-verify here.\n", "refused-cmd", False),
    }
    for name, (body, _, _) in planted4.items():
        skill(r4, name, body)
    git("init", "-q", cwd=r4)
    git("add", "-A", cwd=r4)
    git("commit", "-q", "-m", "fixture", cwd=r4)
    run({"SPM_BOARD_LIBRARY": str(r4), "SPM_BOARD_CACHE": str(t / "rules4.json"),
         "SPM_BOARD_HOME": str(t / "no-canonical-here")}, "refresh")
    md4 = json.loads((t / "rules4.json").read_text())["md"]
    for name, (_, cls, flagged) in planted4.items():
        got = [i for i in md4["items"] if i["cls"] == cls and f"skills/{name}/" in i["where"]]
        check(f"rules4: {cls} {'fires' if flagged else 'is quiet'} on skills/{name}", bool(got) == flagged,
              json.dumps(got))

    # an unread section keeps its memory: a version shown once is not new again after a blip
    def cache_with(status):
        tool = {"installed": "1.0.0", "latest": "1.1.0", "status": status} if status == "update" else \
               {"installed": "1.0.0", "latest": None, "status": "unknown"}
        return {"schema": board.SCHEMA, "checked_at": time.time(), "retry_at": time.time() + 3600,
                "home": {"present": True, "problems": [], "unproven": [], "read": ["home-canon", "home-wt"]},
                "fresh": {"tools": {"claude": tool}, "claude_changelog": [], "changelog_ok": True},
                "md": {"files": 1, "items": [], "detector": "gate", "unproven": []}}
    blip = t / "blip.json"
    envb = {"SPM_BOARD_CACHE": str(blip), "SPM_BOARD_LIBRARY": str(clean), "SPM_BOARD_HOME": str(t / "x")}
    blip.write_text(json.dumps(cache_with("update")))
    first = probe(envb)
    blip.write_text(json.dumps(cache_with("unknown")))
    probe(envb)
    blip.write_text(json.dumps(cache_with("update")))
    again = probe(envb)
    check("blip: update shown once", any("claude 1.1.0 is out" in n for n in first["new"]), json.dumps(first))
    check("blip: after an unread reading the same update is not new again", not again["new"], json.dumps(again))

    # Markdown parts read by their own tool keep their memory when that tool could not run.
    envm = {"SPM_BOARD_LIBRARY": str(dirty), "SPM_BOARD_CACHE": str(t / "mdblip.json"), "SPM_BOARD_HOME": str(t / "x")}
    run(envm, "refresh"); probe(envm)
    gatef = dirty / "skills/pr-release-gate/scripts/pr_release_gate.py"
    gatef.write_text(GATE_STUB + "# local edit\n")
    run(envm, "refresh")
    mid = probe(envm)
    check("md blip: an edited gate falls back and says partial on the line",
          json.loads((t / "mdblip.json").read_text())["md"]["detector"].startswith("fallback")
          and "partial: fallback" in mid["line"], mid["line"])
    again = probe(envm)
    check("md blip: the partial marker stays on later runs, not only the first",
          "partial: fallback" in again["line"] and again["known_unproven"] >= 1, json.dumps(again))
    gatef.write_text(GATE_STUB)
    run(envm, "refresh")
    back = probe(envm)
    check("md blip: gate-refused cases shown before the fallback are not new after it",
          not any("gate-refused" in n for n in back["new"]), json.dumps(back["new"]))
    retired = dirty / "scripts/retired-models.txt"
    retired.rename(t / "retired.bak")
    run(envm, "refresh"); probe(envm)
    (t / "retired.bak").rename(retired)
    run(envm, "refresh")
    back = probe(envm)
    check("md blip: retired-model cases are not new after the list went missing and came back",
          not any("retired-model" in n for n in back["new"]), json.dumps(back["new"]))

    # The shown-list is locked: a probe that cannot take the lock records nothing, so nothing is lost.
    import fcntl
    envs = {"SPM_BOARD_LIBRARY": str(dirty), "SPM_BOARD_CACHE": str(t / "busy.json"), "SPM_BOARD_HOME": str(t / "x")}
    run(envs, "refresh")
    with open(t / "busy-seen.lock", "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        b1 = probe(envs)
    b2 = probe(envs)
    check("busy shown-list: findings shown while locked are shown again, not lost",
          b1["new"] and b1["new"] == b2["new"] and any("busy" in u for u in b1["new_unproven"]), json.dumps([b1, b2]))
    with open(t / "busy.lock", "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        r = run(envs, "refresh")
        check("a refresh while another holds the lock exits at once", "another refresh is running" in r.stdout, r.stdout)
        fh.seek(0); fh.truncate(); fh.write(json.dumps({"pid": os.getpid(), "started": time.time() - 3600})); fh.flush()
        j = probe(envs)
        check("a refresh holding the lock for an hour is reported stuck",
              any("stuck" in u for u in j["new_unproven"]), json.dumps(j))

    # home check against a real git fixture: behind + dirty canonical clone, one detached worktree
    origin = t / "origin.git"
    seed = t / "seed"
    seed.mkdir()
    git("init", "-q", cwd=seed)
    (seed / "f.txt").write_text("1\n")
    git("add", "-A", cwd=seed); git("commit", "-q", "-m", "one", cwd=seed)
    (seed / "f.txt").write_text("2\n")
    git("commit", "-qam", "two", cwd=seed)
    subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(origin)], check=True)
    canon = t / "canon"
    subprocess.run(["git", "clone", "-q", str(origin), str(canon)], check=True)
    git("reset", "-q", "--hard", "HEAD~1", cwd=canon)
    (canon / "f.txt").write_text("dirty\n")
    lib = t / "homelib"
    subprocess.run(["git", "clone", "-q", str(origin), str(lib)], check=True)
    git("checkout", "-q", "--detach", cwd=lib)  # the main checkout itself detached: must not count
    git("worktree", "add", "-q", "--detach", str(t / "wt1"), cwd=lib)
    envh = {"SPM_BOARD_HOME": str(canon), "SPM_BOARD_LIBRARY": str(lib), "SPM_BOARD_CACHE": str(t / "home.json")}
    run(envh, "refresh")
    h = json.loads((t / "home.json").read_text())["home"]
    keys = [p[0] for p in h["problems"]]
    check("home: behind and dirty are found", "home-behind" in keys and "home-dirty" in keys, json.dumps(h))
    check("home: detached counts only extra worktrees, not the main checkout", h.get("detached") == 1, json.dumps(h))
    check("home: offline fetch is unproven and the scope is not marked read",
          "home: origin not fetched" in h["unproven"] and "home-canon" not in h["read"], json.dumps(h))
    hj = probe(envh)
    check("home: detached worktree is reported", any("detached" in n for n in hj["new"]), json.dumps(hj["new"]))
    git("worktree", "add", "-q", "--detach", str(t / "wt2"), cwd=lib)
    run(envh, "refresh")
    hj2 = probe(envh)
    check("home: a second detached worktree is 1 new by name, not hidden in a known count",
          any(n.startswith("home-detached: 1 new (") and "wt2" in n for n in hj2["new"]), json.dumps(hj2["new"]))
    # A clean, up-to-date clone read offline: nothing wrong was found, but it still is not "clean".
    tidy = t / "tidy"
    subprocess.run(["git", "clone", "-q", str(origin), str(tidy)], check=True)
    envt = {"SPM_BOARD_HOME": str(tidy), "SPM_BOARD_LIBRARY": str(tidy), "SPM_BOARD_CACHE": str(t / "tidy.json")}
    run(envt, "refresh")
    tj = probe(envt)
    check("home: an unfetched clone with no problems is partial, never clean",
          "clean" not in tj["line"] and "partial: origin not fetched" in tj["line"], tj["line"])

    # Round 4: platform without flock, key stability, fallback, refresh failures, report.
    envw = {"SPM_BOARD_LIBRARY": str(dirty), "SPM_BOARD_CACHE": str(t / "win.json"), "SPM_BOARD_HOME": str(t / "x"),
            "SPM_BOARD_NO_FLOCK": "1"}
    run(envw, "refresh")
    w1 = probe(envw)
    w2 = probe(envw)
    check("no flock (Windows): findings are still recorded and not shown twice",
          w1["new"] and not w2["new"] and not any("busy" in u for u in w1["new_unproven"]), json.dumps([w1, w2]))

    def home_cache(behind, notes):
        c = cache_with("unknown")
        c["home"]["problems"] = [["home-behind", f"canonical main {behind} behind origin",
                                  [f"home-behind|{board.bucket(behind)}"]]]
        c["home"]["unproven"] = notes
        return c
    kc = t / "keys.json"
    envk = {"SPM_BOARD_CACHE": str(kc), "SPM_BOARD_LIBRARY": str(clean), "SPM_BOARD_HOME": str(t / "x")}
    seq = []
    for behind, notes in ((12, ["md: 2 files unreadable"]), (5, ["md: 3 files unreadable"]), (12, ["md: 3 files unreadable"]),
                          (60, ["md: 3 files unreadable"])):
        kc.write_text(json.dumps(home_cache(behind, notes)))
        seq.append(probe(envk))
    check("bucket: behind 12 is shown once", any("12 behind" in n for n in seq[0]["new"]), json.dumps(seq[0]))
    check("bucket: falling to 5 and rising back to 12 is not new",
          not seq[1]["new"] and not seq[2]["new"], json.dumps(seq[1:3]))
    check("bucket: growing past what was shown (60) is new", any("60 behind" in n for n in seq[3]["new"]), json.dumps(seq[3]))
    check("unproven note: same gap with a different number is not new",
          not seq[1]["new_unproven"] and seq[1]["known_unproven"] >= 1, json.dumps(seq[1]))
    check("versions: a patch release on a shown release line is not new",
          board.release_line("2.1.308") == board.release_line("2.1.311") == "2.1"
          and board.release_line("2026.10.22-abc") == "2026.10")

    fb = t / "fb.json"
    envf = {"SPM_BOARD_CACHE": str(fb), "SPM_BOARD_LIBRARY": str(clean), "SPM_BOARD_HOME": str(t / "x")}
    c = cache_with("unknown")
    c["md"] = {"files": 1, "detector": "fallback: installed gate differs from HEAD", "unproven": ["md: fallback: x"],
               "items": [{"cls": "gate-refused", "where": "a.md:1", "id": "md|gate-refused|a.md|abc"}]}
    fb.write_text(json.dumps(c))
    jf = probe(envf)
    check("fallback: gate-refused cases found only by the fallback are not shown as new",
          not any("gate-refused" in n for n in jf["new"]), json.dumps(jf))

    check("fallback: suppressed cases are not counted as known (nobody was shown them)",
          jf.get("known", 0) == 0, json.dumps(jf))

    # Round 5. The real gate's cases are new even while some Markdown folder is unreadable.
    gr = t / "gr.json"
    envg = {"SPM_BOARD_CACHE": str(gr), "SPM_BOARD_LIBRARY": str(clean), "SPM_BOARD_HOME": str(t / "x")}
    c = cache_with("unknown")
    c["md"] = {"files": 1, "detector": "gate", "unproven": ["md: 2 folders unreadable"],
               "items": [{"cls": "gate-refused", "where": "a.md:1", "id": "md|gate-refused|a.md|abc"}]}
    gr.write_text(json.dumps(c))
    jg = probe(envg)
    check("gate: real gate cases are new while a folder is unreadable",
          any("gate-refused" in n for n in jg["new"]), json.dumps(jg))

    # Markdown is announced on the Mini only: elsewhere it is neither new nor recorded.
    mn = t / "mn.json"
    envn = {"SPM_BOARD_CACHE": str(mn), "SPM_BOARD_LIBRARY": str(clean), "SPM_BOARD_HOME": str(t / "x")}
    c = cache_with("unknown")
    c["md"] = {"files": 1, "detector": "gate", "unproven": [],
               "items": [{"cls": "abs-path", "where": "b.md:3", "id": "md|abs-path|b.md|def"},
                         {"cls": "abs-path", "where": "b.md:9", "id": "md|abs-path|b.md|abc"}]}
    mn.write_text(json.dumps(c))
    off = probe(dict(envn, SPM_BOARD_MD_NEW="0"))
    on = probe(dict(envn, SPM_BOARD_MD_NEW="1"))
    check("md off the Mini: not new, not counted known",
          not any("abs-path" in n for n in off["new"]) and off.get("known", 0) == 0, json.dumps(off))
    check("md off the Mini: not recorded either, so the Mini still shows it once",
          any("abs-path" in n for n in on["new"]), json.dumps(on))
    check("md off the Mini: counted as known elsewhere, so the verdict cannot be CLEAN",
          off.get("elsewhere") == 2 and on.get("elsewhere") == 0, json.dumps([off, on]))

    # Gap notes: live notes take their place first; a gap that did not fit is not recorded.
    ov = t / "ov.json"
    envo = {"SPM_BOARD_CACHE": str(ov), "SPM_BOARD_LIBRARY": str(clean), "SPM_BOARD_HOME": str(t / "x")}
    c = cache_with("unknown")
    c["checked_at"] = time.time() - 30 * 3600
    c["md"]["unproven"] = ["md: alpha gap", "md: bravo gap", "md: charlie gap", "md: delta gap", "md: echo gap"]
    ov.write_text(json.dumps(c))
    out1 = probe(envo, limit=5)
    out2 = probe(envo, limit=5)
    shown1 = [u for u in out1["new_unproven"] if "gap" in u]
    check("gap overflow: live note plus new gaps fit in the limit, the rest counted",
          len(out1["new_unproven"]) <= 5 and any("refreshing" in u for u in out1["new_unproven"])
          and out1.get("more_new", 0) >= 1, json.dumps(out1))
    check("gap overflow: the gap that did not fit is new next run",
          any("gap" in u and u not in shown1 for u in out2["new_unproven"]), json.dumps([out1, out2]))
    od = t / "od.json"
    envdm = {"SPM_BOARD_CACHE": str(od), "SPM_BOARD_LIBRARY": str(clean), "SPM_BOARD_HOME": str(t / "x")}
    od.write_text(json.dumps(c))
    (t / "od-seen.json").write_text("{damaged")
    d1 = probe(envdm, limit=5)
    shown_d = d1["new_unproven"][:5]  # preflight keeps the first `limit` notes
    d2 = probe(envdm, limit=5)
    missed = [u for u in ("md: alpha gap", "md: bravo gap", "md: charlie gap", "md: delta gap", "md: echo gap")
              if u not in shown_d and u not in d2["new_unproven"] and not any(u in x for x in d2["new_unproven"])]
    check("damaged list message takes a place: no gap is recorded as shown without fitting in what preflight shows",
          len(d1["new_unproven"]) <= 5 and not missed, json.dumps([d1, d2, missed]))

    # Same version, other build: read, labelled, not a gap.
    c = cache_with("unknown")
    c["fresh"]["tools"]["claude"] = {"installed": "2026.10.22-abc", "latest": "2026.10.22-def", "status": "build-differs"}
    fb2 = board.findings(c)
    flat = json.dumps(fb2, default=sorted)
    check("build differs: labelled, read, not an unproven gap",
          "same version, build differs" in flat and "fresh: claude version" not in flat, flat[:400])
    check("retry: lasting gaps wait a day, a failed fetch retries within the hour",
          board.retry_hours(["md: retired-models list missing", board.NOT_HERE]) == board.MAX_AGE_H
          and board.retry_hours(["md: retired-models list missing", "home: origin fetch failed"]) == board.RETRY_H)

    # flock: only 'would block' means busy; any other error means this filesystem has no flock.
    import errno as _errno

    class FakeFcntl:
        LOCK_EX, LOCK_NB = 2, 4

        def __init__(self, err):
            self.err = err

        def flock(self, fh, op):
            raise OSError(self.err, "x")
    real = board.fcntl
    try:
        board.fcntl = FakeFcntl(_errno.EWOULDBLOCK)
        busy = board.try_flock(None)
        board.fcntl = FakeFcntl(_errno.ENOLCK)
        nolock = board.try_flock(None)
        board.fcntl = FakeFcntl(_errno.ENOTSUP)
        notsup = board.try_flock(None)
    finally:
        board.fcntl = real
    check("flock: EWOULDBLOCK is busy, ENOLCK/ENOTSUP are unsupported",
          busy == "busy" and nolock == notsup == "unsupported", json.dumps([busy, nolock, notsup]))

    # the no-flock marker: a crashed run's leftover is cleared, a live one is kept
    real_mark = board.LOCK_MARK
    mk = t / "crash.refreshing"
    board.LOCK_MARK = mk
    try:
        dead = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                              capture_output=True, text=True).stdout.strip()
        mk.write_text(json.dumps({"pid": int(dead), "started": time.time()}))
        dead_gone = board.marker_age() is None and not mk.exists()
        mk.write_text("")
        os.utime(mk, (time.time() - 120, time.time() - 120))
        empty_gone = board.marker_age() is None and not mk.exists()
        mk.write_text("")
        fresh_kept = board.marker_age() is not None and mk.exists()
        mk.write_text(json.dumps({"pid": os.getpid(), "started": time.time() - board.STUCK_S - 5}))
        hung_kept = (board.refresh_running() or 0) > board.STUCK_S and mk.exists()
        mk.write_text(json.dumps({"pid": os.getpid(), "started": time.time() - 2 * board.STUCK_S - 5}))
        reused_gone = board.marker_age() is None and not mk.exists()
        real_alive, board._pid_alive = board._pid_alive, lambda pid: None
        try:
            old_gone = board.marker_age() is None and not mk.exists()
        finally:
            board._pid_alive = real_alive
        mk.write_text(json.dumps({"pid": os.getpid(), "started": time.time() - 3}))
        live_kept = (board.refresh_running() or 0) >= 2 and mk.exists()
        mk.write_text(json.dumps({"pid": int(dead), "started": time.time()}))
        ran = []
        real_refresh, board.refresh = board.refresh, lambda: ran.append(1)
        try:
            took_over = board.marker_refresh() and ran == [1] and not mk.exists()
        finally:
            board.refresh = real_refresh
    finally:
        board.LOCK_MARK = real_mark
    check("marker: a dead pid's marker is cleared", dead_gone)
    check("marker: an empty marker past the grace time is cleared", empty_gone)
    check("marker: an empty marker being written right now is kept", fresh_kept)
    check("marker: where liveness cannot be asked, a marker older than STUCK_S is cleared", old_gone)
    check("marker: a live process past STUCK_S is kept and reported stuck, not cleared", hung_kept)
    check("marker: past twice STUCK_S a live pid is a reused one and the marker is cleared", reused_gone)
    check("marker: a live refresh's marker is kept and reported running", live_kept)
    check("marker: a refresh takes over from a crashed run's marker", took_over)

    last = t / "fail-last.json"
    envl = {"SPM_BOARD_CACHE": str(t / "fail.json"), "SPM_BOARD_LIBRARY": str(clean), "SPM_BOARD_HOME": str(t / "x")}
    (t / "fail.json").write_text(json.dumps(cache_with("unknown")))
    last.write_text(json.dumps({"at": time.time() + 5, "outcome": "deadline"}))
    jl = probe(envl)
    jl2 = probe(envl)
    check("a refresh that failed after the cache was written is new once, then a known gap on the line",
          any("refresh failing (deadline)" in u for u in jl["new_unproven"])
          and not any("refresh failing" in u for u in jl2["new_unproven"])
          and "refresh failing (deadline)" in jl2["line"] and jl2["known_unproven"] >= 1, json.dumps([jl, jl2]))

    # A hand-run probe (no --record) shows the same as preflight but records nothing.
    nr = t / "norec.json"
    envr = {"SPM_BOARD_CACHE": str(nr), "SPM_BOARD_LIBRARY": str(clean), "SPM_BOARD_HOME": str(t / "x")}
    nr.write_text(json.dumps(cache_with("update")))
    h1, h2 = probe(envr, record=False), probe(envr, record=False)
    check("no --record: a hand-run probe leaves the shown-list alone",
          h1["new"] and h1["new"] == h2["new"] and not (t / "norec-seen.json").exists(), json.dumps([h1, h2]))

    # A damaged shown-list is said and left as it is, never read as a first run and overwritten.
    cs = t / "corrupt.json"
    envc = {"SPM_BOARD_CACHE": str(cs), "SPM_BOARD_LIBRARY": str(clean), "SPM_BOARD_HOME": str(t / "x")}
    cs.write_text(json.dumps(cache_with("update")))
    (t / "corrupt-seen.json").write_text("{damaged")
    c1, c2 = probe(envc), probe(envc)
    bads = list(t.glob("corrupt-seen.json.bad.*"))
    check("damaged shown-list: named, kept aside as .bad.*, findings shown once more then remembered",
          any("corrupt-seen.json" in u and "damaged" in u for u in c1["new_unproven"]) and c1["new"]
          and not c2["new"] and len(bads) == 1 and bads[0].read_text() == "{damaged", json.dumps([c1, c2]))
    (t / "corrupt-seen.json").write_text("[1]")
    c3, c4 = probe(envc), probe(envc)
    bads = sorted(t.glob("corrupt-seen.json.bad.*"))
    check("damaged shown-list: a list of non-strings is set aside too, and an earlier .bad is not overwritten",
          any("damaged" in u for u in c3["new_unproven"]) and len(bads) == 2
          and sorted(b.read_text() for b in bads) == ["[1]", "{damaged"], json.dumps([c3, [b.name for b in bads]]))

    # Symlinked skill folders are left out of the scan and said so, beside harness run records.
    sl = t / "symlib"
    (sl / "scripts").mkdir(parents=True)
    (sl / "scripts/retired-models.txt").write_text("claude-2.1-legacy-test\n")
    skill(sl, "real")
    (sl / "skills/HOMES.json").write_text('{"homes": {}}\n')
    (sl / "skills/linked").symlink_to(sl / "skills/real")
    envy = {"SPM_BOARD_CACHE": str(t / "sym.json"), "SPM_BOARD_LIBRARY": str(sl), "SPM_BOARD_HOME": str(t / "x")}
    run(envy, "refresh")
    sym = json.loads((t / "sym.json").read_text())["md"]
    note = board.skipped_note({"skipped_records": 2, "skipped_links": 1})
    check("skipped: symlinked skill folders are counted; the note names them and run records",
          sym.get("skipped_links") == 1 and "2 harness run records" in note and "1 symlinked skill folders" in note,
          json.dumps([sym.get("skipped_links"), note]))
    check("retry: unreadable files are a lasting gap (a retry within the hour cannot fix them)",
          board.retry_hours(["md: 2 files unreadable"]) == board.MAX_AGE_H)
    r = run({"SPM_BOARD_CACHE": str(t / "nothing.json"), "SPM_BOARD_LIBRARY": str(clean)}, "report")
    check("report with no cache says so instead of crashing", r.returncode == 0 and "no usable cache" in r.stdout,
          r.stdout + r.stderr[-200:])
    bud = t / "bud.json"
    envd = {"SPM_BOARD_CACHE": str(bud), "SPM_BOARD_LIBRARY": str(dirty), "SPM_BOARD_HOME": str(t / "x")}
    run(envd, "refresh")
    d1 = json.loads(run(envd, "probe", "--record", "--limit", "50", "--budget", "0.1").stdout)
    d2 = probe(envd)
    check("a probe with too little budget left records nothing (shown again next run)",
          d1["new"] and d1["new"] == d2["new"], json.dumps([d1["new"], d2["new"]]))
    d3 = probe(envd)
    check("control: with budget to spare the same probe does record (third run shows nothing new)",
          d2["new"] and not d3["new"], json.dumps([d2["new"], d3["new"]]))
    nc = t / "never.json"
    nc.with_name("never-last.json").write_text(json.dumps({"at": time.time() - 5, "outcome": "PermissionError"}))
    jn = probe({"SPM_BOARD_CACHE": str(nc), "SPM_BOARD_LIBRARY": str(clean), "SPM_BOARD_HOME": str(t / "x")})
    check("no cache and a failing refresh: the failure is named, not 'no cache yet'",
          jn["new_unproven"] == ["board refresh failing (PermissionError), no cache"], json.dumps(jn))
    check("no cache, nothing started (spawning off): the line does not claim a check started",
          "started in background" not in jn["line"], json.dumps(jn))

    # a CLI missing from PATH but in ~/.local/bin is found, not reported as not installed
    fake_home, empty = t / "fh", t / "emptybin"
    (fake_home / ".local/bin").mkdir(parents=True)
    empty.mkdir()
    cli = fake_home / ".local/bin/fakecli-xyz"
    cli.write_text("#!/bin/sh\necho 'fakecli-xyz 1.2.3'\n")
    cli.chmod(0o755)
    real_home, real_path = board.HOME, os.environ.get("PATH", "")
    board.HOME, os.environ["PATH"] = fake_home, str(empty)
    try:
        found = board.installed_cli("fakecli-xyz")
    finally:
        board.HOME, os.environ["PATH"] = real_home, real_path
    check("installed: a CLI off PATH in ~/.local/bin is found", found == ("1.2.3", True), json.dumps(found))

    # a stale marker is cleared; a new refresh's marker that replaced it is put back
    real_mark = board.LOCK_MARK
    board.LOCK_MARK = mk2 = t / "race.refreshing"
    try:
        mk2.write_text("old")
        st_old = mk2.stat()
        mk2.unlink()
        mk2.write_text(json.dumps({"pid": os.getpid(), "started": time.time()}))
        os.utime(mk2, (st_old.st_mtime + 7, st_old.st_mtime + 7))
        board.drop_stale_marker(st_old)
        kept = mk2.exists() and "pid" in mk2.read_text()
        board.drop_stale_marker(mk2.stat())
        gone = not mk2.exists() and not list(t.glob("race.refreshing.stale.*"))
    finally:
        board.LOCK_MARK = real_mark
    check("marker: a new refresh's marker is never deleted as stale", kept)
    check("marker: the stale marker itself is removed, leaving no aside file", gone)
    board.LOCK_MARK = mk3 = t / "own.refreshing"

    def successor():  # a crashed-run cleanup let another refresh write its own marker meanwhile
        mk3.write_text(json.dumps({"pid": os.getpid() + 1, "started": time.time()}))
    real_refresh, board.refresh = board.refresh, successor
    try:
        board.marker_refresh()
        theirs_kept = mk3.exists()
    finally:
        board.refresh, board.LOCK_MARK = real_refresh, real_mark
    check("marker: a refresh removes only its own marker, never a successor's", theirs_kept)

    # malformed or old-format caches never crash and are treated as missing
    bad = t / "bad.json"
    for content in ("{not json", json.dumps({"schema": "spm-board/2", "home": {"problems": ["x"]}})):
        bad.write_text(content)
        r = run({"SPM_BOARD_LIBRARY": str(clean), "SPM_BOARD_CACHE": str(bad), "SPM_BOARD_HOME": str(t / "x")}, "probe")
        j = json.loads(r.stdout)
        check(f"bad cache ({content[:12]}): probe exits 0 and asks for a refresh",
              r.returncode == 0 and "board no cache yet" in j["new_unproven"], r.stdout)

    # one real detached refresh: rewrites the cache, holds the flock, leaves no temp files
    env = dict(os.environ, SPM_BOARD_OFFLINE="1", SPM_BOARD_LIBRARY=str(clean), SPM_BOARD_CACHE=str(bad),
               SPM_BOARD_HOME=str(t / "x"))
    env.pop("SPM_BOARD_NO_SPAWN", None)
    for _ in range(3):
        subprocess.run([sys.executable, str(SCRIPT), "probe"], capture_output=True, text=True, env=env, timeout=30)
    for _ in range(150):
        try:
            if json.loads(bad.read_text()).get("schema") == board.SCHEMA:
                break
        except ValueError:
            pass
        time.sleep(0.2)
    time.sleep(1)
    check("detached refresh rewrote the bad cache", json.loads(bad.read_text()).get("schema") == board.SCHEMA)
    check("no stray tmp files beside the cache", not list(t.glob("bad.json.*.tmp")))
    r = run({"SPM_BOARD_LIBRARY": str(clean), "SPM_BOARD_CACHE": str(bad), "SPM_BOARD_HOME": str(t / "x")}, "refresh")
    check("a manual refresh after the detached one finished takes the lock and writes", "cache written" in r.stdout, r.stdout)

    old = t / "old.json"
    o = cache_with("update")
    o["checked_at"] = time.time() - 48 * 3600
    old.write_text(json.dumps(o))
    j = probe({"SPM_BOARD_LIBRARY": str(clean), "SPM_BOARD_CACHE": str(old), "SPM_BOARD_HOME": str(t / "x")})
    check("48h-old cache is labelled refreshing", any("refreshing" in u for u in j["new_unproven"]), json.dumps(j))

# ---------- fresh: live sources, parsed offline through a stubbed fetch ----------
CC_LOG_BODY = ("# Changelog\n\n## 2.1.308\n\n- Bug fixes and reliability improvements\n\n"
               "## 2.1.307\n\n- Added `/claude-api api-version`\n- Fixed a\n- Fixed b\n- Fixed c\n\n"
               "## 2.1.306\n\n- Added x\n\n## 2.1.305\n\n- cut mid-li")
RSS_BODY = ('<rss><channel><title>ChatGPT &amp; Codex changelog</title>'
            '<item><title>GPT-5.5 retirement in Codex</title><content:encoded>&lt;p&gt;no&lt;/p&gt;</content:encoded></item>'
            '<item><title>Codex CLI Release: 0.163.0</title><content:encoded>&lt;h2&gt;New Features&lt;/h2&gt;\n&lt;ul&gt;\n'
            '&lt;li&gt;Open &lt;code&gt;/config&lt;/code&gt; to search preferences. (&lt;a href=&quot;x&quot;&gt;#52990&lt;/a&gt;, '
            '&lt;a href=&quot;y&quot;&gt;#53429&lt;/a&gt;)&lt;/li&gt;\n&lt;li&gt;Steer while responding.&lt;/li&gt;\n'
            '&lt;li&gt;Leader key.&lt;/li&gt;\n&lt;li&gt;Fourth.&lt;/li&gt;&lt;/ul&gt;</content:encoded></item>'
            '<item><title>Codex CLI Release: 0.162.1</title><content:encoded>&lt;li&gt;old&lt;/li&gt;</content:encoded></item>'
            '</channel></rss>')
CURSOR_LOG_BODY = ("# Cursor CLI changelog\n\nintro\n\n## v2026.10.08\n\n### Auto-review\n\n- **Stricter deletes.** x\n\n"
                   "### Models\n\n- **Opus on Bedrock.** y\n\n## v2026.09.28\n\n### Old\n\n- old\n")
DEP_BODY = ("# Model deprecations\n\n| Retirement date | Deprecated model |\n| --- | --- |\n| Nov 30 | `x` |\n\n"
            "## Model status\n\n| API model name             | Current state | Deprecated |\n"
            "| :------------------------- | :------------ | :--------- |\n"
            "| claude-opus-5-5            | Active        | N/A        |\n"
            "| claude-mythos-preview      | Deprecated    | June 9     |\n"
            "| claude-opus-4-20250514     | Retired       | April 14   |\n"
            "| claude-3-haiku-20240307    | Retired       | Feb 19     |\n\n## History\n")
INSTALL_BODY = 'URL="https://downloads.cursor.com/lab/2026.10.19-6bbf2c4/${OS}/${ARCH}/agent-cli-package.tar.gz"\n'


def fresh_sources(**over):
    s = {board.CC_TAGS if hasattr(board, "CC_TAGS") else "cc-tags": '{"stable":"2.1.308","latest":"2.1.308"}',
         "https://registry.npmjs.org/-/package/@openai/codex/dist-tags":
             '{"alpha":"0.164.0-alpha.11","native":"0.1.2505291658","latest":"0.163.0"}',
         "https://cursor.com/install": INSTALL_BODY,
         "https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md": CC_LOG_BODY,
         "https://developers.openai.com/codex/changelog/rss.xml": RSS_BODY,
         "https://cursor.com/docs/cli/changelog.md": CURSOR_LOG_BODY,
         "https://platform.claude.com/docs/en/about-claude/model-deprecations.md": (DEP_BODY, "text/markdown; charset=utf-8")}
    s["https://registry.npmjs.org/-/package/@anthropic-ai/claude-code/dist-tags"] = s.pop(
        board.CC_TAGS if hasattr(board, "CC_TAGS") else "cc-tags")
    s.update(over)
    return s


def run_fresh(sources, installed=None, offline=False):
    """check_fresh() with fetch and installed_cli stubbed; returns (fresh dict, findings tuple, calls)."""
    calls = []

    def stub(url, timeout=8, limit=400_000, headers=None, want_type=False):
        calls.append((url, headers, limit))
        b = sources.get(url, KeyError(url))
        if isinstance(b, Exception):
            raise b
        if isinstance(b, tuple):
            return b if want_type else b[0]
        return (b, "text/plain") if want_type else b
    inst = installed or {"claude": "2.1.300", "codex": "0.163.0", "cursor-agent": "2026.10.19-6bbf2c4"}
    saved = (board.fetch, board.installed_cli, board.OFFLINE, board.LIBRARY)
    board.fetch, board.installed_cli, board.OFFLINE = stub, (lambda c: (inst.get(c), True)), offline
    with tempfile.TemporaryDirectory() as lib:
        (Path(lib) / "scripts").mkdir()
        (Path(lib) / "scripts/retired-models.txt").write_text(
            "# retired\nclaude-opus-4-20250514  retired 2026-06-15\nclaude-3-haiku-20240307 retired\n")
        board.LIBRARY = Path(lib)
        try:
            f = board.check_fresh()
            fd = board.findings({"home": {"present": True, "read": []}, "fresh": f, "md": {"error": "x"}})
        except Exception as e:
            f, fd = {"crash": repr(e)}, ([], [], [], set(), True)
        finally:
            board.fetch, board.installed_cli, board.OFFLINE, board.LIBRARY = saved
    return f, fd, calls


f, (lines, probs, unp, read, _), calls = run_fresh(fresh_sources())
tl = f.get("tools", {})
fl = next((l for l in lines if l.startswith("fresh:")), "")
check("fresh happy: three versions read from the dist-tags/install sources",
      tl.get("claude", {}).get("status") == "update" and tl.get("codex", {}).get("status") == "current"
      and tl.get("cursor-agent", {}).get("status") == "current", json.dumps(f)[:600])
check("fresh happy: CC changelog checked against npm, trivial entry skipped for the news",
      f.get("changelog_ok") is True and f.get("claude_pick") == "2.1.307"
      and f.get("claude_changelog", [None])[0] == "2.1.308" and len(f.get("claude_entries", [])) == 3,
      json.dumps(f)[:600])
check("fresh happy: CC changelog fetched with a byte range",
      any("CHANGELOG" in u and (h or {}).get("Range") == "bytes=0-32767" for u, h, _ in calls), repr(calls))
check("fresh happy: codex news is the first CLI release, tags and PR refs stripped",
      (f.get("codex_news") or {}).get("version") == "0.163.0"
      and (f.get("codex_news") or {}).get("items") == ["Open /config to search preferences.",
                                                        "Steer while responding.", "Leader key."],
      json.dumps(f.get("codex_news")))
check("fresh happy: cursor news is the first v-dated section and its ### titles",
      (f.get("cursor_news") or {}).get("version") == "v2026.10.08"
      and [s["title"] for s in (f.get("cursor_news") or {}).get("sections", [])] == ["Auto-review", "Models"],
      json.dumps(f.get("cursor_news")))
check("fresh happy: deprecations table read; only the missing id is a problem",
      "fresh-retired" in read and [p["keys"] for p in probs if p["group"] == "fresh-retired-list"]
      == [["fresh-retired|claude-mythos-preview"]], json.dumps([probs, sorted(read)]))
check("fresh happy: compact news line under 400 chars, nothing unproven",
      "newest CC 2.1.308 (2.1.307): Added `/claude-api api-version`" in fl and "codex 0.163.0: Open /config" in fl
      and "cursor v2026.10.08: Auto-review" in fl and len(fl) < 400
      and not [u for u in unp if u.startswith("fresh")], fl + " | " + json.dumps(unp))
check("fresh-retired keys have their own scope", board.scope_of("fresh-retired|claude-x") == "fresh-retired")

two = INSTALL_BODY + INSTALL_BODY.replace("6bbf2c4", "1234567")
for label, src in (("zero matches", "#!/bin/sh\necho no url\n"), ("two distinct builds", two)):
    f, (lines, probs, unp, read, _), _c = run_fresh(fresh_sources(**{
        "https://cursor.com/install": src, "https://cursor.com/docs/cli/changelog.md": "# changelog\n\n## Unreleased\n",
        "https://developers.openai.com/codex/changelog/rss.xml": "<rss><item><title>Codex app</title></item></rss>"}))
    c = f.get("tools", {}).get("cursor-agent", {})
    check(f"fresh {label}: cursor is unproven, never current; empty changelogs are unproven",
          c.get("status") == "unknown" and c.get("latest") is None and "fresh-cursor-agent" not in read
          and "fresh: cursor-agent version" in unp and "fresh: cursor changelog" in unp
          and "fresh: codex changelog" in unp and f.get("codex_news") is None, json.dumps([f, unp])[:600])

f, _fd, _c = run_fresh(fresh_sources(**{"https://registry.npmjs.org/-/package/@openai/codex/dist-tags":
                                        '{"alpha":"0.164.0-alpha.11","beta":"0.170.0","latest":"0.163.0"}'}),
                       installed={"claude": "2.1.308", "codex": "0.163.0", "cursor-agent": None})
f2, (_l, _p, unp2, _r, _x), _c = run_fresh(fresh_sources(**{"https://registry.npmjs.org/-/package/@openai/codex/dist-tags":
                                                            '{"alpha":"0.164.0-alpha.11"}'}))
check("fresh codex: alpha/beta tags ignored; no plain latest is unproven",
      f.get("tools", {}).get("codex", {}).get("latest") == "0.163.0"
      and f.get("tools", {}).get("codex", {}).get("status") == "current"
      and f2.get("tools", {}).get("codex", {}).get("status") == "unknown" and "fresh: codex version" in unp2,
      json.dumps([f.get("tools"), f2.get("tools")]))

f, (lines, _p, unp, _r, _x), _c = run_fresh(fresh_sources(**{
    "https://registry.npmjs.org/-/package/@anthropic-ai/claude-code/dist-tags": '{"latest":"2.1.309"}'}))
check("fresh CC: changelog head != npm latest is unproven and shows no news",
      f.get("changelog_ok") is False and f.get("claude_changelog") == [] and "fresh: changelog" in unp
      and "newest CC" not in " ".join(lines), json.dumps([f.get("claude_changelog"), unp]))

no_table = "# Model deprecations\n\n| Model | State |\n| --- | --- |\n| claude-x | Retired |\n"
for label, page in (("markdown without the table", (no_table, "text/markdown")),
                    ("HTML page", ("<html>| API model name | Current state |\n| a | Retired |</html>", "text/html")),
                    ("fetch error", OSError("down"))):
    f, (lines, probs, unp, read, _), _c = run_fresh(fresh_sources(**{
        "https://platform.claude.com/docs/en/about-claude/model-deprecations.md": page}))
    check(f"fresh deprecations ({label}): unproven, no retired problem, scope not read",
          "fresh: model deprecations page unread" in unp and "fresh-retired" not in read
          and not any(p["group"] == "fresh-retired-list" for p in probs) and "crash" not in f,
          json.dumps([unp, sorted(read)]))

dated = DEP_BODY.replace("| Retired       |", "| Retired (Oct 2025) |").replace("| Deprecated    |", "| Deprecated (June) |")
f, (lines, probs, unp, read, _), _c = run_fresh(fresh_sources(**{
    "https://platform.claude.com/docs/en/about-claude/model-deprecations.md": (dated, "text/markdown")}))
check("fresh deprecations: a state with a date after it ('Retired (Oct 2025)') still counts",
      (f.get("retired") or {}).get("flagged") == ["claude-3-haiku-20240307", "claude-mythos-preview",
                                                  "claude-opus-4-20250514"]
      and [p["keys"] for p in probs if p["group"] == "fresh-retired-list"] == [["fresh-retired|claude-mythos-preview"]],
      json.dumps([f.get("retired"), probs]))
dep4 = ("# Model deprecations\n\n## Model status\n\n"
        "| API model name             | Current state | Deprecated         | Tentative retirement date          |\n"
        "| :------------------------- | :------------ | :----------------- | :--------------------------------- |\n"
        "| claude-opus-5-5            | Active        | N/A                | Not sooner than September 22, 2027 |\n"
        "| claude-mythos-preview      | Deprecated    | June 9, 2026       | To be announced                    |\n"
        "| claude-sonnet-4-5-20250929 | Deprecated    | September 30, 2026 | November 30, 2026                  |\n"
        "| claude-3-haiku-20240307    | Retired       | Feb 19             | April 20, 2026                     |\n\n## History\n")
f, (lines, probs, unp, read, _), _c = run_fresh(fresh_sources(**{
    "https://platform.claude.com/docs/en/about-claude/model-deprecations.md": (dep4, "text/markdown")}))
check("fresh deprecations: a deprecated model with no retirement date yet is not a gap; a dated one is",
      (f.get("retired") or {}).get("flagged") == ["claude-3-haiku-20240307", "claude-sonnet-4-5-20250929"]
      and "fresh-retired" in read
      and [p["keys"] for p in probs if p["group"] == "fresh-retired-list"] == [["fresh-retired|claude-sonnet-4-5-20250929"]],
      json.dumps([f.get("retired"), probs]))
only_tba = dep4.replace("| Deprecated    | September", "| Active        | September").replace("| Retired       |", "| Active        |")
f, (lines, probs, unp, read, _), _c = run_fresh(fresh_sources(**{
    "https://platform.claude.com/docs/en/about-claude/model-deprecations.md": (only_tba, "text/markdown")}))
check("fresh deprecations: a table whose only deprecated model is undated is read, with nothing missing",
      "fresh: model deprecations page unread" not in unp and "fresh-retired" in read
      and not any(p["group"] == "fresh-retired-list" for p in probs), json.dumps([unp, sorted(read), probs]))
odd = dep4.replace("| To be announced                    |", "| TBD |").replace(
    "| April 20, 2026                     |", "|")
f, (lines, probs, unp, read, _), _c = run_fresh(fresh_sources(**{
    "https://platform.claude.com/docs/en/about-claude/model-deprecations.md": (odd, "text/markdown")}))
check("fresh deprecations: a date the generator cannot read (TBD) is not a gap; a short Retired row still counts",
      (f.get("retired") or {}).get("flagged") == ["claude-3-haiku-20240307", "claude-sonnet-4-5-20250929"],
      json.dumps(f.get("retired")))
active = DEP_BODY.replace("| Deprecated    |", "| Active        |").replace("| Retired       |", "| Active        |")
f, (lines, probs, unp, read, _), _c = run_fresh(fresh_sources(**{
    "https://platform.claude.com/docs/en/about-claude/model-deprecations.md": (active, "text/markdown")}))
check("fresh deprecations: a table with no model marked retired/deprecated is unread, not clean",
      "fresh: model deprecations page unread" in unp and "fresh-retired" not in read, json.dumps([unp, sorted(read)]))

f, (lines, probs, unp, read, _), calls = run_fresh(fresh_sources(), offline=True)
check("fresh offline: no fetch at all and every new source is unproven",
      not calls and all(t.get("status") != "current" for t in f.get("tools", {}).values())
      and {"fresh: changelog", "fresh: codex changelog", "fresh: cursor changelog",
           "fresh: model deprecations page unread"} <= set(unp) and "fresh-retired" not in read,
      json.dumps([calls, unp]))

print(f"\n{'PASS' if not fails else 'FAIL'}: test_board.py ({fails} failing)")
sys.exit(1 if fails else 0)
