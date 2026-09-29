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


def locked(usd=0.10, **kw):
    """A budget whose run already locked gemini.MODEL, so the chain never advances."""
    b = budget(usd, **kw)
    b.lock_model(gemini.MODEL, dict(PRICE))
    return b


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
    b, fake = locked(1.0), FakeGemini([], counts=[(429, None)])
    outs = [gemini.call(BODY, KEY, b, fake, **NO_SLEEP) for _ in range(9)]
    assert b.count_calls == 24 and len(fake.calls) == 24 and outs[-1] == {"error": "count cap"}
    assert all(o["error"] == "countTokens http_429" for o in outs[:8])


def test_a_429_on_count_is_retried_within_the_cap():
    fake = FakeGemini([ftext("hi")], counts=[(429, None), (200, {"totalTokens": 100})])
    out = gemini.call(BODY, KEY, budget(), fake, **NO_SLEEP)
    assert "data" in out and fake.urls() == ["count", "count", "generate"]


@pytest.mark.parametrize("status", [429, 503])
def test_generate_retries_count_and_reserve_again_at_most_twice(status):
    b, fake = locked(), FakeGemini([(status, None)] * 3)
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


# ── model chain (founder 29/09/2026: a quota-limited model is never a blocker) ──────────────────

def _models(fake) -> list[str]:
    return [u.rsplit("/", 1)[1].split(":")[0] for u, _, _ in fake.calls]


@pytest.mark.parametrize("status", [404, 429, 503])
def test_an_unlocked_run_advances_past_a_refusing_model_and_locks_the_one_that_answers(status):
    tries = 3 if status in gemini.RETRY_STATUSES else 1
    b, fake = budget(), FakeGemini([(status, None)] * tries + [ftext("hi")])
    out = gemini.call(BODY, KEY, b, fake, **NO_SLEEP)
    assert "data" in out and b.model == gemini.CHAIN[1]
    assert _models(fake) == [gemini.CHAIN[0]] * 2 * tries + [gemini.CHAIN[1]] * 2
    assert b.price == gemini.PRICES[gemini.CHAIN[1]]


def test_a_quota_refusal_on_count_also_advances():
    fake = FakeGemini([ftext("hi")], counts=[(429, None)] * 3 + [(200, {"totalTokens": 100})])
    b = budget()
    assert "data" in gemini.call(BODY, KEY, b, fake, **NO_SLEEP) and b.model == gemini.CHAIN[1]


def test_every_body_names_the_model_its_url_names():
    fake = FakeGemini([(429, None)] * 3 + [ftext("hi")])
    gemini.call(BODY, KEY, budget(), fake, **NO_SLEEP)
    for url, payload, _ in fake.calls:
        body = json.loads(payload)
        body = body.get("generateContentRequest", body)
        assert url.rsplit("/", 1)[1].startswith(body["model"].removeprefix("models/") + ":")


def test_a_locked_run_never_switches_model_even_when_its_model_refuses():
    b, fake = budget(), FakeGemini([ftext("hi"), (429, None), (429, None), (429, None)])
    assert "data" in gemini.call(BODY, KEY, b, fake, **NO_SLEEP) and b.model == gemini.MODEL
    out = gemini.call(BODY, KEY, b, fake, **NO_SLEEP)
    assert out == {"error": "gemini http_429"} and set(_models(fake)) == {gemini.MODEL}


def test_a_non_quota_failure_does_not_advance():
    b, fake = budget(), FakeGemini([(500, None)])
    assert gemini.call(BODY, KEY, b, fake, **NO_SLEEP) == {"error": "gemini http_500"}
    assert set(_models(fake)) == {gemini.MODEL} and b.model is None


def test_every_model_refusing_ends_with_the_last_refusal_and_no_lock():
    fake = FakeGemini([(404, None)] * len(gemini.CHAIN))
    b = budget(1.0)
    assert gemini.call(BODY, KEY, b, fake, **NO_SLEEP) == {"error": "gemini http_404"}
    assert _models(fake) == [m for m in gemini.CHAIN for _ in range(2)] and b.model is None


def test_chain_is_fully_priced_and_the_first_model_is_the_dearest():
    on = dt.date(2026, 10, 1)
    rows = [gemini.price_table(on, m) for m in gemini.CHAIN]
    assert all(rows) and gemini.CHAIN[0] == gemini.MODEL
    assert all(r["in"] <= PRICE["in"] and r["out"] <= PRICE["out"] for r in rows)


