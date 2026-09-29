"""Release review r4 P1: a lock that lands during count or between retries stops this model at once.

Split from test_jev_platform_gemini_chain.py to keep each file under 300 lines. No key, no network.
"""
from __future__ import annotations

import json
import threading

import pytest
from jev_scale_support import FakeGemini, ftext

from jev_platform import gemini

KEY = "gk-test-not-a-real-key"
BODY = gemini.request_body([{"role": "user", "parts": [{"text": "hello"}]}])
OTHER = gemini.CHAIN[1]


def _run(lock_on: str, first_generate):
    b = gemini.GeminiBudget(0.10, dict(gemini.PRICES[gemini.MODEL]))
    inner, sent = FakeGemini([first_generate, ftext("hi")]), []

    def fake(url, payload, headers, timeout):
        sent.append((url.rsplit("/", 1)[1].split(":")[0], url.rsplit(":", 1)[1]))
        if url.endswith(lock_on) and not b.model:
            b.lock_model(OTHER, gemini.PRICES[OTHER])  # another writer thread succeeds on another model
        return inner(url, payload, headers, timeout)
    return gemini.call(BODY, KEY, b, fake, sleep=lambda s: None), sent, b


def test_a_lock_between_retries_moves_the_call_to_the_locked_model():
    out, sent, b = _run(":generateContent", (503, None))
    assert "data" in out and b.model == OTHER
    assert [m for m, kind in sent if kind == "generateContent"] == [gemini.MODEL, OTHER]


def test_a_lock_during_count_sends_nothing_more_to_this_model():
    out, sent, b = _run(":countTokens", ftext("unused"))
    assert (gemini.MODEL, "generateContent") not in sent and b.model == OTHER


def test_while_no_model_is_locked_a_second_call_sends_nothing_until_the_first_settles():
    """Release review r5 P1: a writer paused between its checks and its send could still send to an old model."""
    b = gemini.GeminiBudget(0.10, dict(gemini.PRICES[gemini.MODEL]))
    inner, sends, b_sent, out = FakeGemini([ftext("a"), ftext("b")]), [], threading.Event(), {}

    def fake(url, payload, headers, timeout):
        sends.append((threading.current_thread().name, url.rsplit("/", 1)[1].split(":")[0]))
        if threading.current_thread().name == "B":
            b_sent.set()
        elif url.endswith(":generateContent") and "B" not in {t.name for t in threading.enumerate()}:
            second.start()
            assert not b_sent.wait(0.3), "call B sent while call A was still choosing the run's model"
        return inner(url, payload, headers, timeout)
    second = threading.Thread(name="B", target=lambda: out.update(b=gemini.call(BODY, KEY, b, fake)))
    assert "data" in gemini.call(BODY, KEY, b, fake, sleep=lambda s: None)
    second.join(5)
    assert "data" in out["b"] and {m for _, m in sends} == {gemini.MODEL} == {b.model}



@pytest.mark.parametrize("bound", [gemini.MAX_OUTPUT_TOKENS + 1, 8192, 0, -1, None, "2048"])
def test_a_body_asking_for_more_output_than_is_reserved_sends_nothing(bound):
    """Release review r6 P1: a caller-set maxOutputTokens above the priced 2,048 was sent under-reserved."""
    body = dict(BODY, generationConfig={**BODY["generationConfig"], "maxOutputTokens": bound})
    b, fake = gemini.GeminiBudget(0.10, dict(gemini.PRICES[gemini.MODEL])), FakeGemini([ftext("hi")])
    assert gemini.call(body, KEY, b, fake, sleep=lambda s: None)["error"].startswith("refused: maxOutputTokens")
    assert fake.calls == [] and b.spent == 0


def test_the_body_is_copied_before_its_checks_so_a_later_change_is_never_sent():
    """Release review r7 P1: the caller's body changed after the output-bound check reached Google."""
    body = gemini.request_body([{"role": "user", "parts": [{"text": "hello"}]}])
    inner = FakeGemini([ftext("hi")], counts=[(404, None), (200, {"totalTokens": 100})])

    def fake(url, payload, headers, timeout):
        body["generationConfig"]["maxOutputTokens"] = 8192  # the caller mutates its dict mid-call
        return inner(url, payload, headers, timeout)
    b = gemini.GeminiBudget(0.10, dict(gemini.PRICES[gemini.MODEL]))
    assert "data" in gemini.call(body, KEY, b, fake, sleep=lambda s: None)
    sent = [json.loads(p)["generationConfig"]["maxOutputTokens"] for u, p, _ in inner.calls if ":generate" in u]
    assert sent == [gemini.MAX_OUTPUT_TOKENS]
