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


# ── a corrupt state file must not abort the whole run ──────────────────────────
# `json.loads("5")` succeeds, so a clobbered store slips past the decode guard and
# reaches `.get()`. The AttributeError is caught by the top-level handler as
# `FATAL ... exit 2` — the hour's health check is skipped entirely, and a monitor that
# dies on bad input reports nothing about anything.
@pytest.mark.parametrize("payload", ["5", '"clobbered"', "null", "[1, 2, 3]"])
def test_corrupt_alert_state_alerts_instead_of_crashing(monkeypatch, tmp_path, payload):
    state = tmp_path / "alert-state.json"
    state.write_text(payload)
    monkeypatch.setattr(health, "ALERT_STATE", state)

    resurface, why = health.should_resurface(["unite api/health"])

    assert resurface is True
    assert why


@pytest.mark.parametrize("payload", ["5", '"clobbered"', "null", "[1, 2, 3]"])
def test_corrupt_prior_record_reads_as_absent(monkeypatch, tmp_path, payload):
    (tmp_path / "unite-group-2026-08-21T000000.json").write_text(payload)
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)

    assert health.prior_run() is None


def test_a_valid_prior_record_is_still_loaded(monkeypatch, tmp_path):
    """Negative control: the guard must not make every prior run look absent."""
    (tmp_path / "unite-group-2026-08-21T000000.json").write_text(
        '{"started": "2026-08-21T00:00:00+00:00", "checks": []}'
    )
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)

    assert health.prior_run()["started"] == "2026-08-21T00:00:00+00:00"


# ── the guard has to be as deep as the consumers reach ─────────────────────────
# A reviewer caught `isinstance(record, dict)` being one level too shallow: both
# regressed() and check_github_commits_growth() iterate prior["checks"] and call
# .get() on each element, so `{"checks": {...}}` iterates the dict's KEYS and lands
# .get() on a str — the same crash, one level deeper.
@pytest.mark.parametrize(
    "payload",
    [
        '{"checks": {"name": "x"}}',
        '{"checks": "not a list"}',
        '{"checks": 5}',
        '{"checks": [{"name": "ok", "tier": 1, "status": "PASS"}, "a bare string"]}',
    ],
)
def test_prior_record_with_unusable_checks_reads_as_absent(monkeypatch, tmp_path, payload):
    (tmp_path / "unite-group-2026-08-21T000000.json").write_text(payload)
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)

    assert health.prior_run() is None


def test_a_record_with_no_checks_key_is_still_usable(monkeypatch, tmp_path):
    """Negative control: both consumers default to [], so an absent key is fine."""
    (tmp_path / "unite-group-2026-08-21T000000.json").write_text('{"started": "t"}')
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)

    assert health.prior_run() == {"started": "t"}


def test_regressed_survives_every_record_prior_run_will_hand_it(monkeypatch, tmp_path):
    """The guard is only worth anything if it covers what the consumer actually does."""
    (tmp_path / "unite-group-2026-08-21T000000.json").write_text(
        '{"checks": [{"name": "unite api/health", "tier": 1, "status": "PASS"}]}'
    )
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)
    now = [{"name": "unite api/health", "tier": 1, "status": "FAIL", "detail": "HTTP 503"}]

    assert health.regressed(now, health.prior_run()) == ["unite api/health"]


def test_a_non_object_advisor_entry_is_an_unreadable_response(monkeypatch):
    """The advisor API is external; one bad entry must not abort the whole run."""
    monkeypatch.setattr(
        health, "supabase_mgmt", lambda env, path: (200, {"lints": [{"level": "WARN"}, "oops"]})
    )

    results = health.check_supabase_advisors({})

    assert [r["status"] for r in results] == ["FAIL", "FAIL"]


def test_a_tier1_entry_missing_its_keys_does_not_raise(monkeypatch, tmp_path):
    """prior_run screens entry TYPE, not entry KEYS — regressed() subscripts both."""
    (tmp_path / "unite-group-2026-08-21T000000.json").write_text(
        '{"checks": [{"tier": 1}, {"name": "unite api/health", "tier": 1, "status": "PASS"}]}'
    )
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)
    now = [{"name": "unite api/health", "tier": 1, "status": "FAIL", "detail": "HTTP 503"}]

    assert health.regressed(now, health.prior_run()) == ["unite api/health"]
