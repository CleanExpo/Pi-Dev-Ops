"""The founder's $20/day Jev cap holds when JEV_DAILY_CAP_USD is unset. Offline; the ledger is the test's own."""
from __future__ import annotations

import pytest

from jev_platform import spend


def test_unset_means_the_twenty_dollar_default():
    assert spend.daily_cap() == 20.0


def test_a_set_value_overrides_the_default(monkeypatch):
    monkeypatch.setenv("JEV_DAILY_CAP_USD", "5")
    assert spend.daily_cap() == 5.0


@pytest.mark.parametrize("raw", ["", "  ", "0", "-1", "nan", "inf", "abc"])
def test_an_empty_or_invalid_value_raises_rather_than_meaning_no_cap(monkeypatch, raw):
    monkeypatch.setenv("JEV_DAILY_CAP_USD", raw)
    with pytest.raises(ValueError):
        spend.daily_cap()


def test_unset_cap_refuses_a_reserve_that_would_pass_twenty_dollars():
    spend.reserve("t", 19.99)
    with pytest.raises(spend.SpendCapReached):
        spend.reserve("t", 0.02)
    spend.reserve("t", 0.01)  # exactly at the cap is allowed
