"""Account picker edge cases raised in review of PR #971 (RA-8189, AR-03).

Each is a way a bad input could still look like a clean pick. Every test was seen failing
before its fix. Helpers and fixtures are shared with tests/test_account_picker.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_account_picker import FIX, NOW, ap, pick, run_cli, skipped  # noqa: E402


def test_w5_dangling_log_symlink_is_unknown_not_absent(tmp_path: Path) -> None:
    (tmp_path / "h.jsonl").symlink_to(tmp_path / "gone" / "h.jsonl")
    with pytest.raises(ap.LogUnknown):
        ap.read_log(tmp_path / "h.jsonl")


def test_w5_duplicate_keys_in_the_map_are_an_input_error(tmp_path: Path) -> None:
    p = tmp_path / "m.yaml"
    p.write_text("machines:\n  - id: mini\n  - id: macbook\naccounts:\n  - provider: claude\n"
                 "    machines: [mini]\n    machines: [macbook]\n", encoding="utf-8")
    with pytest.raises(ap.InputError):
        ap.load_map(p)


@pytest.mark.parametrize("body", ['{"mini": 1e308, "macbook": 1e308}', '{"mini": 1' + "0" * 400 + "}"],
                         ids=["sum-overflows", "int-beyond-float"])
def test_w5_job_hours_too_large_for_a_float_is_an_input_error(tmp_path: Path, body: str) -> None:
    p = tmp_path / "h.json"
    p.write_text(body, encoding="utf-8")
    with pytest.raises(ap.InputError):
        ap._load_hours(p)


def test_w4_evenness_compares_the_unrounded_deviation() -> None:
    assert ap.evenness({"mini": 7996, "macbook": 12004})["status"] == "uneven"


def test_w4_missing_job_hours_entry_is_not_ranked_as_zero() -> None:
    r = pick([], job_hours={"mini": 10})
    rows = {x["machine"]: x["job_hours"] for x in r["ranked"]}
    assert rows["macbook"] is None and r["pick"] == "mini"


def test_w4_empty_candidate_list_picks_nothing() -> None:
    assert pick([], candidates=[])["pick"] is None


def test_w1_reads_a_record_written_by_the_ar02_logger(tmp_path: Path) -> None:
    import headroom_events as he
    hit = {"event": "weekly_cooling", "pattern_id": "x", "source": "observed", "reset_at": NOW + 3600}
    he.append_events([he.build_record(hit, machine="mini", provider="claude", job="RA-1",
                                      exit_code=1, now=NOW - 60)], tmp_path / "h.jsonl")
    log = ap.read_log(tmp_path / "h.jsonl")
    assert log["malformed"] == 0 and skipped(pick(log["events"]))["mini"] == "cooling: weekly_cooling"


def test_w5_yaml_merge_keys_still_load(tmp_path: Path) -> None:
    p = tmp_path / "m.yaml"
    p.write_text("base: &b {provider: claude, plan: max}\nmachines:\n  - id: mini\naccounts:\n"
                 "  - <<: *b\n    machines: [mini]\n", encoding="utf-8")
    assert ap.load_map(p)["accounts"] == [{"provider": "claude", "max": True, "machines": ["mini"]}]


def test_w5_log_folder_that_cannot_be_searched_is_unknown(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def denied(self: Path) -> bool:
        raise PermissionError(13, "denied")
    monkeypatch.setattr(Path, "is_dir", denied)
    with pytest.raises(ap.LogUnknown):
        ap.read_log(tmp_path / "h.jsonl")


def test_w4_empty_machines_option_picks_nothing(tmp_path: Path) -> None:
    cp = run_cli("--map", str(FIX / "map.yaml"), "--log", str(tmp_path / "h.jsonl"), "--machines", "")
    assert cp.returncode == 1 and json.loads(cp.stdout)["pick"] is None
