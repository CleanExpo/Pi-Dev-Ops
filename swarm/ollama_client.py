"""
swarm/ollama_client.py — Thin async wrapper around Ollama's local REST API.

Uses stdlib urllib only — no extra dependencies.  All calls include a
timeout; never hangs indefinitely.  Returns None on any error so callers
can degrade gracefully without crashing the swarm.
"""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any

from . import config

log = logging.getLogger("swarm.ollama")


def chat(
    model: str,
    system: str,
    user_message: str,
    temperature: float = 0.3,
    json_format: bool = False,
) -> str | None:
    """Send a single chat turn to a local Ollama model.

    Args:
        model:        Ollama model tag (e.g. 'qwen3.5:latest').
        system:       System prompt defining the bot's role.
        user_message: The user/task message.
        temperature:  Sampling temperature (lower = more deterministic).
        json_format:  If True, instructs Ollama to return valid JSON output.

    Returns:
        The model's response text, or None on any error.
    """
    body: dict = {
        "model": model,
        "messages": [
            {"role": "system",  "content": system},
            {"role": "user",    "content": user_message},
        ],
        "stream": False,
        "options": {"temperature": temperature},
    }
    if json_format:
        body["format"] = "json"
    payload = json.dumps(body).encode()

    req = urllib.request.Request(
        f"{config.OLLAMA_BASE_URL}/api/chat",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=config.OLLAMA_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            return data.get("message", {}).get("content", "").strip()
    except Exception as exc:
        log.warning("Ollama chat failed (model=%s): %s", model, exc)
        return None


def health_check(model: str) -> bool:
    """Verify Ollama is running and the given model can load and respond.

    Returns:
        True if the model responds, False otherwise.
    """
    response = chat(
        model=model,
        system="You are a health check responder.",
        user_message="Reply with exactly the text: SWARM_HEALTH_OK",
        temperature=0.0,
    )
    if response and "SWARM_HEALTH_OK" in response:
        log.info("Health check PASS: %s", model)
        return True
    log.warning("Health check FAIL: %s — response: %s", model, response)
    return False


def list_models() -> list[str]:
    """Return list of model tags currently available in this Ollama instance.

    Returns:
        List of model tag strings, or empty list on error.
    """
    req = urllib.request.Request(
        f"{config.OLLAMA_BASE_URL}/api/tags",
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return [m["name"] for m in data.get("models", [])]
    except Exception as exc:
        log.warning("Ollama list_models failed: %s", exc)
        return []
