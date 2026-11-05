"""Night-queue picker: skip cooling accounts, prefer headroom (RA-8189, AR-03).

Each test names the why (W1..W6 in the PR body) it traces to. Inputs follow the
AR-01 map shape (ops/ACCOUNT-MAP.yaml) and the AR-02 record shape (headroom/1).
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "account_picker.py"
FIX = ROOT / "tests" / "fixtures" / "account_picker"
sys.path.insert(0, str(ROOT / "scripts"))

import account_picker as ap  # noqa: E402

NOW_DT = datetime(2026, 11, 5, 4, 0, tzinfo=timezone.utc)
NOW = NOW_DT.timestamp()
MAP = ap.load_map(FIX / "map.yaml")


def rec(event: object, machine: object = "mini", provider: str = "claude", ago_h: float = 1.0,
        reset_in_h: Optional[float] = None, **extra: object) -> dict:
    r = {"schema": "headroom/1", "ts": (NOW_DT - timedelta(hours=ago_h)).isoformat(),
         "machine": machine, "provider": provider, "event": event, "pattern_id": "x",
         "source": "observed", "reset_at": None, "exit_code": 1, "job": "RA-1"}
    if reset_in_h is not None:
        r["reset_at"] = (NOW_DT + timedelta(hours=reset_in_h)).isoformat()
    r.update(extra)
    return r


def pick(events: list, **kw: Any) -> dict:
    return ap.pick(MAP, events, provider=kw.pop("provider", "claude"), now=NOW, **kw)


def skipped(result: dict) -> dict:
    return {s["machine"]: s["reason"] for s in result["skipped"]}


# W1: a cooling seat is skipped; nothing else is.
@pytest.mark.parametrize("event", ["5h_cooling", "weekly_cooling", "auth_expired", "billing_blocked"])
def test_w1_each_skip_event_skips_the_machine(event: str) -> None:
    r = pick([rec(event, reset_in_h=2)])
    assert r["pick"] == "macbook"
    assert skipped(r)["mini"] == f"cooling: {event}"


def test_w1_event_on_other_provider_or_machine_does_not_skip() -> None:
    r = pick([rec("weekly_cooling", provider="codex", reset_in_h=5),
              rec("weekly_cooling", machine="pc", reset_in_h=5)])
    assert r["pick"] == "macbook"
    assert "mini" not in skipped(r) and "macbook" not in skipped(r)
    assert skipped(r)["pc"] == "cooling: weekly_cooling"


def test_w1_machine_without_a_pin_for_the_provider_is_skipped() -> None:
    r = pick([], provider="codex")
    assert r["pick"] == "mini"
    assert skipped(r)["macbook"] == "no codex pin" and skipped(r)["pc"] == "no codex pin"


def test_w1_machine_with_two_pins_for_the_provider_is_skipped() -> None:
    amap = {"machines": ["mini", "macbook"], "accounts": [
        {"provider": "claude", "max": True, "machines": ["mini"]},
        {"provider": "claude", "max": True, "machines": ["mini", "macbook"]}]}
    r = ap.pick(amap, [], provider="claude", now=NOW)
    assert r["pick"] == "macbook" and skipped(r)["mini"] == "2 claude pins"


def test_w1_all_cooling_means_no_pick() -> None:
    evs = [rec("5h_cooling", machine=m, reset_in_h=1) for m in ("mini", "macbook", "pc")]
    assert pick(evs)["pick"] is None


# W2: holds end on time.
def test_w2_printed_reset_wins_and_hold_ends() -> None:
    r = rec("weekly_cooling", ago_h=30, reset_in_h=-0.5)
    assert ap.hold_until(r) < NOW
    assert pick([r])["pick"] in ("mini", "macbook") and "mini" not in skipped(pick([r]))


@pytest.mark.parametrize("event,hold_h", [("5h_cooling", 5), ("weekly_cooling", 24),
                                          ("auth_expired", 12), ("billing_blocked", 12),
                                          ("on_demand_capped", 12)])
def test_w2_null_reset_uses_the_fallback_hold(event: str, hold_h: float) -> None:
    assert "mini" in skipped(pick([rec(event, ago_h=hold_h - 0.1)]))
    assert "mini" not in skipped(pick([rec(event, ago_h=hold_h + 0.1)]))


def test_w2_misread_reset_beyond_eight_days_uses_fallback() -> None:
    r = rec("5h_cooling", ago_h=6, reset_in_h=24 * 30)
    assert "mini" not in skipped(pick([r]))


def test_w2_longest_hold_wins_over_a_newer_short_one() -> None:
    evs = [rec("weekly_cooling", ago_h=10, reset_in_h=40), rec("5h_cooling", ago_h=6)]
    assert skipped(pick(evs))["mini"] == "cooling: weekly_cooling"


# W3: no automated path into paid overflow.
def test_w3_on_demand_capped_is_skipped() -> None:
    assert skipped(pick([rec("on_demand_capped")]))["mini"] == "cooling: on_demand_capped"


# W4: prefer headroom, keep Max seats even.
def test_w4_green_beats_recently_recovered() -> None:
    r = pick([rec("5h_cooling", machine="macbook", ago_h=8)], job_hours={"mini": 9, "macbook": 1})
    assert r["pick"] == "mini"
    assert {x["machine"]: x["state"] for x in r["ranked"]}["macbook"] == "recovered"


def test_w4_fewer_job_hours_wins_between_green_max_seats() -> None:
    assert pick([], job_hours={"mini": 10, "macbook": 4})["pick"] == "macbook"
    assert pick([], job_hours={"mini": 4, "macbook": 10})["pick"] == "mini"


def test_w4_max_seat_beats_undecided_plan() -> None:
    r = pick([], job_hours={"mini": 50, "macbook": 50, "pc": 0})
    assert [x["machine"] for x in r["ranked"]][-1] == "pc"


def test_w4_evenness_within_and_outside_twenty_percent() -> None:
    assert ap.evenness({"mini": 10, "macbook": 11.5})["status"] == "even"
    out = ap.evenness({"mini": 10, "macbook": 16})
    assert out["status"] == "uneven" and out["tolerance"] == 0.2


def test_w4_missing_job_hours_is_unknown_not_even() -> None:
    assert pick([])["evenness"]["status"] == "UNKNOWN"
    assert pick([], job_hours={"mini": 3})["evenness"]["status"] == "UNKNOWN"


def test_w4_candidates_limit_the_choice() -> None:
    assert pick([], candidates=["pc"])["pick"] == "pc"
    with pytest.raises(ap.InputError):
        pick([], candidates=["nope"])


# W5: a failed read never looks like a quiet night.
def test_w5_unmounted_log_folder_is_unknown(tmp_path: Path) -> None:
    with pytest.raises(ap.LogUnknown):
        ap.read_log(tmp_path / "no-ssd" / "headroom" / "h.jsonl")


def test_w5_mounted_folder_without_file_is_absent_not_unknown(tmp_path: Path) -> None:
    out = ap.read_log(tmp_path / "h.jsonl")
    assert out == {"status": "absent", "events": [], "malformed": 0}


def test_w5_malformed_and_unknown_event_lines_are_counted_not_trusted(tmp_path: Path) -> None:
    p = tmp_path / "h.jsonl"
    lines = [json.dumps(rec("weekly_cooling", reset_in_h=5)), "{not json",
             json.dumps(rec("made_up_event")), json.dumps(rec("5h_cooling", schema="other/9")),
             json.dumps(rec("5h_cooling", ts="yesterday")), json.dumps([1, 2])]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = ap.read_log(p)
    assert len(out["events"]) == 1 and out["malformed"] == 5


def test_w5_bad_map_is_an_input_error(tmp_path: Path) -> None:
    for body in ("machines: 3\n", "accounts: []\n", "machines:\n  - id: 'bad id!'\naccounts: []\n", ":\n- ["):
        p = tmp_path / "m.yaml"
        p.write_text(body, encoding="utf-8")
        with pytest.raises(ap.InputError):
            ap.load_map(p)
    with pytest.raises(ap.InputError):
        ap.load_map(tmp_path / "missing.yaml")


def run_cli(*args: str, env_home: Optional[Path] = None) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin", "HOME": str(env_home or ROOT)}
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          env=env, timeout=60)


def test_w5_cli_exit_codes(tmp_path: Path) -> None:
    m = str(FIX / "map.yaml")
    assert run_cli("--map", m, "--log", str(tmp_path / "x" / "h.jsonl")).returncode == 3
    assert run_cli("--map", str(tmp_path / "none.yaml"), "--log", str(tmp_path / "h.jsonl")).returncode == 2
    ok = run_cli("--map", m, "--log", str(tmp_path / "h.jsonl"), "--now", NOW_DT.isoformat())
    assert ok.returncode == 0 and json.loads(ok.stdout)["log"]["status"] == "absent"


# W6: no credential reads, nothing foreign echoed.
def test_w6_output_never_contains_an_email_or_planted_text() -> None:
    cp = run_cli("--map", str(FIX / "map.yaml"), "--log", str(FIX / "cooling.jsonl"),
                 "--now", NOW_DT.isoformat())
    assert cp.returncode == 0 and json.loads(cp.stdout)["pick"] == "macbook"
    assert "@" not in cp.stdout + cp.stderr
    assert "PLANTED-MARKER" not in cp.stdout + cp.stderr


def test_w6_opens_only_the_paths_it_is_given(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".credentials.json").write_text("{}", encoding="utf-8")
    probe = ("import json,runpy,sys\nseen=[]\n"
             "sys.addaudithook(lambda e,a: seen.append(str(a[0])) if e=='open' else None)\n"
             f"sys.argv=['p','--map',{str(FIX / 'map.yaml')!r},'--log',{str(FIX / 'cooling.jsonl')!r}]\n"
             "try:\n runpy.run_path(%r, run_name='__main__')\nexcept SystemExit:\n pass\n"
             "sys.stderr.write('SEEN='+json.dumps(seen))\n" % str(SCRIPT))
    cp = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=60,
                        env={"PATH": "/usr/bin:/bin", "HOME": str(home)})
    seen = json.loads(cp.stderr.split("SEEN=")[-1])
    data = [p for p in seen if not p.endswith((".py", ".pyc", ".so", ".pth")) and "/lib/python" not in p
            and not p.isdigit()]
    assert sorted(set(data)) == sorted({str(FIX / "map.yaml"), str(FIX / "cooling.jsonl")}), data
    assert not any(".claude" in p or "credential" in p.lower() for p in seen)


def test_w5_far_future_timestamp_does_not_crash() -> None:
    r = pick([rec("5h_cooling", ts="9999-12-31T23:00:00+00:00")])
    assert skipped(r)["mini"] == "cooling: 5h_cooling" and r["pick"] == "macbook"


@pytest.mark.parametrize("body", ['{"mini": Infinity}', '{"mini": NaN}', '{"mini": -1}', '{"mini": true}', "[1]"])
def test_w5_bad_job_hours_table_is_an_input_error(tmp_path: Path, body: str) -> None:
    p = tmp_path / "h.json"
    p.write_text(body, encoding="utf-8")
    with pytest.raises(ap.InputError):
        ap._load_hours(p)


def test_w5_wrongly_typed_fields_are_malformed_not_a_crash(tmp_path: Path) -> None:
    p = tmp_path / "h.jsonl"
    lines = [json.dumps(rec(["weekly_cooling"])), json.dumps(rec({"a": 1})),
             json.dumps(rec("5h_cooling", schema=["headroom/1"])), json.dumps(rec("5h_cooling", machine=7))]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = ap.read_log(p)
    assert out["events"] == [] and out["malformed"] == 4


# CodeRabbit review on #971: edge cases where a bad input could still look like a clean pick.
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
