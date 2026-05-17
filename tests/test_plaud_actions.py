"""Tests for scripts/plaud_actions.py."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import plaud_actions


def test_action_dataclass_defaults():
    a = plaud_actions.Action(title="x", description="y", priority=2)
    assert a.title == "x"
    assert a.priority == 2


def test_action_extraction_dataclass():
    ex = plaud_actions.ActionExtraction(
        portfolio="ccw-crm", confidence=0.92,
        reasoning="mentions CCW",
        actions=[plaud_actions.Action(title="t", description="d", priority=3)],
    )
    assert ex.portfolio == "ccw-crm"
    assert len(ex.actions) == 1


def test_batch_result_dataclass():
    br = plaud_actions.BatchResult(
        plaud_id="abc", title="Acme Q2",
        wiki_path="plaud/2026-05-17-acme-q2",
        portfolio="ccw-crm",
        tickets=[],
        status="no_actions",
    )
    assert br.status == "no_actions"


def test_linear_route_namedtuple():
    r = plaud_actions.LinearRoute(team_id="t", project_id="p", status="matched")
    assert r.team_id == "t"
    assert r.status == "matched"


def test_resolve_linear_route_known_portfolio(tmp_path):
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps({"projects": [
        {"id": "ccw-crm", "linear_team_id": "uni-team-uuid", "linear_project_id": "ccw-proj-uuid"},
        {"id": "pi-dev-ops", "linear_team_id": "ra-team-uuid", "linear_project_id": "pidev-proj-uuid"},
    ]}))
    r = plaud_actions.resolve_linear_route("ccw-crm", projects_json_path=pj)
    assert r.team_id == "uni-team-uuid"
    assert r.project_id == "ccw-proj-uuid"
    assert r.status == "matched"


def test_resolve_linear_route_unknown_falls_back_to_pi_dev_ops(tmp_path):
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps({"projects": [
        {"id": "pi-dev-ops", "linear_team_id": "ra-team-uuid", "linear_project_id": "pidev-proj-uuid"},
    ]}))
    r = plaud_actions.resolve_linear_route("unknown", projects_json_path=pj)
    assert r.team_id == "ra-team-uuid"
    assert r.project_id == "pidev-proj-uuid"
    assert r.status == "fallback_unknown"


def test_resolve_linear_route_missing_portfolio_falls_back(tmp_path):
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps({"projects": [
        {"id": "pi-dev-ops", "linear_team_id": "ra", "linear_project_id": "pi"},
    ]}))
    r = plaud_actions.resolve_linear_route("imaginary-portfolio", projects_json_path=pj)
    assert r.status == "fallback_unknown"


def test_resolve_linear_route_missing_projects_json_raises(tmp_path):
    pj = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        plaud_actions.resolve_linear_route("ccw-crm", projects_json_path=pj)


def test_resolve_linear_route_no_default_in_registry_raises(tmp_path):
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps({"projects": [
        {"id": "ccw-crm", "linear_team_id": "u", "linear_project_id": "c"},
    ]}))
    with pytest.raises(RuntimeError, match="pi-dev-ops"):
        plaud_actions.resolve_linear_route("unknown", projects_json_path=pj)


def _anthropic_tool_use_response(portfolio, confidence, reasoning, actions):
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "content": [{
            "type": "tool_use",
            "id": "toolu_1",
            "name": "report_actions",
            "input": {
                "portfolio": portfolio,
                "confidence": confidence,
                "reasoning": reasoning,
                "actions": actions,
            }
        }],
        "stop_reason": "tool_use",
    }


def _anthropic_mock_urlopen(payload, status=200):
    m = MagicMock()
    m.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    m.__enter__.return_value.status = status
    return m


def test_extract_actions_meeting_yields_actions():
    response = _anthropic_tool_use_response(
        portfolio="ccw-crm", confidence=0.92, reasoning="Mentions CCW",
        actions=[
            {"title": "Follow up Toby", "description": "by Friday", "priority": 2},
            {"title": "Update Q2 numbers", "description": "in Linear", "priority": 3},
        ],
    )
    with patch("plaud_actions.urllib.request.urlopen",
               return_value=_anthropic_mock_urlopen(response)):
        ex = plaud_actions.extract_actions(
            page_md="dummy meeting content",
            anthropic_api_key="sk-ant-test",
        )
    assert ex is not None
    assert ex.portfolio == "ccw-crm"
    assert len(ex.actions) == 2
    assert ex.actions[0].title == "Follow up Toby"
    assert ex.actions[0].priority == 2


def test_extract_actions_voice_memo_zero_actions():
    response = _anthropic_tool_use_response(
        portfolio="synthex", confidence=0.85,
        reasoning="Thinking out loud", actions=[],
    )
    with patch("plaud_actions.urllib.request.urlopen",
               return_value=_anthropic_mock_urlopen(response)):
        ex = plaud_actions.extract_actions(page_md="rambling memo",
            anthropic_api_key="sk-ant-test")
    assert ex is not None
    assert ex.actions == []


def test_extract_actions_no_tool_use_in_response_returns_none():
    response = {"content": [{"type": "text", "text": "I refuse to answer"}]}
    with patch("plaud_actions.urllib.request.urlopen",
               return_value=_anthropic_mock_urlopen(response)):
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert ex is None


def test_extract_actions_http_401_returns_auth_error():
    import urllib.error
    err = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
    with patch("plaud_actions.urllib.request.urlopen", side_effect=err):
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert isinstance(ex, plaud_actions._AuthError)


def test_extract_actions_http_429_retries_once_then_succeeds():
    import urllib.error
    err = urllib.error.HTTPError("url", 429, "Too Many", {}, None)
    success = _anthropic_tool_use_response("synthex", 0.9, "", [])
    side_effects = [err, _anthropic_mock_urlopen(success)]
    with patch("plaud_actions.urllib.request.urlopen", side_effect=side_effects), \
         patch("plaud_actions.time.sleep") as mock_sleep:
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert ex is not None
    mock_sleep.assert_called_once()


def test_extract_actions_http_429_twice_returns_none():
    import urllib.error
    err = urllib.error.HTTPError("url", 429, "Too Many", {}, None)
    with patch("plaud_actions.urllib.request.urlopen", side_effect=err), \
         patch("plaud_actions.time.sleep"):
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert ex is None


def test_extract_actions_low_confidence_preserved():
    response = _anthropic_tool_use_response(
        portfolio="unknown", confidence=0.3,
        reasoning="Ambiguous", actions=[
            {"title": "Some action", "description": "x", "priority": 3},
        ],
    )
    with patch("plaud_actions.urllib.request.urlopen",
               return_value=_anthropic_mock_urlopen(response)):
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert ex.portfolio == "unknown"
    assert ex.confidence == 0.3


def test_extract_actions_missing_key_returns_auth_error():
    ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="")
    assert isinstance(ex, plaud_actions._AuthError)


def test_create_linear_tickets_happy_path():
    actions = [
        plaud_actions.Action(title="Action 1", description="desc 1", priority=2),
        plaud_actions.Action(title="Action 2", description="desc 2", priority=3),
    ]
    refs = [
        plaud_actions.TicketRef(id="i1", identifier="CCW-247", url="u1"),
        plaud_actions.TicketRef(id="i2", identifier="CCW-248", url="u2"),
    ]
    with patch("plaud_actions.create_linear_issue", side_effect=refs):
        result = plaud_actions.create_linear_tickets(
            actions=actions, team_id="t", project_id="p",
            wiki_link="https://wiki/plaud/x.md",
            linear_api_key="lin_api_xxx",
        )
    assert len(result) == 2
    assert result[0].identifier == "CCW-247"


def test_create_linear_tickets_partial_failure():
    actions = [
        plaud_actions.Action(title="A", description="d1", priority=3),
        plaud_actions.Action(title="B", description="d2", priority=3),
        plaud_actions.Action(title="C", description="d3", priority=3),
    ]
    side_effects = [
        plaud_actions.TicketRef(id="i1", identifier="X-1", url=""),
        None,
        plaud_actions.TicketRef(id="i3", identifier="X-3", url=""),
    ]
    with patch("plaud_actions.create_linear_issue", side_effect=side_effects):
        result = plaud_actions.create_linear_tickets(
            actions=actions, team_id="t", project_id="p",
            wiki_link="https://wiki/p", linear_api_key="k",
        )
    assert len(result) == 2
    assert [r.identifier for r in result] == ["X-1", "X-3"]


def test_create_linear_tickets_appends_wiki_backlink_to_description():
    actions = [plaud_actions.Action(title="A", description="original body", priority=3)]
    seen_descriptions: list[str] = []
    def fake_create(**kw):
        seen_descriptions.append(kw["description"])
        return plaud_actions.TicketRef(id="i", identifier="X-1", url="")

    with patch("plaud_actions.create_linear_issue", side_effect=fake_create):
        plaud_actions.create_linear_tickets(
            actions=actions, team_id="t", project_id="p",
            wiki_link="https://wiki/plaud/test-slug.md", linear_api_key="k",
        )
    assert "original body" in seen_descriptions[0]
    assert "https://wiki/plaud/test-slug.md" in seen_descriptions[0]
    assert "Source" in seen_descriptions[0]


def test_rewrite_frontmatter_adds_new_keys(tmp_path):
    page = tmp_path / "p.md"
    page.write_text(
        "---\n"
        "type: plaud-recording\n"
        "plaud_id: abc\n"
        "duration_human: 5m12s\n"
        "---\n"
        "\n# Title\n\nBody.\n"
    )
    plaud_actions.rewrite_frontmatter(page, {
        "tickets": ["CCW-247", "CCW-248"],
        "action_portfolio": "ccw-crm",
        "action_status": "ok",
    })
    text = page.read_text()
    assert "tickets: [CCW-247, CCW-248]" in text
    assert "action_portfolio: ccw-crm" in text
    assert "action_status: ok" in text
    assert "plaud_id: abc" in text
    assert "duration_human: 5m12s" in text
    assert "# Title" in text
    assert "Body." in text


def test_rewrite_frontmatter_updates_existing_keys(tmp_path):
    page = tmp_path / "p.md"
    page.write_text(
        "---\n"
        "type: plaud-recording\n"
        "action_status: partial\n"
        "---\n"
        "\nBody.\n"
    )
    plaud_actions.rewrite_frontmatter(page, {"action_status": "ok"})
    text = page.read_text()
    assert "action_status: ok" in text
    assert "action_status: partial" not in text


def test_rewrite_frontmatter_atomic_no_tmp_leftover(tmp_path):
    page = tmp_path / "p.md"
    page.write_text("---\ntype: plaud-recording\n---\n\nBody.\n")
    plaud_actions.rewrite_frontmatter(page, {"action_status": "ok"})
    assert not list(tmp_path.glob("*.tmp"))


def test_rewrite_frontmatter_no_frontmatter_raises(tmp_path):
    page = tmp_path / "p.md"
    page.write_text("# Just markdown, no frontmatter\n")
    with pytest.raises(ValueError):
        plaud_actions.rewrite_frontmatter(page, {"x": "y"})


def test_read_frontmatter_tickets_returns_existing(tmp_path):
    page = tmp_path / "p.md"
    page.write_text(
        "---\n"
        "type: plaud-recording\n"
        "tickets: [CCW-247, CCW-248]\n"
        "action_status: ok\n"
        "---\n"
        "\nBody.\n"
    )
    fm = plaud_actions.read_frontmatter(page)
    assert fm.get("tickets") == "[CCW-247, CCW-248]"
    assert fm.get("action_status") == "ok"


def test_read_frontmatter_no_frontmatter_returns_empty(tmp_path):
    page = tmp_path / "p.md"
    page.write_text("# No frontmatter\n")
    assert plaud_actions.read_frontmatter(page) == {}


def test_build_digest_single_recording_with_actions():
    br = plaud_actions.BatchResult(
        plaud_id="abc", title="Acme Q2 Pricing",
        wiki_path="plaud/2026-05-17-acme-q2-pricing",
        portfolio="ccw-crm",
        tickets=[
            plaud_actions.TicketRef(id="i1", identifier="CCW-247", url="https://linear.app/u/CCW-247"),
            plaud_actions.TicketRef(id="i2", identifier="CCW-248", url="https://linear.app/u/CCW-248"),
        ],
        status="ok",
    )
    text = plaud_actions.build_digest_text([br])
    assert text is not None
    assert "Acme Q2 Pricing" in text
    assert "ccw-crm" in text or "CCW" in text
    assert "CCW-247" in text
    assert "CCW-248" in text
    assert "plaud/2026-05-17-acme-q2-pricing" in text


def test_build_digest_mixed_batch():
    brs = [
        plaud_actions.BatchResult(plaud_id="a", title="Meeting A",
            wiki_path="plaud/a", portfolio="ccw-crm",
            tickets=[plaud_actions.TicketRef("i", "CCW-1", "")],
            status="ok"),
        plaud_actions.BatchResult(plaud_id="b", title="Voice memo",
            wiki_path="plaud/b", portfolio="synthex",
            tickets=[], status="no_actions"),
    ]
    text = plaud_actions.build_digest_text(brs)
    assert "Meeting A" in text
    assert "Voice memo" in text
    assert "no actions" in text.lower() or "0 tickets" in text.lower()


def test_build_digest_all_zero_returns_none():
    brs = [
        plaud_actions.BatchResult(plaud_id="a", title="t1",
            wiki_path="p1", portfolio="x", tickets=[], status="no_actions"),
        plaud_actions.BatchResult(plaud_id="b", title="t2",
            wiki_path="p2", portfolio="y", tickets=[], status="no_actions"),
    ]
    assert plaud_actions.build_digest_text(brs) is None


def test_build_digest_empty_list_returns_none():
    assert plaud_actions.build_digest_text([]) is None


def test_build_digest_partial_shows_partial_marker():
    br = plaud_actions.BatchResult(plaud_id="a", title="Partial meeting",
        wiki_path="plaud/x", portfolio="ccw-crm",
        tickets=[plaud_actions.TicketRef("i", "CCW-1", "")],
        status="partial")
    text = plaud_actions.build_digest_text([br])
    assert "partial" in text.lower() or "⚠" in text


def _make_cfg(tmp_path, **overrides):
    """Minimal config-shaped object the orchestrator needs. We don't import the
    real IngestConfig — we mirror only what process() touches."""
    from types import SimpleNamespace
    pj = tmp_path / "projects.json"
    if not pj.exists():
        pj.write_text(json.dumps({"projects": [
            {"id": "pi-dev-ops", "linear_team_id": "ra-team", "linear_project_id": "pi-proj"},
            {"id": "ccw-crm", "linear_team_id": "uni-team", "linear_project_id": "ccw-proj"},
            {"id": "synthex", "linear_team_id": "syn-team", "linear_project_id": "syn-proj"},
        ]}))
    state_path = tmp_path / "state.json"
    if not state_path.exists():
        state_path.write_text(json.dumps({"action_status_by_id": {}}))
    cfg = SimpleNamespace(
        state_path=state_path,
        projects_json_path=pj,
        wiki_dir=tmp_path / "Wiki",
        anthropic_api_key="sk-ant-test",
        linear_api_key="lin_api_test",
        bot_token="bot",
        chat_id="chat",
        notify_fn=lambda **k: None,
    )
    cfg.wiki_dir.mkdir(parents=True, exist_ok=True)
    (cfg.wiki_dir / "plaud").mkdir(exist_ok=True)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _write_page(page_path, plaud_id="abc", title="Test", extra_fm=None):
    fm_lines = [
        "type: plaud-recording",
        f"plaud_id: {plaud_id}",
        "duration_human: 5m12s",
    ]
    if extra_fm:
        for k, v in extra_fm.items():
            fm_lines.append(f"{k}: {plaud_actions._serialize_yaml_value(v)}")
    text = "---\n" + "\n".join(fm_lines) + "\n---\n\n" + f"# {title}\n\nBody.\n"
    page_path.write_text(text)
    return page_path


@pytest.fixture(autouse=True)
def _no_kill_switch(monkeypatch):
    monkeypatch.delenv("PLAUD_ACTIONS_ENABLED", raising=False)


def test_process_skips_page_with_existing_tickets(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md",
                       extra_fm={"tickets": ["CCW-1", "CCW-2"], "action_status": "ok"})

    extract_called = MagicMock()
    monkeypatch.setattr(plaud_actions, "extract_actions", extract_called)

    batch_results: list = []
    plaud_actions.process(
        plaud_id="abc", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg,
    )
    extract_called.assert_not_called()
    assert len(batch_results) == 1
    assert batch_results[0].status == "skipped"


def test_process_skips_when_kill_switch_off(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAUD_ACTIONS_ENABLED", "0")
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md")

    extract_called = MagicMock()
    monkeypatch.setattr(plaud_actions, "extract_actions", extract_called)

    batch_results: list = []
    plaud_actions.process(plaud_id="abc", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg)
    extract_called.assert_not_called()


def test_process_happy_path_writes_frontmatter_and_files_tickets(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md", plaud_id="abc", title="Acme")

    monkeypatch.setattr(plaud_actions, "extract_actions",
        lambda **kw: plaud_actions.ActionExtraction(
            portfolio="ccw-crm", confidence=0.9, reasoning="ccw",
            actions=[plaud_actions.Action("Follow up", "by Friday", 2)]))
    monkeypatch.setattr(plaud_actions, "create_linear_issue",
        lambda **kw: plaud_actions.TicketRef(id="i1", identifier="CCW-247", url="u"))

    batch_results: list = []
    plaud_actions.process(plaud_id="abc", page_path=page,
        file_meta={"name": "Acme", "duration": 312000},
        batch_results=batch_results, cfg=cfg)

    assert len(batch_results) == 1
    assert batch_results[0].status == "ok"
    assert batch_results[0].tickets[0].identifier == "CCW-247"
    fm = plaud_actions.read_frontmatter(page)
    assert "CCW-247" in fm.get("tickets", "")
    assert fm.get("action_portfolio") == "ccw-crm"
    assert fm.get("action_status") == "ok"


def test_process_partial_failure_marks_partial(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md")

    monkeypatch.setattr(plaud_actions, "extract_actions",
        lambda **kw: plaud_actions.ActionExtraction(
            portfolio="ccw-crm", confidence=0.9, reasoning="",
            actions=[plaud_actions.Action(f"A{i}", "d", 3) for i in range(3)]))
    side = [plaud_actions.TicketRef("i1", "X-1", ""), None,
            plaud_actions.TicketRef("i3", "X-3", "")]
    monkeypatch.setattr(plaud_actions, "create_linear_issue", lambda **kw: side.pop(0))

    batch_results: list = []
    plaud_actions.process(plaud_id="abc", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg)

    assert batch_results[0].status == "partial"
    assert len(batch_results[0].tickets) == 2
    fm = plaud_actions.read_frontmatter(page)
    assert fm.get("action_status") == "partial"


def test_process_no_actions_marks_no_actions(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md")

    monkeypatch.setattr(plaud_actions, "extract_actions",
        lambda **kw: plaud_actions.ActionExtraction(
            portfolio="synthex", confidence=0.8, reasoning="memo", actions=[]))
    create_called = MagicMock()
    monkeypatch.setattr(plaud_actions, "create_linear_issue", create_called)

    batch_results: list = []
    plaud_actions.process(plaud_id="abc", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg)

    assert batch_results[0].status == "no_actions"
    create_called.assert_not_called()
    fm = plaud_actions.read_frontmatter(page)
    assert "tickets" not in fm
    assert fm.get("action_status") == "no_actions"
    assert fm.get("action_portfolio") == "synthex"


def test_process_low_confidence_routes_to_pi_dev_ops(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md")

    monkeypatch.setattr(plaud_actions, "extract_actions",
        lambda **kw: plaud_actions.ActionExtraction(
            portfolio="ccw-crm", confidence=0.3, reasoning="uncertain",
            actions=[plaud_actions.Action("A", "d", 3)]))
    seen_proj = []
    def fake_create(**kw):
        seen_proj.append(kw["project_id"])
        return plaud_actions.TicketRef("i", "X-1", "")
    monkeypatch.setattr(plaud_actions, "create_linear_issue", fake_create)

    batch_results: list = []
    plaud_actions.process(plaud_id="abc", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg)

    assert seen_proj == ["pi-proj"]
    assert batch_results[0].portfolio == "pi-dev-ops"


def test_process_auth_error_no_frontmatter_change(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md")

    monkeypatch.setattr(plaud_actions, "extract_actions",
        lambda **kw: plaud_actions._AuthError())

    batch_results: list = []
    plaud_actions.process(plaud_id="abc", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg)

    fm = plaud_actions.read_frontmatter(page)
    assert "tickets" not in fm
    assert "action_status" not in fm
    assert batch_results[0].status == "skipped"


def test_process_parse_failure_increments_state_attempts(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md")

    monkeypatch.setattr(plaud_actions, "extract_actions", lambda **kw: None)

    batch_results: list = []
    plaud_actions.process(plaud_id="abc-parsefail", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg)

    state = json.loads(cfg.state_path.read_text())
    assert state["action_status_by_id"]["abc-parsefail"]["attempts"] == 1


def test_process_skips_after_3_parse_failures(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    cfg.state_path.write_text(json.dumps({"action_status_by_id": {
        "abc-poison": {"status": "parse_failed", "attempts": 3, "last_error": ""},
    }}))
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md")

    extract_called = MagicMock()
    monkeypatch.setattr(plaud_actions, "extract_actions", extract_called)

    batch_results: list = []
    plaud_actions.process(plaud_id="abc-poison", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg)

    extract_called.assert_not_called()
    assert batch_results[0].status == "parse_failed"


def test_send_batch_digest_calls_notify_with_built_text(tmp_path):
    from types import SimpleNamespace
    notifs: list = []
    cfg = SimpleNamespace(
        bot_token="t", chat_id="c",
        notify_fn=lambda **k: notifs.append(k),
    )
    brs = [plaud_actions.BatchResult(
        plaud_id="a", title="Meeting", wiki_path="plaud/a",
        portfolio="ccw-crm",
        tickets=[plaud_actions.TicketRef("i", "CCW-1", "")],
        status="ok")]
    plaud_actions.send_batch_digest(cfg, brs)
    assert len(notifs) == 1
    assert "Meeting" in notifs[0]["text"]
    assert "CCW-1" in notifs[0]["text"]


def test_send_batch_digest_silent_when_no_tickets(tmp_path):
    from types import SimpleNamespace
    notifs: list = []
    cfg = SimpleNamespace(
        bot_token="t", chat_id="c",
        notify_fn=lambda **k: notifs.append(k),
    )
    brs = [plaud_actions.BatchResult(plaud_id="a", title="t",
        wiki_path="p", portfolio="x", tickets=[], status="no_actions")]
    plaud_actions.send_batch_digest(cfg, brs)
    assert notifs == []


def test_send_batch_digest_empty_list_silent(tmp_path):
    from types import SimpleNamespace
    notifs: list = []
    cfg = SimpleNamespace(
        bot_token="t", chat_id="c",
        notify_fn=lambda **k: notifs.append(k),
    )
    plaud_actions.send_batch_digest(cfg, [])
    assert notifs == []
