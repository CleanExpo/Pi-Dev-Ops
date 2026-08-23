"""Focused tests for Grill admission and dispatch."""

from __future__ import annotations

from tests._senior_harness_setup_support import (
    Path,
    REPO_ROOT,
    SCRIPT_DIR,
    SHARED_UNDERSTANDING_PHRASE,
    SetupError,
    _delivery,
    _init_repo,
    admit_startup,
    answer_pending_question,
    build_setup_contract,
    confirm_shared_understanding,
    guard_dispatch,
    handle_hook,
    json,
    pytest,
    start_session,
    subprocess,
    sys,
)


def _grill_pretool(
    base: dict[str, str],
    tool_name: str,
    tool_input: dict,
    roots: list[Path] | None = None,
) -> dict:
    return handle_hook(
        {
            **base,
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input,
        },
        surface="codex",
        event="PreToolUse",
        skill_search_roots=roots,
    )


def _ready_grill_delivery(objective: str) -> tuple[dict, dict]:
    receipt = admit_startup(
        build_setup_contract(
            objective, REPO_ROOT, surface="codex", interaction="grill-me"
        )
    )
    payload = _delivery(objective)
    for move in payload["move_graph"][:6]:
        move["status"] = "passed"
    payload["move_graph"][6]["status"] = "ready"
    return receipt, payload


def _grill_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path, list[Path]]:
    project = tmp_path / "hook-project"
    _init_repo(project)
    tracked = project / "README.md"
    state_root = tmp_path / "state"
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(state_root))
    return project, tracked, state_root, [REPO_ROOT / "skills"]


def _new_grill_session(tmp_path: Path, objective: str) -> tuple[Path, dict]:
    sketch = tmp_path / "vault" / "Sketches" / "01-recovery.md"
    sketch.parent.mkdir(parents=True)
    sketch.write_text("# Recovery\n", encoding="utf-8")
    grill = start_session(
        objective,
        sketch,
        [
            {
                "leaf_id": "market",
                "kind": "human-decision",
                "depends_on": [],
                "question": "Which market ships first?",
                "recommendation": "Start with the internal proving ground.",
                "rationale": "It produces evidence before external commitments.",
            }
        ],
        materialization_path=sketch.parent.parent / "Grills" / "01-recovery.md",
    )
    return sketch, grill


