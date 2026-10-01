"""Round 22: the eval harness sent case text to TypeSafe with no screen, unlike every other transport.

A case carrying key material is refused before anything is sent, a direct ask_jev call never posts it, and an
HTTP error body (which could echo the request) is never read back. Offline: fakes, no keys.
"""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from evals.jev_constitution import harness as h
from jev_platform import client

Q = {"id": "t-01", "question": "Does it comply?", "criteria_true": "yes", "criteria_false": "no",
     "quote_verbatim": True}
KEYS = ["key AKIAABCDEFGHIJKLMNOP here", "-----BEGIN RSA PRIVATE KEY-----", "token sk_live_abcdefgh123",
        "slack xoxb-1234567890-abc", "jwt eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.sig",
        "sk-reviewfixtureabcdefgh", "ts-reviewfixtureabcdefgh", "ghp_reviewfixtureabcdefgh"]


def test_the_screen_finds_keys_and_spares_dates():
    assert all(client.credential(k) for k in KEYS)
    assert not client.credential("On 2026-09-29 Dana approved it; the IICRC course ran at 02:00.")


def test_no_committed_case_carries_a_credential():
    cases = [json.loads(line) for f in sorted(h.CASES.glob("*.jsonl")) for line in f.read_text().splitlines()
             if line.strip()]
    assert len(cases) > 1000 and not [c for c in cases if client.credential(str(c.get("state", "")))]


@pytest.mark.parametrize("where", ["state", "question", "criteria_true", "criteria_false"])
@pytest.mark.parametrize("key", KEYS)
def test_ask_jev_never_posts_a_credential(where, key):
    sent = []
    q = {**Q, where: key} if where != "state" else Q
    status, noul, _ = h.ask_jev(q, key if where == "state" else "plain", "k",
                                post=lambda body, k: sent.append(body) or (200, {}))
    assert sent == [] and status == 0 and noul is None


def test_a_clean_case_is_still_sent():
    sent = []
    h.ask_jev(Q, "plain scenario on 2026-09-29", "k", post=lambda body, k: sent.append(body) or (200, {}))
    assert len(sent) == 1


def test_a_case_with_a_credential_refuses_the_question():
    cases = [{"state": f"s{i}", "label": i % 2 == 0, "class": "normal"} for i in range(4)]
    cases[2]["state"] = KEYS[0]
    assert "a case carries a credential; nothing is sent" in h.question_problems(Q, cases=cases)
    assert "a case carries a credential; nothing is sent" not in h.question_problems(Q, cases=cases[:2])


def test_an_error_body_is_never_read(monkeypatch):
    def refuse(req, timeout):
        raise urllib.error.HTTPError(h.API_URL, 400, "bad", {}, io.BytesIO(b"echo: AKIAABCDEFGHIJKLMNOP"))
    monkeypatch.setattr(client, "open_url", refuse)
    status, resp = h._post({"state": "x"}, "k")
    assert status == 400 and "AKIA" not in str(resp) and "echo" not in str(resp)
