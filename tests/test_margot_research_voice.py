"""tests/test_margot_research_voice.py — research-on-demand + voice reply."""
from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import margot_bot  # noqa: E402
from swarm import voice_compose as VC  # noqa: E402


# ── Research-request parsing ───────────────────────────────────────────────


def test_parse_research_requests_default_depth_quick():
    text = '[RESEARCH topic="competitor X status"]'
    requests, cleaned = margot_bot.parse_research_requests(text)
    assert len(requests) == 1
    assert requests[0].topic == "competitor X status"
    assert requests[0].depth == "quick"
    assert cleaned == ""


def test_parse_research_requests_explicit_depth():
    text = '[RESEARCH depth="deep" topic="ANZ regulatory shifts 2026"]'
    requests, _ = margot_bot.parse_research_requests(text)
    assert len(requests) == 1
    assert requests[0].depth == "deep"


def test_parse_research_requests_multiple():
    text = '''Looking into a few things.

[RESEARCH topic="competitor pricing"]
[RESEARCH depth="quick" topic="market size ANZ restoration"]
[RESEARCH depth="deep" topic="EU AI Act enforcement timeline"]

I'll have detail shortly.'''
    requests, cleaned = margot_bot.parse_research_requests(text)
    assert len(requests) == 3
    assert requests[0].depth == "quick"
    assert requests[1].depth == "quick"
    assert requests[2].depth == "deep"
    assert "[RESEARCH" not in cleaned
    assert "Looking into a few things." in cleaned
    assert "I'll have detail shortly." in cleaned


def test_parse_research_requests_no_sentinel():
    text = "Plain reply, no research needed."
    requests, cleaned = margot_bot.parse_research_requests(text)
    assert requests == []
    assert cleaned == text


def test_parse_research_requests_empty_topic_skipped():
    text = '[RESEARCH topic=""]'
    requests, _ = margot_bot.parse_research_requests(text)
    assert requests == []


# ── Phase-2 batch execution ────────────────────────────────────────────────


def test_run_research_batch_calls_quick_for_default(monkeypatch):
    calls: list[dict] = []

    def fake_quick(*, topic, use_corpus=False):
        calls.append({"topic": topic, "depth": "quick"})
        return {"summary": f"Quick result for {topic}", "status": "ok"}

    fake_module = types.SimpleNamespace(
        deep_research=fake_quick,
        deep_research_max=lambda **kw: {"error": "should not be called"},
    )
    monkeypatch.setitem(sys.modules, "swarm.margot_tools", fake_module)

    requests = [
        margot_bot.ResearchRequest(topic="A", depth="quick"),
        margot_bot.ResearchRequest(topic="B", depth="quick"),
    ]
    findings = asyncio.run(margot_bot._run_research_batch(requests))
    assert len(findings) == 2
    assert findings[0]["summary"] == "Quick result for A"
    assert findings[1]["summary"] == "Quick result for B"
    assert {c["topic"] for c in calls} == {"A", "B"}


def test_run_research_batch_calls_max_for_deep(monkeypatch):
    fake_module = types.SimpleNamespace(
        deep_research=lambda **kw: {"error": "should_not_call_quick"},
        deep_research_max=lambda **kw: {
            "interaction_id": "int-xyz", "status": "dispatched",
        },
    )
    monkeypatch.setitem(sys.modules, "swarm.margot_tools", fake_module)

    requests = [margot_bot.ResearchRequest(topic="X", depth="deep")]
    findings = asyncio.run(margot_bot._run_research_batch(requests))
    assert len(findings) == 1
    assert findings[0]["depth"] == "deep"
    assert "int-xyz" in findings[0]["summary"]
    assert findings[0]["error"] is None


def test_run_research_batch_handles_error_response(monkeypatch):
    fake_module = types.SimpleNamespace(
        deep_research=lambda **kw: {"error": "margot_unreachable"},
        deep_research_max=lambda **kw: {"error": "margot_unreachable"},
    )
    monkeypatch.setitem(sys.modules, "swarm.margot_tools", fake_module)

    requests = [margot_bot.ResearchRequest(topic="X", depth="quick")]
    findings = asyncio.run(margot_bot._run_research_batch(requests))
    assert len(findings) == 1
    assert findings[0]["error"] == "margot_unreachable"
    assert findings[0]["summary"] == ""


