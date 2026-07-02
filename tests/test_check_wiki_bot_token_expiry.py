"""Tests for scripts/check_wiki_bot_token_expiry.py (RA-6905)."""
from __future__ import annotations

from datetime import date

from scripts.check_wiki_bot_token_expiry import check_expiry


def test_missing_expiry_warns_but_ok():
    code, lines = check_expiry(None, today=date(2026, 7, 2))
    assert code == 0
    assert any("unset" in line for line in lines)


def test_valid_expiry_far_future():
    code, lines = check_expiry("2026-12-31", today=date(2026, 7, 2))
    assert code == 0
    assert any("passed" in line for line in lines)


def test_expiry_within_warn_window():
    code, lines = check_expiry("2026-07-10", today=date(2026, 7, 2), warn_days=14)
    assert code == 1
    assert any("warning" in line for line in lines)


def test_expired_token_fails():
    code, lines = check_expiry("2026-06-01", today=date(2026, 7, 2))
    assert code == 2
    assert any("expired" in line for line in lines)