def test_a_locked_run_whose_price_expires_sends_nothing_and_does_not_switch(monkeypatch):
    b, fake = budget(), FakeGemini([ftext("hi"), ftext("again")])
    assert "data" in gemini.call(BODY, KEY, b, fake, **NO_SLEEP) and b.model == gemini.MODEL
    sent = len(fake.calls)
    monkeypatch.setattr(gemini, "today", lambda: dt.date(2027, 1, 1))
    assert gemini.call(BODY, KEY, b, fake, **NO_SLEEP) == {"error": "price table expired"}
    assert len(fake.calls) == sent and b.model == gemini.MODEL


def test_an_unlocked_run_after_expiry_sends_nothing(monkeypatch):
    monkeypatch.setattr(gemini, "today", lambda: dt.date(2027, 1, 1))
    fake = FakeGemini([ftext("hi")])
    assert gemini.call(BODY, KEY, budget(), fake, **NO_SLEEP) == {"error": "no chain model has a current price"}
    assert fake.calls == []


# ── carried thinking: the pre-send input bound is countTokens + earlier thoughtsTokenCount ─────────

def _turn2(first_usage, usd=gemini.RUN_CAP_USD):
    """Turn 1 on a fresh budget with `first_usage`, then the body a second turn would send."""
    b = budget(usd)
    b.lock_model(gemini.MODEL, dict(PRICE))
    gemini.call(BODY, KEY, b, FakeGemini([ftext("step one", usage=first_usage)]), **NO_SLEEP)
    two = gemini.request_body(BODY["contents"] + [{"role": "model", "parts": [{"text": "step one"}]},
                                                  {"role": "user", "parts": [{"text": "go on"}]}])
    return b, two


def test_second_turn_reserves_for_the_thinking_carried_in_and_is_not_an_overrun():
    b, two = _turn2({"promptTokenCount": 100, "candidatesTokenCount": 10, "thoughtsTokenCount": 300})
    before = b.tokens["reserved_in"]
    fake = FakeGemini([ftext("done", usage={"promptTokenCount": 400, "candidatesTokenCount": 5})])
    out = gemini.call(two, KEY, b, fake, **NO_SLEEP)
    assert "data" in out and out["counted"] == 400
    ceiling = gemini.INPUT_TOKEN_LIMIT[gemini.MODEL]
    assert b.tokens["reserved_in"] - before == ceiling and b.tokens["carried"] == 300


def test_billed_prompt_above_count_plus_carried_thinking_is_still_an_overrun():
    b, two = _turn2({"promptTokenCount": 100, "candidatesTokenCount": 10, "thoughtsTokenCount": 300})
    fake = FakeGemini([ftext("done", usage={"promptTokenCount": 401, "candidatesTokenCount": 5})])
    assert gemini.call(two, KEY, b, fake, **NO_SLEEP)["error"] == "overrun"


def test_unreported_usage_leaves_the_next_turn_unboundable_and_nothing_is_sent():
    b, two = _turn2(None)
    fake = FakeGemini([ftext("done")])
    out = gemini.call(two, KEY, b, fake, **NO_SLEEP)
    assert out == {"error": "thinking tokens unreported: input cannot be bounded"} and fake.calls == []


def test_a_single_turn_body_carries_no_thinking_even_after_earlier_calls():
    b, _ = _turn2({"promptTokenCount": 100, "candidatesTokenCount": 10, "thoughtsTokenCount": 300})
    before = b.tokens["reserved_in"]
    out = gemini.call(BODY, KEY, b, FakeGemini([ftext("hi")]), **NO_SLEEP)
    assert "data" in out and b.tokens["reserved_in"] - before == 100 and b.tokens["carried"] == 0


# ── rev 6d: provider input ceiling for multi-turn, price check before every send, malformed thinking ──

