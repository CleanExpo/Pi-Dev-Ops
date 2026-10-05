"""Round 22 P1-ENGINE-REGISTRY-CREDENTIAL-DISCLOSURE: client.send refuses any body carrying key material.

client.ask (engine.decide, calibration) redacted only the state, so a key in committed registry text (question,
either criterion, rule id) was sent. client.send is the one transport under ask, ask_files and scout, so the
decoded credential screen sits there. Offline: a recording fake, no keys, no network.
"""
from __future__ import annotations

import pytest
from jev_scale_support import Recorder, budget

from jev_platform import client

KEYS = ["sk-reviewfixtureabcdefgh", "ts-reviewfixtureabcdefgh", "ghp_reviewfixtureabcdefgh",
        "AKIAABCDEFGHIJKLMNOP", "-----BEGIN PRIVATE KEY-----", "xoxb-1234567890-abc", "sk_live_abcdefgh1"]
RULE = {"id": "probe-01", "question": "Does it comply?", "criteria_true": "yes", "criteria_false": "no"}


@pytest.mark.parametrize("field", ["question", "criteria_true", "criteria_false", "id"])
@pytest.mark.parametrize("key", KEYS)
def test_a_key_in_registry_text_is_never_sent(field, key):
    post = Recorder()
    out = client.ask("plain state", [{**RULE, field: f"before\n{key}"}], post, budget())
    assert post.calls == [] and out == {"error": "credential_in_request"}


def test_a_clean_registry_is_sent():
    post = Recorder()
    out = client.ask("On 2026-09-29 the job ran.", [RULE], post, budget())
    assert len(post.calls) == 1 and out["nouls"] == {"probe-01": 0.9}


@pytest.mark.parametrize("body", [{"k": ["x", ("y", KEYS[0])]}, {KEYS[1]: "v"}, {"a": {"b": KEYS[2]}}])
def test_send_screens_keys_values_lists_and_tuples(body):
    post = Recorder()
    assert client.send(body, post, budget()) == {"error": "credential_in_request"} and post.calls == []
