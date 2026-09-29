"""Offline controls for the Gemini transport and GeminiBudget (jev_platform.gemini, PLAN-scale.md rev 5).

A fake `http_post` stands in for Google. No key, no network.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest
from jev_scale_support import FakeGemini, ftext

from jev_platform import gemini

KEY = "gk-test-not-a-real-key"
PRICE = gemini.PRICES[gemini.MODEL]
BODY = gemini.request_body([{"role": "user", "parts": [{"text": "hello"}]}])
NO_SLEEP = {"sleep": lambda s: None}


def budget(usd=0.10, price=None, **kw):
    return gemini.GeminiBudget(usd, price or dict(PRICE), **kw)


def reservation(counted):
    return counted * PRICE["in"] + gemini.MAX_OUTPUT_TOKENS * PRICE["out"]


def test_count_body_wraps_the_generate_body_byte_for_byte_and_key_is_header_only():
    fake = FakeGemini([ftext("hi")])
    assert "data" in gemini.call(BODY, KEY, budget(), fake, **NO_SLEEP)
    (count_url, count_payload, count_headers), (gen_url, gen_payload, _) = fake.calls
    assert fake.urls() == ["count", "generate"] and count_payload == b'{"generateContentRequest": ' + gen_payload + b"}"
    assert json.loads(count_payload)["generateContentRequest"] == json.loads(gen_payload) == BODY
    assert count_headers["x-goog-api-key"] == KEY and KEY.encode() not in count_payload + gen_payload


def test_body_pins_model_output_cap_and_low_thinking():
    cfg = BODY["generationConfig"]
    assert BODY["model"] == "models/gemini-3.8-flash" and gemini.GENERATE_URL.endswith("gemini-3.8-flash:generateContent")
    assert cfg == {"maxOutputTokens": 2048, "thinkingConfig": {"thinkingLevel": "low"}}


@pytest.mark.parametrize("count", [(500, None), (200, {"nope": 1}), (200, {"totalTokens": -1})])
def test_count_failure_sends_no_generate_and_reserves_nothing(count):
    fake, b = FakeGemini([ftext("hi")], counts=[count]), budget()
    out = gemini.call(BODY, KEY, b, fake, **NO_SLEEP)
    assert "countTokens" in out["error"] and fake.urls() == ["count"] and b.spent == 0.0 and b.attempts == 0


def test_reservation_is_counted_tokens_times_in_plus_2048_times_out():
    fake, b = FakeGemini([ftext("hi", usage=None)], counts=[(200, {"totalTokens": 5000})]), budget()
    gemini.call(BODY, KEY, b, fake, **NO_SLEEP)
    assert b.spent == pytest.approx(reservation(5000)) and b.tokens["counted"] == 5000


def test_missing_usage_keeps_the_full_reservation_and_reported_usage_settles_down():
    kept, settled = budget(), budget()
    gemini.call(BODY, KEY, kept, FakeGemini([ftext("hi", usage=None)]), **NO_SLEEP)
    gemini.call(BODY, KEY, settled, FakeGemini([ftext("hi")]), **NO_SLEEP)
    assert kept.spent == pytest.approx(reservation(100))
    assert settled.spent == pytest.approx(100 * PRICE["in"] + 30 * PRICE["out"])


def test_reported_prompt_above_counted_is_an_overrun_keeping_the_larger_figure():
    usage = {"promptTokenCount": 9000, "candidatesTokenCount": 10}
    b = budget()
    out = gemini.call(BODY, KEY, b, FakeGemini([ftext("hi", usage=usage)]), **NO_SLEEP)
    assert out["error"] == "overrun" and "data" not in out
    assert b.spent == pytest.approx(max(reservation(100), 9000 * PRICE["in"] + 10 * PRICE["out"]))


def test_reservation_over_the_cap_sends_no_generate():
    fake = FakeGemini([ftext("hi")])
    out = gemini.call(BODY, KEY, budget(0.005), fake, **NO_SLEEP)
    assert out["error"].startswith("cap") and "generate" not in fake.urls()


def test_nonzero_count_price_is_reserved_before_each_count_call():
    price = {**PRICE, "count": 1e-6}
    b, fake = budget(price=price), FakeGemini([ftext("hi", usage=None)])
    gemini.call(BODY, KEY, b, fake, **NO_SLEEP)
    nbytes = len(json.dumps(BODY).encode())
    assert b.count_usd == pytest.approx(nbytes * 1e-6) and b.spent == pytest.approx(nbytes * 1e-6 + reservation(100))


def test_cap_too_small_for_the_count_reservation_makes_no_call_at_all():
    fake = FakeGemini([ftext("hi")])
    out = gemini.call(BODY, KEY, budget(0.0001, price={**PRICE, "count": 1.0}), fake, **NO_SLEEP)
    assert out["error"].startswith("cap") and fake.calls == []


def test_the_25th_count_call_is_refused_retries_included():
    b, fake = budget(1.0), FakeGemini([], counts=[(429, None)])
    outs = [gemini.call(BODY, KEY, b, fake, **NO_SLEEP) for _ in range(9)]
    assert b.count_calls == 24 and len(fake.calls) == 24 and outs[-1] == {"error": "count cap"}
    assert all(o["error"] == "countTokens http_429" for o in outs[:8])


def test_a_429_on_count_is_retried_within_the_cap():
    fake = FakeGemini([ftext("hi")], counts=[(429, None), (200, {"totalTokens": 100})])
    out = gemini.call(BODY, KEY, budget(), fake, **NO_SLEEP)
    assert "data" in out and fake.urls() == ["count", "count", "generate"]


@pytest.mark.parametrize("status", [429, 503])
def test_generate_retries_count_and_reserve_again_at_most_twice(status):
    b, fake = budget(), FakeGemini([(status, None)] * 3)
    out = gemini.call(BODY, KEY, b, fake, **NO_SLEEP)
    assert out["error"] == f"gemini http_{status}" and fake.urls() == ["count", "generate"] * 3
    assert b.attempts == 3 and b.spent == pytest.approx(3 * reservation(100))


def test_a_500_is_not_retried_and_keeps_the_reservation():
    b, fake = budget(), FakeGemini([(500, None)])
    assert gemini.call(BODY, KEY, b, fake, **NO_SLEEP) == {"error": "gemini http_500"}
    assert b.spent == pytest.approx(reservation(100)) and len(fake.calls) == 2


def test_transport_exception_is_a_failure_not_a_crash():
    def boom(*a):
        raise TimeoutError("slow")
    assert gemini.call(BODY, KEY, budget(), boom, **NO_SLEEP) == {"error": "countTokens transport failure"}


def test_sensitive_payload_is_refused_before_any_request():
    fake = FakeGemini([ftext("hi")])
    body = gemini.request_body([{"role": "user", "parts": [{"text": "key AKIAABCDEFGHIJKLMNOP"}]}])
    assert gemini.call(body, KEY, budget(), fake, **NO_SLEEP) == {"error": "refused: sensitive payload"}
    assert fake.calls == []


@pytest.mark.parametrize("on, ok", [(dt.date(2026, 12, 31), True), (dt.date(2027, 1, 1), False)])
def test_price_table_expires(on, ok):
    assert (gemini.price_table(on) is not None) is ok
    assert gemini.price_table(on, "gemini-flash-latest") is None


def test_attempt_cap_is_fixed_at_start():
    b = budget(0.10)
    assert b.max_attempts == int(0.10 // (2048 * PRICE["out"])) == 13
