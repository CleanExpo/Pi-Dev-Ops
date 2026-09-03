"""Runtime model guard and Mission Control Model Fabric bootstrap.

Prevents deprecated Ollama/Gemma routes from re-entering the live process.
Pi-CEO must become healthy immediately; OmniRoute setup/provider hydration is
started in a separate bootstrap process so Railway's healthcheck is never held
hostage by provider setup or a slow native dependency.
"""
from __future__ import annotations

import logging
import os
import secrets
import subprocess
import sys
import time
import urllib.request
from collections.abc import MutableMapping

log = logging.getLogger("runtime_model_guard")

SAFE_CHEAP_MODEL = "z-ai/glm-4.7-flash"
OMNIROUTE_PORT = "20128"

# RA-7434 (founder ruling 03/09/2026): margot.casual runs on a FREE ladder that
# app.server.provider_router owns and polices (it refuses Kimi and every
# Anthropic model itself). This guard used to inject a Sonnet pin for that key
# on every boot; with the router's refusal that would fail every Telegram turn
# closed. The key is left exactly as the environment supplies it.
_ROUTER_OWNED_KEYS = {"TAO_MODEL_MARGOT_CASUAL"}

# MARGOT_OLLAMA_BASE_URL is deliberately NOT in this set: it is read only by
# provider_router's margot.casual ladder (RA-7434, step 1) and by nothing else,
# so keeping it cannot reopen a work lane to Ollama. The global OLLAMA_BASE_URL
# still goes, because swarm/model_router, swarm/ollama_client and friends read it.
_OLLAMA_ENV_KEYS = {
    "OLLAMA_BASE_URL",
    "OLLAMA_TIMEOUT_S",
    "OLLAMA_TRIAGE_MODEL",
    "OLLAMA_TRIAGE_MODEL_HEAVY",
    "OLLAMA_TRIAGE_TIMEOUT_S",
    "OLLAMA_KEEP_ALIVE",
    "TAO_CHEAP_LOCAL_MODEL",
}


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_banned_model_spec(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return "gemma" in lowered or lowered.startswith("ollama:")


def sanitise_environment(environ: MutableMapping[str, str]) -> list[str]:
    """Remove deprecated local/Gemma routes and pin a safe direct fallback."""
    changed: list[str] = []

    for key in _OLLAMA_ENV_KEYS:
        if key in environ:
            environ.pop(key, None)
            changed.append(key)

    if "TAO_CHEAP_MODEL" in environ:
        environ.pop("TAO_CHEAP_MODEL", None)
        changed.append("TAO_CHEAP_MODEL")

    for key, value in list(environ.items()):
        if key in _ROUTER_OWNED_KEYS:
            continue
        if key.startswith("TAO_MODEL_") and _is_banned_model_spec(value):
            environ.pop(key, None)
            changed.append(key)

    if environ.get("TAO_CHEAP_PROVIDER") != "openrouter":
        changed.append("TAO_CHEAP_PROVIDER")
    environ["TAO_CHEAP_PROVIDER"] = "openrouter"

    if environ.get("TAO_CHEAP_REMOTE_MODEL") != SAFE_CHEAP_MODEL:
        changed.append("TAO_CHEAP_REMOTE_MODEL")
    environ["TAO_CHEAP_REMOTE_MODEL"] = SAFE_CHEAP_MODEL

    return sorted(set(changed))


def _omniroute_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("DATA_DIR", "/pi-ceo/.omniroute")
    env.setdefault("HOSTNAME", "127.0.0.1")
    env.setdefault("REQUIRE_API_KEY", "false")
    env.setdefault("JWT_SECRET", secrets.token_urlsafe(48))
    env.setdefault("API_KEY_SECRET", secrets.token_hex(32))
    env.setdefault("INITIAL_PASSWORD", secrets.token_urlsafe(24))
    env.setdefault("OMNIROUTE_WS_BRIDGE_SECRET", secrets.token_urlsafe(32))
    return env


def _run_setup(args: list[str], env: dict[str, str], label: str) -> bool:
    try:
        result = subprocess.run(
            args,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=90,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.warning("OmniRoute %s failed: %s", label, exc)
        return False
    if result.returncode != 0:
        tail = (result.stdout or "")[-500:].replace("\n", " ")
        log.warning("OmniRoute %s exited %d: %s", label, result.returncode, tail)
        return False
    log.info("OmniRoute %s complete", label)
    return True


def _hydrate_provider(provider: str, key_env: str, env: dict[str, str]) -> None:
    credential = (os.environ.get(key_env) or "").strip()
    if not credential:
        return
    provider_env = dict(env)
    provider_env["OMNIROUTE_API_KEY"] = credential
    _run_setup(
        [
            "omniroute",
            "setup",
            "--non-interactive",
            "--password",
            env["INITIAL_PASSWORD"],
            "--add-provider",
            "--provider",
            provider,
        ],
        provider_env,
        f"provider {provider}",
    )


def _wait_for_omniroute(timeout_s: float = 25.0) -> bool:
    deadline = time.monotonic() + timeout_s
    url = f"http://127.0.0.1:{OMNIROUTE_PORT}/api/health/ping"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as response:
                if response.status < 500:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False


def start_model_fabric() -> subprocess.Popen[str] | None:
    """Configure and start OmniRoute. Intended to run outside Pi-CEO startup."""
    if not _truthy(os.environ.get("OMNIROUTE_ENABLED")):
        log.info("Mission Control Model Fabric disabled (OMNIROUTE_ENABLED!=1)")
        return None

    env = _omniroute_env()
    os.makedirs(env["DATA_DIR"], exist_ok=True)

    _run_setup(
        [
            "omniroute",
            "setup",
            "--non-interactive",
            "--password",
            env["INITIAL_PASSWORD"],
        ],
        env,
        "base setup",
    )
    _hydrate_provider("openrouter", "OPENROUTER_API_KEY", env)
    _hydrate_provider("anthropic", "ANTHROPIC_API_KEY", env)
    _hydrate_provider("groq", "GROQ_API_KEY", env)

    try:
        proc = subprocess.Popen(
            ["omniroute", "serve", "--port", OMNIROUTE_PORT, "--no-open"],
            env=env,
            stdin=subprocess.DEVNULL,
            text=True,
        )
    except FileNotFoundError as exc:
        log.warning("OmniRoute binary unavailable: %s", exc)
        return None

    if _wait_for_omniroute():
        log.info(
            "Mission Control Model Fabric healthy on loopback:%s (pid=%s)",
            OMNIROUTE_PORT,
            proc.pid,
        )
        return proc

    log.warning(
        "Mission Control Model Fabric did not become healthy; "
        "Pi-CEO continues on direct high-trust provider fallback"
    )
    try:
        proc.terminate()
    except Exception:  # noqa: BLE001
        pass
    return None


def _spawn_model_fabric_bootstrap() -> subprocess.Popen[str] | None:
    """Start slow sidecar hydration without delaying Railway's /health route."""
    if not _truthy(os.environ.get("OMNIROUTE_ENABLED")):
        return None
    try:
        return subprocess.Popen(
            [sys.executable, "scripts/model_fabric_bootstrap.py"],
            env=dict(os.environ),
            stdin=subprocess.DEVNULL,
            text=True,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Mission Control Model Fabric bootstrap spawn failed: %s", exc)
        return None


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    changed = sanitise_environment(os.environ)
    if changed:
        log.warning(
            "production model guard normalised deprecated model configuration: %s",
            ", ".join(changed),
        )

    # Critical ordering: Railway checks /health with a 30s timeout. Never run
    # OmniRoute setup/provider hydration synchronously before Uvicorn starts.
    _spawn_model_fabric_bootstrap()

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
