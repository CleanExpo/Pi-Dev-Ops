"""claude_session_hud.py must never read absence as "zero agents running".

Backs the new "Claude Code sessions" HUD panel on `/control` (the founder asked
for visibility into agent activity and token/context usage, "just like VS
Code"). The data source is `~/.claude/hooks/PreToolUse/context_ceiling.py`'s
own per-session state files — this module is the first reader of them.

RA-1109 (surface-treatment prohibition) is the reason `available` exists at
all: a missing or unreadable directory (wrong host, permissions) must render
distinctly from a directory that genuinely holds zero live sessions.
"""
import json
import time

from app.server import claude_session_hud as hud


def test_absent_directory_reports_unavailable_not_zero(tmp_path, monkeypatch):
    missing = tmp_path / "does-not-exist"
    monkeypatch.setattr(hud, "CEILING_DIR", missing)
    result = hud.claude_session_hud()
    assert result["available"] is False
    assert result["reason"]
    assert result["sessions"] == []
    assert result["checked_dir"] == str(missing)


def _write(dir_path, session_id, **fields):
    (dir_path / f"{session_id}.json").write_text(json.dumps({"session_id": session_id, **fields}))


def test_a_fresh_session_is_reported_live(tmp_path, monkeypatch):
    monkeypatch.setattr(hud, "CEILING_DIR", tmp_path)
    _write(
        tmp_path, "abc123",
        ts=int(time.time()), used_tokens=100_000, window=1_000_000, pct=10.0,
        stage="ok", cwd="/Users/phill/some-project",
    )
    result = hud.claude_session_hud()
    assert result["available"] is True
    assert result["counts"]["live"] == 1
    s = result["sessions"][0]
    assert s["project"] == "some-project"
    assert s["stage"] == "ok"
    assert s["pct"] == 10.0


def test_a_stale_session_is_excluded_from_the_live_list(tmp_path, monkeypatch):
    """Positive control on the filter: without it every session ever run would
    show, turning a HUD into a history dump."""
    monkeypatch.setattr(hud, "CEILING_DIR", tmp_path)
    stale_ts = int(time.time()) - hud.LIVE_WINDOW_S - 60
    _write(tmp_path, "old1", ts=stale_ts, used_tokens=1, window=1, pct=1.0, stage="ok", cwd="/x/y")
    result = hud.claude_session_hud()
    assert result["counts"]["live"] == 0
    assert result["sessions"] == []


def test_a_corrupt_state_file_is_skipped_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(hud, "CEILING_DIR", tmp_path)
    (tmp_path / "broken.json").write_text("{not valid json")
    _write(tmp_path, "good1", ts=int(time.time()), used_tokens=1, window=1, pct=1.0, stage="ok", cwd="/x/y")
    result = hud.claude_session_hud()
    assert result["available"] is True
    assert result["counts"]["live"] == 1
    assert result["sessions"][0]["session_id"] == "good1"


def test_counts_split_by_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(hud, "CEILING_DIR", tmp_path)
    now = int(time.time())
    _write(tmp_path, "s1", ts=now, used_tokens=1, window=1, pct=10.0, stage="ok", cwd="/a")
    _write(tmp_path, "s2", ts=now, used_tokens=1, window=1, pct=46.0, stage="handoff", cwd="/b")
    _write(tmp_path, "s3", ts=now, used_tokens=1, window=1, pct=51.0, stage="hard", cwd="/c")
    result = hud.claude_session_hud()
    assert result["counts"] == {"live": 3, "handoff": 1, "hard": 1}


def test_turn_zero_session_with_null_pct_does_not_crash(tmp_path, monkeypatch):
    """Negative control: the hook itself writes pct=null for turn-zero /
    estimator-unavailable sessions — the reader must not assume a number."""
    monkeypatch.setattr(hud, "CEILING_DIR", tmp_path)
    _write(tmp_path, "brandnew", ts=int(time.time()), used_tokens=None, window=200_000,
           pct=None, stage="turn-zero", cwd="")
    result = hud.claude_session_hud()
    assert result["counts"]["live"] == 1
    assert result["sessions"][0]["pct"] is None
    assert result["sessions"][0]["project"] is None
