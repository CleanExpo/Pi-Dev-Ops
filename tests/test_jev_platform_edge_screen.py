"""Round 23 P1-TEMPLATE-JSON-SCREEN-REMOVAL-DISCLOSURE and P1-CREDENTIAL-MARKDOWN-BOUNDARY-BYPASS.

\\b is Unicode-aware and counts "_" as a word character, so a key touching a CJK letter, or wrapped in
Markdown underscores, had no boundary in the decoded text and was sent. Edges are now "not an ASCII
letter or digit". Each case is refused by the template screen, client.send and the eval harness with
zero sends; ordinary words that merely contain a key prefix stay clean. Offline: fakes, no keys.
"""
from __future__ import annotations

import json

import pytest
from jev_scale_support import Recorder, budget

from evals.jev_constitution import harness as h
from jev_platform import ask, client

KEYS = ["AWS key: AKIAABCDEFGHIJKLMNOP已撤销", "已AKIAABCDEFGHIJKLMNOP", "_AKIAABCDEFGHIJKLMNOP_",
        "_sk-reviewfixtureabcdefgh_", "_ts-reviewfixtureabcdefgh_", "_ghp_reviewfixtureabcdefgh_",
        "已sk-reviewfixtureabcdefgh", "_xoxb-1234567890-abc_", "_sk_live_abcdefgh1_",
        "_eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.sig_"]
FOLDS = ["\u212a", "\u0130", "\u0131", "\u017f"]  # round 24: re.I alone treats these as ASCII letters
KEYS += [f"AWS key: AKIAABCDEFGHIJKLMNOP{c}" for c in FOLDS] + [f"{c}sk-reviewfixtureabcdefgh" for c in FOLDS]
ESCAPES = ["\\n", "\\t", "\\r", "\\u000a"]  # round 28: literal JSON escapes, as in a logged message
KEYS += [f"{{\"message\": \"{e}sk-reviewfixtureabcdefgh\"}}" for e in ESCAPES] + [f"{e}AKIAABCDEFGHIJKLMNOP" for e in ESCAPES]
LOG_ESCAPES = ["\\x1b", "\\v", "\\x00", "\\033", "\\a", "\\U0001F600", "\\N{BEL}"]  # round 29: repr/log escapes
KEYS += [f"{e}sk-reviewfixtureabcdefgh" for e in LOG_ESCAPES] + [f"{e}AKIAABCDEFGHIJKLMNOP" for e in LOG_ESCAPES]
KEYS += ["C:\\sk-reviewfixtureabcdefgh"]  # a lone backslash: blanking eats the s; decoding keeps it
_K = "sk-reviewfixtureabcdefgh"  # round 30: nested escaping and terminal colour codes
KEYS += [json.dumps(json.dumps({"m": "\n" + _K})), json.dumps(json.dumps(json.dumps({"m": "\t" + _K}))),
         json.dumps(repr("\x1b" + _K)), "\x1b[31m" + _K + "\x1b[0m", "\\x1b[31m" + _K, "\\033[1;31m" + _K,
         "\\u001b[0m" + _K, json.dumps("\x1b[31m" + _K)]
KEYS += ["\x9b31m" + _K, "\x1b[38:2:255:0:0m" + _K, "sk-re\x1b[31mviewfixtureabcdefgh",  # round 31
         "\\u0073k-reviewfixtureabcdefgh", "sk-review\\x66ixtureabcdefgh",
         json.dumps("\\u0073k-reviewfixtureabcdefgh"), "\\x41sk-reviewfixtureabcdefgh",
         "abc\x1b[31m" + _K, "\\" * 64 + "u0073k-reviewfixtureabcdefgh"]
_NAMED, _CONT = "\\N{LATIN SMALL LETTER S}k-reviewfixtureabcdefgh", "sk-re\\\nviewfixtureabcdefgh"  # round 32
KEYS += [_NAMED, "sk-review\\N{LATIN SMALL LETTER F}ixtureabcdefgh", json.dumps(_NAMED), json.dumps(json.dumps(_NAMED)),
         _CONT, "sk-re\\\r\nviewfixtureabcdefgh", json.dumps(_CONT), json.dumps(json.dumps(json.dumps(_CONT))),
         "AKIAABCD\\\nEFGHIJKLMNOP"]
KEYS += ["abc\\sk-reviewfixtureabcdefgh", "abc\\AKIAABCDEFGHIJKLMNOP",  # round 33: raw + every stage
         "abc\\u005c\\u0073k-reviewfixtureabcdefgh", "abc\\u005c\\u0041KIAABCDEFGHIJKLMNOP"]
KEYS += ["sk-re\\\rviewfixtureabcdefgh", "AKIAABCD\\\rEFGHIJKLMNOP", json.dumps("sk-re\\\rviewfixtureabcdefgh")]  # round 34
_R36 = ["abc\\\r\\u0073k-reviewfixtureabcdefgh", "abc\\\r\n\\u0073k-reviewfixtureabcdefgh",  # round 36: Python's
        "abc\\\r\\x41KIAABCDEFGHIJKLMNOP", "abc\\\r\n\\x41KIAABCDEFGHIJKLMNOP"]  # own unicode_escape reading
KEYS += _R36 + [json.dumps(t) for t in _R36] + [json.dumps(json.dumps(t)) for t in _R36]
_BAD = "\\x4 "  # Python's unicode_escape refuses the whole text, so only this module's decoder reads the rest
KEYS += [_BAD + "\\u0073k-reviewfixtureabcdefgh", _BAD + "\\N{LATIN SMALL LETTER S}k-reviewfixtureabcdefgh",
         _BAD + "sk-re\\\nviewfixtureabcdefgh", "abc\\ts-reviewfixtureabcdefgh"]  # last: only the raw text shows it
OTHER = ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6已", "_iicrc_", "已iicrc", "iicrc\u212a", "\u017fiicrc", "\\niicrc", "\\x1biicrc", "\\u0069icrc",
         "\\N{LATIN SMALL LETTER I}icrc", "ii\\\ncrc", "abc\\iicrc", "abc\\u005c\\u0069icrc", "ii\\\rcrc",
         "abc\\\r\\u0069icrc", "abc\\\r\n\\u0069icrc"]  # refused by ask.sensitive only
CLEAN = ["task-abcdefghij", "costs-abcdefghijk", "On 2026-09-29 the job ran.", "masks-and-gloves", "see array [1m] values",
         "C:\\Users\\data\\report.txt", "\\d+\\s*\\w+ matches", "\\N{NO SUCH NAME}sk"]


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