def test_run_research_batch_handles_exception(monkeypatch):
    def boom(**kw):
        raise RuntimeError("boom")

    fake_module = types.SimpleNamespace(
        deep_research=boom, deep_research_max=boom,
    )
    monkeypatch.setitem(sys.modules, "swarm.margot_tools", fake_module)

    requests = [margot_bot.ResearchRequest(topic="X", depth="quick")]
    findings = asyncio.run(margot_bot._run_research_batch(requests))
    assert "research_call_raised" in findings[0]["error"]


def test_run_research_batch_module_unavailable(monkeypatch):
    """When margot_tools import itself fails, return error entries."""
    monkeypatch.setitem(sys.modules, "swarm.margot_tools", None)
    requests = [margot_bot.ResearchRequest(topic="X", depth="quick")]
    findings = asyncio.run(margot_bot._run_research_batch(requests))
    # One entry, error set
    assert len(findings) == 1
    assert findings[0]["error"]
    assert findings[0]["summary"] == ""


# ── build_prompt_with_research ─────────────────────────────────────────────


def test_build_prompt_with_research_includes_findings():
    out = margot_bot.build_prompt_with_research(
        user_text="What about competitor X?",
        history=[], context={"cfo": [], "cmo": [], "cto": [], "cs": [],
                              "board_recent": [], "ccw": None},
        draft="Looking into competitor X.",
        research_findings=[{
            "topic": "competitor X", "depth": "quick",
            "summary": "X just raised $50M Series B in May 2026.",
            "error": None,
        }],
    )
    assert "PHASE 2" in out
    assert "X just raised $50M" in out
    assert "Do NOT emit [RESEARCH]" in out


def test_build_prompt_with_research_truncates_huge_summary():
    huge = "X" * 10_000
    out = margot_bot.build_prompt_with_research(
        user_text="q", history=[],
        context={"cfo": [], "cmo": [], "cto": [], "cs": [],
                  "board_recent": [], "ccw": None},
        draft="d",
        research_findings=[{
            "topic": "x", "depth": "quick",
            "summary": huge, "error": None,
        }],
    )
    # Truncation marker present; full huge string NOT present
    assert "…" in out
    assert huge not in out


def test_build_prompt_with_research_renders_error():
    out = margot_bot.build_prompt_with_research(
        user_text="q", history=[],
        context={"cfo": [], "cmo": [], "cto": [], "cs": [],
                  "board_recent": [], "ccw": None},
        draft="d",
        research_findings=[{
            "topic": "x", "depth": "quick",
            "summary": "", "error": "margot_unreachable",
        }],
    )
    assert "[error: margot_unreachable]" in out


# ── handle_turn two-phase research flow ────────────────────────────────────


def test_handle_turn_research_two_phase(tmp_path, monkeypatch):
    """Phase 1 emits [RESEARCH], Phase 2 produces final reply."""
    phase1 = '''Investigating.

[RESEARCH topic="competitor X status"]

Standby.'''
    phase2 = "Competitor X just raised $50M Series B."

    call_count = [0]

    async def fake_llm(*, prompt, timeout_s=120, workspace=None, turn_id=""):
        call_count[0] += 1
        if call_count[0] == 1:
            return 0, phase1, 0.05, None
        # Phase 2 should receive the research finding in its prompt
        assert "PHASE 2" in prompt
        assert "competitor x" in prompt.lower()
        return 0, phase2, 0.07, None

    monkeypatch.setattr(margot_bot, "_call_llm", fake_llm)

    fake_module = types.SimpleNamespace(
        deep_research=lambda **kw: {
            "summary": "X raised $50M Series B in May 2026.",
            "status": "ok",
        },
        deep_research_max=lambda **kw: {"error": "n/a"},
    )
    monkeypatch.setitem(sys.modules, "swarm.margot_tools", fake_module)

    turn = asyncio.run(margot_bot.handle_turn(
        chat_id="789", user_text="What's competitor X doing?",
        repo_root=tmp_path, _send=False,
    ))

    assert turn.research_called is True
    assert turn.margot_text == phase2
    assert turn.cost_usd == pytest.approx(0.12)
    assert call_count[0] == 2


