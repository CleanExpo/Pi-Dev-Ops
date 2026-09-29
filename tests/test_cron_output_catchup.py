"""A scheduled job whose output a deploy wiped must re-run on boot.

Production, 2026-09-29: `zte-v2-score-daily` completed (rc=0) at 03:00 UTC; the #826
deploy at 03:12 replaced the container and with it `.harness/zte-v2-score.json`. Because
`last_fired_at` is durable in Supabase, boot catch-up saw "fired 12 minutes ago" and
skipped it, so every Mission Control ZTE badge request got 404 until the next day.

Mutation controls, each of which must make a test here fail:
  * make `output_missing` return False  -> the missing-output test fails
  * drop `"output"` from the committed zte trigger -> the config test fails
  * remove the `..` guard                -> the escape test fails
"""
from __future__ import annotations

import time
from pathlib import Path

from app.server import config_loader
from app.server.cron_outputs import output_missing, should_fire_on_boot
from app.server.routes import zte


def _trigger(**extra) -> dict:
    return {
        "id": "zte-v2-score-daily",
        "type": "zte_v2_score",
        "hour": 3,
        "minute": 0,
        "enabled": True,
        "last_fired_at": time.time() - 12 * 60,  # fired 12 min ago: NOT overdue
        **extra,
    }


def test_missing_output_fires_even_when_recently_fired(tmp_path: Path) -> None:
    trig = _trigger(output=".harness/zte-v2-score.json")
    assert output_missing(trig, root=tmp_path) is True


def test_present_output_does_not_fire(tmp_path: Path) -> None:
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "zte-v2-score.json").write_text("{}")
    trig = _trigger(output=".harness/zte-v2-score.json")
    assert output_missing(trig, root=tmp_path) is False


def test_no_declared_output_keeps_schedule_only_behaviour(tmp_path: Path) -> None:
    """Negative control: a recently-fired trigger with no `output` stays skipped."""
    trig = _trigger()
    assert output_missing(trig, root=tmp_path) is False
    assert should_fire_on_boot(trig) is False


def test_disabled_trigger_never_fires(tmp_path: Path) -> None:
    trig = _trigger(output=".harness/zte-v2-score.json", enabled=False)
    assert output_missing(trig, root=tmp_path) is False


def test_output_outside_repo_is_ignored(tmp_path: Path) -> None:
    for bad in ("../outside.json", "/etc/definitely-missing.json", ".harness/../../x.json"):
        assert output_missing(_trigger(output=bad), root=tmp_path) is False, bad


def test_committed_zte_trigger_declares_the_file_the_badge_reads() -> None:
    """The declared output must be exactly the path routes/zte.py serves."""
    trig = next(t for t in config_loader.cron_triggers() if t["id"] == "zte-v2-score-daily")
    assert "output" in trig, "zte-v2-score-daily must declare its output file"
    assert (config_loader.REPO_ROOT / trig["output"]).resolve() == zte.SCORE_FILE.resolve()