def _run_external_grill_setup(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "setup_driver.py"),
            "start",
            "/grill-me shape the fresh project",
            "--project",
            str(project),
            "--surface",
            "codex",
            "--interaction",
            "grill-me",
            "--strict-clean",
            "--skill-root",
            str(REPO_ROOT / "skills"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_grill_interaction_binds_skill_and_routes_as_research() -> None:
    contract = build_setup_contract(
        "/grill-me shape the recovery workflow",
        REPO_ROOT,
        surface="codex",
        interaction="grill-me",
    )

    assert contract["interaction"] == "grill-me"
    assert contract["required_skills"]["grill-me"]["name"] == "grill-me"
    assert contract["routing_request"]["signals"]["modalities"] == ["text"]
    assert contract["routing_request"]["signals"]["required_tools"] == [
        "read",
        "research",
    ]


def test_grill_hook_denies_project_action_but_allows_evidence_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path / "state"))
    base = {"session_id": "grill-1", "cwd": str(REPO_ROOT)}
    handle_hook(
        {
            **base,
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/grill-me shape recovery",
        },
        surface="codex",
        event="UserPromptSubmit",
    )

    read_result = _grill_pretool(base, "Read", {"file_path": "CONTEXT.md"})
    assert "permissionDecision" not in read_result["hookSpecificOutput"]

    search_result = _grill_pretool(
        base, "exec_command", {"cmd": "rg -n recovery CONTEXT.md"}
    )
    assert "permissionDecision" not in search_result["hookSpecificOutput"]

    for tool_name, tool_input in (
        ("Edit", {"file_path": "CONTEXT.md"}),
        ("exec_command", {"cmd": "git push origin main"}),
        ("exec_command", {"cmd": "rg recovery $(touch escaped)"}),
        ("exec_command", {"cmd": "sed -i backup CONTEXT.md"}),
        ("exec_command", {"cmd": "sed -n 'w /tmp/grill-sed-write' CONTEXT.md"}),
        ("exec_command", {"cmd": "git diff --output=escaped.diff"}),
        (
            "exec_command",
            {"cmd": "python3 /tmp/grill_session.py show --state /tmp/state.json"},
        ),
        ("mcp__attacker__read", {"action": "mutate"}),
        ("spawn_agent", {"task": "change the project"}),
    ):
        denied = _grill_pretool(base, tool_name, tool_input)
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_grill_blocks_dispatch_until_exact_shared_understanding_and_sketch_remains_bound(
    tmp_path: Path,
) -> None:
    objective = "/grill-me shape recovery"
    receipt, payload = _ready_grill_delivery(objective)
    sketch, grill = _new_grill_session(tmp_path, objective)

    with pytest.raises(SetupError, match="shared-understanding session"):
        guard_dispatch(payload, receipt, "M07")
    with pytest.raises(SetupError, match="shared understanding is confirmed"):
        guard_dispatch(payload, receipt, "M07", grill_session=grill)

    grill = answer_pending_question(grill, "Internal proving ground first.", "DECIDED")
    grill = confirm_shared_understanding(grill, SHARED_UNDERSTANDING_PHRASE)
    assert (
        guard_dispatch(payload, receipt, "M07", grill_session=grill)["status"]
        == "admitted"
    )
    with pytest.raises(SetupError, match="cannot authorize mutating"):
        guard_dispatch(payload, receipt, "M12", grill_session=grill)

    sketch.write_text("# Drifted recovery\n", encoding="utf-8")
    with pytest.raises(SetupError, match="sketch changed"):
        guard_dispatch(payload, receipt, "M07", grill_session=grill)


def test_explicit_grill_setup_admits_a_fresh_external_project(tmp_path: Path) -> None:
    project = tmp_path / "fresh-project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=project, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True)
    (project / "README.md").write_text("# Fresh project\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=project, check=True)

    result = _run_external_grill_setup(project)

    setup = json.loads(result.stdout)["setup_contract"]
    assert setup["repository"]["worktree"] == str(project.resolve())
    assert setup["repository"]["dirty"] is False
    assert setup["interaction"] == "grill-me"
    assert set(setup["required_skills"]) == {
        "senior-harness",
        "model-router",
        "unlazy",
        "grill-me",
    }


def test_grill_hook_rechecks_project_bytes_after_first_tool_and_session_ids_do_not_collide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, tracked, state_root, roots = _grill_project(tmp_path, monkeypatch)

    for session_id in ("a/b", "a_b"):
        base = {"session_id": session_id, "cwd": str(project)}
        handle_hook(
            {
                **base,
                "hook_event_name": "UserPromptSubmit",
                "prompt": "/grill-me shape hook project",
            },
            surface="codex",
            event="UserPromptSubmit",
            skill_search_roots=roots,
        )
    assert len(list(state_root.rglob("*.json"))) == 2

    base = {"session_id": "a/b", "cwd": str(project)}
    first = _grill_pretool(base, "Read", {}, roots)
    assert "permissionDecision" not in first["hookSpecificOutput"]
    tracked.write_text("# Drifted\n", encoding="utf-8")
    second = _grill_pretool(base, "Read", {}, roots)
    assert "permissionDecision" not in second["hookSpecificOutput"]
    assert "recovery-only read" in second["hookSpecificOutput"]["additionalContext"]
    assert (
        "worktree_state_digest changed"
        in second["hookSpecificOutput"]["additionalContext"]
    )

    denied_write = _grill_pretool(base, "Write", {})
    assert denied_write["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert (
        "worktree_state_digest changed"
        in denied_write["hookSpecificOutput"]["permissionDecisionReason"]
    )
