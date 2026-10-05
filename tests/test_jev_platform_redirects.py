"""Round 16 P1-PROVIDER-REDIRECT-CREDENTIAL-DISCLOSURE: no live transport follows a redirect with its credential.

The fake HTTPS handler below sits under the real urllib opener, so the standard redirect handler runs: the provider
answers 302 to another origin, which answers 200. The positive control proves a default opener DOES carry the
credential there; each transport must stop at the 302 with one request sent. Offline: no socket is opened.
"""
from __future__ import annotations

import email.message
import io
import json
import urllib.parse
import urllib.request
import urllib.response

import pytest

from evals.jev_constitution import harness
from jev_platform import __main__ as cli
from jev_platform import gemini

ELSEWHERE = "https://unapproved.example/collect"


class FakeHTTPS(urllib.request.HTTPSHandler):
    seen: list = []

    def https_open(self, req):
        FakeHTTPS.seen.append((req.host, {k.lower(): v for k, v in req.header_items()}))
        away = req.host == "unapproved.example"
        headers = email.message.Message()
        headers["Content-Type"] = "application/json"
        if not away:
            headers["Location"] = ELSEWHERE
        resp = urllib.response.addinfourl(io.BytesIO(b'{"ok": true}' if away else b""), headers, req.full_url,
                                          200 if away else 302)
        resp.msg = "OK" if away else "Found"
        return resp


@pytest.fixture
def fake(monkeypatch):
    FakeHTTPS.seen = []
    monkeypatch.setattr(urllib.request, "HTTPSHandler", FakeHTTPS)
    monkeypatch.setattr(urllib.request, "_opener", None)  # urlopen's cached opener is rebuilt with the fake
    return FakeHTTPS.seen


def test_positive_control_a_default_opener_carries_the_credential_elsewhere(fake):
    req = urllib.request.Request("https://api.typesafe.ai/v1/systemone", data=b"{}", method="POST",
                                 headers={"Authorization": "Bearer ts-test-value-0000"})
    assert urllib.request.build_opener().open(req).status == 200
    assert [h for h, _ in fake] == ["api.typesafe.ai", "unapproved.example"]
    assert fake[1][1]["authorization"] == "Bearer ts-test-value-0000"


def test_typesafe_cli_transport_stops_at_the_redirect(fake, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-test-value-0000")
    assert cli.http_post({"q": 1}, 5)[0] == 302
    assert [h for h, _ in fake] == ["api.typesafe.ai"]


def test_gemini_transport_stops_at_the_redirect(fake):
    url = "https://generativelanguage.googleapis.com/v1beta/models/m:generateContent"
    assert gemini.urllib_post(url, json.dumps({}).encode(), {"x-goog-api-key": "g-test-value-0000"}, 5)[0] == 302
    assert [h for h, _ in fake] == ["generativelanguage.googleapis.com"]


def test_eval_harness_transport_stops_at_the_redirect(fake):
    assert harness._post({"q": 1}, "ts-test-value-0000", 5)[0] == 302
    assert [h for h, _ in fake] == [urllib.parse.urlparse(harness.API_URL).hostname]
