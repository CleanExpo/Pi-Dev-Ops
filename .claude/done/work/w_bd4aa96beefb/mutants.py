"""C3 (w_bd4aa96beefb): the locked v3 mutant runner (w_77f2243a8e50/mutants.py, 16 mutants) plus the skill-router
mutant from Codex round 2 (src/tao/skill_router.default_jev settling by row id alone). The v3 file is read, the
extra entry is inserted at the head of its MUTANTS table (the anchor must occur exactly once), and it runs as-is."""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "w_77f2243a8e50" / "mutants.py"
ANCHOR = "MUTANTS = {\n"
EXTRA = ('    "router-settles-by-row-id": [("src/tao/skill_router.py", '
         '"spend.finish(row, *client._settled(result), call_id=cid)", "spend.finish(row, *client._settled(result))")],\n')
text = SRC.read_text(encoding="utf-8")
if text.count(ANCHOR) != 1:
    print(f"FAIL: anchor occurs {text.count(ANCHOR)} times in {SRC}")
    sys.exit(1)
exec(compile(text.replace(ANCHOR, ANCHOR + EXTRA), str(SRC), "exec"), {"__name__": "__main__"})
