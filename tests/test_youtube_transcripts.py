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
from scripts import youtube_transcript_fetch as yt_fetch  # noqa: E402
from scripts import youtube_transcript_state as yt_state  # noqa: E402
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
    """Never let a test read or append the repo's real marker file.

    Patched on `youtube_transcript_state`, NOT on `youtube_transcripts`: the
    load/mark functions live there and close over that module's global, so
    patching the producer's re-exported name would leave every test reading and
    appending the real `.harness/` marker while still appearing to pass.
    """
    monkeypatch.setattr(yt_state, "MARKER_PATH", tmp_path / "done.jsonl")


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


def test_operational_failure_is_not_recorded_as_no_captions(tmp_path):
    """A fetch that BLEW UP must be retried, never retired as `no_captions`.

    The bug this guards: the default fetcher used to swallow every exception —
    including the ImportError from a missing `youtube-transcript-api` — and
    return None. `_produce_one` writes a done-marker for None, so a single
    missing dependency would have marked the entire accepted watch history as
    having no captions, permanently, on one run that exited 0.
    """
    calls: list[str] = []

    def boom(video_id: str) -> str:
        calls.append(video_id)
        raise ImportError("youtube-transcript-api not installed")

    state = _state(_video())
    first = yt.run(tmp_path / "S", state=state, fetcher=boom)

    assert first.failed == ["dQw4w9WgXcQ"], "operational error not counted as failed"
    assert first.no_captions == [] and first.written == []
    assert not yt_state.MARKER_PATH.exists(), "a failed fetch wrote a completion marker"

    # ...and the next run must actually retry it, which is the whole point.
    second = yt.run(tmp_path / "S", state=state, fetcher=lambda v: calls.append(v) or "t")
    assert len(second.written) == 1, "video was permanently lost after one failure"
    assert calls == ["dQw4w9WgXcQ", "dQw4w9WgXcQ"]


def test_real_fetcher_raises_on_missing_dependency(monkeypatch):
    """The default fetcher itself must raise, not return None, when uninstallable.

    Tested at the real entry point rather than through an injected fake, because
    the injected fake cannot prove the shipped code no longer swallows ImportError.
    """
    import builtins

    real_import = builtins.__import__

    def no_library(name: str, *a, **kw):
        if name == "youtube_transcript_api":
            raise ImportError("No module named 'youtube_transcript_api'")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_library)
    with pytest.raises(ImportError):
        yt_fetch.fetch_transcript("dQw4w9WgXcQ")


def test_caption_absence_still_yields_no_captions(monkeypatch):
    """The other half of the split: TranscriptsDisabled is still a permanent None.

    Without this, "make everything raise" would pass the test above while
    breaking the uncaptioned-video path the marker file exists for.
    """
    ytapi = pytest.importorskip("youtube_transcript_api")

    class _Api:
        def fetch(self, video_id, languages=None):
            raise ytapi.TranscriptsDisabled(video_id)

    monkeypatch.setattr(ytapi, "YouTubeTranscriptApi", _Api)
    assert yt_fetch.fetch_transcript("dQw4w9WgXcQ") is None


def test_limit_counts_fetch_attempts_not_writes(tmp_path):
    """The cap exists to avoid throttling, and throttling is caused by attempts.

    N videos that all turn out to have no captions used to leave `written` at 0,
    so the `len(result.written) >= limit` guard never fired and one run fetched
    the entire backlog — exactly the burst the cap was written to prevent.
    """
    calls: list[str] = []
    vids = [_video(video_key=f"k{i}", video_id=f"vid{i:08d}") for i in range(9)]

    res = yt.run(
        tmp_path / "S", state=_state(*vids),
        fetcher=lambda v: calls.append(v) or None, limit=3,
    )

    assert len(calls) == 3, f"{len(calls)} fetches issued with limit=3"
    assert res.attempted == 3
    assert len(res.no_captions) == 3 and res.written == []


def test_failed_fetches_also_count_against_the_limit(tmp_path):
    """A failing fetch is still a request, so it must consume the same quota."""
    calls: list[str] = []

    def boom(video_id: str) -> str:
        calls.append(video_id)
        raise RuntimeError("IpBlocked")

    vids = [_video(video_key=f"k{i}", video_id=f"vid{i:08d}") for i in range(9)]
    res = yt.run(tmp_path / "S", state=_state(*vids), fetcher=boom, limit=2)

    assert len(calls) == 2 and res.attempted == 2
    assert len(res.failed) == 2
    assert not yt_state.MARKER_PATH.exists()


def test_dry_run_writes_nothing_and_records_nothing(tmp_path):
    src = tmp_path / "S"
    res = yt.run(src, state=_state(_video()), fetcher=lambda _v: "t", dry_run=True)
    assert len(res.written) == 1          # reported as planned...
    assert not src.exists()               # ...but nothing on disk
    assert not yt_state.MARKER_PATH.exists()    # and nothing marked, so a real run still runs


def test_dry_run_does_not_touch_the_network(tmp_path):
    """A plan must issue ZERO fetches.

    Suppressing only the write still sent one real YouTube request per accepted
    video — up to `limit` per invocation, against the API whose throttling that
    limit exists to avoid. Someone running `--dry-run` a few times to see what
    would happen could get the host blocked and make the real run fail, and the
    repo's own manual-verification path opens with exactly that command.
    """
    calls: list[str] = []

    def spy(video_id: str) -> str:
        calls.append(video_id)
        return "transcript"

    vids = [_video(video_key=f"k{i}", video_id=f"vid{i:08d}") for i in range(9)]
    res = yt.run(tmp_path / "S", state=_state(*vids), fetcher=spy, limit=25, dry_run=True)

    assert calls == [], f"a dry run issued {len(calls)} network fetches"
    assert len(res.written) == 9, "a plan must still report what it would fetch"
    assert not yt_state.MARKER_PATH.exists()


def test_dry_run_still_respects_the_limit(tmp_path):
    """The plan must show what a real run would do, so the cap still applies."""
    vids = [_video(video_key=f"k{i}", video_id=f"vid{i:08d}") for i in range(9)]
    res = yt.run(
        tmp_path / "S", state=_state(*vids), fetcher=lambda _v: "t", limit=3, dry_run=True)
    assert res.attempted == 3
    assert len(res.written) == 3


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
    yt_state.MARKER_PATH.write_text(
        json.dumps({"video_id": "aaaaaaaaaaa", "outcome": "written"}) + "\n"
        + "{not json\n"
        + json.dumps({"video_id": "bbbbbbbbbbb", "outcome": "written"}) + "\n",
        encoding="utf-8")
    assert yt._load_done() == {"aaaaaaaaaaa", "bbbbbbbbbbb"}
