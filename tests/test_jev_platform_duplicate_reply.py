"""Round 26 P1-JEV-DUPLICATE-ANSWER-ACCEPTED: a reply with a duplicate key is no signal, never a pass.

json.loads keeps the last of two equal keys, so "q": 0.01 then "q": 0.99 was read as 0.99, a pass. Each
live parser (CLI http_post, the eval harness, Gemini) now refuses duplicates. Offline: a fake opener.
"""
from __future__ import annotations

import io

import pytest
from jev_scale_support import budget

from evals.jev_constitution import harness as h
from jev_platform import __main__ as cli
from jev_platform import client, gemini

DUP_ANSWER = b'{"answers":{"q":{"type":"noul","noul":0.01},"q":{"type":"noul","noul":0.99}},"model":"jev-latest"}'
DUP_FIELD = b'{"answers":{"q":{"type":"noul","noul":0.01,"noul":0.99}},"model":"jev-latest"}'
DUP_TOP = b'{"answers":{"q":{"type":"noul","noul":0.01}},"answers":{"q":{"type":"noul","noul":0.99}}}'
CLEAN = b'{"answers":{"q":{"type":"noul","noul":0.99}},"model":"jev-latest"}'


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def serve(monkeypatch, raw: bytes):
    monkeypatch.setattr(client, "open_url", lambda req, timeout: _Resp(raw))
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-test-not-a-key")


RULE = {"id": "q", "question": "Does it comply?", "criteria_true": "yes", "criteria_false": "no"}


@pytest.mark.parametrize("raw", [DUP_ANSWER, DUP_FIELD, DUP_TOP])
def test_cli_transport_refuses_a_duplicate_reply(monkeypatch, raw):
    serve(monkeypatch, raw)
    out = client.ask("plain", [RULE], cli.http_post, budget())
    assert "nouls" not in out and out["error"].startswith("signal_unavailable")


@pytest.mark.parametrize("raw", [DUP_ANSWER, DUP_FIELD, DUP_TOP])
def test_harness_refuses_a_duplicate_reply(monkeypatch, raw):
    serve(monkeypatch, raw)
    status, noul, _ = h.ask_jev({"question": "q", "criteria_true": "t", "criteria_false": "f"}, "plain", "k")
    assert noul is None


def test_gemini_transport_refuses_a_duplicate_reply(monkeypatch):
    serve(monkeypatch, b'{"candidates":[],"candidates":[{"content":{}}]}')
    assert gemini.urllib_post("https://example.invalid", b"{}", {}, 5) == (0, None)


def test_a_clean_reply_still_scores(monkeypatch):
    serve(monkeypatch, CLEAN)
    assert client.ask("plain", [RULE], cli.http_post, budget())["nouls"] == {"q": 0.99}
    assert h.ask_jev({"question": "q", "criteria_true": "t", "criteria_false": "f"}, "plain", "k")[1] == 0.99
