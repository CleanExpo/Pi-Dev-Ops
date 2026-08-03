#!/usr/bin/env python3
"""secrets_history_check.py — scan the HISTORY of files that are gitignored today.

WHY THIS EXISTS

`secrets_check.py` scans the working tree. Until 2026-08-02 it also passed
`--exclude-standard`, so gitignored files were never scanned at all — and `.env.local`,
`*.pem` and credential dumps are exactly what `.gitignore` covers. That is fixed.

Fixing the working-tree scan does not reach the case that reframes every earlier
all-clear: **a file that was tracked and pushed, and only later gitignored, is in git
history and was outside both the old scan and the new one.** Adding a path to
`.gitignore` changes nothing about what is already in the repo, or on any remote that
fetched it.

This closes that gap: enumerate every path ever added on any branch, keep the ones git
ignores today, and scan every historical blob of each against `secrets_check.py`'s own
pattern set. The patterns are extracted STATICALLY via `ast` rather than imported,
because importing that module fires its CLI and its `.gitignore` auto-patch.

BOUND ON THE CLAIM — read before quoting a clean result. It means "no match for the ten
shapes `secrets_check.py` knows". It does NOT mean "no secrets". Not covered, among
others: Supabase service-role JWTs (`eyJ...`), Stripe keys, Telegram bot tokens,
OpenRouter keys. Widen the pattern set there and this inherits it.

Run: python scripts/secrets_history_check.py
Exit: 0 clean · 1 hits found · 2 the scan could not read anything (not a clean result)
"""
import subprocess
import sys
import ast
import re

REPO = "D:/Pi-Dev-Ops"


def sh(args, inp=None):
    return subprocess.run(
        args, cwd=REPO, input=inp, capture_output=True
    ).stdout.decode("utf-8", "ignore")


def load_patterns():
    """Extract _SECRET_PATTERNS from secrets_check.py without executing it."""
    src = open(f"{REPO}/scripts/secrets_check.py", encoding="utf-8").read()
    for node in ast.walk(ast.parse(src)):
        target = None
        if isinstance(node, ast.AnnAssign):
            target = getattr(node.target, "id", "")
        elif isinstance(node, ast.Assign) and node.targets:
            target = getattr(node.targets[0], "id", "")
        if target == "_SECRET_PATTERNS":
            return ast.literal_eval(node.value)
    raise SystemExit("FAIL: could not extract _SECRET_PATTERNS from secrets_check.py")


PLACEHOLDER = re.compile(
    r"EXAMPLE|PLACEHOLDER|CHANGEME|DUMMY|FAKE|SAMPLE|xxxx+|REPLACE_ME|INSERT_YOUR"
    r"|YOUR_.*_HERE|PASTE_YOUR",
    re.I,
)


def main() -> int:
    compiled = [(re.compile(p), t, s) for p, t, s in load_patterns()]
    print(f"patterns extracted: {len(compiled)}")

    # POSITIVE CONTROL. A null result from a pattern set that cannot match anything looks
    # exactly like a null result from a clean history.
    if not any(rx.search("AKIA" + "ABCDEFGHIJ123456") for rx, _, _ in compiled):
        print("FAIL: positive control - pattern set did not match a planted AWS-shaped key.")
        return 2
    print("positive control: pattern set detects a planted AWS-shaped key = True")

    ever = sh(["git", "log", "--all", "--diff-filter=A", "--name-only", "--pretty=format:"])
    cand = sorted({l.strip() for l in ever.splitlines() if l.strip()})

    # Bytes, not text. In text mode Python translates LF to CRLF on write, so git received
    # every path with a trailing CR, matched nothing real, and the scan covered 0 blobs
    # while reporting "no secrets found" over 6160 paths. A clean result from a broken
    # input list is indistinguishable from a clean repo - the same shape this whole
    # exercise is about, hit inside the tool built to check for it. Hence the guard below.
    res = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=REPO,
        input="\n".join(cand).encode(),
        capture_output=True,
    )
    paths = [
        l.strip()
        for l in res.stdout.decode("utf-8", "ignore").splitlines()
        if l.strip()
    ]

    # Apply the SAME policy exclusions secrets_check.py uses for the working tree —
    # test fixtures and generated .harness/ artefacts — but COUNT and REPORT what was
    # suppressed. Silently narrowing is the exact mechanism this tool exists to answer
    # (".gitignore is a silent scope reducer"), so the number is always printed.
    # First run found 63 hits, every one of them a test fixture or a .harness/ artefact;
    # 63 known-benign lines at the top of a report is how a real hit gets skimmed past.
    excluded = ("tests/", "test/", ".harness/")
    def policy_excluded(p: str) -> bool:
        n = p.replace("\\", "/")
        return (n.startswith(excluded) or "/__tests__/" in n
                or n.endswith(".test.ts") or n.endswith(".test.tsx"))

    hits, scanned, suppressed = {}, 0, 0
    for path in paths:
        for sha in sh(["git", "log", "--all", "--format=%H", "--", path]).split():
            blob = sh(["git", "show", f"{sha}:{path}"])
            if not blob:
                continue
            scanned += 1
            for rx, title, sev in compiled:
                m = rx.search(blob)
                if m and not PLACEHOLDER.search(m.group(0)):
                    if policy_excluded(path):
                        suppressed += 1
                    else:
                        hits.setdefault((path, title, sev), sha[:8])

    print(f"paths checked: {len(paths)}   historical blobs scanned: {scanned}")
    print(f"policy-excluded matches suppressed: {suppressed} "
          f"(test fixtures and .harness/ artefacts — same exclusions as secrets_check.py)")

    if paths and scanned == 0:
        print("FAIL: candidate paths were found but NO historical blob could be read.")
        print("      A null result from a scan that read nothing is not evidence.")
        return 2

    if not hits:
        print("RESULT: NO match for the tracked patterns in the history of any now-ignored file")
        return 0

    for (path, title, sev), sha in sorted(hits.items()):
        print(f"  [{sev}] {path} @ {sha} - {title}")
    print(f"RESULT: {len(hits)} distinct hits - REVIEW REQUIRED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
