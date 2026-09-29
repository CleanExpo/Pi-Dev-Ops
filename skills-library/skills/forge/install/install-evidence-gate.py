#!/usr/bin/env python3
"""Idempotently install the forge fresh-evidence Stop hook on this machine.

Copies 04_evidence_gate.py into ~/.claude/hooks/Stop/ and registers it in
settings.json after 03_quality_gate (or at the end of the first Stop group).
Safe to re-run: does nothing if already installed. Run by bootstrap.sh, or直接:
  python3 ~/.claude/skills/forge/install/install-evidence-gate.py
"""
import json, os, shutil, subprocess, sys, tempfile

HOME = os.environ["HOME"]
INSTALL_DIR = os.path.join(HOME, ".claude", "skills", "forge", "install")
SRC = os.path.join(INSTALL_DIR, "04_evidence_gate.py")
HOOKS_DIR = os.path.join(HOME, ".claude", "hooks")
DST_DIR = os.path.join(HOOKS_DIR, "Stop")
DST = os.path.join(DST_DIR, "04_evidence_gate.py")
# The gate imports hook_failure from the hooks dir above it. Installing the gate
# without it leaves a working hook whose failures go to stderr, which nothing reads —
# a gate that could not run then looks exactly like one that passed. That is the
# failure this gate exists to prevent, so the installer ships both or neither.
DEP_SRC = os.path.join(INSTALL_DIR, "hook_failure.py")
DEP_DST = os.path.join(HOOKS_DIR, "hook_failure.py")
SETTINGS = os.path.join(HOME, ".claude", "settings.json")
CMD = f"/usr/bin/env python3 {DST}"

def atomic_install(src, dst):
    """Replace dst with src's contents atomically, or not at all.

    shutil.copyfile opens the destination for truncating replacement, so an I/O
    error, a full disk, or an interruption mid-write leaves the LIVE registered gate
    empty or half-written — a worse state than the one being upgraded from, and it
    disables an enforcement hook silently. Found by independent review 2026-08-29.

    Writing a temp sibling in the destination directory (same filesystem, so
    os.replace is atomic) means a reader ever only sees the whole old file or the
    whole new one. fsync before the rename so the rename cannot land ahead of the
    data it points at.
    """
    d = os.path.dirname(dst)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".install-tmp-")
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as f:
            shutil.copyfileobj(f, out)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, 0o755)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def probe(gate_path):
    """Run a candidate gate exactly as the registered hook runs it.

    Returns None when the candidate is sound, else the reason it is not.

    Three ways this probe could pass while the hook was broken, all found by
    independent review on 2026-08-29 and all closed here:
      1. SKIP_EVIDENCE_GATE=1 in the installer's environment made the gate return
         before it ever touched hook_failure, so a broken import yielded empty stderr
         and the probe read as a pass. This was first closed HERE, by stripping the
         variable for the probe's own invocation. It is now closed one level down
         instead: the escape hatch was removed from the gate itself on 29/08/2026, so
         there is nothing left to strip and the filter has been taken out. Do not put
         it back as belt-and-braces -- a line that cannot be shown to defend anything
         reads as coverage and is not. The control that replaced it is the sabotage
         evidence-gate:env-bypass-restored in positive_control.py, which reinstates the
         hatch and requires the suite to go red through
         test_skip_env_var_no_longer_switches_the_gate_off.
      2. sys.executable is not necessarily the interpreter the hook runs under —
         CMD invokes `/usr/bin/env python3`. Installing from a virtualenv would
         probe a different Python with a different sys.path than production.
      3. Absence of the fallback markers was treated as success. A gate that dies
         before main() — a SystemExit at import, a signal, any crash — also emits no
         markers. Absence of a bad sign is not a good sign, so success now requires a
         POSITIVE sentinel: `{}` on stdin must produce the absent-transcript
         systemMessage, which only a gate that imported cleanly and reached main()
         can emit. Exit status is checked too.
    """
    env = dict(os.environ)
    try:
        r = subprocess.run(["/usr/bin/env", "python3", gate_path], input="{}",
                           capture_output=True, text=True, timeout=30, env=env)
    except subprocess.TimeoutExpired:
        return "gate did not terminate within 30s"
    if "[hook-failure:no-module]" in r.stderr or "[hook-skip:no-module]" in r.stderr:
        return "cannot import hook_failure — failures would go unlogged"
    if r.returncode != 0:
        return f"gate exited {r.returncode}: {(r.stderr or '').strip()[:200]}"
    if "transcript_path absent" not in r.stdout:
        return ("gate produced no execution sentinel — it did not reach main(); "
                f"stdout={(r.stdout or '').strip()[:120]!r}")
    return None


