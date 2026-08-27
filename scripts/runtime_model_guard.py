"""Runtime model guard for Pi-CEO production.

Prevents deprecated Ollama/Gemma model routes from re-entering the live
process through stale Railway environment variables. The guard runs before
Uvicorn and then replaces itself with the API server process.

Founder directive (2026-08-27): Ollama and Gemma are not permitted in the
Pi-CEO/Margot production runtime.
"""
from __future__ import annotations

import logging
import os
from collections.abc import MutableMapping

log = logging.getLogger("runtime_model_guard")

# Background cheap work can stay inexpensive, but must be remote and explicit.
SAFE_CHEAP_MODEL = "z-ai/glm-4.7-flash"
# Margot is the founder-facing chief-of-staff surface. Do not run her on a cheap
# model. OpenRouter's rolling Sonnet alias currently resolves to Sonnet 5.
MARGOT_MODEL = "openrouter:~anthropic/claude-sonnet-latest"

_OLLAMA_ENV_KEYS = {
    "OLLAMA_BASE_URL",
    "OLLAMA_TIMEOUT_S",
    "OLLAMA_TRIAGE_MODEL",
    "OLLAMA_TRIAGE_MODEL_HEAVY",
    "OLLAMA_TRIAGE_TIMEOUT_S",
    "OLLAMA_KEEP_ALIVE",
    "TAO_CHEAP_LOCAL_MODEL",
}


def _is_banned_model_spec(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return "gemma" in lowered or lowered.startswith("ollama:")


def sanitise_environment(environ: MutableMapping[str, str]) -> list[str]:
    """Remove deprecated local/Gemma routes and pin safe production models.

    Returns variable names only. Values are intentionally never returned or
    logged because environment variables may contain credentials.
    """
    changed: list[str] = []

    for key in _OLLAMA_ENV_KEYS:
        if key in environ:
            environ.pop(key, None)
            changed.append(key)

    # This legacy knob has higher precedence than the newer cheap-tier config.
    # Removing it prevents a stale local tag from silently winning again.
    if "TAO_CHEAP_MODEL" in environ:
        environ.pop("TAO_CHEAP_MODEL", None)
        changed.append("TAO_CHEAP_MODEL")

    # Remove explicit Ollama/Gemma role overrides. Margot is repinned below.
    for key, value in list(environ.items()):
        if key.startswith("TAO_MODEL_") and _is_banned_model_spec(value):
            environ.pop(key, None)
            changed.append(key)

    # Force provider routing away from local Ollama probing on every start.
    if environ.get("TAO_CHEAP_PROVIDER") != "openrouter":
        changed.append("TAO_CHEAP_PROVIDER")
    environ["TAO_CHEAP_PROVIDER"] = "openrouter"

    if environ.get("TAO_CHEAP_REMOTE_MODEL") != SAFE_CHEAP_MODEL:
        changed.append("TAO_CHEAP_REMOTE_MODEL")
    environ["TAO_CHEAP_REMOTE_MODEL"] = SAFE_CHEAP_MODEL

    if environ.get("TAO_MODEL_MARGOT_CASUAL") != MARGOT_MODEL:
        changed.append("TAO_MODEL_MARGOT_CASUAL")
    environ["TAO_MODEL_MARGOT_CASUAL"] = MARGOT_MODEL

    return sorted(set(changed))


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    changed = sanitise_environment(os.environ)
    if changed:
        log.warning(
            "production model guard normalised deprecated model configuration: %s",
            ", ".join(changed),
        )

    # Replace this bootstrap process so Railway signals and restarts still
    # target Uvicorn directly.
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "app.server.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            os.environ.get("PORT", "8080"),
            "--workers",
            "1",
        ],
    )


if __name__ == "__main__":
    main()