def test_a_multi_turn_body_reserves_the_provider_input_ceiling_not_the_estimate():
    b, two = _turn2({"promptTokenCount": 100, "candidatesTokenCount": 10})
    spent = b.spent
    fake = FakeGemini([ftext("done", usage={"promptTokenCount": 100, "candidatesTokenCount": 5})])
    assert "data" in gemini.call(two, KEY, b, fake, **NO_SLEEP)
    ceiling = gemini.INPUT_TOKEN_LIMIT[gemini.MODEL] * PRICE["in"] + gemini.MAX_OUTPUT_TOKENS * PRICE["out"]
    assert ceiling < gemini.RUN_CAP_USD and b.spent - spent == pytest.approx(100 * PRICE["in"] + 5 * PRICE["out"])


def test_a_cap_that_cannot_hold_the_ceiling_sends_no_multi_turn_generate():
    b, two = _turn2({"promptTokenCount": 100, "candidatesTokenCount": 10}, usd=0.10)
    fake = FakeGemini([ftext("done")])
    assert gemini.call(two, KEY, b, fake, **NO_SLEEP) == {"error": "cap: reservation over the run cap"}
    assert fake.urls() == ["count"]


class _Clock:
    def __init__(self):
        self.day = dt.date(2026, 10, 1)

    def expire(self, *a, **k):
        self.day = dt.date(2027, 1, 1)


def test_expiry_during_the_count_call_sends_no_generate(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(gemini, "today", lambda: clock.day)
    inner = FakeGemini([ftext("hi")])

    def fake(url, payload, headers, timeout):
        out = inner(url, payload, headers, timeout)
        clock.expire()
        return out
    assert gemini.call(BODY, KEY, budget(), fake, **NO_SLEEP) == {"error": "price table expired"}
    assert inner.urls() == ["count"]


def test_expiry_during_a_retry_sleep_sends_nothing_more(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(gemini, "today", lambda: clock.day)
    fake = FakeGemini([(503, None), ftext("hi")])
    assert gemini.call(BODY, KEY, budget(), fake, sleep=clock.expire) == {"error": "price table expired"}
    assert fake.urls() == ["count", "generate"]


def test_expiry_before_advancing_sends_nothing_to_the_next_model(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(gemini, "today", lambda: clock.day)
    inner = FakeGemini([(404, None), ftext("hi")])

    def fake(url, payload, headers, timeout):
        out = inner(url, payload, headers, timeout)
        if url.endswith(":generateContent"):
            clock.expire()
        return out
    b = budget()
    assert gemini.call(BODY, KEY, b, fake, **NO_SLEEP) == {"error": "price table expired"}
    assert set(_models(inner)) == {gemini.MODEL} and b.model is None


@pytest.mark.parametrize("bad", [-1, "12", 1.5, True])
def test_malformed_thinking_keeps_the_full_reservation_on_a_single_turn(bad):
    b = budget()
    usage = {"promptTokenCount": 100, "candidatesTokenCount": 5, "thoughtsTokenCount": bad}
    gemini.call(BODY, KEY, b, FakeGemini([ftext("hi", usage=usage)]), **NO_SLEEP)
    assert b.spent == pytest.approx(reservation(100)) and b.thoughts_known is False


def test_malformed_thinking_refuses_the_next_multi_turn_call():
    b, two = _turn2({"promptTokenCount": 100, "candidatesTokenCount": 10, "thoughtsTokenCount": "x"})
    fake = FakeGemini([ftext("done")])
    assert gemini.call(two, KEY, b, fake, **NO_SLEEP) == {"error": "thinking tokens unreported: input cannot be bounded"}
    assert fake.calls == []


def test_run_cap_holds_every_ceiling_attempt_one_turn_may_make():
    ceiling = max(gemini.INPUT_TOKEN_LIMIT[m] * gemini.PRICES[m]["in"] + gemini.MAX_OUTPUT_TOKENS * gemini.PRICES[m]["out"]
                  for m in gemini.CHAIN)
    assert gemini.RUN_CAP_USD >= (1 + gemini.MAX_RETRIES) * ceiling


def test_a_failed_multi_turn_attempt_keeps_its_reservation_and_the_retry_still_fits():
    b, two = _turn2({"promptTokenCount": 100, "candidatesTokenCount": 10})
    fake = FakeGemini([(503, None), ftext("done", usage={"promptTokenCount": 100, "candidatesTokenCount": 5})])
    assert "data" in gemini.call(two, KEY, b, fake, **NO_SLEEP) and fake.urls() == ["count", "generate"] * 2
