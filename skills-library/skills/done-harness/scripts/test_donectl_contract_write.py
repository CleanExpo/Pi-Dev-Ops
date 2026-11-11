"""Controls for RA-8141: `criteria put` and `contract set` write the DRAFT contract.

Headless Claude Code refuses Write/Edit under .claude/, so an unattended run could open a
work item (`start`) but never author its criteria. These commands let the contract be
written through donectl itself, the one Bash path the mutation gate already admits.
Each test builds a throwaway git repo and drives donectl's CLI as a subprocess.
    python3 skills/done-harness/scripts/test_donectl_contract_write.py   (exit 1 on failure)
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
DONECTL = os.path.join(HERE, "donectl.py")
sys.path.insert(0, HERE)
import donectl  # noqa: E402


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True)


def run(repo, *args):
    p = subprocess.run([sys.executable, DONECTL, *args], cwd=repo, capture_output=True,
                       text=True, env={**os.environ, "HOME": os.path.join(repo, "..", "home")})
    try:
        out = json.loads(p.stdout)
    except ValueError:
        out = {"raw": p.stdout, "stderr": p.stderr}
    return out, p.returncode


def make_repo(tmp):
    r = os.path.join(tmp, "repo")
    os.makedirs(r)
    os.makedirs(os.path.join(tmp, "home"))
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "t")
    open(os.path.join(r, "a.txt"), "w").write("a\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "init")
    out, rc = run(r, "init")
    assert rc == 0, out
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "done tree")
    out, rc = run(r, "start", "probe goal")
    assert rc == 0, out
    return r, out["contract_path"]


def contract(path):
    return json.load(open(path))


def t_criteria_put_writes_and_locks(r, cpath):
    out, rc = run(r, "criteria", "put", "--id", "C1", "--text", "a.txt exists",
                  "--recipe", "test -f a.txt")
    assert rc == 0, out
    c = contract(cpath)["criteria"]
    assert c == [{"id": "C1", "text": "a.txt exists", "recipe": "test -f a.txt"}], c
    out, rc = run(r, "lock")
    assert rc == 0 and out["contract_status"] == "LOCKED", out
    out, rc = run(r, "verify")
    assert rc == 0, out


def t_timeout_is_validated_and_kept(r, cpath):
    out, rc = run(r, "criteria", "put", "--id", "C1", "--text", "t", "--recipe", "true",
                  "--timeout", "0")
    assert rc == 2, out
    out, rc = run(r, "criteria", "put", "--id", "C1", "--text", "t", "--recipe", "true",
                  "--timeout", "60")
    assert rc == 0, out
    assert contract(cpath)["criteria"][0]["timeout"] == 60


def t_duplicate_id_refused_unless_replace(r, cpath):
    assert run(r, "criteria", "put", "--id", "C1", "--text", "t", "--recipe", "true")[1] == 0
    out, rc = run(r, "criteria", "put", "--id", "C1", "--text", "u", "--recipe", "false")
    assert rc == 2 and "already" in out["error"], out
    out, rc = run(r, "criteria", "put", "--id", "C1", "--text", "u", "--recipe", "false",
                  "--replace")
    assert rc == 0, out
    c = contract(cpath)["criteria"]
    assert len(c) == 1 and c[0]["text"] == "u", c


def t_missing_fields_refused(r, cpath):
    for args in (["--text", "t", "--recipe", "true"], ["--id", "C1", "--recipe", "true"],
                 ["--id", "C1", "--text", "t"], ["--id", " ", "--text", "t", "--recipe", "x"]):
        out, rc = run(r, "criteria", "put", *args)
        assert rc == 2, (args, out)
    assert contract(cpath)["criteria"] == []


def t_locked_contract_is_never_edited(r, cpath):
    assert run(r, "criteria", "put", "--id", "C1", "--text", "t", "--recipe", "true")[1] == 0
    assert run(r, "lock")[1] == 0
    before = open(cpath).read()
    out, rc = run(r, "criteria", "put", "--id", "C2", "--text", "t", "--recipe", "true")
    assert rc == 1 and "LOCKED" in out["error"], out
    src = os.path.join(r, "..", "c.json")
    json.dump({"criteria": [{"id": "X", "text": "t", "recipe": "true"}]}, open(src, "w"))
    out, rc = run(r, "contract", "set", "--from", src)
    assert rc == 1 and "LOCKED" in out["error"], out
    assert open(cpath).read() == before


def t_contract_set_replaces_criteria_only(r, cpath):
    before = contract(cpath)
    src = os.path.join(r, "..", "c.json")
    crit = [{"id": "C1", "text": "one", "recipe": "true"},
            {"id": "C2", "statement": "two", "recipe": "true", "timeout": 30}]
    json.dump({"criteria": crit, "work_id": "w_forged", "goal": "forged"}, open(src, "w"))
    out, rc = run(r, "contract", "set", "--from", src)
    assert rc == 0, out
    after = contract(cpath)
    assert after["criteria"] == crit, after
    for k in ("work_id", "goal", "identity_key", "baseline_observed", "version"):
        assert after[k] == before[k], k
    assert run(r, "lock")[1] == 0


def t_contract_set_accepts_bare_list(r, cpath):
    src = os.path.join(r, "..", "c.json")
    json.dump([{"id": "C1", "text": "one", "recipe": "true"}], open(src, "w"))
    assert run(r, "contract", "set", "--from", src)[1] == 0
    assert len(contract(cpath)["criteria"]) == 1


def t_contract_set_validates_like_lock(r, cpath):
    src = os.path.join(r, "..", "c.json")
    bad_sets = [
        [],
        [{"id": "C1", "text": "", "recipe": "true"}],
        [{"id": "C1", "text": "t", "recipe": "true"}, {"id": "C1", "text": "u", "recipe": "true"}],
        [{"id": "C1", "text": "t", "recipe": "true", "timeout": 99999}],
        [{"id": "C1", "text": "t", "recipe": {"cmd": "true"}}],
        ["not an object"],
    ]
    for crit in bad_sets:
        json.dump({"criteria": crit}, open(src, "w"))
        out, rc = run(r, "contract", "set", "--from", src)
        assert rc == 2, (crit, out)
    open(src, "w").write("{not json")
    out, rc = run(r, "contract", "set", "--from", src)
    assert rc == 2, out
    out, rc = run(r, "contract", "set", "--from", src + ".missing")
    assert rc == 2, out
    assert contract(cpath)["criteria"] == []


def t_no_active_work_refused(r, cpath):
    git(r, "checkout", "-q", "-b", "other")
    out, rc = run(r, "criteria", "put", "--id", "C1", "--text", "t", "--recipe", "true")
    assert rc == 1 and "start" in out["error"], out


def t_gate_admits_the_new_commands(r, cpath):
    # Positive control: the name `add` WOULD be refused ("dd " is on the denylist), which is
    # why the verb is `put`. If this ever starts passing, the denylist changed; re-check.
    assert not donectl.command_is_donectl(
        "%s %s criteria add --id C1" % (shlex.quote(shutil.which("python3")), shlex.quote(DONECTL)))
    for cmd in ('python3 %s criteria put --id C1 --text "a (b) #c" --recipe "test -f a.txt && true"' % shlex.quote(DONECTL),
                "python3 %s contract set --from /tmp/c.json" % shlex.quote(DONECTL)):
        assert donectl.command_is_donectl(cmd.replace("python3", shlex.quote(shutil.which("python3")), 1)) or \
            donectl.command_is_donectl(cmd), cmd




def t_authoring_cannot_land_after_lock_wins_a_race(r, cpath):
    # review r1 P1: pause an authoring write between reading the DRAFT and saving it, let
    # `lock` run meanwhile; the locked bytes must still be exactly what got written.
    import threading
    out, rc = run(r, "criteria", "put", "--id", "C1", "--text", "t", "--recipe", "true")
    assert rc == 0, out
    old_home, old_draft = os.environ.get("HOME"), donectl._draft_contract
    os.environ["HOME"] = os.path.join(r, "..", "home")
    drafted = threading.Event()

    def slow_draft(*a, **kw):
        res = old_draft(*a, **kw)
        drafted.set()
        time.sleep(1.0)
        return res

    donectl._draft_contract = slow_draft
    try:
        res = {}
        w = threading.Thread(target=lambda: res.setdefault("w", donectl.criteria_add(
            "C2", "t2", "true", cwd=r)))
        w.start()
        assert drafted.wait(5)
        lk = threading.Thread(target=lambda: res.setdefault("l", donectl.lock(cwd=r)))
        lk.start()
        w.join(10)
        lk.join(10)
    finally:
        donectl._draft_contract = old_draft
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home
    lockj = json.load(open(os.path.join(os.path.dirname(cpath), "lock.json")))
    assert lockj["contract_digest"] == donectl.digest(contract(cpath)), (res, contract(cpath))
    out, rc = run(r, "status")
    assert "STALE" not in json.dumps(out), out


def t_race_serialised_without_fcntl(r, cpath):
    # review r2 P1: the no-fcntl path (Windows) must serialise too.
    saved = sys.modules.get("fcntl")
    sys.modules["fcntl"] = None
    try:
        t_authoring_cannot_land_after_lock_wins_a_race(r, cpath)
    finally:
        if saved is None:
            sys.modules.pop("fcntl", None)
        else:
            sys.modules["fcntl"] = saved


def _active_path(r):
    return os.path.join(r, ".claude", "done", "ACTIVE.json")


def t_active_mapping_cannot_escape_done_tree(r, cpath):
    # review r2 P1: a tampered ACTIVE.json must not steer a write outside root/work.
    outside = os.path.join(r, "..", "outside")
    os.makedirs(outside)
    shutil.copy(cpath, os.path.join(outside, "contract.json"))
    before = open(os.path.join(outside, "contract.json")).read()
    a = json.load(open(_active_path(r)))
    wid = os.path.basename(os.path.dirname(cpath))
    raw = json.dumps(a).replace(json.dumps(wid), json.dumps(os.path.abspath(outside)))
    assert raw != json.dumps(a), a
    open(_active_path(r), "w").write(raw)
    out, rc = run(r, "criteria", "put", "--id", "C1", "--text", "t", "--recipe", "true")
    assert rc != 0, out
    assert open(os.path.join(outside, "contract.json")).read() == before


def t_foreign_contract_refused(r, cpath):
    c = contract(cpath)
    c["identity_key"] = "someone-else"
    json.dump(c, open(cpath, "w"))
    out, rc = run(r, "criteria", "put", "--id", "C1", "--text", "t", "--recipe", "true")
    assert rc == 1 and "does not belong" in out["error"], out


def t_unreadable_lock_still_locked(r, cpath):
    # review r2 P1: a present-but-corrupt lock.json is still a lock.
    assert run(r, "criteria", "put", "--id", "C1", "--text", "t", "--recipe", "true")[1] == 0
    assert run(r, "lock")[1] == 0
    open(os.path.join(os.path.dirname(cpath), "lock.json"), "w").write("{not json")
    before = open(cpath).read()
    out, rc = run(r, "criteria", "put", "--id", "C2", "--text", "t", "--recipe", "true")
    assert rc == 1 and "LOCKED" in out["error"], out
    assert open(cpath).read() == before


def t_symlinked_work_dir_refused(r, cpath):
    # review r3 P1: `work` itself a symlink to outside the done root.
    work = os.path.dirname(os.path.dirname(cpath))
    outside = os.path.join(r, "..", "outside-work")
    shutil.move(work, outside)
    os.symlink(os.path.abspath(outside), work)
    oc = os.path.join(outside, os.path.basename(os.path.dirname(cpath)), "contract.json")
    before = open(oc).read()
    out, rc = run(r, "criteria", "put", "--id", "C1", "--text", "t", "--recipe", "true")
    assert rc != 0, out
    src = os.path.join(r, "..", "c.json")
    json.dump([{"id": "X", "text": "t", "recipe": "true"}], open(src, "w"))
    out, rc = run(r, "contract", "set", "--from", src)
    assert rc != 0, out
    assert open(oc).read() == before


def t_tmp_symlink_not_followed(r, cpath):
    # review r3 P1: a planted contract.json.tmp symlink must never receive the body.
    victim = os.path.join(r, "..", "victim.txt")
    open(victim, "w").write("SECRET\n")
    os.symlink(os.path.abspath(victim), cpath + ".tmp")
    out, rc = run(r, "criteria", "put", "--id", "C1", "--text", "t", "--recipe", "true")
    assert open(victim).read() == "SECRET\n"
    if rc == 0:
        assert not os.path.islink(cpath) and contract(cpath)["criteria"][0]["id"] == "C1"


def _lockdir(r):
    return os.path.join(r, "..", "home", ".cache", "donectl", "contract-locks")


def t_lock_file_symlink_not_followed(r, cpath):
    # review r4 P1: a planted <key>.lock symlink must not truncate an outside file.
    import hashlib
    d = _lockdir(r)
    os.makedirs(d, exist_ok=True)
    key = hashlib.sha256(os.path.realpath(os.path.join(r, ".claude", "done")).encode()).hexdigest()[:24]
    victim = os.path.join(r, "..", "victim.txt")
    open(victim, "w").write("SECRET\n")
    os.symlink(os.path.abspath(victim), os.path.join(d, key + ".lock"))
    out, rc = run(r, "criteria", "put", "--id", "C1", "--text", "t", "--recipe", "true")
    assert rc != 0, out
    assert open(victim).read() == "SECRET\n"


def t_lock_dir_symlink_refused(r, cpath):
    d = _lockdir(r)
    os.makedirs(os.path.dirname(d), exist_ok=True)
    outside = os.path.join(r, "..", "outside-locks")
    os.makedirs(outside)
    os.symlink(os.path.abspath(outside), d)
    out, rc = run(r, "criteria", "put", "--id", "C1", "--text", "t", "--recipe", "true")
    assert rc != 0, out
    assert os.listdir(outside) == [], os.listdir(outside)


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("t_")]


def main():
    failed = 0
    for t in TESTS:
        tmp = tempfile.mkdtemp(prefix="donectl-cw-")
        try:
            r, cpath = make_repo(tmp)
            t(r, cpath)
            print("PASS", t.__name__)
        except Exception:
            failed += 1
            print("FAIL", t.__name__)
            traceback.print_exc()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print("%d/%d passed" % (len(TESTS) - failed, len(TESTS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
