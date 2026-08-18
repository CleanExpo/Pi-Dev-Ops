"""The daily digest must not report success when the push was refused.

Observed in Railway production on 2026-08-18T08:00:18Z, two adjacent lines:

    digest: TELEGRAM_BOT_TOKEN or chat id missing — skipping push
    Daily digest pushed at 2026-08-18T08:00:14 UTC

`push_digest_to_telegram()` returns False on a refused push WITHOUT raising, and the
scheduler discarded that return value, logging success unconditionally. The digest is the
autonomous engine's only status channel to the founder; an engine whose channel is dead
while the log claims it fired is indistinguishable from a working one. RA-1109.

The mutation control for these tests is to restore the defect — drop the `if pushed:`
branch in `cron_scheduler.cron_loop` and log the info line unconditionally. Both tests
must fail. A regression test that cannot fail is worth nothing.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from unittest.mock import patch

import pytest

from app.server import cron_scheduler


class _StopLoop(Exception):
    """Sentinel raised from the patched sleep to end the otherwise-infinite loop."""


def _run_one_iteration(push_result: bool, caplog) -> None:
    """Drive exactly one `cron_loop` iteration at a digest hour and stop.

    `await asyncio.sleep(60)` sits at the top of the `while True` body, OUTSIDE the
    iteration's try/except, so raising there is the one way out that cannot be swallowed
    by the loop's own error handling.
    """
    sleeps = {"n": 0}

    async def fake_sleep(_seconds: float) -> None:
        sleeps["n"] += 1
        # 1 = the startup delay, 2 = this iteration's sleep, 3 = the next one: stop there,
        # after the digest block for iteration one has already run.
        if sleeps["n"] >= 3:
            raise _StopLoop
        return None

    # 08:00 UTC is a default digest hour (PI_CEO_DIGEST_HOURS defaults to "8,20") and
    # minute 0 satisfies the `now.minute < 5` window.
    fixed_now = datetime.datetime(2026, 8, 18, 8, 0, 0)

    class _FakeDatetime(datetime.datetime):
        @classmethod
        def utcnow(cls) -> datetime.datetime:
            return fixed_now

    with (
        patch.object(cron_scheduler.asyncio, "sleep", fake_sleep),
        patch.object(cron_scheduler.datetime, "datetime", _FakeDatetime),
        patch.object(cron_scheduler, "_load_triggers", return_value=[]),
        # The import inside the digest block is function-local, so it resolves through
        # the module object at call time — patch the attribute the import actually
        # resolves, never sys.modules (see commit c8ff7336).
        patch("app.server.digest.push_digest_to_telegram", return_value=push_result),
    ):
        with caplog.at_level(logging.INFO, logger="pi-ceo.cron"):
            with pytest.raises(_StopLoop):
                asyncio.run(cron_scheduler.cron_loop())


def test_refused_push_is_not_reported_as_pushed(caplog) -> None:
    """A False return must not produce the success line, and must log an error."""
    _run_one_iteration(push_result=False, caplog=caplog)

    messages = [r.getMessage() for r in caplog.records]
    pushed_claims = [m for m in messages if "Daily digest pushed at" in m]
    assert not pushed_claims, (
        "scheduler claimed the digest was pushed after push_digest_to_telegram() "
        f"returned False: {pushed_claims}"
    )

    failures = [
        m for m in messages
        if "Daily digest NOT pushed" in m and "returned False" in m
    ]
    assert failures, (
        "a refused digest push must be logged as an error naming the cause; "
        f"got: {messages}"
    )
    assert any(
        r.levelno >= logging.ERROR
        for r in caplog.records
        if "Daily digest NOT pushed" in r.getMessage()
    ), "the refused-push line must be logged at ERROR, not INFO"


def test_successful_push_still_reports_success(caplog) -> None:
    """Positive control: the success path must still log success.

    Without this, a mutant that deletes the info branch entirely would pass the test
    above while silencing the working case too.
    """
    _run_one_iteration(push_result=True, caplog=caplog)

    messages = [r.getMessage() for r in caplog.records]
    assert any("Daily digest pushed at" in m for m in messages), (
        f"a successful push must still be reported: {messages}"
    )
    assert not any("Daily digest NOT pushed" in m for m in messages)
