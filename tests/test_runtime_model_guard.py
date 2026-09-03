from __future__ import annotations

import os

from scripts import runtime_model_guard as guard


def test_sanitise_environment_blocks_ollama_gemma_for_work_lanes() -> None:
    env = {
        "OLLAMA_BASE_URL": "http://old-local:11434",
        "TAO_CHEAP_MODEL": "ollama:gemma4:latest",
        "TAO_MODEL_MONITOR": "openrouter:google/gemma-4-26b-a4b-it",
        "TAO_MODEL_OTHER": "openrouter:anthropic/claude-sonnet-latest",
    }

    changed = guard.sanitise_environment(env)

    assert "OLLAMA_BASE_URL" not in env
    assert "TAO_CHEAP_MODEL" not in env
    assert "TAO_MODEL_MONITOR" not in env
    assert env["TAO_CHEAP_PROVIDER"] == "openrouter"
    assert env["TAO_CHEAP_REMOTE_MODEL"] == guard.SAFE_CHEAP_MODEL
    assert env["TAO_MODEL_OTHER"] == "openrouter:anthropic/claude-sonnet-latest"
    assert "TAO_MODEL_MONITOR" in changed


def test_sanitise_environment_leaves_margot_casual_to_ra7434() -> None:
    """RA-7434: margot.casual runs on a FREE ladder owned by provider_router.

    The guard used to inject TAO_MODEL_MARGOT_CASUAL=<Sonnet> on every Railway
    boot. provider_router now refuses any Anthropic model for that role, so the
    injection would fail every Telegram turn closed. The guard must neither pin
    that key nor strip a gemma value from it — the router polices it.
    """
    env = {"TAO_MODEL_MARGOT_CASUAL": "openrouter:google/gemma-4-26b-a4b-it:free"}
    changed = guard.sanitise_environment(env)
    assert env["TAO_MODEL_MARGOT_CASUAL"] == "openrouter:google/gemma-4-26b-a4b-it:free"
    assert "TAO_MODEL_MARGOT_CASUAL" not in changed

    env = {}
    changed = guard.sanitise_environment(env)
    assert "TAO_MODEL_MARGOT_CASUAL" not in env
    assert "TAO_MODEL_MARGOT_CASUAL" not in changed
    assert not hasattr(guard, "MARGOT_MODEL")


def _apply_sanitised_env(monkeypatch, env: dict[str, str]) -> None:
    for k in list(os.environ):
        if k.startswith(("TAO_", "OLLAMA_")):
            monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_guard_then_router_keeps_margot_ladder_step_1(monkeypatch) -> None:
    """Round-2 P1 (Codex): the guard is Railway's start command; if it deletes
    OLLAMA_BASE_URL, margot.casual's step 1 can never fire on Railway even when
    the founder configures it. After sanitise_environment a configured,
    reachable Ollama must still resolve margot.casual to ladder-step-1."""
    from app.server import provider_ollama, provider_router  # noqa: PLC0415

    env = {
        "OLLAMA_BASE_URL": "http://ollama.local:11434/v1",
        "MARGOT_OLLAMA_BASE_URL": "http://margot-ollama:11434/v1",
    }
    guard.sanitise_environment(env)
    assert "OLLAMA_BASE_URL" not in env, "the work-lane strip must stay"
    assert env["MARGOT_OLLAMA_BASE_URL"] == "http://margot-ollama:11434/v1"

    _apply_sanitised_env(monkeypatch, env)
    probes: list = []
    monkeypatch.setattr(provider_ollama, "is_reachable", lambda **kw: probes.append(kw) or True)

    pm = provider_router.select_provider_model("margot.casual")
    assert (pm.provider, pm.model_id, pm.source) == ("ollama", "gemma4:latest", "ladder-step-1")
    assert probes == [{"base_url": "http://margot-ollama:11434/v1"}]


def test_guard_then_router_still_keeps_work_lanes_off_ollama(monkeypatch) -> None:
    """Control for the test above: keeping OLLAMA_BASE_URL must not reopen a
    work lane to Ollama. The guard's TAO_CHEAP_PROVIDER=openrouter pin and its
    stripping of ollama: per-role specs are what hold that line."""
    from app.server import provider_ollama, provider_router  # noqa: PLC0415

    env = {
        "OLLAMA_BASE_URL": "http://ollama.local:11434/v1",
        "MARGOT_OLLAMA_BASE_URL": "http://margot-ollama:11434/v1",
        "TAO_MODEL_MONITOR": "ollama:qwen3.5:latest",
        "TAO_CHEAP_MODEL": "qwen3.5:latest",
    }
    guard.sanitise_environment(env)
    _apply_sanitised_env(monkeypatch, env)
    monkeypatch.setattr(provider_ollama, "is_reachable", lambda **kw: True)

    for role in ("monitor", "intent_classify", "guardian", "scribe.draft", "sprinkle.triage"):
        pm = provider_router.select_provider_model(role)
        assert pm.provider == "openrouter", (role, pm)
        assert pm.model_id == guard.SAFE_CHEAP_MODEL


def test_model_fabric_uses_serve_subcommand(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(guard, "_run_setup", lambda *args, **kwargs: True)
    monkeypatch.setattr(guard, "_wait_for_omniroute", lambda *args, **kwargs: True)

    launched: list[list[str]] = []

    class FakeProc:
        pid = 123

        def terminate(self) -> None:
            return None

    def fake_popen(args, **kwargs):  # noqa: ANN001
        launched.append(list(args))
        return FakeProc()

    monkeypatch.setattr(guard.subprocess, "Popen", fake_popen)

    proc = guard.start_model_fabric()

    assert proc is not None
    assert launched == [["omniroute", "serve", "--port", guard.OMNIROUTE_PORT, "--no-open"]]


def test_main_spawns_sidecar_before_exec(monkeypatch) -> None:
    events: list[str] = []
    monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
    monkeypatch.setattr(guard, "sanitise_environment", lambda env: [])
    monkeypatch.setattr(guard, "_spawn_model_fabric_bootstrap", lambda: events.append("bootstrap"))

    def fake_execvp(file, args):  # noqa: ANN001
        events.append("uvicorn")
        raise RuntimeError("stop test")

    monkeypatch.setattr(guard.os, "execvp", fake_execvp)

    try:
        guard.main()
    except RuntimeError as exc:
        assert str(exc) == "stop test"

    assert events == ["bootstrap", "uvicorn"]
