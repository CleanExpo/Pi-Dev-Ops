"""C3 (w_96d0d2e86f28): the locked v3 mutant runner (w_77f2243a8e50/mutants.py) with its three shadow anchors
moved to the round-3 shadow code (the handle is now the machine call id, the own row is `row`), plus the
skill-router mutant from round 2 and two shadow mutants from round 3. Every replacement and the insertion
anchor must occur exactly once in the v3 file, or this runner fails before planting anything."""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "w_77f2243a8e50" / "mutants.py"
ANCHOR = "MUTANTS = {\n"
MOVED = [
    ('(SH, "(spend_id, spend_call_id, call_id)", "(spend_id, None, call_id)")',
     '(SH, "(spend_id, call_id, row)", "(spend_id, None, row)")'),
    ('(SH, "(spend_id, spend_call_id, call_id)", "(spend_id, str(spend_id), call_id)")',
     '(SH, "(spend_id, call_id, row)", "(spend_id, str(spend_id), row)")'),
    ('"spend.finish(machine[0], status, actual, input_tokens, call_id=machine[1])",',
     '"spend.finish(machine, status, actual, input_tokens, call_id=call_id)",'),
    ('"spend.finish(machine[0], status, actual, input_tokens)")',
     '"spend.finish(machine, status, actual, input_tokens)")'),
]
EXTRA = (
    '    "router-settles-by-row-id": [("src/tao/skill_router.py", '
    '"spend.finish(row, *client._settled(result), call_id=cid)", "spend.finish(row, *client._settled(result))")],\n'
    '    "shadow-handle-is-row-id": [(SH, "    return call_id\\n\\n\\ndef finish_call", "    return row\\n\\n\\ndef finish_call")],\n'
    '    "shadow-own-settle-any-row": [(SH, "WHERE spend_call_id=?\\",", "WHERE spend_call_id=? OR 1\\",")],\n'
)
text = SRC.read_text(encoding="utf-8")
for find, repl in MOVED + [(ANCHOR, ANCHOR + EXTRA)]:
    if text.count(find) != 1:
        print(f"FAIL: {find!r} occurs {text.count(find)} times in {SRC}")
        sys.exit(1)
    text = text.replace(find, repl)
exec(compile(text, str(SRC), "exec"), {"__name__": "__main__"})
