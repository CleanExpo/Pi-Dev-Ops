"""Round 23 P1-TEMPLATE-JSON-SCREEN-REMOVAL-DISCLOSURE and P1-CREDENTIAL-MARKDOWN-BOUNDARY-BYPASS.

\\b is Unicode-aware and counts "_" as a word character, so a key touching a CJK letter, or wrapped in
Markdown underscores, had no boundary in the decoded text and was sent. Edges are now "not an ASCII
letter or digit". Each case is refused by the template screen, client.send and the eval harness with
zero sends; ordinary words that merely contain a key prefix stay clean. Offline: fakes, no keys.
"""
from __future__ import annotations

import pytest
from jev_scale_support import Recorder, budget

from evals.jev_constitution import harness as h
from jev_platform import ask, client

KEYS = ["AWS key: AKIAABCDEFGHIJKLMNOP已撤销", "已AKIAABCDEFGHIJKLMNOP", "_AKIAABCDEFGHIJKLMNOP_",
        "_sk-reviewfixtureabcdefgh_", "_ts-reviewfixtureabcdefgh_", "_ghp_reviewfixtureabcdefgh_",
        "已sk-reviewfixtureabcdefgh", "_xoxb-1234567890-abc_", "_sk_live_abcdefgh1_",
        "_eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.sig_"]
OTHER = ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6已", "_iicrc_", "已iicrc"]  # refused by ask.sensitive only
CLEAN = ["task-abcdefghij", "costs-abcdefghijk", "On 2026-09-29 the job ran.", "masks-and-gloves"]


@pytest.mark.parametrize("text", KEYS)
def test_a_key_at_a_unicode_or_underscore_edge_is_a_credential(text):
    assert client.credential(text) and ask.sensitive(text)


@pytest.mark.parametrize("text", OTHER)
def test_hex_and_iicrc_at_those_edges_are_refused(text):
    assert ask.sensitive(text)


@pytest.mark.parametrize("text", CLEAN)
def test_words_that_contain_a_prefix_are_not_credentials(text):
    assert not client.credential(text)


@pytest.mark.parametrize("text", KEYS + OTHER)
def test_the_template_screen_refuses_it(text):
    manifest = {"questions": {"probe": {"type": "noul", "question": "Does it comply?", "true": text, "false": "no"}}}
    questions, err = ask.build_questions(manifest, ["probe"])
    assert questions is None and err == "template refused: probe"


@pytest.mark.parametrize("text", KEYS)
def test_client_send_and_the_harness_never_post_it(text):
    post = Recorder()
    rule = {"id": "probe-01", "question": "Does it comply?", "criteria_true": text, "criteria_false": "no"}
    assert client.ask("plain state", [rule], post, budget()) == {"error": "credential_in_request"}
    sent = []
    status, noul, _ = h.ask_jev({"question": "q", "criteria_true": "t", "criteria_false": "f"}, text, "k",
                                post=lambda body, k: sent.append(body) or (200, {}))
    assert post.calls == [] and sent == [] and noul is None