def main():
    if not os.path.exists(SRC):
        print(f"skip: source hook not found at {SRC}"); return 0
    # A missing dependency is fatal here, not a warning. It used to warn and carry on,
    # letting the probe decide — but the probe only proves `hook_failure` was
    # IMPORTABLE, and after <stage> the interpreter searches the rest of sys.path.
    # An ambient module of that name (PYTHONPATH, site-packages, the working
    # directory) satisfied the import and the sentinel, so the installer registered a
    # gate whose reporter came from somewhere it never declared and may not exist on
    # the next run. Absence of DEP_SRC is already known here; refuse on it directly
    # rather than treating import-resolution-from-anywhere as proof of installation.
    # Found by independent review 2026-08-29.
    if not os.path.exists(DEP_SRC):
        print(f"FAIL: required dependency missing at {DEP_SRC}")
        print("nothing was installed or registered; any existing hook is untouched")
        return 1

    # Stage and probe BEFORE replacing anything. The previous version copied over the
    # live gate first, so on an upgrade a failed probe returned 1 having already
    # overwritten a working hook with the broken candidate — leaving it registered and
    # active. The fresh-install tests could not see this, because on a fresh install
    # there is nothing to clobber. Found by independent review 2026-08-29.
    # Layout mirrors production: the gate resolves hook_failure from its parent's
    # parent, so the candidate must sit at <stage>/Stop/ with the module at <stage>/.
    stage = tempfile.mkdtemp(prefix="evidence-gate-stage-")
    try:
        stage_stop = os.path.join(stage, "Stop")
        os.makedirs(stage_stop)
        stage_gate = os.path.join(stage_stop, "04_evidence_gate.py")
        shutil.copyfile(SRC, stage_gate)
        os.chmod(stage_gate, 0o755)
        shutil.copyfile(DEP_SRC, os.path.join(stage, "hook_failure.py"))

        reason = probe(stage_gate)
        if reason:
            print(f"FAIL: {reason}")
            print("nothing was installed or registered; any existing hook is untouched")
            return 1

        os.makedirs(DST_DIR, exist_ok=True)
        # Dependency FIRST, then the gate. If the run dies between them, the machine
        # is left with the new module and the old gate — both of which work. The other
        # order leaves a new gate whose module is missing or stale, which is precisely
        # the ship-both-or-neither state this installer exists to prevent.
        atomic_install(DEP_SRC, DEP_DST)
        atomic_install(stage_gate, DST)
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    if not os.path.exists(SETTINGS):
        print("note: no settings.json — hook copied but not registered (register manually)"); return 0
    s = json.load(open(SETTINGS))
    stop = s.setdefault("hooks", {}).setdefault("Stop", [])
    existing = [h.get("command", "") for grp in stop for h in grp.get("hooks", [])]
    if any("04_evidence_gate.py" in c for c in existing):
        print("already installed + registered — no change"); return 0
    entry = {"type": "command", "command": CMD}
    if stop and stop[0].get("hooks") is not None:
        hooks = stop[0]["hooks"]
        idx = next((i for i, h in enumerate(hooks) if "03_quality_gate" in h.get("command", "")), len(hooks) - 1)
        hooks.insert(idx + 1, entry)
    else:
        stop.append({"hooks": [entry]})
    json.dump(s, open(SETTINGS, "w"), indent=2)
    json.load(open(SETTINGS))  # validity check
    print("installed + registered 04_evidence_gate.py after 03_quality_gate")
    return 0

if __name__ == "__main__":
    sys.exit(main())
