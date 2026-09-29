"""WP-11 scorecard: the aaa-rating.md rules applied to live-suite receipts.

The rules that matter most are the ones that stop a grade being flattering:
a check with no evidence is not met, a missing receipt is not met, one bad
surface sets Mission Control's level, and a measured failure is reported even
when an unmeasured check already blocks the level.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import mission_control_scorecard as sc


def _receipt(folder: Path, stem: str, checks: dict[str, str], sha: str | None = "abc123") -> None:
    body = {
        "surface": stem,
        "target": "https://example.test",
        "deployed_sha": sha,
        "run_at": "2026-09-29T00:00:00Z",
        "checks": [{"check": k, "result": v, "detail": f"{k} detail"} for k, v in checks.items()],
    }
    (folder / f"{stem}.json").write_text(json.dumps(body), encoding="utf-8")


READ_OK = {"1-stayed-on-page": "PASS", "1-landmark": "PASS", "2-no-hidden-refusals": "PASS"}
L2_OK = {"5-failure-path": "PASS", "6-auth-boundary": "PASS", "8-accessibility": "PASS"}


def _all_green(folder: Path, surface: str = "MC-13", path: str = "_command-centre") -> None:
    _receipt(folder, f"{surface}{path}", READ_OK)
    _receipt(folder, f"{surface}{path}@phone", READ_OK)
    _receipt(folder, f"{surface}{path}-L2", L2_OK)


def test_unmeasured_check_one_keeps_every_surface_below_level_one(tmp_path: Path) -> None:
    _all_green(tmp_path)
    row = sc.score_surface("MC-13", sc.load_receipts(tmp_path))
    assert row["level"] == 0
    assert row["blocked_by"].startswith("check 1: not measured")
    assert row["measured_failures"] == []


def test_missing_receipts_are_not_met_never_pass(tmp_path: Path) -> None:
    row = sc.score_surface("MC-13", sc.load_receipts(tmp_path))
    assert row["checks"]["4"]["met"] is False
    assert row["checks"]["2"]["met"] is False
    assert row["checks"]["8"]["met"] is False


def test_measured_failure_is_reported_even_above_the_blocking_level(tmp_path: Path) -> None:
    _all_green(tmp_path)
    _receipt(tmp_path, "MC-13_command-centre-L2", {**L2_OK, "8-accessibility": "FAIL"})
    row = sc.score_surface("MC-13", sc.load_receipts(tmp_path))
    assert any(f.startswith("8: 8-accessibility FAIL") for f in row["measured_failures"])


def test_failure_path_na_counts_as_met_but_other_na_does_not(tmp_path: Path) -> None:
    _all_green(tmp_path)
    _receipt(tmp_path, "MC-13_command-centre-L2", {**L2_OK, "5-failure-path": "N/A"})
    got = sc.receipts_for("MC-13", sc.load_receipts(tmp_path))
    assert sc.judge("5", "MC-13", got, "abc").met is True
    _receipt(tmp_path, "MC-13_command-centre-L2", {**L2_OK, "6-auth-boundary": "N/A"})
    got = sc.receipts_for("MC-13", sc.load_receipts(tmp_path))
    assert sc.judge("6", "MC-13", got, "abc").met is False


def test_phone_receipt_decides_check_nine(tmp_path: Path) -> None:
    _all_green(tmp_path)
    _receipt(tmp_path, "MC-13_command-centre@phone", {**READ_OK, "2-no-hidden-refusals": "FAIL"})
    got = sc.receipts_for("MC-13", sc.load_receipts(tmp_path))
    assert sc.judge("9", "MC-13", got, "abc").met is False
    assert sc.judge("2", "MC-13", got, "abc").met is True  # desktop check 2 is separate


def test_write_only_checks_are_na_for_read_only_surfaces(tmp_path: Path) -> None:
    got = sc.receipts_for("MC-13", sc.load_receipts(tmp_path))
    assert sc.judge("3", "MC-13", got, "abc").met is True
    assert sc.judge("3", "MC-02", got, "abc").met is False


def test_no_deployed_sha_fails_live_deploy_linkage(tmp_path: Path) -> None:
    _receipt(tmp_path, "MC-13_command-centre", READ_OK, sha=None)
    row = sc.score_surface("MC-13", sc.load_receipts(tmp_path))
    assert row["checks"]["13"]["met"] is False
    assert "no deployed SHA" in row["checks"]["13"]["reason"]


def test_hub_receipt_maps_to_mc00_and_its_level_two_is_not_measured(tmp_path: Path) -> None:
    _receipt(tmp_path, "control-hub", {"1-nav-labels": "PASS", "2-no-hidden-refusals": "PASS"})
    row = sc.score_surface("MC-00", sc.load_receipts(tmp_path))
    assert row["receipts"] == ["desktop"]
    assert row["checks"]["8"]["reason"].startswith("not measured")


def test_mission_control_level_is_the_lowest_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    levels = iter([3] * 19 + [1])
    monkeypatch.setattr(sc, "score_surface", lambda s, r: {"surface": s, "level": next(levels)})
    assert sc.build_scorecard({})["mission_control_level"] == 1


def test_cli_writes_markdown_and_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _all_green(tmp_path)
    out = tmp_path / "card.json"
    assert sc.main([str(tmp_path), "--json", str(out)]) == 0
    assert "below Level 1" in capsys.readouterr().out
    assert len(json.loads(out.read_text())["surfaces"]) == 20


def test_cli_rejects_a_missing_folder(tmp_path: Path) -> None:
    assert sc.main([str(tmp_path / "nope")]) == 2
