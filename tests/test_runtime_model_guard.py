from __future__ import annotations

from scripts import runtime_model_guard as guard


def test_sanitise_environment_blocks_ollama_gemma_and_pins_margot() -> None:
    env = {
        "OLLAMA_BASE_URL": "http://old-local:11434",
        "TAO_CHEAP_MODEL": "ollama:gemma4:latest",
        "TAO_MODEL_MARGOT_CASUAL": "openrouter:google/gemma-4-26b-a4b-it",
        "TAO_MODEL_OTHER": "openrouter:anthropic/claude-sonnet-latest",
    }

    changed = guard.sanitise_environment(env)

    assert "OLLAMA_BASE_URL" not in env
    assert "TAO_CHEAP_MODEL" not in env
    assert env["TAO_CHEAP_PROVIDER"] == "openrouter"
    assert env["TAO_CHEAP_REMOTE_MODEL"] == guard.SAFE_CHEAP_MODEL
    assert env["TAO_MODEL_MARGOT_CASUAL"] == guard.MARGOT_MODEL
    assert env["TAO_MODEL_OTHER"] == "openrouter:anthropic/claude-sonnet-latest"
    assert "TAO_MODEL_MARGOT_CASUAL" in changed


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
