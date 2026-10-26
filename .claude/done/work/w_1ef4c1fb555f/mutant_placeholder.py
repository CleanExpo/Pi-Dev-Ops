"""C4 control for w_1ef4c1fb555f: each mutant of the placeholder rule must make `claude plugin test` FAIL.

Run from the worktree root. Exit 0 only when BOTH mutants are caught. Exit 1 when a mutant survives,
2 when a mutant cannot be applied (the guarded line is missing or duplicated, so the control would be vacuous).
Works on a temporary copy of mods/mission-control; the worktree is never modified.
"""
import pathlib, shutil, subprocess, sys, tempfile

CLAUDE = "/Users/phill-mac/.local/bin/claude"
MOD = pathlib.Path("mods/mission-control")
LINE = "const placeholder = host === CLOUD_CLAIM_HOST"
MUTANTS = {
    "placeholder-never-matches": "const placeholder = false",   # railway alarms again -> placeholder test must fail
    "everything-is-placeholder": "const placeholder = true",    # real stale hosts stop alarming -> stale tests must fail
}

src = (MOD / "hooks" / "fleet.ts").read_text(encoding="utf-8")
if src.count(LINE) != 1:
    print(f"CANNOT APPLY: guarded line found {src.count(LINE)} times (need exactly 1)")
    sys.exit(2)

survivors = []
for name, repl in MUTANTS.items():
    with tempfile.TemporaryDirectory(prefix="mc-mutant-") as td:
        copy = pathlib.Path(td) / "mission-control"
        shutil.copytree(MOD, copy)
        (copy / "hooks" / "fleet.ts").write_text(src.replace(LINE, repl), encoding="utf-8")
        cp = subprocess.run([CLAUDE, "plugin", "test", str(copy)], capture_output=True, text=True, timeout=240)
        tail = (cp.stdout + cp.stderr).strip().splitlines()[-3:]
        print(f"{name}: rc={cp.returncode} :: {' | '.join(tail)[:200]}")
        if cp.returncode == 0:
            survivors.append(name)
if survivors:
    print(f"SURVIVED: {survivors}")
    sys.exit(1)
print("both mutants caught")
