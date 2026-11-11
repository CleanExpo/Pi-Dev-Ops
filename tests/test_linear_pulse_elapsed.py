"""RA-8031 — Pulse "Elapsed" must read the epoch seconds sessions actually store."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from app.server.linear_pulse import _elapsed_minutes


def test_epoch_float_started_45_min_ago_is_45() -> None:
    assert _elapsed_minutes(time.time() - 2700) == 45


def test_epoch_int_started_45_min_ago_is_45() -> None:
    assert _elapsed_minutes(int(time.time()) - 2700) == 45


def test_iso_string_still_accepted() -> None:
    started = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
    assert _elapsed_minutes(started.replace("+00:00", "Z")) == 45


@pytest.mark.parametrize("value", [0, 0.0, None, "", "not-a-date", object(), True])
def test_missing_or_unparseable_is_zero(value: object) -> None:
    assert _elapsed_minutes(value) == 0  # type: ignore[arg-type]
