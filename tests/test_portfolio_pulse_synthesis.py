"""tests/test_portfolio_pulse_synthesis.py — RA-1892.

Coverage:
  * synthesize() calls provider_router.run_via_provider with role
    "portfolio.synthesis"
  * Output is capped at 400 words
  * LLM error → deterministic fallback "(synthesis unavailable: ...)"
  * BOARD-TRIGGER sentinel parses cleanly when emitted (parser parity
    with margot_bot._BOARD_TRIGGER_RE)
  * provider_router ROLE_TIER includes "portfolio.synthesis" → "top"
  * run_all_projects attaches cross_portfolio_synthesis attribute
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import portfolio_pulse  # noqa: E402
from swarm import portfolio_pulse_synthesis as pps  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_pulse(project_id: str, body: str = "deploy ok, ci green") -> "portfolio_pulse.PulseResult":
    return portfolio_pulse.PulseResult(
        project_id=project_id,
        date="2026-05-03",
        sections=[
            portfolio_pulse.PulseSection(name="deploys", body_md=body),
            portfolio_pulse.PulseSection(name="ci", body_md="green"),
            portfolio_pulse.PulseSection(name="prs", body_md="3 open"),
        ],
    )


class _FakeProviderRouter:
    """Drop-in replacement for app.server.provider_router with a recording
    run_via_provider stub. Installed via monkeypatch.setitem on sys.modules."""

    def __init__(self, response: str = "Across the portfolio today, "
                                          "everything is fine.",
                  rc: int = 0, error: str | None = None,
                  raise_exc: Exception | None = None):
        self.response = response
        self.rc = rc
        self.error = error
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    async def run_via_provider(self, prompt: str, *, role: str,
                                  task_class: str = "default",
                                  timeout_s: int = 120,
                                  workspace: str | None = None,
                                  session_id: str = "",
                                  thinking: str = "adaptive"):
        self.calls.append({
            "prompt": prompt, "role": role, "task_class": task_class,
            "timeout_s": timeout_s, "session_id": session_id,
            "thinking": thinking,
        })
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.rc, self.response, 0.0, self.error


def _install_fake_router(monkeypatch, fake: _FakeProviderRouter) -> None:
    import types  # noqa: PLC0415
    mod = types.ModuleType("app.server.provider_router")
    mod.run_via_provider = fake.run_via_provider  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.server.provider_router", mod)


# ── Tests ──────────────────────────────────────────────────────────────────


def test_synthesize_calls_provider_router_with_correct_role(monkeypatch):
    """The synthesis call uses role 'portfolio.synthesis'."""
    fake = _FakeProviderRouter(
        response="Across the portfolio today, deploys ran clean and "
                  "Linear movement was healthy across all seven projects.",
    )
    _install_fake_router(monkeypatch, fake)

    pulses = {
        "pi-ceo": _make_pulse("pi-ceo"),
        "restoreassist": _make_pulse("restoreassist"),
    }
    out = pps.synthesize(pulses)

    assert len(fake.calls) == 1
    assert fake.calls[0]["role"] == "portfolio.synthesis"
    assert "Across the portfolio today" in out
    # Both project ids should appear in the prompt
    prompt = fake.calls[0]["prompt"]
    assert "pi-ceo" in prompt
    assert "restoreassist" in prompt


def test_synthesize_caps_at_400_words(monkeypatch):
    """A long LLM response is truncated to 400 words."""
    long_response = " ".join(["word"] * 600)
    fake = _FakeProviderRouter(response=long_response)
    _install_fake_router(monkeypatch, fake)

    out = pps.synthesize({"pi-ceo": _make_pulse("pi-ceo")})
    word_count = len(out.split())
    # Allow +1 for a trailing ellipsis token
    assert word_count <= pps.MAX_WORDS + 1, (
        f"synthesis exceeded {pps.MAX_WORDS} words: {word_count}"
    )


def test_synthesize_falls_back_on_llm_error(monkeypatch):
    """Non-zero rc / error string → deterministic fallback body."""
    fake = _FakeProviderRouter(rc=1, response="", error="upstream_500")
    _install_fake_router(monkeypatch, fake)

    out = pps.synthesize({"pi-ceo": _make_pulse("pi-ceo")})
    assert out.startswith("_(synthesis unavailable:")
    assert "upstream_500" in out


def test_synthesize_falls_back_on_exception(monkeypatch):
    """run_via_provider raising → deterministic fallback body."""
    fake = _FakeProviderRouter(raise_exc=RuntimeError("boom"))
    _install_fake_router(monkeypatch, fake)

    out = pps.synthesize({"pi-ceo": _make_pulse("pi-ceo")})
    assert out.startswith("_(synthesis unavailable:")
    assert "boom" in out


def test_synthesize_empty_input_returns_fallback(monkeypatch):
    """Empty per-project map → fallback without firing the LLM."""
    fake = _FakeProviderRouter()
    _install_fake_router(monkeypatch, fake)

    out = pps.synthesize({})
    assert out.startswith("_(synthesis unavailable:")
    assert len(fake.calls) == 0  # no LLM call was made


def test_synthesize_provider_router_import_failure(monkeypatch):
    """If provider_router can't import, synthesize returns fallback."""
    # Force the import inside _call_llm to fail
    import builtins  # noqa: PLC0415
    real_import = builtins.__import__

    def _bad_import(name, *args, **kwargs):
        if name == "app.server.provider_router":
            raise ImportError("no module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _bad_import)
    monkeypatch.delitem(sys.modules, "app.server.provider_router", raising=False)

    out = pps.synthesize({"pi-ceo": _make_pulse("pi-ceo")})
    assert out.startswith("_(synthesis unavailable:")
    assert "provider_router_unavailable" in out


def test_board_trigger_sentinel_parses_cleanly(monkeypatch):
    """When the LLM emits a BOARD-TRIGGER sentinel, the same regex used
    by margot_bot extracts it cleanly."""
    response = (
        "Across the portfolio today, RestoreAssist shipped TestFlight "
        "build 26 and CI is green everywhere except Synthex, which has "
        "two flaky tests blocking merge. \n\n"
        "[BOARD-TRIGGER score=8 topic=\"Synthex CI flake blocking merges\"]"
        "Two consecutive flake events on the same test in 24h — likely "
        "real, worth a quick triage decision.[/BOARD-TRIGGER]"
    )
    fake = _FakeProviderRouter(response=response)
    _install_fake_router(monkeypatch, fake)

    out = pps.synthesize({"pi-ceo": _make_pulse("pi-ceo")})

    # Same regex as swarm.margot_bot._BOARD_TRIGGER_RE
    pattern = re.compile(
        r"\[BOARD-TRIGGER\s+score\s*=\s*(\d+)\s+topic\s*=\s*\"([^\"]+)\"\]"
        r"\s*([\s\S]*?)\s*\[/BOARD-TRIGGER\]",
    )
    matches = pattern.findall(out)
    assert len(matches) == 1
    score, topic, content = matches[0]
    assert int(score) == 8
    assert "Synthex" in topic
    assert content.strip()  # non-empty rationale


def test_role_tier_registered():
    """provider_router.ROLE_TIER must list 'portfolio.synthesis' as 'top'."""
    from app.server import provider_router  # noqa: PLC0415
    assert provider_router.ROLE_TIER.get("portfolio.synthesis") == "top"


def test_run_all_projects_attaches_synthesis_attribute(monkeypatch, tmp_path):
    """run_all_projects must expose cross_portfolio_synthesis on its result
    and write a synthesis markdown file."""
    fake = _FakeProviderRouter(
        response="Across the portfolio today, all seven projects healthy.",
    )
    _install_fake_router(monkeypatch, fake)

    results = portfolio_pulse.run_all_projects(repo_root=tmp_path)

    assert hasattr(results, "cross_portfolio_synthesis")
    assert "Across the portfolio today" in results.cross_portfolio_synthesis
    # Synthesis file written
    synth_path = tmp_path / ".harness" / "portfolio-pulse" / "_synthesis" / \
        f"{results[0].date}.md"
    assert synth_path.exists()
    body = synth_path.read_text(encoding="utf-8")
    assert "Cross-Portfolio Synthesis" in body
    assert "Across the portfolio today" in body


def test_run_all_projects_skips_synthesis_when_disabled(monkeypatch, tmp_path):
    """include_synthesis=False short-circuits — no LLM call, empty attribute."""
    fake = _FakeProviderRouter()
    _install_fake_router(monkeypatch, fake)

    results = portfolio_pulse.run_all_projects(
        repo_root=tmp_path, include_synthesis=False,
    )
    assert results.cross_portfolio_synthesis == ""
    assert len(fake.calls) == 0
