"""WP-11 — Mission Control scorecard from one live-suite run's receipts.

Applies docs/plans/mission-control/aaa-rating.md to the JSON receipts written by
dashboard/e2e-live/ (WP-02, WP-06, WP-09): each surface gets the highest level
whose every check is met, and Mission Control gets the LOWEST surface level.

A check is met only on evidence. A check the suite does not measure yet, or a
receipt that is missing, is UNMET ("not measured") — never a pass. N/A (a
check that cannot apply, e.g. check 5 on a server-rendered page) counts as met.

Check 10 (three consecutive scheduled runs) reads earlier runs' scorecards
from --history; see scripts/mission_control_stability.py.

Usage:
    python3 scripts/mission_control_scorecard.py <receipts-dir> [--json out.json]
        [--event schedule --run-id N --run-attempt 1 --history DIR]
Prints a Markdown table (for $GITHUB_STEP_SUMMARY). Exit code is always 0 when
the receipts were read: the grade is the output, not a pass/fail gate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.mission_control_stability import judge_stable, load_history  # noqa: E402

# Surfaces with write actions (work-packages.md WP-07). Checks 3 and 12 apply
# only to these; for every other surface they are N/A.
WRITE_SURFACES = {"MC-01", "MC-02", "MC-03", "MC-05", "MC-07", "MC-10", "MC-11"}
SURFACES = [f"MC-{n:02d}" for n in range(20)]

LEVELS: dict[int, list[str]] = {1: ["1", "2", "3", "4"], 2: ["5", "6", "7", "8", "9"], 3: ["10", "11", "12", "13"]}

# Checks the suite does not measure yet, and why. Each is UNMET until a
# receipt carries it; the reason is what the scorecard prints.
NOT_MEASURED = {
    "3": "write journeys against a PR preview not built (WP-07; Vercel sign-in protection blocks previews until a bypass secret is set)",
}


@dataclass
class Verdict:
    met: bool
    reason: str = ""


def load_receipts(folder: Path) -> dict[str, dict]:
    """Receipt file stem -> parsed receipt. Unreadable files are skipped loudly."""
    out: dict[str, dict] = {}
    for path in sorted(folder.glob("*.json")):
        try:
            out[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"warning: unreadable receipt {path.name}: {exc}", file=sys.stderr)
    return out


def receipts_for(surface: str, receipts: dict[str, dict]) -> dict[str, dict]:
    """Split one surface's receipts into desktop / phone / l2."""
    found: dict[str, dict] = {}
    for stem, body in receipts.items():
        sid = "MC-00" if stem.startswith("control-hub") else stem[:5]
        if sid != surface:
            continue
        kind = ("c7" if stem.endswith("-C7") else "c11" if stem.endswith("-C11") else "w" if stem.endswith("-W") else "phone" if "@phone" in stem
                else "l2" if re.search(r"-L2($|@)", stem) else "desktop")
        found[kind] = body
    return found


def _checks(receipt: dict | None, prefix: str) -> list[dict]:
    if not receipt:
        return []
    return [c for c in receipt.get("checks", []) if str(c.get("check", "")).startswith(prefix)]


def _all_pass(checks: list[dict], what: str, allow_na: bool = False) -> Verdict:
    if not checks:
        return Verdict(False, f"{what}: no result in receipt")
    ok = {"PASS", "N/A"} if allow_na else {"PASS"}
    bad = [c for c in checks if c.get("result") not in ok]
    if bad:
        first = bad[0]
        return Verdict(False, f"{first.get('check')} {first.get('result')}: {str(first.get('detail', ''))[:120]}")
    return Verdict(True)


def suite_passed(surface: str, got: dict[str, dict]) -> bool:
    """Did this run's live suite pass for <surface>? The input to check 10.

    Every live receipt the surface should have must exist (a test that died
    before writing one is a failure), and every check in them is PASS or N/A.
    The panel-coverage (-C7) and register (-C11) receipts are not part of the live
    suite; a write-journey (-W) receipt counts when the surface has one.
    """
    kinds = ("desktop",) if surface == "MC-00" else ("desktop", "phone", "l2")
    if any(not got.get(k) for k in kinds):
        return False
    kinds += ("w",) if got.get("w") else ()  # a write journey that failed breaks the night too
    return all(c.get("result") in ("PASS", "N/A") for k in kinds for c in got[k].get("checks", []))


def _judge_register(receipt: dict | None) -> Verdict:
    """Check 11 from scripts/mission_control_register.py receipts.

    A measured FAIL is reported even when the other half is UNKNOWN; UNKNOWN
    alone (Linear not read) is "not measured", never a pass.
    """
    checks = _checks(receipt, "11-")
    if {c.get("check") for c in checks} != {"11-register", "11-tickets"}:
        return Verdict(False, "not measured: no complete register receipt for this surface")
    failed = [c for c in checks if c.get("result") == "FAIL"]
    if failed:
        return Verdict(False, f"{failed[0]['check']} FAIL: {str(failed[0].get('detail', ''))[:120]}")
    unknown = [c for c in checks if c.get("result") != "PASS"]
    if unknown:
        return Verdict(False, f"not measured: {str(unknown[0].get('detail', ''))[:120]}")
    return Verdict(True)


def _judge_label_honesty(receipt: dict | None) -> Verdict:
    """Check 12 from the write-journey receipt (dashboard/e2e-writes/, MC-xx-W.json).

    Every 12-* result must PASS. No receipt means this surface's write actions
    have no label-honesty journey yet: not measured, never a pass.
    """
    checks = _checks(receipt, "12-")
    if not checks:
        return Verdict(False, "not measured: no write-journey receipt for this surface yet")
    return _all_pass(checks, "check 12")


