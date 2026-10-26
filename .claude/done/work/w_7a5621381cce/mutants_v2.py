"""Mutant control for the railway placeholder fix, v2 (adds the two mutants the Cursor review saw survive,
and the dashboard Fleet tile). Every mutant must make its suite FAIL.

Run from the worktree root. Exit 0 only when every mutant is caught. Exit 1 when one survives,
2 when one cannot be applied (target text missing or duplicated, so that leg would be vacuous),
3 when a dashboard file could not be restored to its original bytes.
Plugin mutants run on a temporary copy. Dashboard mutants edit in place (vitest resolves the
`@/` alias from dashboard/) and restore the original bytes in `finally`.
"""
import hashlib, pathlib, shutil, subprocess, sys, tempfile

CLAUDE = "/Users/phill-mac/.local/bin/claude"
NODE = "/Users/phill-mac/.local/bin/node"
MOD = pathlib.Path("mods/mission-control")
DASH = pathlib.Path("dashboard")
DASH_TESTS = ["__tests__/mesh-fleet.test.ts", "__tests__/fleet-tile.test.tsx"]

PLUGIN = {  # name: (old, new) in hooks/fleet.ts
    "placeholder-never-matches": ("const placeholder = host === CLOUD_CLAIM_HOST", "const placeholder = false"),
    "everything-is-placeholder": ("const placeholder = host === CLOUD_CLAIM_HOST", "const placeholder = true"),
    "alert-guard-removed": ("alert: !placeholder && (stale || DOWN.has(status))", "alert: stale || DOWN.has(status)"),
    "case-insensitive-match": ("const placeholder = host === CLOUD_CLAIM_HOST",
                               "const placeholder = host.toLowerCase() === CLOUD_CLAIM_HOST"),
}
DASHBOARD = {  # name: (file, old, new)
    "dash-never-matches": ("lib/control/mesh-fleet.ts", "const placeholder = host === CLOUD_CLAIM_HOST;",
                           "const placeholder = false;"),
    "dash-everything-is-placeholder": ("lib/control/mesh-fleet.ts", "const placeholder = host === CLOUD_CLAIM_HOST;",
                                       "const placeholder = true;"),
    "dash-label-dropped": ("components/control/FleetTile.tsx", 'machine.placeholder ? "cloud claim" : ', ""),
}


def tail(cp):
    return " | ".join((cp.stdout + cp.stderr).strip().splitlines()[-3:])[:200]


survivors, unapplied = [], []
src = (MOD / "hooks" / "fleet.ts").read_text(encoding="utf-8")
for name, (old, new) in PLUGIN.items():
    if src.count(old) != 1:
        print(f"{name}: CANNOT APPLY (target found {src.count(old)} times)")
        unapplied.append(name)
        continue
    with tempfile.TemporaryDirectory(prefix="mc-mutant-") as td:
        copy = pathlib.Path(td) / "mission-control"
        shutil.copytree(MOD, copy)
        (copy / "hooks" / "fleet.ts").write_text(src.replace(old, new), encoding="utf-8")
        cp = subprocess.run([CLAUDE, "plugin", "test", str(copy)], capture_output=True, text=True, timeout=240)
    print(f"{name}: rc={cp.returncode} :: {tail(cp)}")
    if cp.returncode == 0:
        survivors.append(name)

for name, (rel, old, new) in DASHBOARD.items():
    path = DASH / rel
    original = path.read_bytes()
    text = original.decode("utf-8")
    if text.count(old) != 1:
        print(f"{name}: CANNOT APPLY (target found {text.count(old)} times in {rel})")
        unapplied.append(name)
        continue
    try:
        path.write_text(text.replace(old, new), encoding="utf-8")
        cp = subprocess.run([NODE, "node_modules/vitest/vitest.mjs", "run", *DASH_TESTS],
                            cwd=DASH, capture_output=True, text=True, timeout=300)
    finally:
        path.write_bytes(original)
    if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(original).digest():
        print(f"RESTORE FAILED: {path}")
        sys.exit(3)
    print(f"{name}: rc={cp.returncode} :: {tail(cp)}")
    if cp.returncode == 0:
        survivors.append(name)

if unapplied:
    print(f"UNAPPLIED: {unapplied}")
    sys.exit(2)
if survivors:
    print(f"SURVIVED: {survivors}")
    sys.exit(1)
print(f"all {len(PLUGIN) + len(DASHBOARD)} mutants caught")
