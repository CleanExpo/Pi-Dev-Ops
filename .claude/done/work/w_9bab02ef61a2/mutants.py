"""C3 (w_9bab02ef61a2): the locked v3 mutant runner (w_77f2243a8e50/mutants.py) moved to the round-4 shadow code.

The shadow now writes its own row with the call id in the INSERT and passes that id to the machine reserve, so the
two v3 mirror anchors move to the INSERT, and the v6 extras are kept with their anchors widened (the bare
`WHERE spend_call_id=?",` now also occurs in the link and refused updates). Round 4 adds: the link and the refused
update matching any row, a missed link going unreported, the own call id losing its unique index, and the machine
ledger ignoring the call id it was given. Every replacement and the insertion anchor must occur exactly once in
the v3 file, or this runner fails before planting anything."""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "w_77f2243a8e50" / "mutants.py"
ANCHOR = "MUTANTS = {\n"
INSERT_TAIL = "datetime.now(UTC).isoformat(), call_id),"
MOVED = [
    ('"mirror-drops-call-id": [(SH, "(spend_id, spend_call_id, call_id)", "(spend_id, None, call_id)")]',
     f'"mirror-drops-call-id": [(SH, "{INSERT_TAIL}", "datetime.now(UTC).isoformat(), None),")]'),
    ('"mirror-stores-row-id": [(SH, "(spend_id, spend_call_id, call_id)", "(spend_id, str(spend_id), call_id)")]',
     f'"mirror-stores-another-id": [(SH, "{INSERT_TAIL}", "datetime.now(UTC).isoformat(), call_id[::-1]),")]'),
    ('"spend.finish(machine[0], status, actual, input_tokens, call_id=machine[1])",',
     '"spend.finish(machine, status, actual, input_tokens, call_id=call_id)",'),
    ('"spend.finish(machine[0], status, actual, input_tokens)")',
     '"spend.finish(machine, status, actual, input_tokens)")'),
]
EXTRA = (
    '    "router-settles-by-row-id": [("src/tao/skill_router.py", '
    '"spend.finish(row, *client._settled(result), call_id=cid)", "spend.finish(row, *client._settled(result))")],\n'
    '    "shadow-handle-is-spend-id": [(SH, "    return call_id\\n\\n\\ndef finish_call", '
    '"    return str(spend_id)\\n\\n\\ndef finish_call")],\n'
    '    "shadow-own-settle-any-row": [(SH, "actual_usd=? WHERE spend_call_id=?\\",", '
    '"actual_usd=? WHERE spend_call_id=? OR 1\\",")],\n'
    '    "shadow-link-any-row": [(SH, "SET spend_id=? WHERE spend_call_id=?\\"", '
    '"SET spend_id=? WHERE spend_call_id=? OR 1\\"")],\n'
    '    "shadow-refused-any-row": [(SH, "actual_usd=0 WHERE spend_call_id=?\\"", '
    '"actual_usd=0 WHERE spend_call_id=? OR 1\\"")],\n'
    '    "shadow-missed-link-unreported": [(SUP, ".rowcount != 1:", ".rowcount != 1 and False:")],\n'
    '    "shadow-call-id-not-unique": [(SUP, "CREATE UNIQUE INDEX IF NOT EXISTS calls_spend_call_id", '
    '"CREATE INDEX IF NOT EXISTS calls_spend_call_id")],\n'
    '    "machine-ignores-given-call-id": [(S, "    if call_id is None:\\n", "    if True:\\n")],\n'
)
text = SRC.read_text(encoding="utf-8")
for find, repl in MOVED + [(ANCHOR, ANCHOR + EXTRA)]:
    if text.count(find) != 1:
        print(f"FAIL: {find!r} occurs {text.count(find)} times in {SRC}")
        sys.exit(1)
    text = text.replace(find, repl)
exec(compile(text, str(SRC), "exec"), {"__name__": "__main__"})
