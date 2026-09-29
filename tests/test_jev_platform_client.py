"""Offline controls for jev_platform.client (PLAN.md rev 5): budget, deadline, validation, redaction."""
from __future__ import annotations

import pytest

from jev_platform import client as cl

RULES = [{"id": r, "question": "q?", "criteria_true": "t", "criteria_false": "f"} for r in ("a", "b")]


def ok(nouls, model="jev-1.13.0", tokens=400):
    return 200, {"model": model, "answers": {k: {"type": "noul", "noul": v} for k, v in nouls.items()},
                 "usage": {"input_tokens": tokens}}, None


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def budget(usd=1.0, seconds=100.0, clock=None):
    return cl.Budget(usd, seconds, clock or Clock())


def test_valid_answer_returns_nouls_and_model():
    r = cl.ask("s", RULES, lambda b, t: ok({"a": 0.9, "b": 0.1}), budget())
    assert r == {"nouls": {"a": 0.9, "b": 0.1}, "model": "jev-1.13.0"}


@pytest.mark.parametrize("answers", [
    {"a": {"type": "noul", "noul": 0.9}},                                    # missing b
    {"a": {"type": "noul", "noul": 0.9}, "b": {"type": "noul", "noul": float("nan")}},
    {"a": {"type": "noul", "noul": 0.9}, "b": {"type": "noul", "noul": 1.2}},
    {"a": {"type": "noul", "noul": 0.9}, "b": {"type": "score", "score": 1}},
    {"a": {"type": "noul", "noul": 0.9}, "b": {"type": "noul", "noul": 0.2}, "c": {"type": "noul", "noul": 1}},
])
def test_invalid_responses_are_signal_unavailable(answers):
    r = cl.ask("s", RULES, lambda b, t: (200, {"answers": answers}, None), budget())
    assert r == {"error": "signal_unavailable:invalid_response"}


@pytest.mark.parametrize("status", [401, 500, 503])
def test_http_errors_fail_closed(status):
    assert cl.ask("s", RULES, lambda b, t: (status, None, None), budget())["error"] == f"signal_unavailable:http_{status}"


def test_transport_exception_fails_closed():
    def boom(b, t):
        raise TimeoutError
    assert cl.ask("s", RULES, boom, budget()) == {"error": "signal_unavailable:transport"}


def test_429_retries_then_gives_up_and_keeps_reservations():
    calls, slept = [], []
    b = budget()
    r = cl.ask("s", RULES, lambda body, t: calls.append(1) or (429, None, 1.0), b, sleep=slept.append)
    assert r["error"] == "signal_unavailable:http_429" and len(calls) == 3 and slept == [1.0, 1.0]
    assert b.spent == pytest.approx(3 * cl.RESERVE_USD)


def test_retry_after_beyond_deadline_means_zero_retries():
    calls = []
    r = cl.ask("s", RULES, lambda body, t: calls.append(1) or (429, None, 500.0), budget(seconds=10), sleep=lambda s: None)
    assert r["error"] == "signal_unavailable:http_429" and len(calls) == 1


def test_budget_breach_sends_nothing():
    calls = []
    r = cl.ask("s", RULES, lambda body, t: calls.append(1) or ok({"a": 1, "b": 1}), budget(usd=cl.RESERVE_USD / 2))
    assert r == {"error": "budget_exhausted"} and calls == []


def test_cap_stops_exactly_at_the_breaching_attempt():
    b = budget(usd=cl.RESERVE_USD * 2)
    calls = []
    cl.ask("s", RULES, lambda body, t: calls.append(1) or (429, None, 0.0), b, sleep=lambda s: None)
    assert len(calls) == 2 and b.spent <= b.max_usd + 1e-12


def test_settle_only_on_reported_usage():
    b = budget()
    cl.ask("s", RULES, lambda body, t: ok({"a": 1, "b": 1}, tokens=1000), b)
    assert b.spent == pytest.approx(1000 * cl.USD_PER_TOKEN)
    b2 = budget()
    cl.ask("s", RULES, lambda body, t: (200, {"answers": {"a": {"type": "noul", "noul": 1}, "b": {"type": "noul", "noul": 1}}}, None), b2)
    assert b2.spent == pytest.approx(cl.RESERVE_USD)


def test_timeout_passed_to_post_respects_deadline():
    clock, seen = Clock(), []
    b = budget(seconds=12, clock=clock)
    clock.t = 5
    cl.ask("s", RULES, lambda body, t: seen.append(t) or ok({"a": 1, "b": 1}), b)
    assert seen == [7]


def test_expired_deadline_sends_nothing():
    clock, calls = Clock(), []
    b = budget(seconds=1, clock=clock)
    clock.t = 2
    assert cl.ask("s", RULES, lambda body, t: calls.append(1), b) == {"error": "budget_exhausted"} and calls == []


def test_oversized_request_is_refused_before_sending():
    calls = []
    r = cl.ask("x" * 70_000, RULES, lambda body, t: calls.append(1), budget())
    assert r == {"error": "request_too_large"} and calls == []


@pytest.mark.parametrize("text", [
    "email jo.smith+x@example.com.au", "call +61 412 345 678", "acct 123456789012",
    "key sk-abcdefgh12345", "key ts-abcdefgh12345", "tok ghp_abcdefgh12345",
    "hash " + "a" * 32, "see https://x.io/p?id=5",
])
def test_redaction_patterns(text):
    out, changed = cl.redact(text)
    assert changed and "[redacted]" in out


def test_redaction_leaves_plain_text_alone():
    assert cl.redact("Agent merged PR 412 after 14 checks passed.") == ("Agent merged PR 412 after 14 checks passed.", False)


def test_attempt_cap_is_fixed_and_settlement_does_not_relax_it():
    b = budget(usd=0.50)
    assert b.max_attempts == 186
    for _ in range(186):
        cl.ask("s", RULES, lambda body, t: ok({"a": 1, "b": 1}, tokens=10), b)
    assert b.attempts == 186 and b.spent < 0.01
    assert cl.ask("s", RULES, lambda body, t: ok({"a": 1, "b": 1}), b) == {"error": "budget_exhausted"}
