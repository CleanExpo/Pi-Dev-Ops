#!/usr/bin/env python3
"""Fail when a dashboard client reads the Pi-CEO proxy without reading its
fallback header.

WHY THIS EXISTS
---------------
`app/api/pi-ceo/[...path]/route.ts` never fails loudly on a GET. When the
backend is unreachable, `quietFallback` returns **HTTP 200** with a synthesised
body — empty arrays, zeroed counters, absent fields — and stamps the real
upstream status on `X-Upstream-Status`. The success path never sets it.

So `res.ok` is TRUE when the backend is dead. A client that checks only
`res.ok` renders placeholders as measurements. Measured 2026-09-11: 19
consumers, 38 call sites, 18 of them blind. The Loop Cockpit turned an absent
`enabled` field into the on-screen claim "Autonomy poller is disabled
(TAO_AUTONOMY_ENABLED=0)" — naming an env var as the cause of an outage nothing
had observed.

THE RULE
--------
A failed read must never render as a successful read that found nothing.
Fetch through `lib/pi-ceo-fetch.ts`, or check `X-Upstream-Status` yourself.

RATCHET
-------
Files already blind are grandfathered in `.github/proxy-fallback.baseline.txt`.
CI fails on a NEW blind consumer, and on a baselined file that has become
honest — the baseline only ever shrinks, so a fixed file cannot silently
reserve permission to regress. Run `--update` after fixing one.

CAVEAT, STATED RATHER THAN HIDDEN
---------------------------------
The check is textual. A file that only POSTs through the proxy is not affected
by the fallback (non-GET methods do return real error statuses) but will still
be flagged if it is new. That is deliberate: routing it through the helper
costs nothing and removes the judgement call.

ENUMERATION
-----------
Uses `git ls-files`, so a brand-new file is INVISIBLE until staged. Run after
`git add` (`git add -N` is enough) or this prints "passed" locally and fails in
CI on the file you just wrote — the same blindness documented in CLAUDE.md.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
BASELINE = REPO / ".github" / "proxy-fallback.baseline.txt"
DASHBOARD = "dashboard/"

# The proxy route itself, and the allowlist that names paths, are not consumers.
EXEMPT_SUBSTRINGS = (
    "dashboard/app/api/pi-ceo/",
    "dashboard/lib/pi-ceo-proxy-allowlist",
    "dashboard/lib/pi-ceo-fetch",
    "__tests__/",
)

PROXY_MARKER = "api/pi-ceo"

# Per-CALL-SITE, not per-file. The first version of this gate asked whether the
# FILE mentioned the helper anywhere, which meant migrating one call in a file
# marked the whole file honest while its other calls stayed raw — the gate would
# then certify exactly the defect it exists to find. Found while migrating the
# baselined files with it, before it had certified anything.
#
# A migrated call site reads `fetchProxyJSON("/api/health")` — the helper adds
# the `/api/pi-ceo` prefix itself. So any REMAINING `/api/pi-ceo` literal in a
# client file is a raw call, and the only question left is whether the fallback
# can reach it.
#
# Two shapes genuinely cannot, and are exempt rather than baselined:
#   * `new EventSource(...)` — SSE goes through proxySse(), which returns a real
#     502 and never synthesises a body.
#   * a non-GET `fetch` — quietFallback() only fires for method === "GET";
#     mutations get a real error status.
# EVERY `/api/pi-ceo` literal in a client file is treated as a call site. The
# exemptions below are narrow and each names a mechanism, because the first
# version of this rule also demanded a literal `fetch(` within 120 characters
# and that made it BLIND on three real files:
#
#   MargotAssetsPanel.tsx   const API = "/api/pi-ceo/api/margot/assets"
#   SpecPipelinePanel.tsx   const API = "/api/pi-ceo/api/spec-pipeline"
#   TerminalPanel.tsx       fetchJson<SessionsResp>("/api/pi-ceo/...")
#
# A URL in a const is still fetched somewhere, and `fetchJson<T>(` does not
# contain `fetch(`. The count dropped 18 -> 14 and looked like a cleaner
# result; three of the four files it dropped were defects, not exemptions.
# Caught by reading all four before trusting the narrowing.
#
# So the rule is now: flagged unless a MECHANISM makes the fallback
# unreachable. Guessing wrong flags an extra file, which costs one import.
NON_GET = re.compile(r'method:\s*["\'](POST|PUT|PATCH|DELETE)["\']', re.I)
COMMENT_LINE = re.compile(r'^\s*(//|/\*|\*)')
LOOKBACK = 120   # chars before the URL, enough to catch `EventSource(`
LOOKAHEAD = 260  # chars after, enough to catch an options object's `method:`


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--", f"{DASHBOARD}**/*.ts", f"{DASHBOARD}**/*.tsx"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def is_exempt(rel: str) -> bool:
    return any(s in rel for s in EXEMPT_SUBSTRINGS)


def blind_call_sites(rel: str, text: str) -> list[int]:
    """1-indexed line numbers of raw GET call sites against the proxy."""
    hits = []
    for m in re.finditer(re.escape(PROXY_MARKER), text):
        start = m.start()
        before = text[max(0, start - LOOKBACK):start]
        after = text[start:start + LOOKAHEAD]
        if "EventSource(" in before:
            continue
        if NON_GET.search(after):
            continue
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", start)
        line = text[line_start:line_end if line_end != -1 else len(text)]
        if COMMENT_LINE.match(line):
            # Prose about the endpoint, not a call to it.
            continue
        hits.append(text.count("\n", 0, start) + 1)
    return hits


def blind_consumers() -> list[str]:
    found = []
    for rel in tracked_files():
        if is_exempt(rel):
            continue
        path = REPO / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if PROXY_MARKER not in text:
            continue
        if blind_call_sites(rel, text):
            found.append(rel)
    return sorted(found)


def read_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {
        line.strip()
        for line in BASELINE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def write_baseline(files: list[str]) -> None:
    header = [
        "# Dashboard files that read the Pi-CEO proxy without reading its",
        "# X-Upstream-Status fallback header. See .github/scripts/proxy_fallback_lint.py.",
        "#",
        "# SHRINK-ONLY. Fix a file (route it through lib/pi-ceo-fetch.ts), then",
        "# run `python3 .github/scripts/proxy_fallback_lint.py --update` to drop it.",
        "# Never add a line here to make CI green.",
        "",
    ]
    BASELINE.write_text("\n".join(header + files) + "\n", encoding="utf-8")


def _report_new_blind(new_blind: list[str]) -> None:
    print("FAIL — new client(s) read the Pi-CEO proxy without checking X-Upstream-Status.")
    print("The proxy answers 200 with placeholder data when the backend is down, so")
    print("`res.ok` is true and the placeholders render as measurements.\n")
    for rel in new_blind:
        print(f"  {rel}")
    print("\nFix: import { fetchProxyJSON } from '@/lib/pi-ceo-fetch' and use it.")


def _report_silently_fixed(fixed: list[str]) -> None:
    print("FAIL — these files are no longer blind but are still in the baseline.")
    print("The baseline is shrink-only so a fixed file cannot reserve permission to regress.\n")
    for rel in fixed:
        print(f"  {rel}")
    print("\nFix: python3 .github/scripts/proxy_fallback_lint.py --update")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="rewrite the baseline from current state")
    ap.add_argument("--report", action="store_true", help="list every consumer and its status")
    args = ap.parse_args()

    blind = blind_consumers()

    if args.update:
        write_baseline(blind)
        print(f"baseline updated: {len(blind)} blind consumer(s)")
        return 0

    if args.report:
        total = 0
        for rel in blind:
            text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
            sites = blind_call_sites(rel, text)
            total += len(sites)
            print(f"BLIND    {rel}:{','.join(str(n) for n in sites)}")
        print(f"\n{len(blind)} file(s), {total} raw GET call site(s)")
        return 0

    baseline = read_baseline()
    new_blind = [f for f in blind if f not in baseline]
    fixed = sorted(baseline - set(blind))

    if new_blind:
        _report_new_blind(new_blind)
        return 1

    if fixed:
        _report_silently_fixed(fixed)
        return 1

    print(f"passed — {len(blind)} baselined blind consumer(s), no new ones, none silently fixed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
