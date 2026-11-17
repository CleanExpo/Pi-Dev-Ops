"""RA-8408 — unit tests for app/server/internal_secret.py, the X-Pi-CEO-Secret owner.

Names start test_acNN_ with the acceptance criterion they prove (spec section 15)."""
from __future__ import annotations

import importlib
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.server import config, internal_secret as owner

CURRENT = "fake-current-key-aaaaaaaaaaaaaaaaaaaaaa"
NEXT = "fake-next-key-bbbbbbbbbbbbbbbbbbbbbbbbbbbb"
READ_ONLY = "fake-read-only-key-dddddddddddddddddddd"
NEXT_ENV, READ_ENV, CURRENT_ENV = owner.NEXT_ENV, owner.READ_ONLY_ENV, owner.CURRENT_ENV


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    for name in (NEXT_ENV, READ_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(CURRENT_ENV, CURRENT)
    monkeypatch.setattr(config, "INTERNAL_WEBHOOK_SECRET", CURRENT)
    owner._reset_log_state()


@pytest.fixture
def lines(caplog):
    caplog.set_level(logging.INFO, logger=owner.log.name)
    return lambda: [r.getMessage() for r in caplog.records if r.name == owner.log.name]


# ── AC-2: every helper keeps its exact codes, texts and order ────────────────
FAMILY_A = ("TAO_INTERNAL_WEBHOOK_SECRET not configured on server",
            "Invalid or missing X-Pi-CEO-Secret", "Invalid or missing X-Pi-CEO-Secret")
FAMILY_B = ("TAO_INTERNAL_WEBHOOK_SECRET not configured on server",
            "Missing X-Pi-CEO-Secret header", "Invalid X-Pi-CEO-Secret")
FAMILY_C = ("Internal webhook secret not configured", "X-Pi-CEO-Secret header required", "Invalid secret")
HELPERS = [("routes.mesh", "_check_secret", FAMILY_A), ("routes.conversations", "_check_secret", FAMILY_A),
           ("routes.wiki_sources", "_check_secret", FAMILY_A), ("mesh_fleet_auth", "check", FAMILY_A),
           ("routes.cost_report", "_check_secret", FAMILY_B), ("routes.delegate", "_check_secret", FAMILY_B),
           ("routes.margot", "_check_secret", FAMILY_B),
           ("routes.webhooks", "_require_internal_webhook_secret", FAMILY_C)]


def _call(module, name, value):
    func = getattr(importlib.import_module(f"app.server.{module}"), name)
    if name == "_require_internal_webhook_secret":
        value = SimpleNamespace(headers={} if value is None else {"x-pi-ceo-secret": value})
    try:
        func(value)
    except HTTPException as exc:
        return exc.status_code, exc.detail
    return None


@pytest.mark.parametrize("module,name,texts", HELPERS, ids=[h[0] for h in HELPERS])
def test_ac02_helper_codes_and_texts_are_unchanged(module, name, texts, monkeypatch):
    monkeypatch.setattr(config, "INTERNAL_WEBHOOK_SECRET", "")
    assert _call(module, name, None) == (503, texts[0])  # not configured comes before missing
    monkeypatch.setattr(config, "INTERNAL_WEBHOOK_SECRET", CURRENT)
    assert _call(module, name, None) == (401, texts[1])
    assert _call(module, name, "fake-wrong-key") == (401, texts[2])
    assert _call(module, name, CURRENT) is None


# ── AC-5: empty, malformed, oversized and dummy values never match ──────────
@pytest.mark.parametrize("value", ["\ud800", "x" * 65536, "fake-é-key", " " + CURRENT, CURRENT + "\n"],
                         ids=["lone-surrogate", "64kb", "non-ascii", "leading-space", "trailing-newline"])
def test_ac05_malformed_presented_value_is_a_mismatch(value, monkeypatch):
    monkeypatch.setenv(NEXT_ENV, NEXT)
    assert owner.classify(value, "mesh") == "mismatch"
    assert owner.classify_fleet_read(value) == "mismatch"


def test_ac05_next_alone_never_opens_anything(monkeypatch):
    monkeypatch.setattr(config, "INTERNAL_WEBHOOK_SECRET", "")
    monkeypatch.setenv(NEXT_ENV, NEXT)
    assert owner.classify(NEXT, "mesh") == "unconfigured"
    assert owner.classify_fleet_read(NEXT) == "unconfigured"


def test_ac05_the_process_dummy_value_is_refused(monkeypatch):
    monkeypatch.setattr(owner, "_DUMMY", "fake-known-dummy-value-eeeeeeeeeeeeeee")
    assert owner.classify(owner._DUMMY, "mesh") == "mismatch"
    assert owner.classify_fleet_read(owner._DUMMY) == "mismatch"
    monkeypatch.setattr(config, "INTERNAL_WEBHOOK_SECRET", "")
    monkeypatch.setenv(READ_ENV, READ_ONLY)
    assert owner.classify_fleet_read(owner._DUMMY) == "mismatch"


# ── AC-6: next-value policy ──────────────────────────────────────────────────
IGNORED = {"31-chars": "n" * 31, "space": "fake-next key-" + "b" * 20, "non-ascii": "fake-next-é" + "b" * 25,
           "control": "fake-next-\x07" + "b" * 25, "equals-current": CURRENT, "equals-read-only": READ_ONLY}


def test_ac06_next_of_exactly_32_characters_is_honoured(monkeypatch):
    monkeypatch.setenv(NEXT_ENV, "n" * 32)
    assert owner.classify("n" * 32, "mesh") == "next"
    assert owner.next_state(CURRENT, "n" * 32, "") == "active"


@pytest.mark.parametrize("raw", list(IGNORED.values()), ids=list(IGNORED))
def test_ac06_next_failing_policy_is_ignored_and_current_still_works(raw, monkeypatch):
    monkeypatch.setenv(READ_ENV, READ_ONLY)
    monkeypatch.setenv(NEXT_ENV, raw)
    assert owner.effective_next(CURRENT, raw, READ_ONLY) == ""
    assert owner.classify(CURRENT, "mesh") == "current"
    if raw not in (CURRENT, READ_ONLY):
        assert owner.classify(raw, "mesh") == "mismatch"
        assert owner.next_state(CURRENT, raw, READ_ONLY) == "ignored"


def test_ac06_read_only_value_as_next_stays_refused_on_write_routes(monkeypatch):
    monkeypatch.setenv(READ_ENV, READ_ONLY)
    monkeypatch.setenv(NEXT_ENV, READ_ONLY)
    assert owner.classify(READ_ONLY, "mesh") == "mismatch"


def test_ac06_next_with_surrounding_whitespace_is_honoured_stripped(monkeypatch):
    monkeypatch.setenv(NEXT_ENV, f"  {NEXT}\n")
    assert owner.classify(NEXT, "mesh") == "next"
    assert owner.classify(f"  {NEXT}\n", "mesh") == "mismatch"


def test_ac06_current_with_trailing_newline_and_same_next_is_equals_current(monkeypatch):
    monkeypatch.setattr(config, "INTERNAL_WEBHOOK_SECRET", CURRENT + "\n")
    monkeypatch.setenv(NEXT_ENV, CURRENT)
    assert owner.classify(CURRENT, "mesh") == "current"
    assert owner.next_state(CURRENT, CURRENT, "") == "equals_current"
    assert _startup(monkeypatch, current=CURRENT + "\n", next_value=CURRENT) == [
        ("WARNING", owner.STARTUP_LINES["equals_current"])]


# ── AC-7: read-only stays read-only ──────────────────────────────────────────
@pytest.mark.parametrize("current,next_value,read_only,expected", [
    ("", "", "", 503), ("", NEXT, "", 503), ("", "", READ_ONLY, 401), (CURRENT, "", "", 401)],
    ids=["nothing", "next-only", "read-only-only", "current-only"])
def test_ac07_fleet_check_is_503_only_when_nothing_is_configured(current, next_value, read_only, expected, monkeypatch):
    from app.server import mesh_fleet_auth
    monkeypatch.setattr(config, "INTERNAL_WEBHOOK_SECRET", current)
    monkeypatch.setenv(NEXT_ENV, next_value)
    monkeypatch.setenv(READ_ENV, read_only)
    with pytest.raises(HTTPException) as exc:
        mesh_fleet_auth.check("fake-wrong-key")
    assert exc.value.status_code == expected


def test_ac07_read_only_key_is_refused_by_mesh_and_accepted_by_fleet_read(monkeypatch):
    from app.server.routes import mesh
    monkeypatch.setenv(READ_ENV, READ_ONLY)
    with pytest.raises(HTTPException) as exc:
        mesh._check_secret(READ_ONLY)
    assert exc.value.status_code == 401
    assert owner.classify_fleet_read(READ_ONLY) == "read_only"


# ── AC-8: accepted and rejected lines, exact, rate-limited, no key value ────
def _clock(monkeypatch, start=1000.0):
    now = [start]
    monkeypatch.setattr(owner, "_now", lambda: now[0])
    return now


def test_ac08_acceptance_under_next_logs_one_exact_line_without_keys(monkeypatch, lines):
    monkeypatch.setenv(NEXT_ENV, NEXT)
    assert owner.classify(NEXT, "margot") == "next"
    assert owner.classify(NEXT, "margot") == "next"
    assert lines() == ["internal_secret: accepted slot=next where=margot"]
    assert owner.classify(CURRENT, "margot") == "current"
    assert lines()[-1] == "internal_secret: accepted slot=current where=margot"
    assert not any(CURRENT in m or NEXT in m for m in lines())


def test_ac08_no_accepted_line_when_no_next_is_honoured(monkeypatch, lines):
    monkeypatch.setenv(NEXT_ENV, "too-short")
    assert owner.classify(CURRENT, "mesh") == "current"
    assert owner.classify_fleet_read(CURRENT) == "current"
    assert lines() == []


@pytest.mark.parametrize("next_value", [None, NEXT], ids=["next-unset", "next-set"])
def test_ac08_refusals_log_reason_and_label(next_value, monkeypatch, lines):
    if next_value:
        monkeypatch.setenv(NEXT_ENV, next_value)
    owner.classify("fake-wrong-key", "webhooks")
    owner.classify(None, "webhooks")
    owner.classify_fleet_read("")
    assert lines() == ["internal_secret: rejected reason=mismatch where=webhooks",
                       "internal_secret: rejected reason=missing where=webhooks",
                       "internal_secret: rejected reason=missing where=fleet_read"]


def test_ac08_each_line_is_limited_to_once_per_600_seconds(monkeypatch, lines):
    now = _clock(monkeypatch)
    monkeypatch.setenv(NEXT_ENV, NEXT)
    for presented in ("fake-wrong-key", NEXT):
        owner.classify(presented, "mesh")
    now[0] += 599
    for presented in ("fake-wrong-key", NEXT):
        owner.classify(presented, "mesh")
    assert len(lines()) == 2
    now[0] += 1
    for presented in ("fake-wrong-key", NEXT):
        owner.classify(presented, "mesh")
    assert len(lines()) == 4


def test_ac08_two_labels_give_two_lines(monkeypatch, lines):
    _clock(monkeypatch)
    monkeypatch.setenv(NEXT_ENV, NEXT)
    for where in ("mesh", "delegate"):
        owner.classify(NEXT, where)
        owner.classify("fake-wrong-key", where)
    assert sorted(lines()) == sorted(
        f"internal_secret: {kind} where={where}" for where in ("mesh", "delegate")
        for kind in ("accepted slot=next", "rejected reason=mismatch"))


@pytest.mark.parametrize("next_value,read_only", [("", ""), (NEXT, READ_ONLY)], ids=["slots-empty", "slots-set"])
def test_ac08_every_slot_compare_runs_on_a_current_key_request(next_value, read_only, monkeypatch):
    real, count = owner.hmac.compare_digest, [0]

    def spy(a, b):
        count[0] += 1
        return real(a, b)
    monkeypatch.setenv(NEXT_ENV, next_value)
    monkeypatch.setenv(READ_ENV, read_only)
    monkeypatch.setattr(owner.hmac, "compare_digest", spy)
    assert owner.classify(CURRENT, "mesh") == "current"
    assert owner.classify_fleet_read(CURRENT) == "current"
    assert count[0] == 6


# ── AC-9: start-up lines ─────────────────────────────────────────────────────
def _startup(monkeypatch, current=CURRENT, next_value=None, read_only=None, env_current=True):
    monkeypatch.setattr(config, "INTERNAL_WEBHOOK_SECRET", current)
    for name, value in ((NEXT_ENV, next_value), (READ_ENV, read_only), (CURRENT_ENV, current if env_current else None)):
        monkeypatch.setenv(name, value) if value is not None else monkeypatch.delenv(name, raising=False)
    records: list[logging.LogRecord] = []
    logger = logging.getLogger("test.ra8408.startup")
    handler = logging.Handler()
    handler.emit = records.append
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        owner.log_startup_state(logger)
    finally:
        logger.removeHandler(handler)
    messages = [(r.levelname, r.getMessage()) for r in records]
    assert not any(k in m for _, m in messages for k in (CURRENT, NEXT, READ_ONLY))
    return messages


def test_ac09_line1_current_empty_keeps_the_existing_warning(monkeypatch):
    assert _startup(monkeypatch, current="", next_value=NEXT) == [
        ("WARNING", "TAO_INTERNAL_WEBHOOK_SECRET not set — internal intake webhooks are disabled (503)")]


@pytest.mark.parametrize("next_value,expected", [
    (None, ("INFO", "internal_secret: next slot not set")),
    (NEXT, ("WARNING", "internal_secret: next slot ACTIVE: rotation in progress, finish the swap (docs/runbooks/fleet-key-rotation.md)")),
    (CURRENT, ("WARNING", "internal_secret: next slot equals current: swap applied, now remove TAO_INTERNAL_WEBHOOK_SECRET_NEXT")),
    ("too-short", ("WARNING", "internal_secret: TAO_INTERNAL_WEBHOOK_SECRET_NEXT is set but IGNORED (fails policy)"))],
    ids=["line2-unset", "line3-active", "line4-equals-current", "line5-ignored"])
def test_ac09_lines2to5_next_slot_state(next_value, expected, monkeypatch):
    assert _startup(monkeypatch, next_value=next_value) == [expected]


def test_ac09_line6_current_from_fallback(monkeypatch):
    assert _startup(monkeypatch, env_current=False) == [
        ("INFO", "internal_secret: next slot not set"),
        ("WARNING", "internal_secret: current key comes from the TAO_WEBHOOK_SECRET fallback")]


@pytest.mark.parametrize("next_value,read_only", [(None, CURRENT), (READ_ONLY, READ_ONLY)], ids=["equals-current", "equals-next"])
def test_ac09_line7_read_only_equals_a_write_key(next_value, read_only, monkeypatch):
    messages = _startup(monkeypatch, next_value=next_value, read_only=read_only)
    assert messages[-1] == ("WARNING", "internal_secret: read-only fleet key equals a write key")
    assert len(messages) == 2


# ── AC-10: values are read at call time ──────────────────────────────────────
def test_ac10_changes_after_import_change_the_next_decision(monkeypatch):
    assert owner.classify(NEXT, "mesh") == "mismatch"
    monkeypatch.setenv(NEXT_ENV, NEXT)
    assert owner.classify(NEXT, "mesh") == "next"
    monkeypatch.setattr(config, "INTERNAL_WEBHOOK_SECRET", "fake-other-current-key-ffffffffff")
    assert owner.classify(CURRENT, "mesh") == "mismatch"
    assert owner.classify_fleet_read(READ_ONLY) == "mismatch"
    monkeypatch.setenv(READ_ENV, READ_ONLY)
    assert owner.classify_fleet_read(READ_ONLY) == "read_only"