def judge(check: str, surface: str, got: dict[str, dict], deployed_sha: str | None) -> Verdict:
    """Is aaa-rating.md check <check> met for <surface>, on this run's receipts?"""
    if check in ("3", "12") and surface not in WRITE_SURFACES:
        return Verdict(True, "N/A — no write actions")
    if check in NOT_MEASURED:
        return Verdict(False, f"not measured: {NOT_MEASURED[check]}")
    desktop, phone, l2 = got.get("desktop"), got.get("phone"), got.get("l2")
    if check == "1":
        # Only a receipt carrying the real-data assertion measures check 1; the
        # landmark and settled checks alone pass on an empty or placeholder page.
        if not any(c.get("check") == "1-real-data" for c in _checks(desktop, "1-")):
            return Verdict(False, "not measured: receipt has no 1-real-data result")
        return _all_pass(_checks(desktop, "1-"), "check 1")
    if check == "2":
        return _all_pass(_checks(desktop, "2-"), "check 2")
    if check == "4":
        return Verdict(bool(desktop), "" if desktop else "no receipt for this surface")
    if check in ("5", "6", "8"):
        if surface == "MC-00":
            return Verdict(False, "not measured: the hub has no Level 2 run (level2.spec.ts covers MC-01..19)")
        return _all_pass(_checks(l2, f"{check}-"), f"check {check}", allow_na=(check == "5"))
    if check == "9":
        if surface == "MC-00":
            return Verdict(False, "not measured: phone run excludes the hub nav check")
        return _all_pass(_checks(phone, "1-") + _checks(phone, "2-"), "check 9 (phone)")
    if check == "7":
        # scripts/mission_control_panel_coverage.py; N/A (no data panels) is not met.
        if not got.get("c7"):
            return Verdict(False, "not measured: no panel-coverage receipt for this surface")
        return _all_pass(_checks(got.get("c7"), "7-"), "check 7")
    if check == "11":
        return _judge_register(got.get("c11"))
    if check == "12":
        return _judge_label_honesty(got.get("w"))
    if check == "13":
        if not deployed_sha:
            return Verdict(False, "receipt names no deployed SHA (MC_LIVE_SHA unset)")
        return Verdict(True)
    return Verdict(False, f"unknown check {check}")


def score_surface(surface: str, receipts: dict[str, dict], run: dict | None = None,
                  history: list[dict] | None = None) -> dict:
    """Highest level whose every check (and every lower level's) is met.

    <run> is this run's metadata (event, run_id, run_attempt); <history> is
    earlier scheduled runs' scorecards (mission_control_stability.load_history).
    """
    got = receipts_for(surface, receipts)
    sha = (got.get("desktop") or {}).get("deployed_sha")
    verdicts = {c: judge(c, surface, got, sha) for lvl in (1, 2, 3) for c in LEVELS[lvl] if c != "10"}
    passed = suite_passed(surface, got)
    current = {"run_id": (run or {}).get("run_id"),
               "card": {"run": run or {}, "surfaces": [{"surface": surface, "suite_passed": passed}]}}
    verdicts["10"] = Verdict(*judge_stable(surface, current, history or []))
    level, blocker = 0, ""
    for lvl in (1, 2, 3):
        misses = [c for c in LEVELS[lvl] if not verdicts[c].met]
        if misses:
            blocker = f"check {misses[0]}: {verdicts[misses[0]].reason}"
            break
        level = lvl
    # Measured failures are reported even above the blocking level, so a check
    # that is not measured yet cannot hide one that ran and failed.
    failed = [f"{c}: {v.reason}" for c, v in verdicts.items() if not v.met and not v.reason.startswith("not measured")]
    return {
        "surface": surface,
        "level": level,
        "suite_passed": passed,
        "blocked_by": blocker,
        "measured_failures": failed,
        "checks": {c: {"met": v.met, "reason": v.reason} for c, v in verdicts.items()},
        "receipts": sorted(got),
    }


def build_scorecard(receipts: dict[str, dict], run: dict | None = None,
                    history: list[dict] | None = None) -> dict:
    rows = [score_surface(s, receipts, run, history) for s in SURFACES]
    return {"mission_control_level": min(r["level"] for r in rows), "run": run or {}, "surfaces": rows}


def to_markdown(card: dict) -> str:
    lvl = card["mission_control_level"]
    grade = f"Level {lvl}" if lvl else "below Level 1 (ungraded)"
    lines = [
        f"## Mission Control scorecard — {grade}",
        "",
        "Mission Control's level is its lowest surface (aaa-rating.md). "
        "A check with no evidence is not met.",
        "",
        "| Surface | Level | Blocking the next level | Measured failures |",
        "|---|---|---|---|",
    ]
    for r in card["surfaces"]:
        failed = "<br>".join(r["measured_failures"]) or "—"
        lines.append(f"| {r['surface']} | {r['level']} | {r['blocked_by'] or '—'} | {failed} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("receipts", type=Path)
    ap.add_argument("--json", type=Path, help="also write the scorecard as JSON here")
    ap.add_argument("--event", default="", help="GitHub event that started this run (check 10)")
    ap.add_argument("--run-id", type=int, default=None)
    ap.add_argument("--run-attempt", type=int, default=None)
    ap.add_argument("--history", type=Path, help="earlier scheduled runs' scorecards, one folder per run id")
    args = ap.parse_args(argv)
    if not args.receipts.is_dir():
        print(f"error: {args.receipts} is not a directory", file=sys.stderr)
        return 2
    run = {"event": args.event, "run_id": args.run_id, "run_attempt": args.run_attempt}
    card = build_scorecard(load_receipts(args.receipts), run, load_history(args.history))
    if args.json:
        args.json.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
    sys.stdout.write(to_markdown(card))
    return 0


if __name__ == "__main__":
    sys.exit(main())
