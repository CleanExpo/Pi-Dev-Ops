"""Release review r4 P1: a lock that lands during count or between retries stops this model at once.

Split from test_jev_platform_gemini_chain.py to keep each file under 300 lines. No key, no network.
"""
from __future__ import annotations

import threading

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
