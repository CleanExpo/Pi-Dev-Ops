"""tests/test_discovery.py — RA-2026 (HERMES Discovery loop).

Covers the four protocols + state management + persona loader + cron
dispatcher shim. All LLM/Perplexity calls are hooked out so tests run
in milliseconds without network or model dependencies.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import discovery  # noqa: E402


# ── Test fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """Point Discovery's state + report dirs at tmp_path so tests don't
    pollute ~/.hermes/."""
    monkeypatch.setattr(discovery, "DISCOVERY_STATE_PATH",
                        tmp_path / "discovery-state.json")
    monkeypatch.setattr(discovery, "DISCOVERY_REPORT_DIR",
                        tmp_path / "discovery")
    monkeypatch.setattr(discovery, "CHARTERS_DIR",
                        tmp_path / "business-charters")
    return tmp_path


@pytest.fixture
def make_charter(isolated_state):
    """Helper to write a charter file with a given watch-list."""
    def _make(persona_id: str, watchlist: list[str], extra: str = "") -> Path:
        charters_dir = isolated_state / "business-charters"
        charters_dir.mkdir(parents=True, exist_ok=True)
        path = charters_dir / f"{persona_id}.md"
        body = f"# {persona_id} charter\n\n## Mission\n\nTest mission.\n\n"
        body += "## Watch-list\n\n"
        for q in watchlist:
            body += f"- {q}\n"
        if extra:
            body += "\n" + extra
        path.write_text(body, encoding="utf-8")
        return path
    return _make


@pytest.fixture
def make_projects_json(isolated_state):
    """Helper to write a synthetic .harness/projects.json for the loader."""
    def _make(entries: list[dict]) -> Path:
        path = isolated_state / "projects.json"
        payload = {"version": "1.0", "projects": entries}
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path
    return _make


# ── State management ────────────────────────────────────────────────────────


def test_state_load_returns_default_when_missing(isolated_state):
    state = discovery._load_state()
    assert state == {"version": 1, "hashes": {}}


def test_state_save_round_trip(isolated_state):
    state = {"version": 1, "hashes": {"abc": {"persona_id": "x",
                                                  "first_seen": "2026-05-06T00:00:00+00:00"}}}
    discovery._save_state(state)
    loaded = discovery._load_state()
    assert loaded == state


def test_state_save_atomic(isolated_state):
    """Two consecutive saves should not corrupt each other (tmp+replace)."""
    discovery._save_state({"version": 1, "hashes": {"a": {}}})
    discovery._save_state({"version": 1, "hashes": {"b": {}}})
    loaded = discovery._load_state()
    assert "a" not in loaded["hashes"]
    assert "b" in loaded["hashes"]


def test_state_load_resilient_to_corruption(isolated_state):
    discovery.DISCOVERY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    discovery.DISCOVERY_STATE_PATH.write_text("not valid json {{{")
    loaded = discovery._load_state()
    assert loaded == {"version": 1, "hashes": {}}


# ── Finding hash + dedup ─────────────────────────────────────────────────────


def test_finding_hash_stable():
    f1 = discovery.Finding(persona_id="ra", title="T", url="u", published_date="2026-05-01")
    f2 = discovery.Finding(persona_id="ra", title="T", url="u", published_date="2026-05-01")
    assert f1.hash == f2.hash


def test_finding_hash_distinguishes_url():
    f1 = discovery.Finding(persona_id="ra", title="T", url="u1", published_date="d")
    f2 = discovery.Finding(persona_id="ra", title="T", url="u2", published_date="d")
    assert f1.hash != f2.hash


def test_is_novel_first_time_returns_true(isolated_state):
    f = discovery.Finding(persona_id="ra", title="T", url="u", published_date="d")
    assert discovery.is_novel(f) is True


def test_record_finding_then_not_novel(isolated_state):
    f = discovery.Finding(persona_id="ra", title="T", url="u", published_date="d")
    state = discovery._load_state()
    discovery.record_finding(f, state)
    discovery._save_state(state)
    assert discovery.is_novel(f) is False


def test_prune_stale_hashes_removes_old_entries(isolated_state):
    old_iso = (
        datetime.now(timezone.utc) - timedelta(days=discovery.DEDUP_WINDOW_DAYS + 5)
    ).isoformat()
    fresh_iso = datetime.now(timezone.utc).isoformat()
    state = {
        "version": 1,
        "hashes": {
            "old": {"persona_id": "ra", "first_seen": old_iso},
            "fresh": {"persona_id": "ra", "first_seen": fresh_iso},
        },
    }
    pruned = discovery._prune_stale_hashes(state)
    assert pruned == 1
    assert "old" not in state["hashes"]
    assert "fresh" in state["hashes"]


def test_prune_handles_unparseable_dates_as_stale(isolated_state):
    state = {"version": 1, "hashes": {"x": {"first_seen": "not a date"}}}
    pruned = discovery._prune_stale_hashes(state)
    assert pruned == 1


# ── Charter loader / watch-list parser ───────────────────────────────────────


def test_extract_watchlist_basic():
    text = """# Charter

