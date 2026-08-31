"""tests/test_youtube_transcripts.py — the missing YouTube -> Sources producer.

The point of this producer is that `wiki_ingest._enrich_youtube_frontmatter` has
been able to parse YouTube clips since it was written, and nothing ever wrote
one. So the load-bearing test here is not "does it write a file" — it is the
ROUND TRIP: a clip this producer emits must be one the existing consumer
actually recognises as YouTube and extracts a channel from. That test fails if
either side drifts, which is the failure this whole lane was built to end.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import youtube_transcripts as yt  # noqa: E402
from swarm import wiki_ingest  # noqa: E402


def _state(*videos: dict) -> dict:
    return {"videos": list(videos)}


def _video(**kw) -> dict:
    base = {
        "video_key": "k1", "video_id": "dQw4w9WgXcQ", "status": "accepted",
        "title": "Building agent fleets", "channel": "Some Channel",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "watched_at": "2026-08-30T10:00:00Z",
    }
    base.update(kw)
    return base


@pytest.fixture(autouse=True)
def _isolate_marker(tmp_path, monkeypatch):
    """Never let a test read or append the repo's real marker file."""
    monkeypatch.setattr(yt, "MARKER_PATH", tmp_path / "done.jsonl")


def test_clip_round_trips_through_the_existing_consumer(tmp_path):
    """The whole reason this producer exists: wiki_ingest must recognise its output."""
    src = tmp_path / "Sources"
    res = yt.run(src, state=_state(_video()), fetcher=lambda _v: "hello transcript")

    assert len(res.written) == 1
    clip = Path(res.written[0])
    raw = clip.read_text(encoding="utf-8")

    # The consumer's own two functions, not a re-implementation of them.
    frontmatter = raw[3:raw.find("\n---", 3)]
    assert wiki_ingest._extract_channel(frontmatter) == "Some Channel"
    enriched = wiki_ingest._enrich_youtube_frontmatter(clip, raw)
    assert "channel: " in enriched, "consumer did not treat this as a YouTube clip"
    assert "Some Channel" in enriched
    assert "hello transcript" in enriched


def test_filename_is_keyed_on_the_id_not_the_title(tmp_path):
    """Titles contain slashes and quotes and are not unique; the id is identity."""
    hostile = _video(title='../../etc/passwd "quoted" /slashed')
    res = yt.run(tmp_path / "S", state=_state(hostile), fetcher=lambda _v: "t")
    name = Path(res.written[0]).name
    assert name == "20260830-dQw4w9WgXcQ.md"
    assert "/" not in name and ".." not in name


def test_only_accepted_videos_are_fetched(tmp_path):
    """Relevance is the catalog's decision; this script must not widen it."""
    fetched: list[str] = []

    def fetch(v):
        fetched.append(v)
        return "t"

    state = _state(
        _video(video_key="a", video_id="aaaaaaaaaaa", status="accepted"),
        _video(video_key="b", video_id="bbbbbbbbbbb", status="excluded"),
    )
    yt.run(tmp_path / "S", state=state, fetcher=fetch)
    assert fetched == ["aaaaaaaaaaa"]


def test_a_video_is_never_fetched_twice(tmp_path):
    """Second run must be a no-op — otherwise every cycle re-fetches everything."""
    calls: list[str] = []
    state = _state(_video())

    first = yt.run(tmp_path / "S", state=state, fetcher=lambda v: calls.append(v) or "t")
    second = yt.run(tmp_path / "S", state=state, fetcher=lambda v: calls.append(v) or "t")

    assert len(first.written) == 1
    assert second.written == [] and second.skipped_done == 1
    assert calls == ["dQw4w9WgXcQ"], "transcript re-fetched on the second run"


def test_uncaptioned_video_is_recorded_not_retried(tmp_path):
    """No captions is a permanent answer for that video, not a transient failure."""
    calls: list[str] = []
    state = _state(_video())

    first = yt.run(tmp_path / "S", state=state, fetcher=lambda v: calls.append(v) or None)
    second = yt.run(tmp_path / "S", state=state, fetcher=lambda v: calls.append(v) or None)

    assert first.no_captions == ["dQw4w9WgXcQ"] and first.written == []
    assert second.skipped_done == 1
    assert len(calls) == 1, "uncaptioned video re-fetched — throttling risk"


def test_dry_run_writes_nothing_and_records_nothing(tmp_path):
    src = tmp_path / "S"
    res = yt.run(src, state=_state(_video()), fetcher=lambda _v: "t", dry_run=True)
    assert len(res.written) == 1          # reported as planned...
    assert not src.exists()               # ...but nothing on disk
    assert not yt.MARKER_PATH.exists()    # and nothing marked, so a real run still runs


def test_limit_caps_a_run(tmp_path):
    vids = [_video(video_key=f"k{i}", video_id=f"vid{i:08d}") for i in range(5)]
    res = yt.run(tmp_path / "S", state=_state(*vids), fetcher=lambda _v: "t", limit=2)
    assert len(res.written) == 2


@pytest.mark.parametrize("item,expected", [
    ({"video_id": "dQw4w9WgXcQ"}, "dQw4w9WgXcQ"),
    ({"url": "https://www.youtube.com/watch?v=abcdefghijk"}, "abcdefghijk"),
    ({"url": "https://youtu.be/ABCDEFGHIJK"}, "ABCDEFGHIJK"),
    ({"url": "https://www.youtube.com/shorts/12345678901"}, "12345678901"),
    # Takeout writes the URL into video_id; it must not be used as an id verbatim.
    ({"video_id": "https://www.youtube.com/watch?v=zzzzzzzzzzz"}, "zzzzzzzzzzz"),
    ({"title": "no id anywhere"}, None),
])
def test_video_id_extraction(item, expected):
    assert yt.video_id_of(item) == expected


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("YOUTUBE_TRANSCRIPTS_ENABLED", raising=False)
    assert yt.enabled() is False
    monkeypatch.setenv("YOUTUBE_TRANSCRIPTS_ENABLED", "1")
    assert yt.enabled() is True


def test_torn_marker_line_does_not_lose_the_rest(tmp_path):
    """A half-written line must cost one entry, not the whole history."""
    yt.MARKER_PATH.write_text(
        json.dumps({"video_id": "aaaaaaaaaaa", "outcome": "written"}) + "\n"
        + "{not json\n"
        + json.dumps({"video_id": "bbbbbbbbbbb", "outcome": "written"}) + "\n",
        encoding="utf-8")
    assert yt._load_done() == {"aaaaaaaaaaa", "bbbbbbbbbbb"}
