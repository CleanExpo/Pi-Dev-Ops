"""tests/test_docs_stale_watchdog_ra7027.py — RA-7027 regressions.

The docs-staleness watchdog (RA-635) trusted ONLY the mtime of the newest
dated snapshot dir under `.harness/anthropic-docs/`. On Railway the container
filesystem resets to the committed repo state on every deploy, so the newest
dated dir reverts to whatever was last committed even though the
`intel-refresh-daily-0200` trigger fires successfully every day (proof:
Supabase `cron_state.last_fired_at`). Result: guaranteed
[WATCHDOG][DOCS-STALE] false positives after any deploy that lands between
two 02:00 UTC fires.

Fix mirrors the RA-7030 board-meeting pattern: staleness is the MINIMUM of
artefact age and the enabled `intel_refresh` trigger's `last_fired_at` age.

Review hardening (codex findings on PR #591):
  1. Trigger timestamps are VALIDATED before being trusted — malformed
     values must not TypeError (aborting later watchdogs), and future
     epochs must not yield negative ages that suppress alerts forever.
     Applies to both the docs overlay and the RA-7030 board overlay via
     the shared `_validated_trigger_age_h` helper.
  2. A fire only counts when ALL required doc sources fetched — 1-of-3
     success must not refresh `last_fired_at` while two sources stay
     permanently dead.
  3. Snapshot publish is atomic — a failed write must not leave a
     fresh-but-empty dated dir that masks the artefact-age check.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import httpx
import pytest

from app.server import cron_watchdogs as cw

_LOG = logging.getLogger("test")


def _make_stale_docs_root(tmp_path, hours_old: float):
    """Build .harness/anthropic-docs/<dated>/ with an old mtime."""
    docs_root = tmp_path / ".harness" / "anthropic-docs"
    dated = docs_root / "2026-07-02"
    dated.mkdir(parents=True, exist_ok=True)
    (dated / "release-notes-overview.md").write_text("ok\n", encoding="utf-8")
    then = time.time() - hours_old * 3600
    os.utime(dated, (then, then))
    return docs_root


def _intel_trigger(last_fired_at):
    return {
        "id": "intel-refresh-daily-0200",
        "type": "intel_refresh",
        "enabled": True,
        "last_fired_at": last_fired_at,
    }


# ── dual-truth overlay (original RA-7027 fix) ─────────────────────────────────


@pytest.mark.asyncio
async def test_fresh_intel_trigger_suppresses_docs_stale_alert(monkeypatch, tmp_path):
    """Artefact 300h old (>192h) but trigger fired 1h ago → NO alert."""
    from app.server import config

    docs_root = _make_stale_docs_root(tmp_path, hours_old=300)
    monkeypatch.setattr(cw, "_anthropic_docs_dir", lambda: docs_root)
    monkeypatch.setattr(config, "LINEAR_API_KEY", "")
    monkeypatch.setattr(cw, "_docs_stale_last_raised", 0)

    await cw._watchdog_docs_staleness(_LOG, [_intel_trigger(time.time() - 3600)])

    # The no-API-key fire path stamps _docs_stale_last_raised; staying 0
    # proves the watchdog returned before the alert branch.
    assert cw._docs_stale_last_raised == 0


@pytest.mark.asyncio
async def test_stale_artifact_and_stale_trigger_still_fires(monkeypatch, tmp_path):
    """Both artefact AND trigger >192h stale → alert still raised (true positive)."""
    from app.server import config

    docs_root = _make_stale_docs_root(tmp_path, hours_old=300)
    monkeypatch.setattr(cw, "_anthropic_docs_dir", lambda: docs_root)
    monkeypatch.setattr(config, "LINEAR_API_KEY", "")
    monkeypatch.setattr(cw, "_docs_stale_last_raised", 0)

    await cw._watchdog_docs_staleness(_LOG, [_intel_trigger(time.time() - 300 * 3600)])

    assert cw._docs_stale_last_raised > 0


@pytest.mark.asyncio
async def test_no_triggers_arg_keeps_legacy_behaviour(monkeypatch, tmp_path):
    """Called without triggers (legacy signature) a stale artefact still alerts."""
    from app.server import config

    docs_root = _make_stale_docs_root(tmp_path, hours_old=300)
    monkeypatch.setattr(cw, "_anthropic_docs_dir", lambda: docs_root)
    monkeypatch.setattr(config, "LINEAR_API_KEY", "")
    monkeypatch.setattr(cw, "_docs_stale_last_raised", 0)

    await cw._watchdog_docs_staleness(_LOG)

    assert cw._docs_stale_last_raised > 0


# ── finding 1: timestamp validation ──────────────────────────────────────────


def test_validated_trigger_age_rejects_garbage():
    """Malformed values return None instead of raising."""
    for bad in ("not-a-number", None, [], {}, True, float("nan"), float("inf")):
        assert cw._validated_trigger_age_h(bad) is None, bad


def test_validated_trigger_age_rejects_far_future_but_allows_skew():
    now = time.time()
    # 10 days in the future → rejected (would be a negative age).
    assert cw._validated_trigger_age_h(now + 10 * 86400) is None
    # 60s ahead → clock skew, clamped to age 0.
    assert cw._validated_trigger_age_h(now + 60) == 0.0
    # 2h ago → ~2h age.
    age = cw._validated_trigger_age_h(now - 2 * 3600)
    assert age is not None and 1.9 < age < 2.1


@pytest.mark.asyncio
async def test_future_timestamp_does_not_suppress_docs_alert(monkeypatch, tmp_path):
    """A bogus FUTURE last_fired_at must be ignored — the stale artefact alone
    still raises the alert (reviewer reproduced permanent suppression)."""
    from app.server import config

    docs_root = _make_stale_docs_root(tmp_path, hours_old=300)
    monkeypatch.setattr(cw, "_anthropic_docs_dir", lambda: docs_root)
    monkeypatch.setattr(config, "LINEAR_API_KEY", "")
    monkeypatch.setattr(cw, "_docs_stale_last_raised", 0)

    await cw._watchdog_docs_staleness(_LOG, [_intel_trigger(time.time() + 10 * 86400)])

    assert cw._docs_stale_last_raised > 0


@pytest.mark.asyncio
async def test_malformed_timestamp_does_not_abort_watchdog(monkeypatch, tmp_path):
    """A string last_fired_at must not TypeError (which would abort the
    watchdogs scheduled after this one in cron_loop)."""
    from app.server import config

    docs_root = _make_stale_docs_root(tmp_path, hours_old=300)
    monkeypatch.setattr(cw, "_anthropic_docs_dir", lambda: docs_root)
    monkeypatch.setattr(config, "LINEAR_API_KEY", "")
    monkeypatch.setattr(cw, "_docs_stale_last_raised", 0)

    await cw._watchdog_docs_staleness(_LOG, [_intel_trigger("2026-07-16T02:00:00Z")])

    assert cw._docs_stale_last_raised > 0


@pytest.mark.asyncio
async def test_board_overlay_ignores_future_timestamp(monkeypatch, tmp_path):
    """RA-7030 board overlay has the identical weakness — a future
    last_fired_at must not suppress the board-silence alert."""
    from app.server import config

    meetings = tmp_path / ".harness" / "board-meetings"
    meetings.mkdir(parents=True, exist_ok=True)
    stale_file = meetings / "2026-07-02-minutes.md"
    stale_file.write_text("minutes\n", encoding="utf-8")
    then = time.time() - 300 * 3600
    os.utime(stale_file, (then, then))

    monkeypatch.setattr(cw, "_board_meetings_dir", lambda: meetings)
    monkeypatch.setattr(config, "LINEAR_API_KEY", "")
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_ALERT_CHAT_ID", "")
    monkeypatch.setattr(cw, "_board_meeting_silent_last_raised", 0)

    triggers = [{
        "id": "board-meeting-daily",
        "type": "board_meeting",
        "enabled": True,
        "last_fired_at": time.time() + 10 * 86400,
    }]
    await cw._watchdog_board_meeting_silence(_LOG, triggers)

    # Alert path stamps the cooldown unconditionally at its end.
    assert cw._board_meeting_silent_last_raised > 0


# ── finding 2: fire only counts when ALL sources fetched ─────────────────────


def _refresh_result(fetched_urls, errors):
    return {
        "fetched_urls": fetched_urls,
        "new_snapshot_path": "unused",
        "delta_summary": {},
        "brief_path": None,
        "errors": errors,
    }


@pytest.mark.asyncio
async def test_intel_refresh_total_fetch_failure_raises(monkeypatch):
    """All fetches failed → RuntimeError, so last_fired_at stays stale."""
    from app.server import cron_triggers as ct
    from app.server.agents import anthropic_intel_refresh as air

    async def _all_failed(dry_run=False):
        return _refresh_result([], [(u, "boom") for u in air._DOCS_URLS])

    monkeypatch.setattr(air, "refresh_anthropic_intel", _all_failed)

    with pytest.raises(RuntimeError, match=r"only 0/3 doc sources"):
        await ct._fire_intel_refresh_trigger(
            {"id": "intel-refresh-daily-0200", "type": "intel_refresh"}, _LOG,
        )


@pytest.mark.asyncio
async def test_intel_refresh_partial_fetch_failure_raises(monkeypatch):
    """1 of 3 sources fetched → still a failure. A partial fetch must not
    refresh last_fired_at while the other sources stay permanently dead."""
    from app.server import cron_triggers as ct
    from app.server.agents import anthropic_intel_refresh as air

    async def _partial(dry_run=False):
        return _refresh_result(
            [air._DOCS_URLS[0]],
            [(u, "boom") for u in air._DOCS_URLS[1:]],
        )

    monkeypatch.setattr(air, "refresh_anthropic_intel", _partial)

    with pytest.raises(RuntimeError, match=r"only 1/3 doc sources"):
        await ct._fire_intel_refresh_trigger(
            {"id": "intel-refresh-daily-0200", "type": "intel_refresh"}, _LOG,
        )


@pytest.mark.asyncio
async def test_intel_refresh_full_success_does_not_raise(monkeypatch):
    """All 3 sources fetched → normal completion."""
    import subprocess

    from app.server import cron_triggers as ct
    from app.server.agents import anthropic_intel_refresh as air

    async def _full(dry_run=False):
        return _refresh_result(list(air._DOCS_URLS), [])

    monkeypatch.setattr(air, "refresh_anthropic_intel", _full)

    class _Done:
        returncode = 0
        stdout = "consolidated"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _Done())

    await ct._fire_intel_refresh_trigger(
        {"id": "intel-refresh-daily-0200", "type": "intel_refresh"}, _LOG,
    )


# ── finding 3: atomic snapshot publish ────────────────────────────────────────


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class _FakeClient:
    """Stands in for httpx.AsyncClient; behaviour driven by a url→text|Exception map."""

    def __init__(self, responses):
        self._responses = responses

    def __call__(self, *args, **kwargs):  # constructor stand-in
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url):
        value = self._responses[url]
        if isinstance(value, Exception):
            raise value
        return _FakeResponse(value)


@pytest.mark.asyncio
async def test_failed_write_leaves_no_dated_dir(monkeypatch, tmp_path):
    """A write failure mid-publish must not leave a fresh dated dir (empty or
    partial) that would mask the artefact-age staleness check for 8 days."""
    from app.server.agents import anthropic_intel_refresh as air

    fake = _FakeClient({u: f"content for {u}\n" for u in air._DOCS_URLS})
    monkeypatch.setattr(air.httpx, "AsyncClient", fake)

    real_write_text = Path.write_text
    calls = {"n": 0}

    def _failing_write_text(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("disk full")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _failing_write_text)

    snapshot_dir = tmp_path / "anthropic-docs"
    with pytest.raises(OSError, match="disk full"):
        await air.refresh_anthropic_intel(
            snapshot_dir=str(snapshot_dir),
            brief_dir=str(tmp_path / "board-meetings"),
        )

    dated = [d for d in snapshot_dir.iterdir() if d.is_dir() and d.name[:4].isdigit()]
    assert dated == [], f"failed publish must not leave a dated dir: {dated}"


@pytest.mark.asyncio
async def test_successful_publish_writes_all_files_atomically(monkeypatch, tmp_path):
    """Happy path: dated dir appears with all files, no temp dirs left behind."""
    from app.server.agents import anthropic_intel_refresh as air

    fake = _FakeClient({u: f"content for {u}\n" for u in air._DOCS_URLS})
    monkeypatch.setattr(air.httpx, "AsyncClient", fake)

    snapshot_dir = tmp_path / "anthropic-docs"
    result = await air.refresh_anthropic_intel(
        snapshot_dir=str(snapshot_dir),
        brief_dir=str(tmp_path / "board-meetings"),
    )

    assert len(result["fetched_urls"]) == len(air._DOCS_URLS)
    dated = [d for d in snapshot_dir.iterdir() if d.is_dir() and d.name[:4].isdigit()]
    assert len(dated) == 1
    assert len(list(dated[0].iterdir())) == len(air._DOCS_URLS)
    leftovers = [d for d in snapshot_dir.iterdir() if d.name.startswith(".")]
    assert leftovers == [], f"temp dirs must not survive publish: {leftovers}"


# ── scheduler-level: total failure advances nothing ───────────────────────────


@pytest.mark.asyncio
async def test_scheduler_total_failure_advances_no_state(monkeypatch, tmp_path):
    """Drive the real dispatcher (`_fire_trigger`, the exact seam cron_loop
    awaits) with every fetch failing: the RuntimeError must propagate
    (cron_loop only sets `last_fired_at = time.time()` AFTER a successful
    await, so propagation IS the no-advance guarantee) and no dated snapshot
    dir may appear on disk."""
    from app.server import cron_triggers as ct
    from app.server.agents import anthropic_intel_refresh as air

    fake = _FakeClient({u: httpx.ConnectError("boom") for u in air._DOCS_URLS})
    monkeypatch.setattr(air.httpx, "AsyncClient", fake)
    monkeypatch.chdir(tmp_path)  # default snapshot_dir is CWD-relative

    trigger = {
        "id": "intel-refresh-daily-0200",
        "type": "intel_refresh",
        "enabled": True,
        "last_fired_at": 1234567890.0,
    }

    with pytest.raises(RuntimeError, match=r"only 0/3 doc sources"):
        await ct._fire_trigger(trigger, _LOG)

    assert trigger["last_fired_at"] == 1234567890.0
    snapshot_root = tmp_path / ".harness" / "anthropic-docs"
    if snapshot_root.exists():
        dated = [
            d for d in snapshot_root.iterdir() if d.is_dir() and d.name[:4].isdigit()
        ]
        assert dated == [], "total failure must not write a snapshot"
