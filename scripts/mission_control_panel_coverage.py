"""AAA check 7 — component-test coverage per Mission Control surface.

docs/plans/mission-control/aaa-rating.md check 7: every panel on a page has at
least one vitest test covering its loaded, empty and error states. This reads
the panels per surface from dashboard/e2e-live/panel-coverage.json and one
vitest JSON report, and writes one receipt per surface (`MC-xx-C7.json`) with a
`7-component-tests` result that scripts/mission_control_scorecard.py reads.

A state is covered only by a PASSING test whose title starts with LOADED,
EMPTY or ERROR (the convention the panel test files already use), in a test
file that imports the panel. A file that imports several listed panels counts
for one of them only through tests whose describe/title names that panel, so
one file's error cases cannot stand in for another panel's. A surface with no
data panels is N/A, which the scorer does not count as met.

Usage:
    python3 scripts/mission_control_panel_coverage.py <vitest-report.json> <receipts-dir>
        [--registry dashboard/e2e-live/panel-coverage.json] [--dashboard dashboard]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

STATES = ("LOADED", "EMPTY", "ERROR")
_IMPORT = re.compile(r"""(?:\bfrom\s+|\bimport\s*\(\s*|^\s*import\s+)["']([^"']+)["']""", re.M)
_MOCK = re.compile(r"""\bvi\.(?:do)?[mM]ock\(\s*["']([^"']+)["']""")
_EXTS = (".tsx", ".ts", ".jsx", ".js")


def _strip_ext(path: str) -> str:
    for ext in _EXTS:
        if path.endswith(ext):
            return path[: -len(ext)]
    return path.removesuffix("/index")


def _resolve(spec: str, test_file: Path, dashboard: Path) -> str | None:
    if spec.startswith("@/"):
        return _strip_ext(spec[2:])
    if spec.startswith("."):
        full = os.path.normpath(os.path.join(test_file.parent, spec))
        return _strip_ext(os.path.relpath(full, dashboard))
    return None


def imported_modules(test_file: Path, dashboard: Path) -> set[str]:
    """Dashboard-relative modules a test file imports and does not mock.

    A module replaced with vi.mock is a stand-in, so that file is not testing
    it — even if the mock factory imports the real module.
    """
    try:
        text = test_file.read_text(encoding="utf-8")
    except OSError:
        return set()
    imported = {_resolve(s, test_file, dashboard) for s in _IMPORT.findall(text)}
    mocked = {_resolve(s, test_file, dashboard) for s in _MOCK.findall(text)}
    return {m for m in imported - mocked if m}


def passing_titles(report: dict) -> dict[str, list[tuple[str, str]]]:
    """Test file path -> [(title, describe path + title)] for every passing test."""
    out: dict[str, list[tuple[str, str]]] = {}
    for suite in report.get("testResults", []):
        rows = [
            (a.get("title", ""), " ".join([*a.get("ancestorTitles", []), a.get("title", "")]))
            for a in suite.get("assertionResults", [])
            if a.get("status") == "passed"
        ]
        out[suite.get("name", "")] = rows
    return out


def panel_name(module: str) -> str:
    """Component name, or "<route>/page" for a Next.js page module."""
    parts = module.split("/")
    return "/".join(parts[-2:]) if parts[-1] == "page" else parts[-1]


def states_covered(module: str, registered: set[str], dashboard: Path,
                   titles: dict[str, list[tuple[str, str]]]) -> dict[str, list[str]]:
    """State -> test files proving it for one panel module."""
    name = panel_name(module).split("/")[-1] if not module.endswith("/page") else "page"
    found: dict[str, list[str]] = {s: [] for s in STATES}
    for file, rows in titles.items():
        imports = imported_modules(Path(file), dashboard)
        if module not in imports:
            continue
        shared = len(imports & registered) > 1
        for title, full in rows:
            state = next((s for s in STATES if re.match(rf"{s}\b", title)), None)
            if state and (not shared or name in full):
                found[state].append(os.path.basename(file))
    return found


def judge_surface(modules: list[str], registered: set[str], dashboard: Path,
                  titles: dict[str, list[tuple[str, str]]]) -> tuple[str, str]:
    """(result, detail) for one surface's 7-component-tests check."""
    if not modules:
        return "N/A", "no data panels on this page"
    gaps: list[str] = []
    for module in modules:
        found = states_covered(module, registered, dashboard, titles)
        missing = [s for s in STATES if not found[s]]
        if missing:
            gaps.append(f"{panel_name(module)} lacks {'/'.join(missing)}")
    if gaps:
        return "FAIL", "; ".join(gaps)
    return "PASS", f"{len(modules)} panel(s) with passing LOADED, EMPTY and ERROR tests"


def write_receipts(registry: dict, report: dict, dashboard: Path, out_dir: Path) -> dict[str, str]:
    """Write MC-xx-C7.json per surface; return surface -> result."""
    surfaces: dict[str, list[str]] = registry["surfaces"]
    registered = {m for mods in surfaces.values() for m in mods}
    titles = passing_titles(report)
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results: dict[str, str] = {}
    for surface, modules in sorted(surfaces.items()):
        result, detail = judge_surface(modules, registered, dashboard, titles)
        body = {"surface": f"{surface}-C7", "run_at": now,
                "checks": [{"check": "7-component-tests", "result": result, "detail": detail}]}
        (out_dir / f"{surface}-C7.json").write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        results[surface] = result
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report", type=Path, help="vitest --reporter=json output")
    ap.add_argument("out_dir", type=Path, help="receipts directory")
    ap.add_argument("--registry", type=Path, default=Path("dashboard/e2e-live/panel-coverage.json"))
    ap.add_argument("--dashboard", type=Path, default=Path("dashboard"))
    args = ap.parse_args(argv)
    try:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    results = write_receipts(registry, report, args.dashboard.resolve(), args.out_dir)
    passed = sum(r == "PASS" for r in results.values())
    print(f"check 7: {passed}/{len(results)} surfaces pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