def test_handle_turn_no_research_single_phase(tmp_path, monkeypatch):
    """No [RESEARCH] sentinel → only Phase 1 fires."""
    call_count = [0]

    async def fake_llm(*, prompt, timeout_s=120, workspace=None, turn_id=""):
        call_count[0] += 1
        return 0, "Direct answer, no research needed.", 0.04, None

    monkeypatch.setattr(margot_bot, "_call_llm", fake_llm)

    turn = asyncio.run(margot_bot.handle_turn(
        chat_id="789", user_text="hi", repo_root=tmp_path, _send=False,
    ))

    assert turn.research_called is False
    assert call_count[0] == 1
    assert turn.cost_usd == pytest.approx(0.04)


def test_handle_turn_phase2_failure_falls_back_to_draft(tmp_path, monkeypatch):
    phase1 = '''Looking up.

[RESEARCH topic="x"]

Hold on.'''

    call_count = [0]

    async def fake_llm(*, prompt, timeout_s=120, workspace=None, turn_id=""):
        call_count[0] += 1
        if call_count[0] == 1:
            return 0, phase1, 0.05, None
        return 1, "", 0.0, "phase2_boom"

    monkeypatch.setattr(margot_bot, "_call_llm", fake_llm)

    fake_module = types.SimpleNamespace(
        deep_research=lambda **kw: {"summary": "x", "status": "ok"},
        deep_research_max=lambda **kw: {"error": "n/a"},
    )
    monkeypatch.setitem(sys.modules, "swarm.margot_tools", fake_module)

    turn = asyncio.run(margot_bot.handle_turn(
        chat_id="789", user_text="q", repo_root=tmp_path, _send=False,
    ))

    # Falls back to Phase 1 draft (with sentinel stripped)
    assert "Looking up." in turn.margot_text
    assert "Hold on." in turn.margot_text
    assert "[RESEARCH" not in turn.margot_text
    assert turn.research_called is True


# ── Voice reply ────────────────────────────────────────────────────────────


def test_margot_reply_friendly_text_strips_emoji():
    out = VC.margot_reply_friendly_text("CCW NPS 72 ✅, runway 22m 💰")
    assert "✅" not in out and "💰" not in out
    # CCW preserved; NPS gets abbreviation-expanded to "N P S"
    assert "CCW" in out
    assert "N P S" in out
    assert "22m" in out


def test_margot_reply_friendly_text_expands_acronyms():
    out = VC.margot_reply_friendly_text(
        "MRR is steady; NRR drift; DORA medium",
    )
    assert "M R R" in out
    assert "N R R" in out
    assert "D O R A" in out


def test_margot_reply_friendly_text_normalises_currency():
    out = VC.margot_reply_friendly_text("Revenue $4,500/month, GM 88%")
    assert "4,500 dollars" in out
    assert "88 percent" in out


def test_margot_reply_friendly_text_does_not_apply_section_transitions():
    """Margot replies are prose, not 6-pager — no '1.' rewriting."""
    out = VC.margot_reply_friendly_text(
        "1. The first thing is X. 2. The second is Y."
    )
    assert "Section 1 of 6" not in out
    assert "1." in out  # numbered prose preserved as-is


def test_compose_margot_voice_reply_no_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    text, audio = VC.compose_margot_voice_reply(
        "Short reply about CCW.", out_dir=tmp_path / "voice",
        filename_stem="t-1",
    )
    assert audio is None
    assert "CCW" in text


