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


def test_append_log_line(tmp_path):
    log_path = tmp_path / "log.md"
    log_path.write_text("# Log\n\nexisting line\n")
    plaud_ingest.append_log_line(log_path,
        "2026-05-17T14:40 | plaud-ingest | plaud/2026-05-17-foo.md | new recording (12m, 8200 chars)")
    text = log_path.read_text()
    assert "existing line" in text
    assert text.endswith("plaud/2026-05-17-foo.md | new recording (12m, 8200 chars)\n")


def test_regenerate_plaud_index_empty(tmp_path):
    plaud_dir = tmp_path / "plaud"
    plaud_dir.mkdir()
    plaud_ingest.regenerate_plaud_index(plaud_dir)
    idx = (plaud_dir / "_index.md").read_text()
    assert "# Plaud Recordings" in idx
    assert "| Date | Title | Duration | Link |" in idx


def test_regenerate_plaud_index_with_entries(tmp_path):
    plaud_dir = tmp_path / "plaud"
    plaud_dir.mkdir()
    (plaud_dir / "2026-05-17-acme-sync.md").write_text(
        "---\ntype: plaud-recording\nplaud_id: a1\nrecorded_at: 2026-05-17T14:00:00+10:00\n"
        "duration_human: 12m00s\n---\n\n# Acme Sync\n")
    (plaud_dir / "2026-05-16-other.md").write_text(
        "---\ntype: plaud-recording\nplaud_id: a2\nrecorded_at: 2026-05-16T09:00:00+10:00\n"
        "duration_human: 5m00s\n---\n\n# Other\n")
    plaud_ingest.regenerate_plaud_index(plaud_dir)
    idx = (plaud_dir / "_index.md").read_text()
    assert idx.index("Acme Sync") < idx.index("Other")
    assert "12m00s" in idx
    assert "[Acme Sync](2026-05-17-acme-sync.md)" in idx


def test_regenerate_plaud_index_skips_non_plaud(tmp_path):
    plaud_dir = tmp_path / "plaud"
    plaud_dir.mkdir()
    (plaud_dir / "_index.md").write_text("old")
    (plaud_dir / "random.md").write_text("# Not a plaud recording\n")
    plaud_ingest.regenerate_plaud_index(plaud_dir)
    idx = (plaud_dir / "_index.md").read_text()
    assert "Not a plaud recording" not in idx


from unittest.mock import patch, MagicMock


def test_notify_margot_posts_to_bot_api():
    with patch("plaud_ingest.urllib.request.urlopen") as mock_open:
        mock_open.return_value.__enter__.return_value.status = 200
        plaud_ingest.notify_margot(
            bot_token="123:abc",
            chat_id="-100",
            text="📼 New Plaud: Acme (12m). I've added it to the brain.",
        )
        assert mock_open.called
        req = mock_open.call_args[0][0]
        assert req.full_url == "https://api.telegram.org/bot123:abc/sendMessage"
        body = req.data.decode()
        assert "chat_id" in body
        assert "Acme" in body


def test_notify_margot_swallows_errors(caplog):
    with patch("plaud_ingest.urllib.request.urlopen", side_effect=OSError("network down")):
        plaud_ingest.notify_margot(bot_token="t", chat_id="c", text="x")
    assert "telegram" in caplog.text.lower() or "notify" in caplog.text.lower()


import asyncio


class _FakeContent:
    def __init__(self, text):
        self.text = text


class _FakeResult:
    def __init__(self, payload):
        self.content = [_FakeContent(json.dumps(payload))]


class _FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def initialize(self):
        pass

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        return _FakeResult(self.responses.get(name, {}))


def test_plaud_client_list_files_since():
    fake = _FakeSession({"list_files": {"files": [
        {"id": "abc", "name": "Foo", "created_at": "2026-05-17T14:32:00+10:00",
         "duration": 720000},
    ]}})
    files = asyncio.run(plaud_ingest.PlaudClient(fake).list_files_since("2026-05-17"))
    assert len(files) == 1
    assert files[0]["id"] == "abc"
    assert fake.calls[0][0] == "list_files"


