"""RA-7317 — controls for the Unite-Group health check's accept bands.

Every test here was watched failing against the pre-fix script. The defect they guard
is a monitor that reported PASS on a 404: the accept band was "anything under 500",
and the GET fallback its own comment promised never fired on 404/405.

The script path is overridable so the identical file can be run against an older copy
(the positive control that proves these tests can fail).
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HEALTH_CHECK_SCRIPT = Path(
    os.environ.get("UG_HEALTH_CHECK_SCRIPT", ROOT / "scripts" / "unite_group_health_check.py")
)
SPEC = importlib.util.spec_from_file_location(
    "unite_group_health_check_under_test", HEALTH_CHECK_SCRIPT
)
assert SPEC and SPEC.loader
health = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(health)

URL = "https://unite-group.in/api/health"


def scripted_http(monkeypatch, by_method):
    """Patch http_get to answer per HTTP method, recording the methods actually used."""
    seen: list[str] = []

    def fake(url, headers=None, method="GET", timeout=None):
        seen.append(method)
        outcome = by_method[method]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome, {}, b""

    monkeypatch.setattr(health, "http_get", fake)
    return seen


# ── the P0: a 404 must never read as healthy ───────────────────────────────────
def test_head_404_issues_the_promised_get(monkeypatch):
    seen = scripted_http(monkeypatch, {"HEAD": 404, "GET": 200})

    res = health.check_unite_health_api(URL)

    assert seen == ["HEAD", "GET"], "404 from HEAD must fall back to GET"
    assert res["status"] == "PASS"
    assert res["data"]["code"] == 200


def test_head_405_issues_the_promised_get(monkeypatch):
    seen = scripted_http(monkeypatch, {"HEAD": 405, "GET": 503})

    res = health.check_unite_health_api(URL)

    assert seen == ["HEAD", "GET"], "405 from HEAD must fall back to GET"
    assert res["status"] == "FAIL"


def test_a_missing_endpoint_is_a_failure(monkeypatch):
    """The exact live defect: 404 everywhere reported PASS with HTTP 404."""
    scripted_http(monkeypatch, {"HEAD": 404, "GET": 404})

    res = health.check_unite_health_api(URL)

    assert res["status"] == "FAIL"
    assert res["data"]["code"] == 404


@pytest.mark.parametrize("code", [301, 302, 307, 401, 403, 404, 429, 500, 503])
def test_only_2xx_passes(monkeypatch, code):
    """A 302 is an auth wall or a redirect away from the endpoint, not a health report."""
    scripted_http(monkeypatch, {"HEAD": code, "GET": code})

    assert health.check_unite_health_api(URL)["status"] == "FAIL"


@pytest.mark.parametrize("code", [200, 204])
def test_2xx_passes(monkeypatch, code):
    scripted_http(monkeypatch, {"HEAD": code, "GET": code})

    assert health.check_unite_health_api(URL)["status"] == "PASS"


def test_unreachable_is_a_failure(monkeypatch):
    scripted_http(monkeypatch, {"HEAD": OSError("boom"), "GET": OSError("boom")})

    res = health.check_unite_health_api(URL)

    assert res["status"] == "FAIL"
    assert res["detail"] == "unreachable"


# ── advisor drift is bounded in both directions ────────────────────────────────
def advisors_returning(monkeypatch, lints):
    monkeypatch.setattr(health, "supabase_mgmt", lambda env, path: (200, {"lints": lints}))


def total_check(results):
    return next(r for r in results if r["name"] == "supabase advisor total")


def test_empty_advisor_list_is_not_a_clean_read(monkeypatch):
    """A collapse to zero scored `drift -71 <= 5` and read as healthy."""
    advisors_returning(monkeypatch, [])

    assert total_check(health.check_supabase_advisors({}))["status"] == "FAIL"


def test_large_drop_warns_rather_than_passing_silently(monkeypatch):
    advisors_returning(
        monkeypatch, [{"level": "WARN"}] * (health.ADVISOR_BASELINE - health.ADVISOR_BASELINE_SLACK - 1)
    )

    assert total_check(health.check_supabase_advisors({}))["status"] == "WARN"


def test_baseline_still_passes(monkeypatch):
    advisors_returning(monkeypatch, [{"level": "WARN"}] * health.ADVISOR_BASELINE)

    assert total_check(health.check_supabase_advisors({}))["status"] == "PASS"


def test_growth_beyond_slack_still_fails(monkeypatch):
    advisors_returning(
        monkeypatch, [{"level": "WARN"}] * (health.ADVISOR_BASELINE + health.ADVISOR_BASELINE_SLACK + 1)
    )

    assert total_check(health.check_supabase_advisors({}))["status"] == "FAIL"