## Mission

Mission.

## Watch-list

- query 1
- query 2
- query 3

## Other section

ignored
"""
    out = discovery._extract_watchlist(text)
    assert out == ["query 1", "query 2", "query 3"]


def test_extract_watchlist_handles_capitalisation():
    text = "## Watchlist\n\n- a\n- b\n"
    assert discovery._extract_watchlist(text) == ["a", "b"]


def test_extract_watchlist_empty_when_section_missing():
    assert discovery._extract_watchlist("# nothing here") == []


def test_extract_watchlist_empty_on_empty_input():
    assert discovery._extract_watchlist("") == []


def test_load_persona_config_round_trip(isolated_state, make_charter, make_projects_json):
    make_charter("ra", ["q1 about RA", "q2 about RA"])
    pj = make_projects_json([
        {
            "id": "ra",
            "linear_project_id": "p-uuid",
            "linear_team_id": "t-uuid",
            "linear_team_key": "RA",
            "discovery_enabled": True,
        }
    ])
    cfg = discovery.load_persona_config("ra", projects_json_path=pj)
    assert cfg is not None
    assert cfg.persona_id == "ra"
    assert cfg.linear_project_id == "p-uuid"
    assert cfg.linear_team_key == "RA"
    assert cfg.watchlist == ["q1 about RA", "q2 about RA"]
    assert cfg.enabled is True


def test_load_persona_config_returns_none_when_missing(isolated_state, make_projects_json):
    pj = make_projects_json([])
    assert discovery.load_persona_config("nonexistent", projects_json_path=pj) is None


def test_load_persona_config_handles_disabled_flag(isolated_state, make_charter, make_projects_json):
    make_charter("ra", ["q1"])
    pj = make_projects_json([
        {"id": "ra", "linear_project_id": "p", "linear_team_id": "t",
         "linear_team_key": "RA", "discovery_enabled": False}
    ])
    cfg = discovery.load_persona_config("ra", projects_json_path=pj)
    assert cfg is not None
    assert cfg.enabled is False


def test_load_persona_config_handles_missing_charter_gracefully(
    isolated_state, make_projects_json
):
    """Charter file missing → cfg loads but watch-list is empty."""
    pj = make_projects_json([
        {"id": "ra", "linear_project_id": "p", "linear_team_id": "t",
         "linear_team_key": "RA"}
    ])
    cfg = discovery.load_persona_config("ra", projects_json_path=pj)
    assert cfg is not None
    assert cfg.watchlist == []


# ── SCAN protocol ────────────────────────────────────────────────────────────


def test_scan_returns_empty_when_no_perplexity_hook(isolated_state, make_charter, make_projects_json):
    make_charter("ra", ["q1"])
    pj = make_projects_json([{"id": "ra", "linear_project_id": "p",
                                "linear_team_id": "t", "linear_team_key": "RA"}])
    cfg = discovery.load_persona_config("ra", projects_json_path=pj)
    assert cfg is not None
    discovery.set_perplexity_hook(None)  # explicitly clear
    findings = discovery.scan(cfg)
    assert findings == []


def test_scan_calls_hook_per_watchlist_query(isolated_state, make_charter, make_projects_json):
    make_charter("ra", ["q1", "q2", "q3"])
    pj = make_projects_json([{"id": "ra", "linear_project_id": "p",
                                "linear_team_id": "t", "linear_team_key": "RA"}])
    cfg = discovery.load_persona_config("ra", projects_json_path=pj)
    received: list[str] = []
    def fake(q):
        received.append(q)
        return [discovery.Finding(persona_id="", title=f"finding for {q}",
                                    url=f"http://example/{q}",
                                    published_date="2026-05-06",
                                    summary="canned")]
    discovery.set_perplexity_hook(fake)
    try:
        findings = discovery.scan(cfg)
    finally:
        discovery.set_perplexity_hook(None)
    assert sorted(received) == ["q1", "q2", "q3"]
    assert len(findings) == 3
    assert all(f.persona_id == "ra" for f in findings)
    assert all(f.raw_query in ("q1", "q2", "q3") for f in findings)


def test_scan_skips_gemma_when_summary_already_present(isolated_state, make_charter, make_projects_json):
    """If Perplexity already returns a summary, Gemma is not invoked."""
    make_charter("ra", ["q"])
    pj = make_projects_json([{"id": "ra", "linear_project_id": "p",
                                "linear_team_id": "t", "linear_team_key": "RA"}])
    cfg = discovery.load_persona_config("ra", projects_json_path=pj)
    discovery.set_perplexity_hook(lambda q: [
        discovery.Finding(persona_id="", title="t", url="u",
                            published_date="d", summary="pre-summarised"),
    ])
    try:
        with patch.object(discovery, "_summarise_with_gemma") as mock_gemma:
            mock_gemma.return_value = "should not run"
            findings = discovery.scan(cfg)
            assert mock_gemma.call_count == 0
    finally:
        discovery.set_perplexity_hook(None)
    assert findings[0].summary == "pre-summarised"


# ── Severity routing thresholds ──────────────────────────────────────────────


def test_severity_thresholds_are_sane():
    """Sanity check on severity bands."""
    assert discovery.SEV_PROPOSAL_MIN == 4
    assert discovery.SEV_ESCALATE_MIN == 7
    assert discovery.SEV_PROPOSAL_MIN < discovery.SEV_ESCALATE_MIN


# ── Kill-switch + gating ────────────────────────────────────────────────────


def test_run_persona_cycle_skips_when_swarm_disabled(isolated_state, make_charter, make_projects_json, monkeypatch):
    monkeypatch.setenv("TAO_SWARM_ENABLED", "0")
    make_charter("ra", ["q"])
    pj = make_projects_json([{"id": "ra", "linear_project_id": "p",
                                "linear_team_id": "t", "linear_team_key": "RA"}])
    _orig_load = discovery.load_persona_config
    monkeypatch.setattr(discovery, "load_persona_config",
                        lambda pid, **kw: _orig_load(pid, projects_json_path=pj))
    report = discovery.run_persona_cycle("ra")
    assert report.error == "swarm_disabled"


def test_run_persona_cycle_skips_when_hard_stop(isolated_state, make_charter, make_projects_json, monkeypatch):
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")
    monkeypatch.setenv("TAO_HARD_STOP_FILE", str(isolated_state / "HARD_STOP"))
    (isolated_state / "HARD_STOP").write_text("halt")
    make_charter("ra", ["q"])
    pj = make_projects_json([{"id": "ra", "linear_project_id": "p",
                                "linear_team_id": "t", "linear_team_key": "RA"}])
    _orig_load = discovery.load_persona_config
    monkeypatch.setattr(discovery, "load_persona_config",
                        lambda pid, **kw: _orig_load(pid, projects_json_path=pj))
    report = discovery.run_persona_cycle("ra")
    assert report.error == "hard_stop"


def test_run_persona_cycle_persona_not_found(isolated_state, make_projects_json, monkeypatch):
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")
    monkeypatch.delenv("TAO_HARD_STOP_FILE", raising=False)
    pj = make_projects_json([])
    _orig_load = discovery.load_persona_config
    monkeypatch.setattr(discovery, "load_persona_config",
                        lambda pid, **kw: _orig_load(pid, projects_json_path=pj))
    report = discovery.run_persona_cycle("nonexistent")
    assert report.error == "persona_not_found"


def test_run_persona_cycle_persona_disabled(isolated_state, make_charter, make_projects_json, monkeypatch):
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")
    monkeypatch.delenv("TAO_HARD_STOP_FILE", raising=False)
    make_charter("ra", ["q"])
    pj = make_projects_json([{"id": "ra", "linear_project_id": "p",
                                "linear_team_id": "t", "linear_team_key": "RA",
                                "discovery_enabled": False}])
    _orig_load = discovery.load_persona_config
    monkeypatch.setattr(discovery, "load_persona_config",
                        lambda pid, **kw: _orig_load(pid, projects_json_path=pj))
    report = discovery.run_persona_cycle("ra")
    assert report.error == "persona_disabled"


# ── End-to-end happy path ────────────────────────────────────────────────────


def test_run_persona_cycle_happy_path(isolated_state, make_charter, make_projects_json, monkeypatch):
    """SCAN → GAP → PROPOSAL with all hooks injected. Verify report shape."""
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")
    monkeypatch.delenv("TAO_HARD_STOP_FILE", raising=False)
    make_charter("ra", ["regulator update"])
    pj = make_projects_json([{"id": "ra", "linear_project_id": "p",
                                "linear_team_id": "t", "linear_team_key": "RA"}])

    discovery.set_perplexity_hook(lambda q: [
        discovery.Finding(persona_id="", title="Regulator update X",
                            url="http://gov/X", published_date="2026-05-06",
                            summary="The regulator updated standard Z."),
    ])

    def fake_classifier(finding, persona):
        return discovery.GapClassification(
            finding_hash=finding.hash, gap_class="regulatory",
            severity=8, rationale="14-day window",
        )
    discovery.set_gap_classifier(fake_classifier)

    def fake_drafter(finding, classification, persona):
        return (
            f"Reg update for {persona.persona_id}",
            f"Body: {finding.summary}\nGap: {classification.gap_class}",
        )
    discovery.set_proposal_drafter(fake_drafter)

    fake_router_calls: list[dict] = []
    def fake_router(finding, classification, persona, proposal_id):
        out = {
            "fired": True, "channels": ["board", "telegram"],
            "proposal_id": proposal_id,
        }
        fake_router_calls.append(out)
        return out
    discovery.set_escalation_router(fake_router)

    # Patch margot_tools.propose_idea so we don't hit Linear
    propose_calls: list[dict] = []
    def fake_propose(**kwargs):
        propose_calls.append(kwargs)
        return {"status": "created", "identifier": "RA-9999",
                "id": "uuid", "labels": ["margot-idea", "discovery-loop"],
                "originator": "discovery_loop"}
    monkeypatch.setattr(
        "swarm.margot_tools.propose_idea", fake_propose,
    )

    _orig_load = discovery.load_persona_config
    monkeypatch.setattr(
        discovery, "load_persona_config",
        lambda pid, **kw: _orig_load(pid, projects_json_path=pj),
    )

    try:
        report = discovery.run_persona_cycle("ra")
    finally:
        discovery.set_perplexity_hook(None)
        discovery.set_gap_classifier(None)
        discovery.set_proposal_drafter(None)
        discovery.set_escalation_router(None)

    assert report.error is None
    assert report.findings_total == 1
    assert report.findings_novel == 1
    assert len(report.proposals_created) == 1
    assert report.proposals_created[0] == "RA-9999"
    assert len(report.escalations) == 1  # sev=8 > SEV_ESCALATE_MIN
    assert fake_router_calls[0]["fired"] is True

    # Verify propose_idea was called with originator="discovery_loop"
    assert len(propose_calls) == 1
    assert propose_calls[0].get("originator") == "discovery_loop"
    assert "Reg update for ra" in propose_calls[0]["title"]


def test_run_persona_cycle_dedups_second_run(isolated_state, make_charter, make_projects_json, monkeypatch):
    """Second cycle within dedup window emits zero new proposals."""
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")
    monkeypatch.delenv("TAO_HARD_STOP_FILE", raising=False)
    make_charter("ra", ["q"])
    pj = make_projects_json([{"id": "ra", "linear_project_id": "p",
                                "linear_team_id": "t", "linear_team_key": "RA"}])

    discovery.set_perplexity_hook(lambda q: [
        discovery.Finding(persona_id="", title="static finding",
                            url="http://x", published_date="d", summary="s"),
    ])
    discovery.set_gap_classifier(
        lambda f, p: discovery.GapClassification(
            finding_hash=f.hash, gap_class="operational", severity=5,
        )
    )
    monkeypatch.setattr("swarm.margot_tools.propose_idea",
                        lambda **kw: {"status": "created", "identifier": "RA-1",
                                       "id": "u", "labels": [], "originator": "discovery_loop"})
    _orig_load = discovery.load_persona_config
    monkeypatch.setattr(
        discovery, "load_persona_config",
        lambda pid, **kw: _orig_load(pid, projects_json_path=pj),
    )

    try:
        first = discovery.run_persona_cycle("ra")
        second = discovery.run_persona_cycle("ra")
    finally:
        discovery.set_perplexity_hook(None)
        discovery.set_gap_classifier(None)

    assert first.findings_novel == 1
    assert second.findings_novel == 0
    assert len(second.proposals_created) == 0


def test_run_persona_cycle_skips_proposal_for_low_severity(isolated_state, make_charter, make_projects_json, monkeypatch):
    """sev < SEV_PROPOSAL_MIN (4) should not create a Linear ticket."""
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")
    monkeypatch.delenv("TAO_HARD_STOP_FILE", raising=False)
    make_charter("ra", ["q"])
    pj = make_projects_json([{"id": "ra", "linear_project_id": "p",
                                "linear_team_id": "t", "linear_team_key": "RA"}])

    discovery.set_perplexity_hook(lambda q: [
        discovery.Finding(persona_id="", title="trivial", url="u",
                            published_date="d", summary="s"),
    ])
    discovery.set_gap_classifier(
        lambda f, p: discovery.GapClassification(
            finding_hash=f.hash, gap_class="operational", severity=2,
        )
    )

    propose_calls: list[dict] = []
    monkeypatch.setattr("swarm.margot_tools.propose_idea",
                        lambda **kw: propose_calls.append(kw) or {"status": "created"})
    _orig_load = discovery.load_persona_config
    monkeypatch.setattr(
        discovery, "load_persona_config",
        lambda pid, **kw: _orig_load(pid, projects_json_path=pj),
    )

    try:
        report = discovery.run_persona_cycle("ra")
    finally:
        discovery.set_perplexity_hook(None)
        discovery.set_gap_classifier(None)

    assert report.findings_novel == 1
    assert len(report.proposals_created) == 0
    assert len(propose_calls) == 0  # never called


# ── propose_idea originator behaviour (RA-2026 extension) ────────────────────


def test_propose_idea_dry_run_originator_human():
    from swarm import margot_tools
    out = margot_tools.propose_idea(
        title="t", description="d", dry_run=True,
        originator="human",
    )
    assert out["originator"] == "human"
    assert out["labels"] == [margot_tools.MARGOT_IDEA_LABEL]


def test_propose_idea_dry_run_originator_discovery_loop():
    from swarm import margot_tools
    out = margot_tools.propose_idea(
        title="t", description="d", dry_run=True,
        originator="discovery_loop",
    )
    assert out["originator"] == "discovery_loop"
    assert out["labels"] == [
        margot_tools.MARGOT_IDEA_LABEL,
        margot_tools.DISCOVERY_LOOP_LABEL,
    ]


def test_propose_idea_default_originator_is_human():
    """Backwards-compat: callers that don't pass originator should still work."""
    from swarm import margot_tools
    out = margot_tools.propose_idea(title="t", dry_run=True)
    assert out["originator"] == "human"
    assert out["labels"] == [margot_tools.MARGOT_IDEA_LABEL]


