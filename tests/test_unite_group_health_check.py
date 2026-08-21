"""RA-7317 — controls for the Unite-Group health check's accept bands.

Every test here was watched failing against the pre-fix script. The defect they guard
is a monitor that reported PASS on a 404: the accept band was "anything under 500",
and the GET fallback its own comment promised never fired on 404/405.

The script path is overridable so the identical file can be run against an older copy
(the positive control that proves these tests can fail).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import urllib.error
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

# The statuses main() actually routes to an alert. tier1_failing and regressed() both
# read status == "FAIL"; anything else is written to JSON and reaches nobody.
_ALERTING_STATUSES = {"FAIL"}


class _Calls(list):
    """A list that can also carry the follow_redirects flags — a plain list cannot
    hold attributes, and pretending otherwise broke every caller of this helper."""

    follow_flags: list[bool]


def scripted_http(monkeypatch, by_method):
    """Patch http_get to answer per HTTP method, recording the calls actually made."""
    seen = _Calls()
    follow_flags: list[bool] = []

    def fake(url, headers=None, method="GET", timeout=None, follow_redirects=True):
        seen.append(method)
        follow_flags.append(follow_redirects)
        outcome = by_method[method]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome, {}, b""

    monkeypatch.setattr(health, "http_get", fake)
    seen.follow_flags = follow_flags
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


def test_large_drop_reaches_an_alert_path(monkeypatch):
    """A Tier-1 WARN reaches NO alert path — tier1_failing and regressed() both read
    status == "FAIL" only. This was a WARN until a reviewer traced it."""
    advisors_returning(
        monkeypatch, [{"level": "WARN"}] * (health.ADVISOR_BASELINE - health.ADVISOR_BASELINE_SLACK - 1)
    )

    verdict = total_check(health.check_supabase_advisors({}))["status"]

    assert verdict == "FAIL"
    assert verdict in _ALERTING_STATUSES


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
def test_a_corrupt_prior_record_is_unreadable_not_absent(monkeypatch, tmp_path, payload):
    """Not `is None` — that is the distinction whose loss silenced the monitor."""
    (tmp_path / "unite-group-2026-08-21T000000.json").write_text(payload)
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)

    prior = health.prior_run()

    assert prior and prior["unreadable"] is True


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
def test_an_unreadable_prior_record_is_not_reported_as_no_prior_run(monkeypatch, tmp_path, payload):
    """`None` here meant "no prior run", which sends main() down the baseline path and
    takes a live Tier-1 failure out SILENT at exit 0. A record we cannot read is a run
    that happened whose checks are unknown — truthy, with no statuses to compare."""
    (tmp_path / "unite-group-2026-08-21T000000.json").write_text(payload)
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)

    prior = health.prior_run()

    assert prior, "must be truthy — main() reads bool(prior) to detect a first run"
    assert prior["unreadable"] is True
    assert prior["checks"] == []


def test_a_record_with_no_checks_key_is_still_usable(monkeypatch, tmp_path):
    """Negative control: both consumers default to [], so an absent key is fine."""
    (tmp_path / "unite-group-2026-08-21T000000.json").write_text('{"started": "t"}')
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)

    assert health.prior_run() == {"started": "t"}


def test_regressed_detects_a_regression_in_a_well_formed_record(monkeypatch, tmp_path):
    """Named for what it does. It was called `..._survives_every_record_prior_run_will_
    hand_it`, which claimed coverage it did not have — a reviewer caught the overclaim,
    and the very next finding lived in the gap it implied was covered. The real
    every-record case is the parametrised test below."""
    (tmp_path / "unite-group-2026-08-21T000000.json").write_text(
        '{"checks": [{"name": "unite api/health", "tier": 1, "status": "PASS"}]}'
    )
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)
    now = [{"name": "unite api/health", "tier": 1, "status": "FAIL", "detail": "HTTP 503"}]

    assert health.regressed(now, health.prior_run()) == ["unite api/health"]


# The overclaim, made good: walk the CONSUMER over every record shape prior_run will
# actually hand it. A guard that is never driven through the code path it protects is
# an assertion about that path, not a test of it.
@pytest.mark.parametrize(
    "payload",
    [
        '{"checks": [{"name": ["a", "b"], "tier": 1, "status": "PASS"}]}',   # unhashable key
        '{"checks": [{"name": 7, "tier": 1, "status": "PASS"}]}',
        '{"checks": [{"name": "ok", "tier": 1, "status": {"x": 1}}]}',
        '{"checks": [{"tier": 1}]}',                                          # missing both
        '{"checks": []}',
        '{"started": "t"}',                                                   # no checks key
        '{"checks": [{"name": "unite api/health", "tier": 1, "status": "PASS"}]}',
        '5',
        '{"checks": "not a list"}',
    ],
)
def test_regressed_never_raises_on_anything_prior_run_returns(monkeypatch, tmp_path, payload):
    (tmp_path / "unite-group-2026-08-21T000000.json").write_text(payload)
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)
    now = [{"name": "unite api/health", "tier": 1, "status": "FAIL", "detail": "HTTP 503"}]

    health.regressed(now, health.prior_run())   # must not raise


@pytest.mark.parametrize(
    "payload",
    [
        '{"signature": 5, "last_alert_at": "2026-08-21T00:00:00+00:00"}',
        '{"signature": "unite api/health", "last_alert_at": "2026-08-21T00:00:00+00:00"}',
        '{"signature": {"a": 1}, "last_alert_at": "2026-08-21T00:00:00+00:00"}',
    ],
)
def test_a_wrongly_typed_signature_alerts_instead_of_crashing(monkeypatch, tmp_path, payload):
    """The outer isinstance(state, dict) guard did not cover what was inside it, and
    `sorted(5)` aborts the run before stdout — suppressing the alert it was deciding."""
    state = tmp_path / "alert-state.json"
    state.write_text(payload)
    monkeypatch.setattr(health, "ALERT_STATE", state)

    resurface, why = health.should_resurface(["unite api/health"])

    assert resurface is True
    assert why


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


# ── end-to-end: the monitor must not go silent on a live failure ───────────────
def _drive_main(monkeypatch, tmp_path, prior_payload, failing=True):
    """Run main() over a stubbed run_all so the whole alert chain is exercised."""
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)
    monkeypatch.setattr(health, "LATEST_MD", tmp_path / "latest.md")
    monkeypatch.setattr(health, "ALERT_STATE", tmp_path / "alert-state.json")
    status = "FAIL" if failing else "PASS"
    monkeypatch.setattr(
        health,
        "run_all",
        lambda: [{"name": "unite api/health", "tier": 1, "status": status,
                  "detail": "HTTP 503", "data": {"code": 503}}],
    )
    if prior_payload is not None:
        (tmp_path / "unite-group-2026-08-21T000000.json").write_text(prior_payload)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = health.main()
    return code, buf.getvalue().strip()


@pytest.mark.parametrize(
    "payload",
    ['{"checks": "not a list"}', '{"checks": {"name": "x"}}', "5", '"clobbered"'],
)
def test_a_corrupt_prior_record_does_not_silence_a_live_failure(monkeypatch, tmp_path, payload):
    """The defect two reviewers caught: corrupt prior -> baseline path -> exit 0,
    silent, while the endpoint is down. Hermes delivers on non-empty stdout, so
    silence here is the monitor reporting nothing about a live outage."""
    code, delivered = _drive_main(monkeypatch, tmp_path, payload)

    assert code == 1
    assert delivered, "stdout empty means Hermes delivers nothing"
    assert "unite api/health" in delivered


def test_a_genuine_first_run_is_still_silent(monkeypatch, tmp_path):
    """Negative control: the baseline path must survive. Without this, 'always alert'
    would satisfy the test above."""
    code, delivered = _drive_main(monkeypatch, tmp_path, None)

    assert code == 0
    assert delivered == ""


def test_a_healthy_prior_still_reports_the_regression(monkeypatch, tmp_path):
    """Negative control: the normal regression path is untouched."""
    code, delivered = _drive_main(
        monkeypatch, tmp_path,
        '{"checks": [{"name": "unite api/health", "tier": 1, "status": "PASS"}]}',
    )

    assert code == 1
    assert "REGRESSION" in delivered


def test_two_unreadable_priors_do_not_share_state(monkeypatch, tmp_path):
    """A dict(CONST) shallow copy shares the inner list; one caller appending to it
    would poison every later call in the process."""
    (tmp_path / "unite-group-2026-08-21T000000.json").write_text('{"checks": "not a list"}')
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)

    first = health.prior_run()
    first["checks"].append({"name": "poison", "tier": 1, "status": "PASS"})

    assert health.prior_run()["checks"] == []


# ── the endpoint check must SEE a 3xx, not chase it ────────────────────────────
def test_the_health_check_declines_redirects(monkeypatch):
    """urlopen installs HTTPRedirectHandler by default, so the caller never sees a
    3xx — it sees whatever the redirect lands on. Measured live against the protected
    preview: the true first hop is 302 to Vercel's SSO wall, and the default handler
    returned 200 with an HTML login page. The 2xx-only band was decorative."""
    seen = scripted_http(monkeypatch, {"HEAD": 302, "GET": 302})

    res = health.check_unite_health_api(URL)

    assert seen.follow_flags == [False]
    assert res["status"] == "FAIL"
    assert res["data"]["code"] == 302


def test_the_get_fallback_also_declines_redirects(monkeypatch):
    """A 302 stops at HEAD, so the test above records ONE flag and would pass even if
    the GET fallback still chased redirects. Drive the fallback with a 404, which is
    the only way to reach the second request — the same do-not-overclaim lesson a
    reviewer taught this file one round earlier."""
    seen = scripted_http(monkeypatch, {"HEAD": 404, "GET": 302})

    res = health.check_unite_health_api(URL)

    assert seen == ["HEAD", "GET"], "the GET fallback must actually be exercised"
    assert seen.follow_flags == [False, False]
    assert res["status"] == "FAIL"
    assert res["data"]["code"] == 302


def test_http_get_still_follows_redirects_by_default(monkeypatch):
    """Negative control: check_http probes pages, which legitimately redirect. The
    no-follow behaviour must be opt-in, not a change to every caller."""
    import inspect

    sig = inspect.signature(health.http_get)

    assert sig.parameters["follow_redirects"].default is True


@pytest.mark.parametrize(
    "payload",
    [
        '{"signature": ["x", 5], "last_alert_at": "2026-08-21T00:00:00+00:00"}',
        '{"signature": [{"a": 1}, "x"], "last_alert_at": "2026-08-21T00:00:00+00:00"}',
        '{"signature": [None], "last_alert_at": "2026-08-21T00:00:00+00:00"}',
    ],
)
def test_a_signature_with_mixed_element_types_alerts_instead_of_crashing(
    monkeypatch, tmp_path, payload
):
    """`sorted(["x", 5])` raises TypeError: '<' not supported between int and str.
    Guarding that the signature is a list did not guard what is in it."""
    state = tmp_path / "alert-state.json"
    state.write_text(payload)
    monkeypatch.setattr(health, "ALERT_STATE", state)

    resurface, why = health.should_resurface(["unite api/health"])

    assert resurface is True
    assert why


# ── no single check may abort the run ──────────────────────────────────────────
# Six defects across four review rounds were the same shape: an input raised out of
# one check, hit the top-level handler, and took the whole hour's monitoring with it.
# Exit 2 with empty stdout means the other fourteen checks never ran.
def test_a_crashed_check_becomes_a_failing_check(monkeypatch):
    def explode():
        raise urllib.error.URLError("nodename nor servname provided")

    out = health.guarded("hermes gateway", 1, explode)

    assert len(out) == 1
    assert out[0]["status"] == "FAIL"
    assert out[0]["name"] == "hermes gateway"
    assert out[0]["tier"] == 1
    assert "URLError" in out[0]["detail"]
    assert out[0]["data"]["crashed"] is True


def test_a_crashed_tier1_check_reaches_the_alert_path(monkeypatch, tmp_path):
    """A FAIL alerts; the silence it replaces did not. That is the whole point."""
    crashed = health.guarded("hermes model", 1, lambda: (_ for _ in ()).throw(OSError("boom")))

    assert crashed[0]["status"] in _ALERTING_STATUSES


def test_guarded_normalises_single_and_list_returns():
    """Half the checks return one record, half return a list. Both must flatten."""
    one = health.guarded("x", 1, lambda: health.mk("x", 1, "PASS", "d"))
    many = health.guarded("y", 1, lambda: [health.mk("y1", 1, "PASS", "d"),
                                           health.mk("y2", 1, "PASS", "d")])

    assert [r["name"] for r in one] == ["x"]
    assert [r["name"] for r in many] == ["y1", "y2"]


def test_a_healthy_check_passes_through_untouched():
    """Negative control: the guard must not rewrite a check that worked."""
    original = health.mk("x", 1, "PASS", "all good", code=200)

    assert health.guarded("x", 1, lambda: original) == [original]


def test_a_dns_failure_no_longer_aborts_the_run(monkeypatch):
    """The exact round-9 P0: http_get does not catch URLError, and supabase_rest and
    check_integration_sync have no handler of their own."""
    def boom(*a, **k):
        raise urllib.error.URLError("dns is down")

    monkeypatch.setattr(health, "http_get", boom)
    env = {"SUPABASE_UNITE_GROUP_URL": "https://x.supabase.co",
           "SUPABASE_UNITE_GROUP_SERVICE_KEY": "k"}

    out = health.guarded("integration sync", 1, health.check_integration_sync, env)

    assert out[0]["status"] == "FAIL"
    assert "URLError" in out[0]["detail"]


def test_an_unreadable_config_no_longer_aborts_the_run(monkeypatch, tmp_path):
    """The other round-9 finding: check_hermes_model reads config.yaml with no handler,
    so a non-UTF8 or permission-denied file killed the run."""
    monkeypatch.setattr(health, "HERMES_HOME", tmp_path)
    (tmp_path / "config.yaml").write_bytes(b"\xff\xfe\x00not utf8 \xc3\x28")

    out = health.guarded("hermes model", 1, health.check_hermes_model)

    assert out[0]["status"] == "FAIL"
    assert "UnicodeDecodeError" in out[0]["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        '{"signature": ["unite api/health"], "last_alert_at": 1755734400}',
        '{"signature": ["unite api/health"], "last_alert_at": null}',
        '{"signature": ["unite api/health"], "last_alert_at": ["2026-08-21"]}',
    ],
)
def test_a_non_string_last_alert_at_alerts_instead_of_crashing(monkeypatch, tmp_path, payload):
    """fromisoformat raises TypeError on a non-str, and the handler caught only
    KeyError/ValueError. should_resurface runs OUTSIDE guarded(), so this aborted
    main() after write_outputs and before stdout_report — record written, alert never
    delivered."""
    state = tmp_path / "alert-state.json"
    state.write_text(payload)
    monkeypatch.setattr(health, "ALERT_STATE", state)

    resurface, why = health.should_resurface(["unite api/health"])

    assert resurface is True
    assert why


def test_main_alerts_even_if_should_resurface_itself_explodes(monkeypatch, tmp_path):
    """Defence in depth for the path guarded() cannot reach. Not knowing whether to
    alert is a reason to alert, never a reason to go quiet."""
    def explode(_failing):
        raise RuntimeError("alert-state store is on fire")

    monkeypatch.setattr(health, "should_resurface", explode)
    code, delivered = _drive_main(
        monkeypatch, tmp_path,
        '{"checks": [{"name": "unite api/health", "tier": 1, "status": "FAIL"}]}',
    )

    assert code == 1
    assert delivered, "a broken alert-state store must not silence a live failure"


# ── the invariant, asserted once for every step rather than once per defect ────
@pytest.mark.parametrize(
    "victim",
    ["regressed", "write_outputs", "should_resurface", "prior_run"],
)
def test_no_step_between_the_checks_and_stdout_can_silence_the_alert(
    monkeypatch, tmp_path, victim
):
    """Three separate defects landed in this stretch — a TypeError parsing
    last_alert_at, an OSError writing the JSON record — each aborting main() after the
    work was done and before the alert went out. Rather than a test per defect, break
    each step in turn and require the alert regardless."""
    def explode(*_a, **_k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(health, victim, explode)
    code, delivered = _drive_main(
        monkeypatch, tmp_path,
        '{"checks": [{"name": "unite api/health", "tier": 1, "status": "PASS"}]}',
    )

    assert delivered, f"breaking {victim} silenced a live Tier-1 failure"
    assert code == 1


def test_the_alert_names_the_failing_check_when_the_record_cannot_be_written(
    monkeypatch, tmp_path
):
    """A fallback that delivered an EMPTY alert would satisfy the test above. The
    content has to survive the failure too, not just the delivery."""
    def explode(*_a, **_k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(health, "write_outputs", explode)
    _code, delivered = _drive_main(
        monkeypatch, tmp_path,
        '{"checks": [{"name": "unite api/health", "tier": 1, "status": "PASS"}]}',
    )

    assert "unite api/health" in delivered
    assert "HTTP 503" in delivered


def test_a_healthy_run_is_still_silent_when_every_step_works(monkeypatch, tmp_path):
    """Negative control for the whole guard family: never_fatal must not turn a clean
    run into an alert."""
    code, delivered = _drive_main(
        monkeypatch, tmp_path,
        '{"checks": [{"name": "unite api/health", "tier": 1, "status": "PASS"}]}',
        failing=False,
    )

    assert code == 0
    assert delivered == ""


# ── every fallback must point TOWARD alerting ─────────────────────────────────
@pytest.mark.parametrize(
    "victim", ["regressed", "write_outputs", "should_resurface", "prior_run"]
)
def test_a_broken_step_alerts_even_when_the_resurface_throttle_is_active(
    monkeypatch, tmp_path, victim
):
    """The earlier invariant test left the throttle idle, so `resurface` rescued every
    case and a wrong fallback stayed invisible. With a recent alert for the SAME
    failing set, resurface is throttled OFF — and then the regressed fallback of `[]`
    read as "no regression" and delivered nothing. A fallback is a direction, not a
    placeholder."""
    import datetime as _dt

    (tmp_path / "alert-state.json").write_text(json.dumps({
        "last_alert_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "signature": ["unite api/health"],
    }))

    def explode(*_a, **_k):
        raise RuntimeError(f"{victim} exploded")

    monkeypatch.setattr(health, victim, explode)
    monkeypatch.setattr(health, "ALERT_STATE", tmp_path / "alert-state.json")
    code, delivered = _drive_main(
        monkeypatch, tmp_path,
        '{"checks": [{"name": "unite api/health", "tier": 1, "status": "PASS"}]}',
    )

    assert delivered, f"{victim} failing went silent while the throttle was active"
    assert code == 1


def test_an_empty_prior_record_does_not_read_as_no_prior_run(monkeypatch, tmp_path):
    """`{}` passes every shape guard and is still falsy, and main() reads bool(prior)
    to tell a first run from a later one. The fifth door into the same silencing bug."""
    (tmp_path / "unite-group-2026-08-21T000000.json").write_text("{}")
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)

    prior = health.prior_run()

    assert prior, "an empty record exists; it must not read as absent"
    assert prior["unreadable"] is True


def test_an_empty_prior_record_does_not_silence_a_live_failure(monkeypatch, tmp_path):
    code, delivered = _drive_main(monkeypatch, tmp_path, "{}")

    assert code == 1
    assert "unite api/health" in delivered


def test_a_reporter_that_dies_before_printing_still_reaches_hermes(monkeypatch, tmp_path):
    """never_fatal keeps main() alive, but staying alive is not the goal. If
    stdout_report raises before its first print, the alert is decided (alert=True,
    exit 1) and never emitted — and Hermes delivers on stdout content, not exit code."""
    def die_before_printing(_checks, _regressions, _json_path, _alert):
        raise RuntimeError("died before the first print")

    monkeypatch.setattr(health, "stdout_report", die_before_printing)
    code, delivered = _drive_main(
        monkeypatch, tmp_path,
        '{"checks": [{"name": "unite api/health", "tier": 1, "status": "PASS"}]}',
    )

    assert code == 1
    assert delivered, "alert decided but never emitted"
    assert "unite api/health" in delivered
    assert "HTTP 503" in delivered


def test_the_fallback_alert_stays_quiet_on_a_healthy_run(monkeypatch, tmp_path):
    """Negative control: the last-resort emitter must not fire when nothing is wrong."""
    def die_before_printing(_checks, _regressions, _json_path, _alert):
        raise RuntimeError("died")

    monkeypatch.setattr(health, "stdout_report", die_before_printing)
    code, delivered = _drive_main(
        monkeypatch, tmp_path,
        '{"checks": [{"name": "unite api/health", "tier": 1, "status": "PASS"}]}',
        failing=False,
    )

    assert code == 0
    assert delivered == ""


def test_an_unreadable_env_file_does_not_abort_the_run(monkeypatch):
    """load_env is the first line of run_all, and run_all is called directly from
    main() rather than through guarded(). An unreadable ~/.hermes/.env raised before a
    single check executed — the first link, left unguarded while the last was fixed."""
    def boom():
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(health, "load_env", boom)
    monkeypatch.setattr(health, "check_http", lambda *a, **k: health.mk("x", 1, "PASS", "d"))
    monkeypatch.setattr(health, "check_unite_health_api", lambda *a: health.mk("y", 1, "PASS", "d"))

    checks = health.run_all()

    assert checks, "an unreadable env file must not stop every check from running"


def test_a_total_check_run_failure_still_alerts(monkeypatch, tmp_path):
    """If run_all fails outright, that is itself the most important thing to report."""
    def boom():
        raise RuntimeError("everything is on fire")

    monkeypatch.setattr(health, "run_all", boom)
    monkeypatch.setattr(health, "LOG_DIR", tmp_path)
    monkeypatch.setattr(health, "LATEST_MD", tmp_path / "l.md")
    monkeypatch.setattr(health, "ALERT_STATE", tmp_path / "a.json")
    (tmp_path / "unite-group-2026-08-21T000000.json").write_text(
        '{"checks": [{"name": "health check run", "tier": 1, "status": "PASS"}]}'
    )

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = health.main()

    assert code == 1
    assert "health check run" in buf.getvalue()


def test_a_failed_alert_state_write_does_not_kill_the_run(monkeypatch, tmp_path):
    """note_alert runs AFTER stdout_report, so this never silenced anything — the
    alert is already delivered. It exits 2 instead of 1 and skips the throttle record,
    which is louder in both directions, not quieter. Bookkeeping should not decide the
    exit code of a run that did its job."""
    def boom(_failing):
        raise RuntimeError("alert-state volume gone")

    monkeypatch.setattr(health, "note_alert", boom)
    code, delivered = _drive_main(
        monkeypatch, tmp_path,
        '{"checks": [{"name": "unite api/health", "tier": 1, "status": "PASS"}]}',
    )

    assert code == 1, "a delivered alert must not report itself as a crashed run"
    assert "unite api/health" in delivered
