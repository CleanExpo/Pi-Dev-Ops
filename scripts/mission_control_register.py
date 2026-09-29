"""AAA check 11 — "Nothing documented broken", one receipt per surface.

docs/plans/mission-control/aaa-rating.md check 11: "No open CONFLICTING or
STRUCTURAL_ONLY row in the register, and no open ticket tagged to a Mission
Control surface as a defect." Two halves, two receipt checks:

- 11-register reads docs/plans/mission-control/coverage-register.md. A row
  whose evidence state is CONFLICTING or STRUCTURAL_ONLY fails; a surface with
  no row fails too, since an unlisted surface is undocumented, not clean.
- 11-tickets reads Linear: open issues (not completed or cancelled) carrying
  the label `mc-defect`. A ticket names its surfaces as MC-00..MC-19 in its
  title or description. One that names none fails no surface, because it
  cannot be placed; it is listed in each surface's detail and printed as a
  warning so it stays visible until someone names a surface on it.

Without LINEAR_API_KEY, or when Linear does not answer, 11-tickets is UNKNOWN
and the scorer reports check 11 "not measured" — never a pass.

Usage:
    python3 scripts/mission_control_register.py <out-dir> [--register PATH]
Writes MC-xx-C11.json. Exit 0 whenever the receipts were written.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "plans" / "mission-control" / "coverage-register.md"
SURFACES = [f"MC-{n:02d}" for n in range(20)]
LABEL = "mc-defect"
BAD_STATES = {"CONFLICTING", "STRUCTURAL_ONLY"}
STATES = ("VERIFIED", "PARTIAL", "STRUCTURAL_ONLY", "CONFLICTING", "UNKNOWN")
SURFACE_RE = re.compile(r"\bMC-(0\d|1\d)\b")
QUERY = """query($label: String!) { issues(first: 100, filter: {
  labels: { name: { eq: $label } }, state: { type: { nin: ["completed", "canceled"] } } }) {
  nodes { identifier title description } } }"""

Fetch = Callable[[str, dict], dict]


def register_states(text: str) -> dict[str, str]:
    """Surface -> evidence state word, from the register's Markdown table."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or not re.fullmatch(r"MC-\d\d", cells[0]):
            continue
        word = re.match(r"[A-Z_]+", cells[4])
        out[cells[0]] = word.group(0) if word and word.group(0) in STATES else "UNKNOWN"
    return out


def linear_fetch(api_key: str) -> Fetch:
    def fetch(query: str, variables: dict) -> dict:
        req = urllib.request.Request(
            "https://api.linear.app/graphql",
            data=json.dumps({"query": query, "variables": variables}).encode(),
            headers={"Authorization": api_key, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    return fetch


def open_defects(fetch: Fetch | None) -> tuple[dict[str, list[str]] | None, str, list[str]]:
    """Surface -> open mc-defect ticket ids, plus ids that name no surface.

    The map is None with a reason when Linear was unread.
    """
    if fetch is None:
        return None, "LINEAR_API_KEY not set; open defect tickets not read", []
    try:
        body = fetch(QUERY, {"label": LABEL})
        nodes = body["data"]["issues"]["nodes"]
    except Exception as exc:  # noqa: BLE001 — any failure means "not read"
        return None, f"Linear did not answer ({type(exc).__name__}); open defect tickets not read", []
    found: dict[str, list[str]] = {s: [] for s in SURFACES}
    unplaced: list[str] = []
    for node in nodes:
        text = f"{node.get('title') or ''}\n{node.get('description') or ''}"
        named = {f"MC-{m}" for m in SURFACE_RE.findall(text)} & set(SURFACES)
        if not named:
            unplaced.append(str(node.get("identifier")))
        for surface in sorted(named):
            found[surface].append(str(node.get("identifier")))
    return found, "", unplaced


def surface_checks(surface: str, states: dict[str, str],
                   defects: dict[str, list[str]] | None, why: str,
                   unplaced: list[str] | None = None) -> list[dict]:
    state = states.get(surface)
    if state is None:
        reg = {"result": "FAIL", "detail": "no row in coverage-register.md"}
    elif state in BAD_STATES:
        reg = {"result": "FAIL", "detail": f"register row is {state}"}
    else:
        reg = {"result": "PASS", "detail": f"register row is {state}"}
    if defects is None:
        tix = {"result": "UNKNOWN", "detail": why}
    elif defects[surface]:
        tix = {"result": "FAIL", "detail": f"open {LABEL} tickets: {', '.join(defects[surface])}"}
    else:
        note = f"; not placed on any surface, so not counted: {', '.join(unplaced)}" if unplaced else ""
        tix = {"result": "PASS", "detail": f"no open {LABEL} ticket names this surface{note}"}
    return [{"check": "11-register", **reg}, {"check": "11-tickets", **tix}]


def write_receipts(out_dir: Path, register_text: str, fetch: Fetch | None) -> dict[str, list[dict]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    states = register_states(register_text)
    defects, why, unplaced = open_defects(fetch)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    written: dict[str, list[dict]] = {}
    for surface in SURFACES:
        checks = surface_checks(surface, states, defects, why, unplaced)
        body = {"surface": f"{surface}-C11", "run_at": now, "checks": checks}
        (out_dir / f"{surface}-C11.json").write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        written[surface] = checks
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--register", type=Path, default=REGISTER)
    args = ap.parse_args(argv)
    key = (os.environ.get("LINEAR_API_KEY") or "").strip()
    written = write_receipts(args.out_dir, args.register.read_text(encoding="utf-8"),
                             linear_fetch(key) if key else None)
    ok = sum(all(c["result"] == "PASS" for c in checks) for checks in written.values())
    print(f"check 11: {ok}/{len(written)} surfaces pass")
    unplaced = next((c["detail"].split("counted: ")[1] for cs in written.values() for c in cs
                     if c["check"] == "11-tickets" and "counted: " in c["detail"]), "")
    if unplaced:
        print(f"::warning::{LABEL} tickets name no surface (MC-nn); not counted: {unplaced}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
