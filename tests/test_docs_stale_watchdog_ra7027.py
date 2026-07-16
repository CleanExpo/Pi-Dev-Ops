"""tests/test_docs_stale_watchdog_ra7027.py — RA-7027 regressions.

The docs-staleness watchdog (RA-635) trusted ONLY the mtime of the newest
dated snapshot dir under `.harness/anthropic-docs/`. On Railway the container
filesystem resets to the committed repo state on every deploy, so the newest
dated dir reverts to whatever was last committed (frozen at 2026-07-02) even
though the `intel-refresh-daily-0200` trigger fires successfully every day
(proof: Supabase `cron_state.last_fired_at`). Result: guaranteed
[WATCHDOG][DOCS-STALE] false positives after any deploy that lands between
two 02:00 UTC fires.

Fix mirrors the RA-7030 board-meeting pattern: staleness is the MINIMUM of
artefact age and the enabled `intel_refresh` trigger's `last_fired_at` age.

Companion fix: `_fire_intel_refresh_trigger` now raises when ALL doc fetches
fail (no snapshot written), so `last_fired_at` stays stale on real outages
and the trigger-truth overlay cannot mask a genuinely broken fetch path.
"""
from __future__ import annotations

import logging
import os
import time

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


@pytest.mark.asyncio
async def test_fresh_intel_trigger_suppresses_docs_stale_alert(monkeypatch, tmp_path):
    """Artefact 300h old (>192h) but trigger fired 1h ago → NO alert."""
    from app.server import config

    docs_root = _make_stale_docs_root(tmp_path, hours_old=300)
    monkeypatch.setattr(cw, "_anthropic_docs_dir", lambda: docs_root)
    monkeypatch.setattr(config, "LINEAR_API_KEY", "")
    monkeypatch.setattr(cw, "_docs_stale_last_raised", 0)

    triggers = [{
        "id": "intel-refresh-daily-0200",
        "type": "intel_refresh",
        "enabled": True,
        "last_fired_at": time.time() - 3600,
    }]

    await cw._watchdog_docs_staleness(_LOG, triggers)

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

    triggers = [{
        "id": "intel-refresh-daily-0200",
        "type": "intel_refresh",
        "enabled": True,
        "last_fired_at": time.time() - 300 * 3600,
    }]

    await cw._watchdog_docs_staleness(_LOG, triggers)

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


@pytest.mark.asyncio
async def test_intel_refresh_total_fetch_failure_raises(monkeypatch):
    """All fetches failed → RuntimeError, so last_fired_at stays stale."""
    from app.server import cron_triggers as ct
    from app.server.agents import anthropic_intel_refresh as air

    async def _all_failed(dry_run=False):
        return {
            "fetched_urls": [],
            "new_snapshot_path": "unused",
            "delta_summary": {},
            "brief_path": None,
            "errors": [("https://docs.claude.com/x", "boom")],
        }

    monkeypatch.setattr(air, "refresh_anthropic_intel", _all_failed)

    with pytest.raises(RuntimeError, match="doc fetches failed"):
        await ct._fire_intel_refresh_trigger(
            {"id": "intel-refresh-daily-0200", "type": "intel_refresh"}, _LOG,
        )


@pytest.mark.asyncio
async def test_intel_refresh_partial_success_does_not_raise(monkeypatch):
    """One URL fetched, others errored → normal completion (no raise)."""
    import subprocess

    from app.server import cron_triggers as ct
    from app.server.agents import anthropic_intel_refresh as air

    async def _partial(dry_run=False):
        return {
            "fetched_urls": ["https://docs.claude.com/en/api/overview"],
            "new_snapshot_path": "unused",
            "delta_summary": {},
            "brief_path": None,
            "errors": [("https://docs.claude.com/x", "boom")],
        }

    monkeypatch.setattr(air, "refresh_anthropic_intel", _partial)

    class _Done:
        returncode = 0
        stdout = "consolidated"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _Done())

    await ct._fire_intel_refresh_trigger(
        {"id": "intel-refresh-daily-0200", "type": "intel_refresh"}, _LOG,
    )
