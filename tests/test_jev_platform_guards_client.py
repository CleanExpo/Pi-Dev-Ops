"""Guard sweep 29/09: every client.py guard has a test that fails when the guard is removed. Offline only."""
from __future__ import annotations

import pytest

from jev_platform import client as cl


def reserved_then_settled(usage) -> float:
    b = cl.Budget(1.0, 100.0, clock=lambda: 0.0)
    assert b.reserve()
    b.settle({"usage": usage})
    return b.spent


@pytest.mark.parametrize("tokens", [-1, cl.RESERVE_TOKENS + 1, True])
def test_settle_ignores_negative_oversized_or_boolean_usage(tokens):
    """guard sweep 29/09: only an int in [0, RESERVE_TOKENS] settles down; anything else keeps the reservation."""
    assert reserved_then_settled({"input_tokens": tokens}) == cl.RESERVE_USD


def test_settle_on_real_usage_moves_spend_so_the_control_can_fail():
    """guard sweep 29/09: positive control for the test above."""
    assert reserved_then_settled({"input_tokens": 0}) == 0.0


@pytest.mark.parametrize("data", [
    {"answers": ["a"]},                                       # answers as a list, not an object
    {"answers": {"a": {"type": "choice", "noul": 0.5}}},     # a noul value under the wrong type
])
def test_validate_refuses_wrong_shapes(data):
    """guard sweep 29/09: validate returns None rather than raising or passing."""
    assert cl.validate(data, ["a"]) is None


def test_validate_accepts_the_same_shape_when_well_formed():
    """guard sweep 29/09: positive control."""
    assert cl.validate({"answers": {"a": {"type": "noul", "noul": 0.5}}}, ["a"]) == {"a": 0.5}


class Scripted:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    def __call__(self, body, timeout):
        self.calls += 1
        return self.replies.pop(0)


def test_only_429_is_retried_even_when_a_503_names_a_retry_after():
    """guard sweep 29/09: a 503 with Retry-After fails closed after ONE call."""
    post, slept = Scripted((503, None, 1), (200, {"answers": {}}, None)), []
    out = cl.send({"q": 1}, post, cl.Budget(1.0, 100.0, clock=lambda: 0.0), sleep=slept.append)
    assert out == {"error": "signal_unavailable:http_503"} and post.calls == 1 and slept == []


def test_429_without_retry_after_fails_closed_without_raising():
    """guard sweep 29/09: no Retry-After means no wait and no retry."""
    post, slept = Scripted((429, None, None), (200, {"answers": {}}, None)), []
    out = cl.send({"q": 1}, post, cl.Budget(1.0, 100.0, clock=lambda: 0.0), sleep=slept.append)
    assert out == {"error": "signal_unavailable:http_429"} and post.calls == 1 and slept == []
