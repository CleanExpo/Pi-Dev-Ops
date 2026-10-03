"""RA-7898 T6 — every Mission Control surface id is present in every list that enumerates them.

The MC list is enumerated in five places. A surface added to one and missed in another
is invisible to whichever check reads the list it is missing from, and passes there by
absence. This compares all five against the register script's SURFACES.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from scripts import mission_control_register as mr
from scripts import mission_control_scorecard as sc

ROOT = Path(__file__).resolve().parents[1]


def test_register_and_scorecard_agree() -> None:
    assert mr.SURFACES == sc.SURFACES
    assert "MC-20" in mr.SURFACES


def test_every_surface_has_a_register_row() -> None:
    text = (ROOT / "docs/plans/mission-control/coverage-register.md").read_text(encoding="utf-8")
    rows = set(re.findall(r"^\| (MC-\d\d) \|", text, re.M))
    assert rows == set(mr.SURFACES)


def test_every_page_surface_is_in_the_live_suite_and_panel_coverage() -> None:
    live = (ROOT / "dashboard/e2e-live/surfaces.ts").read_text(encoding="utf-8")
    # MC-02..MC-12 come from CONTROL_SECTIONS via CONTROL_IDS; the rest are literal ids.
    in_live = set(re.findall(r'"(MC-\d\d)"', live))
    coverage = json.loads((ROOT / "dashboard/e2e-live/panel-coverage.json").read_text(encoding="utf-8"))
    # MC-00 is the shell, proved by control-hub.spec.ts rather than a LIVE_SURFACES row.
    assert in_live | {"MC-00"} == set(mr.SURFACES)
    assert set(coverage["surfaces"]) == set(mr.SURFACES)


def test_the_surface_regex_matches_every_surface_and_no_more() -> None:
    for sid in mr.SURFACES:
        assert mr.SURFACE_RE.search(f"fixes {sid} today"), sid
    assert not mr.SURFACE_RE.search(f"MC-{len(mr.SURFACES):02d}")
