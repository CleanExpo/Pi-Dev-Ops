"""Release review r8, fixed as a class: gemini.call sends only the body shape the reservation prices.

Every unpriced feature is refused before any request; every body the platform itself builds passes.
No key, no network.
"""
from __future__ import annotations

import pytest
from jev_scale_support import FakeGemini, ftext

from jev_platform import agent_tools, gemini

KEY = "gk-test-not-a-real-key"
USER = {"role": "user", "parts": [{"text": "hello"}]}
BODY = gemini.request_body([USER])
CFG = BODY["generationConfig"]

UNPRICED = {
    "grounding with Google Search": dict(BODY, tools=[{"googleSearch": {}}]),
    "code execution": dict(BODY, tools=[{"codeExecution": {}}]),
    "URL context": dict(BODY, tools=[{"urlContext": {}}]),
    "declarations smuggling a search tool": dict(BODY, tools=[{"functionDeclarations": [], "googleSearch": {}}]),
    "cached content": dict(BODY, cachedContent="cachedContents/abc"),
    "tool config": dict(BODY, toolConfig={"functionCallingConfig": {"mode": "ANY"}}),
    "safety settings": dict(BODY, safetySettings=[]),
    "several replies": dict(BODY, generationConfig={**CFG, "candidateCount": 8}),
    "one explicit reply": dict(BODY, generationConfig={**CFG, "candidateCount": 1}),
    "audio output": dict(BODY, generationConfig={**CFG, "responseModalities": ["AUDIO"]}),
    "a thinking budget": dict(BODY, generationConfig={**CFG, "thinkingConfig": {"thinkingBudget": 24576}}),
    "a higher thinking level": dict(BODY, generationConfig={**CFG, "thinkingConfig": {"thinkingLevel": "high"}}),
    "no thinking config": dict(BODY, generationConfig={"maxOutputTokens": 2048}),
    "a boolean output bound": dict(BODY, generationConfig={**CFG, "maxOutputTokens": True}),
    "a file reference": dict(BODY, contents=[{"role": "user", "parts": [{"fileData": {"fileUri": "gs://x/v.mp4"}}]}]),
    "inline media": dict(BODY, contents=[{"role": "user", "parts": [{"inlineData": {"data": "AA=="}}]}]),
    "a system-role turn": dict(BODY, contents=[{"role": "system", "parts": [{"text": "x"}]}]),
    "empty contents": dict(BODY, contents=[]),
    "a system instruction with a file": dict(BODY, systemInstruction={"parts": [{"fileData": {"fileUri": "x"}}]}),
    "a non-string model": dict(BODY, model=["models/a", "models/b"]),
}


@pytest.mark.parametrize("name", UNPRICED)
def test_an_unpriced_request_sends_nothing(name):
    b, fake = gemini.GeminiBudget(0.10, dict(gemini.PRICES[gemini.MODEL])), FakeGemini([ftext("hi")])
    assert gemini.call(UNPRICED[name], KEY, b, fake, sleep=lambda s: None)["error"].startswith("refused: ")
    assert fake.calls == [] and b.spent == 0


def test_every_body_the_platform_builds_is_sent():
    model_turn = {"role": "model", "parts": [{"text": "thinking", "thought": True, "thoughtSignature": "c2ln"},
                                             {"functionCall": {"name": "read_file", "args": {"path": "a.py"}}}]}
    reply = {"role": "user", "parts": [{"functionResponse": {"name": "read_file", "response": {"ok": True}}}]}
    bodies = [BODY, gemini.request_body([USER], "system text", agent_tools.DECLARATIONS)]
    for body in bodies:
        b, fake = gemini.GeminiBudget(0.10, dict(gemini.PRICES[gemini.MODEL])), FakeGemini([ftext("hi")])
        assert "data" in gemini.call(body, KEY, b, fake, sleep=lambda s: None)
    b = gemini.GeminiBudget(gemini.RUN_CAP_USD, dict(gemini.PRICES[gemini.MODEL]))  # multi-turn prices the input limit
    multi = gemini.request_body([USER, model_turn, reply], "system text", agent_tools.DECLARATIONS)
    assert "data" in gemini.call(multi, KEY, b, FakeGemini([ftext("hi")]), sleep=lambda s: None)
