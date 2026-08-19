"""The Telegram intent path must never hold a live turn open.

`classify_llm` is layer 2 of the Telegram classifier: it fires on every message
the regex layer cannot place. It used to inherit the global OLLAMA_TIMEOUT_S
(120s), so a single slow local model made the bot look dead for two minutes per
message. These tests hold the short budget and the degrade path in place.
"""
from __future__ import annotations

from unittest.mock import patch

from swarm import config as cfg
from swarm import intent_router

BASE = {"intent": "unknown", "confidence": 0.0, "fields": {}}


def test_triage_budget_is_far_below_the_global_ollama_timeout():
    """A user-facing turn must not be able to wait the batch timeout."""
    assert cfg.OLLAMA_TRIAGE_TIMEOUT_S < cfg.OLLAMA_TIMEOUT_S
    assert cfg.OLLAMA_TRIAGE_TIMEOUT_S <= 30


def test_classify_llm_passes_the_short_budget_to_the_client():
    """The regression that caused the freeze: no timeout_s reached the client."""
    with patch("swarm.ollama_client.chat", return_value=None) as chat:
        intent_router.classify_llm("something unclassifiable", BASE)

    assert chat.call_args is not None, "the triage model was never called"
    assert chat.call_args.kwargs.get("timeout_s") == cfg.OLLAMA_TRIAGE_TIMEOUT_S


def test_classify_llm_degrades_to_base_when_the_model_times_out():
    """A timed-out local model returns None; the turn must still answer."""
    with patch("swarm.ollama_client.chat", return_value=None):
        assert intent_router.classify_llm("anything", BASE) == BASE


def test_classify_llm_degrades_to_base_when_the_client_raises():
    """Ollama down (connection refused) must not propagate into the turn."""
    with patch("swarm.ollama_client.chat", side_effect=OSError("connection refused")):
        assert intent_router.classify_llm("anything", BASE) == BASE


def test_classify_llm_degrades_to_base_on_unparseable_output():
    """A small local model emitting prose must not crash the classifier."""
    with patch("swarm.ollama_client.chat", return_value="I think you want a ticket!"):
        assert intent_router.classify_llm("anything", BASE) == BASE


def test_ollama_requests_keep_the_model_resident():
    """The cold start is removed, not budgeted around.

    Ollama unloads a model 5 minutes after its last request by default, so an
    assistant idle between messages pays a 20-40s reload on the next one — long
    enough that the 15s interactive budget above would fall back to regex on the
    first message every single time. keep_alive holds the model in memory so the
    short budget is the right budget rather than a self-inflicted degradation.
    """
    import json
    from unittest.mock import MagicMock

    from swarm import ollama_client

    captured: dict = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"message": {"content": "ok"}}).encode()

    def _fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data)
        captured["timeout"] = timeout
        return _Resp()

    with patch("swarm.ollama_client.urllib.request.urlopen", _fake_urlopen):
        ollama_client.chat(model="qwen3.5:latest", system="s", user_message="u",
                           timeout_s=15)

    assert captured["body"]["keep_alive"] == cfg.OLLAMA_KEEP_ALIVE
    assert captured["timeout"] == 15, "the per-call budget must reach the socket"
