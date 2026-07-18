from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "weekly_enhancement_loop", ROOT / "scripts" / "weekly_enhancement_loop.py"
)
assert SPEC and SPEC.loader
wel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wel)


def _completed(argv, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


@pytest.fixture(autouse=True)
def _isolate_hard_stop(monkeypatch, tmp_path):
    monkeypatch.setattr(wel, "HARD_STOP_FILE", tmp_path / "no-hard-stop")


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.invalid"], check=True)
    (path / "README.md").write_text("baseline\n")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "baseline"], check=True)


def test_model_tools_replace_shell_with_argument_vector_probe():
    tools = {tool["name"]: tool for tool in wel.TOOLS}

    assert "run_bash" not in tools
    assert tools["run_probe"]["input_schema"]["properties"]["argv"]["type"] == "array"


def test_probe_rejects_shell_and_network_commands(tmp_path):
    for argv in (
        ["bash", "-lc", "env"],
        ["curl", "https://example.invalid"],
        ["git", "push", "origin", "main"],
        ["python", "-c", "import os; print(os.environ)"],
    ):
        output = wel._exec_tool("run_probe", {"argv": argv}, tmp_path)
        assert output.startswith("ERROR: probe not allowed")


def test_model_probe_environment_excludes_inherited_secrets(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-openrouter-secret")
    monkeypatch.setenv("GH_ENHANCE_PAT", "fake-github-secret")

    def fake_run(argv, **kwargs):
        captured.update(kwargs["env"])
        return _completed(argv)

    monkeypatch.setattr(wel.subprocess, "run", fake_run)
    wel._exec_tool("run_probe", {"argv": ["git", "status", "--porcelain"]}, tmp_path)

    assert "OPENROUTER_API_KEY" not in captured
    assert "GH_ENHANCE_PAT" not in captured
    assert "GITHUB_TOKEN" not in captured
    assert set(captured) <= wel.MODEL_SUBPROCESS_ENV_KEYS
    assert Path(captured["HOME"]).is_relative_to(tmp_path)


def test_clone_uses_scoped_gh_token_without_persisting_it(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setenv("GH_ENHANCE_PAT", "fake-github-secret")

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return _completed(argv)

    monkeypatch.setattr(wel.subprocess, "run", fake_run)
    wel._clone("CleanExpo/Pi-Dev-Ops", tmp_path / "clone")

    assert captured["argv"][:3] == ["gh", "repo", "clone"]
    assert "fake-github-secret" not in " ".join(captured["argv"])
    assert captured["env"]["GH_TOKEN"] == "fake-github-secret"
    assert "OPENROUTER_API_KEY" not in captured["env"]
    assert not (tmp_path / "clone" / ".git" / "config").exists()


def test_repo_input_must_be_registered_cleanexpo_repo(monkeypatch, tmp_path):
    registry = tmp_path / "projects.json"
    registry.write_text(json.dumps({"projects": [{"repo": "CleanExpo/Pi-Dev-Ops"}]}))
    monkeypatch.setattr(wel, "REGISTRY", registry)

    assert wel.validate_repo("CleanExpo/Pi-Dev-Ops") == "CleanExpo/Pi-Dev-Ops"
    for value in (
        "OtherOrg/Pi-Dev-Ops",
        "CleanExpo/not-registered",
        "CleanExpo/Pi-Dev-Ops; touch /tmp/pwned",
        "CleanExpo/Pi-Dev-Ops --help",
        "../Pi-Dev-Ops",
    ):
        with pytest.raises(ValueError):
            wel.validate_repo(value)


def test_protected_paths_are_denied_before_write(tmp_path):
    protected = (
        ".github/workflows/pwn.yml",
        ".env",
        "config/.env.production",
        "app/server/auth.py",
        "app/server/config.py",
        "dashboard/middleware.ts",
        "dashboard/app/api/auth/route.ts",
        "dashboard/app/api/actions/kill/route.ts",
        "supabase/migrations/999_attack.sql",
        ".git/config",
    )

    for path in protected:
        output = wel._exec_tool("write_file", {"path": path, "content": "blocked"}, tmp_path)
        assert output.startswith("ERROR: protected path"), path
        assert not (tmp_path / path).exists()


def test_change_gate_rejects_protected_and_too_many_files(monkeypatch, tmp_path):
    monkeypatch.setattr(wel, "_changed_files", lambda _cwd: [f"file-{n}.txt" for n in range(6)])
    with pytest.raises(wel.PolicyViolation, match="changed-file ceiling"):
        wel._validate_changes(tmp_path)

    monkeypatch.setattr(wel, "_changed_files", lambda _cwd: [".github/workflows/pwn.yml"])
    with pytest.raises(wel.PolicyViolation, match="protected path"):
        wel._validate_changes(tmp_path)


def test_missing_authoritative_usage_cost_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(wel, "_openrouter_key", lambda: "fake-key")
    monkeypatch.setattr(wel, "_post", lambda *_args, **_kwargs: {"content": [], "stop_reason": "end_turn", "usage": {}})

    with pytest.raises(wel.CostAccountingError, match="usage.cost"):
        wel.run_phase("monitor", wel.MODEL_SCAN, "scan", tmp_path, 1, {"usd": 0.0})


def test_worst_case_request_is_reserved_before_call(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(wel, "_openrouter_key", lambda: "fake-key")
    monkeypatch.setattr(wel, "MAX_COST_USD", 0.000001)
    monkeypatch.setattr(wel, "_post", lambda *_args, **_kwargs: calls.append(True))

    with pytest.raises(wel.CostCeilingHit, match="reserve"):
        wel.run_phase("monitor", wel.MODEL_SCAN, "scan", tmp_path, 1, {"usd": 0.0})
    assert calls == []


def test_provider_cost_may_not_exceed_reserved_cost(monkeypatch, tmp_path):
    monkeypatch.setattr(wel, "_openrouter_key", lambda: "fake-key")
    monkeypatch.setattr(wel, "MAX_COST_USD", 100.0)
    monkeypatch.setattr(
        wel,
        "_post",
        lambda *_args, **_kwargs: {
            "content": [],
            "stop_reason": "end_turn",
            "usage": {"cost": 99.0},
        },
    )

    with pytest.raises(wel.CostAccountingError, match="reserved"):
        wel.run_phase("monitor", wel.MODEL_SCAN, "scan", tmp_path, 1, {"usd": 0.0})


def test_phase_has_hard_iteration_and_role_token_caps(monkeypatch, tmp_path):
    payloads = []
    monkeypatch.setattr(wel, "_openrouter_key", lambda: "fake-key")
    monkeypatch.setattr(wel, "MAX_COST_USD", 100.0)
    monkeypatch.setattr(wel, "MAX_PHASE_ITERS", 2)

    def fake_post(payload, *_args, **_kwargs):
        payloads.append(payload)
        return {
            "content": [{"type": "tool_use", "id": f"t{len(payloads)}", "name": "list_dir", "input": {}}],
            "stop_reason": "tool_use",
            "usage": {"cost": 0.000001},
        }

    monkeypatch.setattr(wel, "_post", fake_post)
    with pytest.raises(wel.PhaseLimitHit):
        wel.run_phase("monitor", wel.MODEL_SCAN, "scan", tmp_path, 1, {"usd": 0.0})

    assert len(payloads) == 2
    assert all(payload["max_tokens"] == wel.ROLE_MAX_TOKENS["monitor"] for payload in payloads)
    assert wel.MAX_PHASE_ITERS <= wel.ABSOLUTE_MAX_PHASE_ITERS


def test_unknown_model_without_pricing_is_rejected_before_call(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(wel, "_openrouter_key", lambda: "fake-key")
    monkeypatch.setattr(wel, "_post", lambda *_args, **_kwargs: calls.append(True))

    with pytest.raises(wel.CostAccountingError, match="pricing"):
        wel.run_phase("monitor", "unknown/provider-model", "scan", tmp_path, 1, {"usd": 0.0})
    assert calls == []


def test_repo_test_oracle_is_required(monkeypatch, tmp_path):
    monkeypatch.setattr(wel, "_changed_files", lambda _cwd: ["README.md"])
    with pytest.raises(wel.GateFailure, match="test oracle"):
        wel._run_repo_tests(tmp_path)


def test_repo_test_failure_blocks_all_outward_git(monkeypatch, tmp_path):
    repo = tmp_path / "pi-dev-ops"
    repo.mkdir()
    _init_repo(repo)
    monkeypatch.setattr(wel, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(wel, "_clone", lambda _repo, _dest: None)
    monkeypatch.setattr(wel, "run_phase", lambda role, *_args, **_kwargs: (
        '{"approved": true, "score": 9, "blocking_findings": []}' if role == "evaluator" else "ok"
    ))
    (repo / "README.md").write_text("changed\n")
    monkeypatch.setattr(wel, "_run_repo_tests", lambda _cwd: (_ for _ in ()).throw(wel.GateFailure("tests failed")))
    outward = []
    monkeypatch.setattr(wel, "_push_branch", lambda *_args: outward.append("push"))
    monkeypatch.setattr(wel, "_open_or_get_pr", lambda *_args: outward.append("pr"))

    with pytest.raises(wel.GateFailure, match="tests failed"):
        wel.enhance_repo("CleanExpo/Pi-Dev-Ops", False, {"usd": 0.0})
    assert outward == []


def test_evaluator_must_return_structured_score_of_at_least_eight():
    approved = wel._parse_evaluation('{"approved": true, "score": 8, "blocking_findings": []}')
    assert approved["score"] == 8

    for text in (
        "looks good to me",
        '{"approved": true, "score": 7, "blocking_findings": []}',
        '{"approved": false, "score": 10, "blocking_findings": []}',
        '{"approved": true, "score": 10, "blocking_findings": ["unsafe"]}',
    ):
        with pytest.raises(wel.GateFailure):
            wel._parse_evaluation(text)


def test_checked_git_raises_instead_of_false_green(monkeypatch, tmp_path):
    monkeypatch.setattr(
        wel,
        "_git",
        lambda *_args: _completed(["git"], returncode=1, stderr="fake git failure"),
    )
    with pytest.raises(wel.GitFailure, match="fake git failure"):
        wel._git_checked(tmp_path, "status", "--porcelain")


def test_dry_run_creates_no_branch_commit_push_or_pr(monkeypatch, tmp_path):
    repo = tmp_path / "pi-dev-ops"
    repo.mkdir()
    _init_repo(repo)
    before_head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    monkeypatch.setattr(wel, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(wel, "_clone", lambda _repo, _dest: None)

    def fake_phase(role, *_args, **_kwargs):
        if role == "generator":
            (repo / "README.md").write_text("changed\n")
        if role == "evaluator":
            return '{"approved": true, "score": 9, "blocking_findings": []}'
        return "ok"

    monkeypatch.setattr(wel, "run_phase", fake_phase)
    monkeypatch.setattr(wel, "_run_repo_tests", lambda _cwd: [["python", "-m", "pytest", "tests", "-x", "-q"]])
    monkeypatch.setattr(wel, "_open_or_get_pr", lambda *_args: pytest.fail("PR attempted in dry-run"))
    monkeypatch.setattr(wel, "_push_branch", lambda *_args: pytest.fail("push attempted in dry-run"))

    result = wel.enhance_repo("CleanExpo/Pi-Dev-Ops", True, {"usd": 0.0})
    after_head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    branches = subprocess.run(
        ["git", "-C", str(repo), "branch", "--format=%(refname:short)"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert result["outcome"] == "dry-run"
    assert before_head == after_head
    assert branches == ["main"]


def test_existing_verified_pr_is_idempotently_reused(monkeypatch):
    calls = []

    def fake_gh(repo, argv):
        calls.append(argv)
        if argv[:3] == ["pr", "list", "--head"]:
            return [{"url": "https://github.com/CleanExpo/Pi-Dev-Ops/pull/1"}]
        if argv[:2] == ["pr", "view"]:
            return {
                "url": "https://github.com/CleanExpo/Pi-Dev-Ops/pull/1",
                "state": "OPEN",
                "headRefName": "enhance-review/weekly-2026-07-17",
                "baseRefName": "main",
            }
        pytest.fail(f"unexpected gh call: {argv}")

    monkeypatch.setattr(wel, "_gh_json", fake_gh)
    evidence = wel._open_or_get_pr(
        "CleanExpo/Pi-Dev-Ops", "enhance-review/weekly-2026-07-17", "2026-07-17"
    )

    assert evidence["url"].endswith("/pull/1")
    assert not any(argv[:3] == ["pr", "create", "--repo"] for argv in calls)


def test_null_or_unverifiable_pr_can_never_be_recorded_opened(monkeypatch):
    responses = iter([[], None])
    monkeypatch.setattr(wel, "_gh_json", lambda *_args: next(responses))

    with pytest.raises(wel.GateFailure, match="PR create"):
        wel._open_or_get_pr(
            "CleanExpo/Pi-Dev-Ops", "enhance-review/weekly-2026-07-17", "2026-07-17"
        )


def test_workflow_quotes_dispatch_input_and_does_not_expose_secrets_job_wide():
    workflow = (ROOT / ".github" / "workflows" / "weekly-enhancement-loop.yml").read_text()

    job_env = workflow.split("steps:", 1)[0]
    assert "OPENROUTER_API_KEY" not in job_env
    assert "GH_ENHANCE_PAT" not in job_env
    assert 'args+=(--repo "$TARGET_REPO")' in workflow
    assert "format('--repo {0}'" not in workflow
    assert "OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}" in workflow
    assert "GH_ENHANCE_PAT: ${{ secrets.GH_ENHANCE_PAT }}" in workflow
