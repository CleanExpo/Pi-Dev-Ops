"""Round 25 P1-JEV-RETRY-MUTABLE-BODY-DISCLOSURE: a retry sends the screened snapshot, not the caller's dict.

The fake transport changes the caller's body after the first request and answers 429, so the retry is
the moment a changed body could leave. Offline: fakes, no keys.
"""
from __future__ import annotations

import json

from jev_scale_support import budget

from jev_platform import ask, client, scout

SECRET = "sk-reviewfixtureabcdefgh"


def racing_post(original: dict):
    sent = []

    def post(body, timeout):
        sent.append(json.dumps(body))
        if len(sent) == 1:
            original["questions"]["q"]["criteria"]["true"] = SECRET  # a caller changes it mid-flight
            return 429, {}, 0.0
        return 200, {"answers": {}}, None
    return post, sent


def body() -> dict:
    return {"state": "plain", "model": "jev-latest",
            "questions": {"q": {"type": "noul", "instructions": "q", "criteria": {"true": "t", "false": "f"}}}}


def test_client_send_retries_the_screened_snapshot():
    original = body()
    post, sent = racing_post(original)
    client.send(original, post, budget(), sleep=lambda s: None)
    assert len(sent) == 2 and SECRET not in sent[1]


def test_scout_guarded_send_retries_the_screened_snapshot(monkeypatch):
    original = body()
    post, sent = racing_post(original)
    monkeypatch.setattr(client.time, "sleep", lambda s: None)
    scout.guarded_send(original, post, budget())
    assert len(sent) == 2 and SECRET not in sent[1]


def test_scout_sends_the_body_it_screened_not_a_later_change(monkeypatch):
    """A caller changing the body between scout's screen and client.send must not get an IICRC term out:
    client.send screens credentials only, so scout has to send its own screened snapshot."""
    original = body()
    real = ask.sensitive_payload

    def screen_then_race(obj):
        verdict = real(obj)
        original["questions"]["q"]["criteria"]["true"] = "per the IICRC S500 text"  # concurrent change
        return verdict
    monkeypatch.setattr(ask, "sensitive_payload", screen_then_race)
    sent = []
    scout.guarded_send(original, lambda b, t: sent.append(json.dumps(b)) or (200, {"answers": {}}, None), budget())
    assert len(sent) == 1 and "IICRC" not in sent[0]
