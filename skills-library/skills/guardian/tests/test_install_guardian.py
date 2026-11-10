#!/usr/bin/env python3
"""Tests for install/install_guardian.py. HOME is always a temp dir. Run: python3 test_install_guardian.py"""
import os, shutil, subprocess, sys, tempfile, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
INST = os.path.join(os.path.dirname(HERE), "install", "install_guardian.py")


def run(home, *args):
    env = dict(os.environ, HOME=home, PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, INST, *args], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout


def test_dry_run_writes_nothing(tmp):
    rc, out = run(tmp, "--dry-run")
    assert rc == 0 and "would copy" in out, out
    assert not os.path.exists(os.path.join(tmp, ".local"))


def test_install_is_idempotent_and_backs_up_a_differing_file(tmp):
    bin_ = os.path.join(tmp, ".local", "bin"); os.makedirs(bin_)
    open(os.path.join(bin_, "jobs_lock.py"), "w").write("old\n")
    rc, out = run(tmp)
    assert rc == 0 and "backup     jobs_lock.py" in out, out
    baks = [n for n in os.listdir(bin_) if n.startswith("jobs_lock.py.bak-")]
    assert len(baks) == 1 and open(os.path.join(bin_, baks[0])).read() == "old\n"
    assert sorted(n for n in os.listdir(bin_) if ".bak-" not in n) == ["guardian-watcher.py", "jev-cap-watcher.py", "jobs_lock.py", "live_claude_drift.py"]
    rc, out = run(tmp)
    assert rc == 0 and out.count("unchanged") == 4 and "backup" not in out, out
    assert len([n for n in os.listdir(bin_) if ".bak-" in n]) == 1
    assert not os.path.exists(os.path.join(tmp, "Library"))   # launchd untouched
    assert os.stat(os.path.join(bin_, "live_claude_drift.py")).st_mode & 0o111   # launchd runs it


def test_symlinked_destination_is_refused_and_outside_file_untouched(tmp):
    bin_ = os.path.join(tmp, ".local", "bin"); os.makedirs(bin_)
    outside = os.path.join(tmp, "elsewhere.py")
    open(outside, "w").write("precious\n")
    os.symlink(outside, os.path.join(bin_, "guardian-watcher.py"))
    rc, out = run(tmp)
    assert rc != 0 and "refus" in out.lower() and "guardian-watcher.py" in out, (rc, out)
    assert open(outside).read() == "precious\n"
    assert os.path.islink(os.path.join(bin_, "guardian-watcher.py"))
    assert not [n for n in os.listdir(bin_) if ".bak-" in n]


def test_symlinked_destination_is_refused_in_dry_run_too(tmp):
    bin_ = os.path.join(tmp, ".local", "bin"); os.makedirs(bin_)
    outside = os.path.join(tmp, "elsewhere.py"); open(outside, "w").write("precious\n")
    os.symlink(outside, os.path.join(bin_, "jobs_lock.py"))
    rc, out = run(tmp, "--dry-run")
    assert rc != 0 and "refus" in out.lower(), (rc, out)


def test_dangling_symlink_destination_is_refused(tmp):
    other = os.path.join(tmp, "other"); os.makedirs(other)
    os.makedirs(os.path.join(tmp, ".local"))
    bin_ = os.path.join(tmp, ".local", "bin"); os.makedirs(bin_)
    inside_link = os.path.join(bin_, "jev-cap-watcher.py")
    os.symlink(os.path.join(other, "x.py"), inside_link)   # dangling link: still a link
    rc, out = run(tmp)
    assert rc != 0 and not os.path.exists(os.path.join(other, "x.py")), (rc, out)


def snapshot(root):
    out = []
    for d, ds, fs in os.walk(root):
        out += [os.path.join(d, n) for n in ds + fs]
    return sorted(out)


def _linked_case(tmp, link_local, dry):
    outside = os.path.join(tmp, "outside"); os.makedirs(outside)
    keep = os.path.join(outside, "keep.txt"); open(keep, "w").write("precious\n")
    home = os.path.join(tmp, "home"); os.makedirs(home)
    if link_local:
        os.symlink(outside, os.path.join(home, ".local"))
    else:
        os.makedirs(os.path.join(home, ".local"))
        os.symlink(outside, os.path.join(home, ".local", "bin"))
    before_out, before_home = snapshot(outside), snapshot(home)
    rc, out = run(home, *(("--dry-run",) if dry else ()))
    assert rc == 1 and "REFUSED" in out, (rc, out)
    assert open(keep).read() == "precious\n"
    assert snapshot(outside) == before_out, snapshot(outside)
    assert snapshot(home) == before_home, snapshot(home)


def test_symlinked_bin_dir_is_refused_and_nothing_written(tmp):
    _linked_case(tmp, link_local=False, dry=False)


def test_symlinked_dot_local_is_refused_and_nothing_written(tmp):
    _linked_case(tmp, link_local=True, dry=False)


def test_symlinked_bin_dir_is_refused_in_dry_run(tmp):
    _linked_case(tmp, link_local=False, dry=True)


def test_symlinked_dot_local_is_refused_in_dry_run(tmp):
    _linked_case(tmp, link_local=True, dry=True)


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        tmp = tempfile.mkdtemp(prefix="guardian-inst-test-")
        try:
            fn(tmp); print("PASS " + name)
        except BaseException:  # noqa: BLE001
            failed += 1; print("FAIL %s\n%s" % (name, traceback.format_exc()))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
