#!/usr/bin/env python3
"""Generate the two arms from the live seat files.

Both arms are derived from the same source so they cannot drift apart by hand.
The no-method arm is the with-method arm minus every reference to METHOD.md and
nothing else. The script prints exactly what it removed, so the single-variable
claim is auditable rather than asserted.

  make_arms.py            write arms/with-method/ and arms/no-method/
  make_arms.py --verify   re-derive and confirm the only difference is METHOD
"""

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
BENCH = pathlib.Path.home() / ".claude/agents/bench"

SEATS = [
    "eng-concurrency", "eng-observability", "eng-failure",
    "eng-authz", "eng-data", "eng-release", "eng-test",
]

# Each pattern removes one METHOD reference. Anything a pattern does not match
# is reported, because a silently-unapplied strip would leave METHOD in the
# control arm and quietly invalidate the whole experiment.
STRIPS = [
    (r"- `~/\.claude/agents/bench/METHOD\.md`[^\n]*\n(?:  [^\n]*\n)*", ""),
    (r"\*\*Read both of these before you answer:\*\*", "**Read this before you answer:**"),
    (r"\s*Where the method and your domain\s+instinct disagree, the method wins and you say so in one line\.", ""),
]


def derive(text):
    removed = []
    for pattern, repl in STRIPS:
        new, n = re.subn(pattern, repl, text)
        removed.append(n)
        text = new
    return text, removed


def main():
    verify = "--verify" in sys.argv
    ok = True

    for seat in SEATS:
        src = BENCH / f"{seat}.md"
        if not src.exists():
            print(f"cannot determine: {src} missing", file=sys.stderr)
            sys.exit(2)
        original = src.read_text()
        stripped, counts = derive(original)

        if any(c == 0 for c in counts):
            print(f"  WARN {seat}: strip pattern(s) {[i for i, c in enumerate(counts) if c == 0]} matched nothing")
            ok = False
        if "METHOD.md" in stripped:
            print(f"  FAIL {seat}: METHOD.md still present in the no-method arm")
            ok = False

        if not verify:
            for arm, body in (("with-method", original), ("no-method", stripped)):
                d = HERE / "arms" / arm
                d.mkdir(parents=True, exist_ok=True)
                (d / f"{seat}.md").write_text(body)

        delta = len(original.splitlines()) - len(stripped.splitlines())
        print(f"  {seat:<18} -{delta} lines removed from the no-method arm")

    print(f"\n{len(SEATS)} seats, two arms." if not verify else f"\n{len(SEATS)} seats verified.")
    print("The arms differ only in the METHOD.md reference. Everything else — the domain, the")
    print("failure mechanisms, the CONTRACT reference — is byte-identical.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