def test_compose_margot_voice_reply_too_long_skips_synth(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fake")
    long_reply = "word " * 300  # > 800 chars

    called = [False]

    def fake_synth(text, *, out_path, voice_id=None, api_key=None):
        called[0] = True
        return out_path

    monkeypatch.setattr(VC, "synthesise_voice", fake_synth)
    text, audio = VC.compose_margot_voice_reply(
        long_reply, out_dir=tmp_path / "voice",
        filename_stem="t-1",
    )
    assert audio is None
    assert called[0] is False  # synth not called when over cap


def test_compose_margot_voice_reply_under_cap_synthesises(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fake")

    def fake_synth(text, *, out_path, voice_id=None, api_key=None):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"\x00fake-mp3")
        return out_path

    monkeypatch.setattr(VC, "synthesise_voice", fake_synth)
    text, audio = VC.compose_margot_voice_reply(
        "CCW NPS 72.", out_dir=tmp_path / "voice",
        filename_stem="t-1",
    )
    assert audio is not None
    assert audio.exists()


def test_compose_margot_voice_reply_custom_max_chars(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fake")
    monkeypatch.setattr(VC, "synthesise_voice",
                         lambda text, *, out_path, **kw: None)
    # 50-char cap; 80-char reply → skips
    _, audio = VC.compose_margot_voice_reply(
        "x" * 80, out_dir=tmp_path / "voice",
        filename_stem="t", max_chars=50,
    )
    assert audio is None


def test_compose_margot_voice_reply_env_override_max_chars(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fake")
    monkeypatch.setenv("MARGOT_VOICE_REPLY_MAX_CHARS", "30")

    called = [False]

    def fake_synth(text, *, out_path, voice_id=None, api_key=None):
        called[0] = True
        return out_path

    monkeypatch.setattr(VC, "synthesise_voice", fake_synth)
    _, audio = VC.compose_margot_voice_reply(
        "x" * 60, out_dir=tmp_path / "voice", filename_stem="t",
    )
    # 60 > 30 cap → no synth
    assert called[0] is False
    assert audio is None


# ── handle_turn voice integration ──────────────────────────────────────────


def test_handle_turn_voice_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("MARGOT_VOICE_REPLY_ENABLED", raising=False)

    async def fake_llm(*, prompt, timeout_s=120, workspace=None, turn_id=""):
        return 0, "Short reply.", 0.01, None

    monkeypatch.setattr(margot_bot, "_call_llm", fake_llm)

    sent_kwargs: dict = {}

    def fake_send(**kw):
        sent_kwargs.update(kw)
        return True

    monkeypatch.setattr(margot_bot, "_send_telegram", fake_send)

    asyncio.run(margot_bot.handle_turn(
        chat_id="789", user_text="hi", repo_root=tmp_path, _send=True,
    ))
    # No audio attached
    assert sent_kwargs.get("audio_path") is None


def test_handle_turn_voice_enabled_attaches_audio(tmp_path, monkeypatch):
    monkeypatch.setenv("MARGOT_VOICE_REPLY_ENABLED", "1")

    async def fake_llm(*, prompt, timeout_s=120, workspace=None, turn_id=""):
        return 0, "Short reply about MRR.", 0.01, None

    monkeypatch.setattr(margot_bot, "_call_llm", fake_llm)

    # Stub voice_compose to deterministically return a fake audio path
    fake_audio = tmp_path / "fake.mp3"
    fake_audio.write_bytes(b"fake")

    def fake_compose_voice(text, *, out_dir, filename_stem,
                            max_chars=None):
        return text, fake_audio

    fake_vc = types.SimpleNamespace(
        compose_margot_voice_reply=fake_compose_voice,
    )
    monkeypatch.setitem(sys.modules, "swarm.voice_compose", fake_vc)

    sent_kwargs: dict = {}

    def fake_send(**kw):
        sent_kwargs.update(kw)
        return True

    monkeypatch.setattr(margot_bot, "_send_telegram", fake_send)

    asyncio.run(margot_bot.handle_turn(
        chat_id="789", user_text="hi", repo_root=tmp_path, _send=True,
    ))

    assert sent_kwargs.get("audio_path") == fake_audio


def test_handle_turn_voice_compose_failure_falls_back_to_text(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("MARGOT_VOICE_REPLY_ENABLED", "1")

    async def fake_llm(*, prompt, timeout_s=120, workspace=None, turn_id=""):
        return 0, "Short reply.", 0.01, None

    monkeypatch.setattr(margot_bot, "_call_llm", fake_llm)

    def fake_compose_voice(text, *, out_dir, filename_stem,
                            max_chars=None):
        raise RuntimeError("voice compose boom")

    fake_vc = types.SimpleNamespace(
        compose_margot_voice_reply=fake_compose_voice,
    )
    monkeypatch.setitem(sys.modules, "swarm.voice_compose", fake_vc)

    sent_kwargs: dict = {}

    def fake_send(**kw):
        sent_kwargs.update(kw)
        return True

    monkeypatch.setattr(margot_bot, "_send_telegram", fake_send)

    turn = asyncio.run(margot_bot.handle_turn(
        chat_id="789", user_text="hi", repo_root=tmp_path, _send=True,
    ))
    # Compose failed → no audio, turn still successful, text sent
    assert sent_kwargs.get("audio_path") is None
    assert sent_kwargs.get("text") == "Short reply."
    assert not turn.error
