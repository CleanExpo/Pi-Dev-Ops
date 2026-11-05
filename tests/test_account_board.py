"""Ops Board usage board over ACCOUNT-MAP + HEADROOM (RA-8190, AR-04).

Each test names the why (W1..W6 in the PR body) it traces to. Inputs follow the
AR-01 map shape (ops/ACCOUNT-MAP.yaml) and the AR-02 record shape (headroom/1).
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "account_board.py"
FIX = ROOT / "tests" / "fixtures" / "account_board"
sys.path.insert(0, str(ROOT / "scripts"))

import account_board as ab  # noqa: E402

NOW_DT = datetime(2026, 11, 5, 4, 0, tzinfo=UTC)
NOW = NOW_DT.timestamp()
MAP = ab.load_accounts(FIX / "map.yaml")
CLEAN = """version: 1
machines: [{id: mini}, {id: macbook}]
accounts:
  - {label: claude-mini, provider: claude, plan: max, email: a@x.invalid, machines: [mini]}
  - {label: claude-macbook, provider: claude, plan: max, email: b@x.invalid, machines: [macbook]}
"""


def rec(event: str, machine: str = "mini", provider: str = "claude", ago_h: float = 1.0,
        reset_in_h: float | None = None) -> dict:
    reset = None if reset_in_h is None else (NOW_DT + timedelta(hours=reset_in_h)).isoformat()
    return {"schema": "headroom/1", "ts": (NOW_DT - timedelta(hours=ago_h)).isoformat(),
            "machine": machine, "provider": provider, "event": event, "reset_at": reset}


def row(board: dict, label: str) -> dict:
    return next(r for r in board["rows"] if r["label"] == label)


def kinds(board: dict) -> list:
    return sorted(a["kind"] for a in board["alerts"])


def clean_map(tmp_path: Path, text: str = CLEAN) -> dict:
    p = tmp_path / "map.yaml"
    p.write_text(text, encoding="utf-8")
    return ab.load_accounts(p)


# W1: Phill sees which seat can take work, in the ticket's state words.
@pytest.mark.parametrize("event", ["5h_cooling", "weekly_cooling", "auth_expired",
                                   "billing_blocked", "on_demand_capped"])
def test_each_hold_event_is_the_row_state(event: str) -> None:
    board = ab.build(MAP, [rec(event)], now=NOW)
    assert row(board, "claude-mini")["state"] == event
    assert row(board, "claude-macbook")["state"] == "green"


def test_expired_hold_is_green_but_last_event_still_shown() -> None:
    board = ab.build(MAP, [rec("5h_cooling", ago_h=6)], now=NOW)
    r = row(board, "claude-mini")
    assert r["state"] == "green" and r["reset_at"] is None
    assert r["last_event"] == {"event": "5h_cooling", "at": "2026-11-05 08:00 AEST", "machine": "mini"}


def test_events_for_another_provider_do_not_touch_the_row() -> None:
    board = ab.build(MAP, [rec("auth_expired", provider="codex")], now=NOW)
    assert row(board, "claude-mini")["state"] == "green"
    assert row(board, "codex-mini")["state"] == "auth_expired"


# W2: reset times are read in AEST, and a guessed reset is labelled as one.
def test_printed_reset_shown_in_aest() -> None:
    board = ab.build(MAP, [rec("weekly_cooling", reset_in_h=25)], now=NOW)
    r = row(board, "claude-mini")
    assert r["reset_at"] == "2026-11-06 15:00 AEST" and r["reset_source"] == "printed"


def test_no_printed_reset_is_a_fallback_estimate() -> None:
    r = row(ab.build(MAP, [rec("auth_expired")], now=NOW), "claude-mini")
    assert r["reset_at"] == "2026-11-06 01:00 AEST" and r["reset_source"] == "fallback"


# W3: job counts and hours are unknown (null) without a source, never a reassuring 0.
def test_jobs_and_hours_null_without_tables() -> None:
    r = row(ab.build(MAP, [], now=NOW), "claude-mini")
    assert r["active_jobs"] is None and r["queued_jobs"] is None and r["job_hours_7d"] is None


def test_jobs_and_hours_from_tables() -> None:
    board = ab.build(MAP, [], now=NOW, jobs={"mini": {"active": 1, "queued": 3}},
                     hours={"mini": 31.5})
    r = row(board, "claude-mini")
    assert (r["active_jobs"], r["queued_jobs"], r["job_hours_7d"]) == (1, 3, 31.5)
    assert row(board, "claude-macbook")["job_hours_7d"] is None


def test_multi_machine_account_sums_only_when_all_known(tmp_path: Path) -> None:
    amap = clean_map(tmp_path, CLEAN.replace("machines: [mini]}", "machines: [mini, macbook]}"))
    assert row(ab.build(amap, [], now=NOW, hours={"mini": 2, "macbook": 3}),
               "claude-mini")["job_hours_7d"] == 5
    assert row(ab.build(amap, [], now=NOW, hours={"mini": 2}), "claude-mini")["job_hours_7d"] is None


# W4: a mis-pin or a shared Claude email is raised before it costs a night.
def test_fixture_raises_shared_email_and_mis_pin() -> None:
    board = ab.build(MAP, [], now=NOW)
    assert kinds(board) == ["mis_pin", "shared_claude_email"]
    shared = next(a for a in board["alerts"] if a["kind"] == "shared_claude_email")
    assert shared["accounts"] == ["claude-macbook", "claude-mini"]
    assert shared["machines"] == ["macbook", "mini"]
    pin = next(a for a in board["alerts"] if a["kind"] == "mis_pin")
    assert pin == {"kind": "mis_pin", "machine": "pc", "provider": "claude", "pins": 0}


def test_clean_map_raises_nothing(tmp_path: Path) -> None:
    board = ab.build(clean_map(tmp_path), [], now=NOW, usage={"claude-mini": 50, "claude-macbook": 80})
    assert board["alerts"] == []
    assert board["checks"] == {"mis_pin": "ok", "shared_claude_email": "ok", "high_usage": "ok"}


def test_two_claude_pins_on_one_machine_is_a_mis_pin(tmp_path: Path) -> None:
    amap = clean_map(tmp_path, CLEAN.replace("machines: [macbook]}", "machines: [mini]}"))
    pins = [a for a in ab.build(amap, [], now=NOW)["alerts"] if a["kind"] == "mis_pin"]
    assert {"kind": "mis_pin", "machine": "mini", "provider": "claude", "pins": 2} in pins


def test_one_claude_account_on_two_machines_shares_an_email(tmp_path: Path) -> None:
    text = CLEAN.replace("machines: [mini]}", "machines: [mini, macbook]}").replace(
        "  - {label: claude-macbook, provider: claude, plan: max, email: b@x.invalid, machines: [macbook]}\n", "")
    board = ab.build(clean_map(tmp_path, text), [], now=NOW)
    shared = [a for a in board["alerts"] if a["kind"] == "shared_claude_email"]
    assert shared == [{"kind": "shared_claude_email", "accounts": ["claude-mini"],
                       "machines": ["macbook", "mini"]}]


def test_missing_email_is_not_compared(tmp_path: Path) -> None:
    amap = clean_map(tmp_path, CLEAN.replace("a@x.invalid", "null").replace("b@x.invalid", "null"))
    assert "shared_claude_email" not in kinds(ab.build(amap, [], now=NOW))


# W5: usage over 80% of a known window is raised; without a usage source it is UNKNOWN.
def test_usage_over_80_alerts(tmp_path: Path) -> None:
    board = ab.build(clean_map(tmp_path), [], now=NOW, usage={"claude-mini": 81, "claude-macbook": 10})
    assert board["alerts"] == [{"kind": "high_usage", "account": "claude-mini", "pct": 81}]
    assert board["checks"]["high_usage"] == "alert"


def test_usage_unknown_without_table_or_with_gaps(tmp_path: Path) -> None:
    amap = clean_map(tmp_path)
    assert ab.build(amap, [], now=NOW)["checks"]["high_usage"] == "UNKNOWN"
    board = ab.build(amap, [], now=NOW, usage={"claude-mini": 10})
    assert board["checks"]["high_usage"] == "UNKNOWN"
    assert row(board, "claude-macbook")["usage_pct"] is None


@pytest.mark.parametrize("bad", ['{"mini": -1}', '{"mini": "lots"}', '[1]', '{"mini": 1e400}'])
def test_bad_tables_refused(tmp_path: Path, bad: str) -> None:
    p = tmp_path / "t.json"
    p.write_text(bad, encoding="utf-8")
    with pytest.raises(ab.InputError):
        ab.load_number_table(p)


# W6: read-only, no secrets, no raw text, and an unreadable input is never a quiet board.
def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          check=False)


def test_cli_fixture_alerts_and_never_prints_email_or_marker() -> None:
    base = ("--map", str(FIX / "map.yaml"), "--log", str(FIX / "headroom.jsonl"),
            "--now", NOW_DT.isoformat())
    js, md = run(*base), run(*base, "--format", "md")
    assert js.returncode == 1 and md.returncode == 1
    out = json.loads(js.stdout)
    assert out["log"] == {"status": "ok", "events": 2, "malformed": 1}
    assert row(out, "claude-mini")["state"] == "weekly_cooling"
    assert "| claude-mini | claude | max | mini | weekly_cooling |" in md.stdout
    for text in (js.stdout, js.stderr, md.stdout, md.stderr):
        assert "@" not in text and "PLANTED" not in text.upper()


def test_cli_unmounted_log_is_unknown(tmp_path: Path) -> None:
    res = run("--map", str(FIX / "map.yaml"), "--log", str(tmp_path / "no-ssd" / "h.jsonl"))
    assert res.returncode == 3 and res.stdout == ""


@pytest.mark.parametrize("text", ["accounts: []\n", "{{{", CLEAN + "  - {label: 'bad label!', provider: claude}\n",
                                  CLEAN.replace("version: 1", "version: 1\nversion: 2")])
def test_cli_bad_map_exits_2(tmp_path: Path, text: str) -> None:
    p = tmp_path / "map.yaml"
    p.write_text(text, encoding="utf-8")
    res = run("--map", str(p), "--log", str(FIX / "headroom.jsonl"))
    assert res.returncode == 2 and res.stdout == "" and "bad label" not in res.stderr


def test_cli_missing_map_exits_2(tmp_path: Path) -> None:
    assert run("--map", str(tmp_path / "ACCOUNT-MAP.yaml"), "--log", str(FIX / "headroom.jsonl")).returncode == 2


def test_cli_clean_board_exits_0(tmp_path: Path) -> None:
    p = tmp_path / "map.yaml"
    p.write_text(CLEAN, encoding="utf-8")
    log = tmp_path / "h.jsonl"  # folder exists, file absent: a real empty night
    res = run("--map", str(p), "--log", str(log), "--now", NOW_DT.isoformat())
    assert res.returncode == 0 and json.loads(res.stdout)["log"]["status"] == "absent"
