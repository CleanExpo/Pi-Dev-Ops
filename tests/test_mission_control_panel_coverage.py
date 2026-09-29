"""AAA check 7 scorer: panel tests must pass, import the panel, and cover all three states.

The rules that stop a flattering grade: a failing test does not count, a
mocked panel is not a tested panel, one file's cases cannot stand in for
another panel it also imports, and a page with no panels is N/A, not PASS.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import mission_control_panel_coverage as pc
from scripts import mission_control_scorecard as sc

ALL = ["LOADED: shows rows", "EMPTY: says none", "ERROR: says failed"]


def _dashboard(tmp_path: Path) -> Path:
    d = tmp_path / "dashboard"
    (d / "__tests__").mkdir(parents=True)
    return d


def _test_file(d: Path, name: str, body: str) -> str:
    path = d / "__tests__" / name
    path.write_text(body, encoding="utf-8")
    return str(path)


def _report(rows: dict[str, list[tuple[str, str, list[str]]]]) -> dict:
    """file -> [(title, status, ancestors)] as vitest's JSON reporter writes it."""
    return {"testResults": [
        {"name": f, "assertionResults": [
            {"title": t, "status": st, "ancestorTitles": anc} for t, st, anc in tests]}
        for f, tests in rows.items()]}


def _judge(d: Path, modules: list[str], report: dict, registered: set[str] | None = None):
    titles = pc.passing_titles(report)
    return pc.judge_surface(modules, registered or set(modules), d, titles)


def test_panel_with_passing_loaded_empty_error_tests_passes(tmp_path: Path) -> None:
    d = _dashboard(tmp_path)
    f = _test_file(d, "panel.test.tsx", 'import Panel from "@/components/control/Panel";\n')
    report = _report({f: [(t, "passed", ["Panel"]) for t in ALL]})
    assert _judge(d, ["components/control/Panel"], report)[0] == "PASS"


def test_a_failing_test_does_not_cover_its_state(tmp_path: Path) -> None:
    d = _dashboard(tmp_path)
    f = _test_file(d, "panel.test.tsx", 'import Panel from "@/components/control/Panel";\n')
    report = _report({f: [(ALL[0], "passed", []), (ALL[1], "passed", []), (ALL[2], "failed", [])]})
    result, detail = _judge(d, ["components/control/Panel"], report)
    assert result == "FAIL" and "lacks ERROR" in detail


def test_a_file_that_does_not_import_the_panel_does_not_count(tmp_path: Path) -> None:
    d = _dashboard(tmp_path)
    f = _test_file(d, "other.test.tsx", 'import Other from "@/components/control/Other";\n')
    report = _report({f: [(t, "passed", []) for t in ALL]})
    assert _judge(d, ["components/control/Panel"], report)[0] == "FAIL"


def test_a_mocked_panel_is_not_a_tested_panel(tmp_path: Path) -> None:
    d = _dashboard(tmp_path)
    body = ('vi.mock("@/components/control/Panel", async () => await import("@/components/control/Panel"));\n'
            'import Page from "@/components/control/Page";\n')
    f = _test_file(d, "page.test.tsx", body)
    report = _report({f: [(t, "passed", []) for t in ALL]})
    assert _judge(d, ["components/control/Panel"], report, {"components/control/Panel"})[0] == "FAIL"


def test_a_shared_file_counts_only_tests_that_name_the_panel(tmp_path: Path) -> None:
    d = _dashboard(tmp_path)
    body = 'import A from "@/components/control/Alpha";\nimport B from "@/components/control/Beta";\n'
    f = _test_file(d, "both.test.tsx", body)
    report = _report({f: [(t, "passed", ["Alpha"]) for t in ALL] + [(ALL[0], "passed", ["Beta"])]})
    mods = ["components/control/Alpha", "components/control/Beta"]
    result, detail = _judge(d, mods, report)
    assert result == "FAIL" and detail == "Beta lacks EMPTY/ERROR"


def test_relative_imports_resolve_to_the_panel(tmp_path: Path) -> None:
    d = _dashboard(tmp_path)
    f = _test_file(d, "rel.test.tsx", 'import Panel from "../components/control/Panel.tsx";\n')
    report = _report({f: [(t, "passed", []) for t in ALL]})
    assert _judge(d, ["components/control/Panel"], report)[0] == "PASS"


def test_a_page_with_no_panels_is_na_and_the_scorer_does_not_count_it(tmp_path: Path) -> None:
    d = _dashboard(tmp_path)
    assert _judge(d, [], _report({}))[0] == "N/A"
    out = tmp_path / "receipts"
    pc.write_receipts({"surfaces": {"MC-13": []}}, _report({}), d, out)
    got = sc.receipts_for("MC-13", sc.load_receipts(out))
    assert sc.judge("7", "MC-13", got, "abc").met is False


def test_c7_receipt_decides_check_seven_without_replacing_the_desktop_receipt(tmp_path: Path) -> None:
    d = _dashboard(tmp_path)
    f = _test_file(d, "panel.test.tsx", 'import Panel from "@/components/control/Panel";\n')
    out = tmp_path / "receipts"
    out.mkdir()
    (out / "MC-08_control_runs.json").write_text(json.dumps({"checks": [{"check": "1-x", "result": "PASS"}]}))
    report = _report({f: [(t, "passed", []) for t in ALL]})
    pc.write_receipts({"surfaces": {"MC-08": ["components/control/Panel"]}}, report, d, out)
    got = sc.receipts_for("MC-08", sc.load_receipts(out))
    assert set(got) == {"desktop", "c7"}
    assert sc.judge("7", "MC-08", got, "abc").met is True


def test_cli_writes_one_receipt_per_surface(tmp_path: Path) -> None:
    d = _dashboard(tmp_path)
    reg = tmp_path / "reg.json"
    reg.write_text(json.dumps({"surfaces": {"MC-13": [], "MC-08": ["components/control/Panel"]}}))
    rep = tmp_path / "rep.json"
    rep.write_text(json.dumps(_report({})))
    out = tmp_path / "out"
    assert pc.main([str(rep), str(out), "--registry", str(reg), "--dashboard", str(d)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["MC-08-C7.json", "MC-13-C7.json"]
    assert pc.main([str(tmp_path / "missing.json"), str(out), "--registry", str(reg)]) == 2