def test_plaud_client_get_note_and_transcript():
    fake = _FakeSession({
        "get_note": {"summary": "## Summary\nKey decisions."},
        "get_transcript": {"segments": [
            {"start_ms": 0, "end_ms": 5000, "speaker": "A", "text": "Hello"}]},
    })
    client = plaud_ingest.PlaudClient(fake)
    note = asyncio.run(client.get_note("abc"))
    transcript = asyncio.run(client.get_transcript("abc"))
    assert "Key decisions" in note
    assert transcript[0]["text"] == "Hello"


def test_run_once_happy_path_writes_page_and_advances_state(tmp_path):
    state_path = tmp_path / "state.json"
    lock_path = tmp_path / "ingest.lock"
    wiki_dir = tmp_path / "Wiki"
    plaud_dir = wiki_dir / "plaud"

    fake = _FakeSession({
        "list_files": {"files": [{
            "id": "abc123",
            "name": "Acme Q2 Pricing",
            "created_at": "2026-05-17T14:32:00+10:00",
            "duration": 720_000,
            "presigned_url": "https://plaud.cdn/abc.mp3",
        }]},
        "get_note": {"summary": "## Summary\nKey decisions made."},
        "get_transcript": {"segments": [
            {"start_ms": 0, "end_ms": 5000, "speaker": "A", "text": "Hello"}]},
    })

    captured = {}
    def fake_notify(**kw):
        captured["notify"] = kw

    config = plaud_ingest.IngestConfig(
        state_path=state_path,
        lock_path=lock_path,
        wiki_dir=wiki_dir,
        plaud_dir=plaud_dir,
        bot_token="t", chat_id="c",
        run_sync_subprocess=lambda: None,
        notify_fn=fake_notify,
    )
    result = asyncio.run(plaud_ingest.run_once(plaud_ingest.PlaudClient(fake), config))

    assert result["ingested"] == 1
    assert result["status"] == "ok"
    written = list(plaud_dir.glob("*.md"))
    assert any("acme-q2-pricing" in p.name for p in written)
    assert (wiki_dir / "log.md").exists()
    assert "plaud-ingest" in (wiki_dir / "log.md").read_text()
    state = json.loads(state_path.read_text())
    assert state["last_seen_id"] == "abc123"
    assert state["consecutive_failures"] == 0
    assert "Acme Q2 Pricing" in captured["notify"]["text"]


def test_run_once_idempotent_no_new_files(tmp_path):
    state_path = tmp_path / "state.json"
    save_state_initial = {
        "last_seen_id": "abc123",
        "last_seen_ts": "2026-05-17T14:32:00+10:00",
        "last_run_status": "ok", "last_error": None, "consecutive_failures": 0,
    }
    state_path.write_text(json.dumps(save_state_initial))

    fake = _FakeSession({"list_files": {"files": [{
        "id": "abc123",
        "name": "Acme Q2 Pricing",
        "created_at": "2026-05-17T14:32:00+10:00",
        "duration": 720_000,
    }]}})

    config = plaud_ingest.IngestConfig(
        state_path=state_path, lock_path=tmp_path / "lock",
        wiki_dir=tmp_path / "Wiki", plaud_dir=tmp_path / "Wiki" / "plaud",
        bot_token="", chat_id="",
        run_sync_subprocess=lambda: None, notify_fn=lambda **k: None,
    )
    result = asyncio.run(plaud_ingest.run_once(plaud_ingest.PlaudClient(fake), config))
    assert result["ingested"] == 0
    plaud_md = list((tmp_path / "Wiki" / "plaud").glob("*.md")) if (tmp_path / "Wiki" / "plaud").exists() else []
    assert not plaud_md
