#!/usr/bin/env python3
"""
mutate-assert - run a negative control that cannot silently no-op.

The failure this exists to prevent: you mutate a file to break a control, run the suite,
see it pass, and report "negative control passed". The mutation never applied - a typo in
the search string, an escaping slip, a moved line - and a control that was never disabled
reads exactly like a control that is working. Recorded three times in this estate before
being wired here; a lesson that keeps recurring is in the wrong container.

The wiring: the target must match, or nothing runs. Match failure exits 2 BEFORE the
command is invoked, so there is no result to misread. The file is always restored.

THREE distinct answers, because two of them used to look identical:

    didn't APPLY  the mutation never landed              -> 2  nothing was run
    didn't RUN    the mutant crashed before the control  -> 3  the red is the mutation's
                  could evaluate anything                      own fault, not evidence
    didn't FIRE   the control stayed green with its      -> 1  the real finding
                  subject broken

Exit 3 was added 2026-08-04, after this tool printed "PASS - the control fired" for a
mutation that referenced a variable the change under test had deleted. The suite went red
on a NameError, and under --expect-fail a crash is indistinguishable from a control
working. A control that fires because the program crashed has tested nothing - and the
tool built to catch exactly that class asserted the opposite.

    mutate-assert.py --file <path> --find <regex> --replace <text> \
                     --run "<command>" [--expect-fail] [--count N] [--cwd DIR] [--literal]

Exit codes:
    0  outcome matched expectation
    1  outcome did NOT match  (a negative control that failed to fire - the real finding)
    2  target not found / wrong count / command already failing - nothing usable ran
    3  the mutated program did not run (syntax, name or import error from the mutation)

Bytes in, bytes out: line endings are preserved, so this will not renormalise a file whose
blob is mixed. See the .gitattributes note in Pi-Dev-Ops for why that matters.
"""
# PEP 604 (`str | None`) is evaluated at def-time on 3.9, so this file crashed at import
# under the macOS system python3 that its own `#!/usr/bin/env python3` shebang selects.
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys

# Signatures meaning the program failed to RUN rather than failed to PASS.
#
# Deliberately tight. AttributeError and TypeError are NOT here: a genuine assertion path
# raises them, and a false "didn't run" would send you hunting a mutation bug that does not
# exist. Missing a crash costs you the old behaviour; inventing one costs the tool its
# credibility, which is the only thing that makes anyone read its verdict.
CRASH_SIGNATURES = (
    "SyntaxError",
    "IndentationError",
    "NameError",
    "ImportError",
    "ModuleNotFoundError",
    "ERROR collecting",
    "INTERNALERROR",
)


def crash_marks(output: str) -> list[str]:
    return [s for s in CRASH_SIGNATURES if s in output]


def invoke(cmd: str, cwd: str | None) -> tuple[int, str]:
    proc = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                          text=True, errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--find", required=True, help="regex, matched against the decoded file")
    ap.add_argument("--replace", required=True)
    ap.add_argument("--run", required=True, help="command whose outcome is the control's verdict")
    ap.add_argument("--expect-fail", action="store_true",
                    help="the command SHOULD fail once mutated (the usual negative control)")
    ap.add_argument("--count", type=int, default=1, help="required number of matches (default 1)")
    ap.add_argument("--cwd", default=None)
    ap.add_argument("--literal", action="store_true",
                    help="treat --replace as literal text, not an re.sub template")
    a = ap.parse_args()

    with open(a.file, "rb") as fh:
        original = fh.read()
    text = original.decode("utf-8")

    matches = list(re.finditer(a.find, text))
    if len(matches) != a.count:
        print(f"MUTATION TARGET NOT APPLIED - found {len(matches)} match(es), required {a.count}.",
              file=sys.stderr)
        print(f"  file:  {a.file}", file=sys.stderr)
        print(f"  find:  {a.find}", file=sys.stderr)
        print("Nothing was run. A control you did not disable is not a control you tested.",
              file=sys.stderr)
        return 2

    try:
        # --literal is the default-safe path: re.sub treats backslashes in the REPLACEMENT as
        # template escapes, so a replacement containing a backslash escape raises. Conflating
        # that with "the control did not fire" is the exact misread this tool exists to
        # prevent, so it exits 2 (nothing ran), never 1.
        repl = (lambda _m: a.replace) if a.literal else a.replace
        mutated = re.sub(a.find, repl, text, count=a.count).encode("utf-8")
    except re.error as exc:
        print(f"REPLACEMENT IS NOT A VALID re.sub TEMPLATE: {exc}", file=sys.stderr)
        print("Nothing was run. Pass --literal to treat the replacement as literal text "
              "(disables backreferences).", file=sys.stderr)
        return 2
    if mutated == original:
        print("MUTATION PRODUCED NO CHANGE - the replacement is identical to the original.",
              file=sys.stderr)
        return 2

    # Cheapest half of the exit-3 check, and the only half that can run BEFORE the command:
    # a mutant that does not parse cannot possibly exercise the control.
    if a.file.endswith(".py"):
        try:
            ast.parse(mutated.decode("utf-8"))
        except SyntaxError as exc:
            print(f"MUTANT DOES NOT PARSE: {exc}", file=sys.stderr)
            print("Nothing was run. A red result here would be the mutation's syntax error, "
                  "not the control firing.", file=sys.stderr)
            return 3

    print(f"mutation applied ({a.count} site) - {matches[0].group(0)[:70]!r}")
    try:
        with open(a.file, "wb") as fh:
            fh.write(mutated)
        code, output = invoke(a.run, a.cwd)
    finally:
        with open(a.file, "wb") as fh:
            fh.write(original)
        print("file restored")
    sys.stdout.write(output)
    failed = code != 0

    marks = crash_marks(output)
    if failed and marks:
        # Differential, paid for only when it matters. The same signature may already be in
        # the output without any mutation, in which case the command was broken before we
        # touched it and this run is evidence of nothing in either direction.
        print("\ncrash signature seen: " + ", ".join(marks) +
              " - re-running the ORIGINAL to find out whether the mutation caused it")
        base_code, base_output = invoke(a.run, a.cwd)
        if crash_marks(base_output) or base_code != 0:
            print("COMMAND WAS ALREADY FAILING before the mutation. Nothing usable ran, so no "
                  "verdict is available.", file=sys.stderr)
            return 2
        print("MUTANT DID NOT RUN - the mutated program crashed (" + ", ".join(marks) +
              "), and the original does not.", file=sys.stderr)
        print("This is NOT the control firing. The red belongs to the mutation. Rewrite it so "
              "it produces a program that RUNS and is merely wrong, then try again.",
              file=sys.stderr)
        return 3

    if a.expect_fail and failed:
        print("PASS - the control fired when its subject was broken.")
        return 0
    if a.expect_fail and not failed:
        print("FAIL - the control stayed GREEN with its subject broken. It proves nothing.",
              file=sys.stderr)
        return 1
    if not a.expect_fail and not failed:
        print("PASS - command still succeeded under mutation, as expected.")
        return 0
    print("FAIL - command failed but was expected to survive the mutation.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
