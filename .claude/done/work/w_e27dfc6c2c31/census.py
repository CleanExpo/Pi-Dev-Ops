"""C3: every non-test Python file committed at HEAD that names the TypeSafe endpoint also records spend.

A file passes when it imports jev_platform.spend (or `from jev_platform import ... spend`) or calls
reserve_call(...). Exit 0 only when the census found at least one endpoint file (positive control)
and none of them is unrecorded."""
import re
import subprocess
import sys

ROOT = sys.argv[1]
ENDPOINT = "api.typesafe.ai"
RECORDS = re.compile(r"from jev_platform import [^\n]*\bspend\b|import jev_platform\.spend|from jev_platform\.spend import|\breserve_call\(")


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, check=True).stdout


files = [f for f in git("ls-tree", "-r", "--name-only", "HEAD").splitlines()
         if f.endswith(".py") and not f.startswith(("tests/", ".claude/")) and "/tests/" not in f]
hits, missing = [], []
for f in files:
    text = git("show", f"HEAD:{f}")
    if ENDPOINT not in text:
        continue
    hits.append(f)
    if not RECORDS.search(text):
        missing.append(f)
print(f"endpoint files: {len(hits)}")
for f in hits:
    print(("UNRECORDED " if f in missing else "ok         ") + f)
if len(hits) < 4:
    print("FAIL: fewer than 4 endpoint files found; the census is not seeing the code")
    sys.exit(1)
sys.exit(1 if missing else 0)
