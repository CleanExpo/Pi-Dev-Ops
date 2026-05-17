"""Tests for scripts/plaud_ingest.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import plaud_ingest


def test_slug_basic():
    assert plaud_ingest.slug_from_name("Acme Q2 Pricing") == "acme-q2-pricing"


def test_slug_punctuation():
    assert plaud_ingest.slug_from_name("Acme Q2 Pricing!?") == "acme-q2-pricing"


def test_slug_unicode_folds_to_ascii():
    assert plaud_ingest.slug_from_name("Café Sync") == "cafe-sync"


def test_slug_empty_falls_back_to_id():
    assert plaud_ingest.slug_from_name("", fallback_id="abc123") == "abc123"


def test_slug_whitespace_only_falls_back():
    assert plaud_ingest.slug_from_name("   ", fallback_id="xyz") == "xyz"


def test_slug_collapses_consecutive_dashes():
    assert plaud_ingest.slug_from_name("foo --- bar") == "foo-bar"


def test_splitter_no_split_under_limit():
    segments = [{"start_ms": i*1000, "end_ms": (i+1)*1000, "speaker": "A", "text": "x"*10}
                for i in range(50)]
    parts = plaud_ingest.split_segments(segments, max_chars=10_000)
    assert len(parts) == 1
    assert parts[0] == segments


def test_splitter_breaks_on_segment_boundary():
    segments = [{"start_ms": i*1000, "end_ms": (i+1)*1000, "speaker": "A", "text": "x"*1000}
                for i in range(60)]  # ~60k chars total
    parts = plaud_ingest.split_segments(segments, max_chars=20_000)
    assert len(parts) >= 3
    rebuilt = [seg for part in parts for seg in part]
    assert rebuilt == segments
    for part in parts:
        chars = sum(len(s["text"]) for s in part)
        assert chars <= 20_000 or len(part) == 1


def test_splitter_single_huge_segment_kept_intact():
    # Pathological: one segment alone exceeds limit. Don't split mid-segment.
    segments = [{"start_ms": 0, "end_ms": 60_000, "speaker": "A", "text": "x"*30_000}]
    parts = plaud_ingest.split_segments(segments, max_chars=20_000)
    assert parts == [segments]


def test_format_page_single_part():
    page = plaud_ingest.format_page(
        plaud_id="abc123",
        title="Acme Q2 Pricing",
        recorded_at="2026-05-17T14:32:00+10:00",
        duration_ms=720_000,
        ingested_at="2026-05-17T14:40:03+10:00",
        audio_url="https://plaud.cdn/abc.mp3",
        summary_md="## Summary\nKey decisions.",
        segments=[{"start_ms": 0, "end_ms": 5000, "speaker": "A", "text": "Hello"}],
        part=None,
    )
    assert page.startswith("---\n")
    assert "type: plaud-recording" in page
    assert "plaud_id: abc123" in page
    assert "duration_human: 12m00s" in page
    assert "## Summary" in page
    assert "[00:00 - 00:05] A: Hello" in page


def test_format_page_multi_part_part_one_keeps_summary():
    page = plaud_ingest.format_page(
        plaud_id="abc123", title="Long Meeting",
        recorded_at="2026-05-17T14:00:00+10:00", duration_ms=3_600_000,
        ingested_at="2026-05-17T15:10:00+10:00", audio_url="https://plaud.cdn/abc.mp3",
        summary_md="## Summary\nKey decisions.",
        segments=[{"start_ms": 0, "end_ms": 5000, "speaker": "A", "text": "Hello"}],
        part=(1, 3),
    )
    assert "part: 1/3" in page
    assert "## Summary" in page
    assert "Key decisions." in page


def test_format_page_multi_part_part_two():
    page = plaud_ingest.format_page(
        plaud_id="abc123", title="Long Meeting",
        recorded_at="2026-05-17T14:00:00+10:00", duration_ms=3_600_000,
        ingested_at="2026-05-17T15:10:00+10:00", audio_url="https://plaud.cdn/abc.mp3",
        summary_md=None,
        segments=[{"start_ms": 1_800_000, "end_ms": 1_805_000, "speaker": "A", "text": "midway"}],
        part=(2, 3),
    )
    assert "part: 2/3" in page
    assert "## Summary" not in page
    assert "[30:00 - 30:05] A: midway" in page


def test_format_duration_human():
    assert plaud_ingest.format_duration_human(23_000) == "23s"
    assert plaud_ingest.format_duration_human(323_000) == "5m23s"
    assert plaud_ingest.format_duration_human(3_923_000) == "1h05m23s"


def test_format_timestamp():
    assert plaud_ingest.format_timestamp(0) == "00:00"
    assert plaud_ingest.format_timestamp(5_500) == "00:05"
    assert plaud_ingest.format_timestamp(125_000) == "02:05"


import json
import os


def test_state_load_missing_returns_fresh(tmp_path):
    state = plaud_ingest.load_state(tmp_path / "nope.json")
    assert state["last_seen_id"] == ""
    assert state["last_seen_ts"]
    assert state["consecutive_failures"] == 0


def test_state_load_corrupt_returns_fresh_logs_warn(tmp_path, caplog):
    p = tmp_path / "state.json"
    p.write_text("{not json")
    state = plaud_ingest.load_state(p)
    assert state["last_seen_id"] == ""
    assert "corrupt" in caplog.text.lower() or "WARN" in caplog.text


def test_state_save_round_trip(tmp_path):
    p = tmp_path / "state.json"
    plaud_ingest.save_state(p, {
        "last_seen_id": "abc",
        "last_seen_ts": "2026-05-17T14:40:00+10:00",
        "last_run_status": "ok",
        "last_error": None,
        "consecutive_failures": 0,
    })
    loaded = json.loads(p.read_text())
    assert loaded["last_seen_id"] == "abc"
    assert loaded["consecutive_failures"] == 0


def test_state_save_is_atomic(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"last_seen_id": "old"}))
    plaud_ingest.save_state(p, {"last_seen_id": "new", "last_seen_ts": "t",
                                "last_run_status": "ok", "last_error": None,
                                "consecutive_failures": 0})
    loaded = json.loads(p.read_text())
    assert loaded["last_seen_id"] == "new"
    assert not list(tmp_path.glob("*.tmp"))


def test_lock_acquire_release(tmp_path):
    lockfile = tmp_path / "ingest.lock"
    with plaud_ingest.pid_lock(lockfile) as acquired:
        assert acquired is True
        assert lockfile.exists()
        assert int(lockfile.read_text().strip()) == os.getpid()
    assert not lockfile.exists()


def test_lock_blocks_when_held_by_live_pid(tmp_path):
    lockfile = tmp_path / "ingest.lock"
    lockfile.write_text(str(os.getpid()))
    with plaud_ingest.pid_lock(lockfile) as acquired:
        assert acquired is False
    assert lockfile.read_text().strip() == str(os.getpid())


def test_lock_clears_stale_dead_pid(tmp_path):
    lockfile = tmp_path / "ingest.lock"
    lockfile.write_text("999999")
    with plaud_ingest.pid_lock(lockfile) as acquired:
        assert acquired is True
        assert int(lockfile.read_text().strip()) == os.getpid()


def test_write_page_new_file(tmp_path):
    target = plaud_ingest.write_page(tmp_path, "2026-05-17-foo", "content one")
    assert target == tmp_path / "2026-05-17-foo.md"
    assert target.read_text() == "content one"


def test_write_page_collision_appends_suffix(tmp_path):
    (tmp_path / "2026-05-17-foo.md").write_text("existing")
    target = plaud_ingest.write_page(tmp_path, "2026-05-17-foo", "content two")
    assert target == tmp_path / "2026-05-17-foo-2.md"
    assert target.read_text() == "content two"
    assert (tmp_path / "2026-05-17-foo.md").read_text() == "existing"


def test_write_page_collision_chains(tmp_path):
    (tmp_path / "2026-05-17-foo.md").write_text("a")
    (tmp_path / "2026-05-17-foo-2.md").write_text("b")
    target = plaud_ingest.write_page(tmp_path, "2026-05-17-foo", "c")
    assert target == tmp_path / "2026-05-17-foo-3.md"
