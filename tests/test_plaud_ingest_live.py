"""Live integration test — calls the real Plaud MCP. Opt-in via RUN_PLAUD_LIVE=1.

Catches Plaud API schema drift before production cron does.
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import plaud_ingest


@pytest.mark.skipif(os.environ.get("RUN_PLAUD_LIVE") != "1",
                    reason="set RUN_PLAUD_LIVE=1 to run live Plaud integration test")
def test_live_ingest_one_recording(tmp_path):
    state_path = tmp_path / "state.json"
    wiki_dir = tmp_path / "Wiki"
    plaud_dir = wiki_dir / "plaud"

    cfg = plaud_ingest.IngestConfig(
        state_path=state_path,
        lock_path=tmp_path / "lock",
        wiki_dir=wiki_dir,
        plaud_dir=plaud_dir,
        bot_token="", chat_id="",  # no Telegram DM during test
        run_sync_subprocess=lambda: None,
        notify_fn=lambda **k: None,
    )

    async def go():
        async with plaud_ingest.connect_real_plaud() as client:
            files = await client.list_files_since("2020-01-01")
            assert files, "Plaud account has zero recordings — cannot run live test"
            state = plaud_ingest.load_state(state_path)
            state["last_seen_ts"] = "2020-01-01T00:00:00+00:00"
            plaud_ingest.save_state(state_path, state)
            return await plaud_ingest.run_once(client, cfg)

    result = asyncio.run(go())
    assert result["status"] in ("ok", "locked")
    if result["status"] == "ok":
        assert result["ingested"] >= 1
        written = list(plaud_dir.glob("*.md"))
        assert written, "no wiki file was written"
        fm = plaud_ingest._parse_frontmatter(written[0].read_text())
        assert fm and fm.get("type") == "plaud-recording"
