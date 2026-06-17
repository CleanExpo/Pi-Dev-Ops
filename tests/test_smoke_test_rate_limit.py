"""Regression checks for production-safe smoke-test rate limiting."""

from pathlib import Path


def test_prod_smoke_skips_login_rate_limit_hammer():
    source = Path("scripts/smoke_test.py").read_text()

    assert "if PROD_MODE:" in source
    assert "Rapid login rate-limit hammer skipped in prod" in source
    assert "Do not poison the shared production auth limiter" in source


def test_local_smoke_keeps_login_rate_limit_coverage():
    source = Path("scripts/smoke_test.py").read_text()

    assert 'body={"password": "wrong-password-rate-limit-test"}' in source
    assert "Rapid requests trigger 429 Too Many Requests" in source