# ── Cron dispatcher shim ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fire_discovery_trigger_invokes_run_persona_cycle(isolated_state, monkeypatch):
    captured: list[str] = []
    def fake_cycle(persona_id):
        captured.append(persona_id)
        return discovery.CycleReport(persona_id=persona_id,
                                       started_at="2026-05-06",
                                       finished_at="2026-05-06")
    monkeypatch.setattr(discovery, "run_persona_cycle", fake_cycle)

    import logging
    log = logging.getLogger("test")
    await discovery._fire_discovery_trigger(
        {"id": "discovery-ra", "type": "discovery", "persona": "ra"}, log,
    )
    assert captured == ["ra"]


@pytest.mark.asyncio
async def test_fire_discovery_trigger_handles_missing_persona(isolated_state, monkeypatch):
    """No persona field, no id-derived persona → log warning, no crash."""
    captured: list[str] = []
    monkeypatch.setattr(
        discovery, "run_persona_cycle",
        lambda pid: captured.append(pid) or discovery.CycleReport(
            persona_id=pid, started_at="x", finished_at="x"
        ),
    )
    import logging
    log = logging.getLogger("test")
    await discovery._fire_discovery_trigger({"id": "no-persona-here", "type": "discovery"}, log)
    # Falls through to derive persona from "id" suffix
    assert captured == ["here"]


# ── _persist_report ─────────────────────────────────────────────────────────


def test_persist_report_writes_jsonl(isolated_state):
    report = discovery.CycleReport(
        persona_id="ra", started_at="2026-05-06T00:00:00+00:00",
        finished_at="2026-05-06T00:01:00+00:00",
        findings_total=2, findings_novel=1,
        proposals_created=["RA-100"],
    )
    discovery._persist_report(report)
    out_dir = discovery.DISCOVERY_REPORT_DIR / "ra"
    assert out_dir.exists()
    files = list(out_dir.glob("*.jsonl"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text().strip())
    assert payload["persona_id"] == "ra"
    assert payload["proposals_created"] == ["RA-100"]
