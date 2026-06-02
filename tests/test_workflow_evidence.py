from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / ".harness" / "workflows" / "validate_workflow_evidence.py"

spec = importlib.util.spec_from_file_location("workflow_validator", VALIDATOR_PATH)
validator = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(validator)


def _manifest(tmp_path: Path, *, max_changed_files: int = 12) -> Path:
    data = {
        "workflow_id": "senior-engineer-build-loop",
        "intent": "feature",
        "risk": "medium",
        "models": {"planner": "gpt-5.5", "reviewer": "gpt-5.5"},
        "budgets": {
            "max_agents": 6,
            "max_turns_per_agent": 8,
            "max_wall_minutes": 60,
            "max_changed_files": max_changed_files,
        },
        "scope": {
            "allowed_paths": [],
            "denied_paths": [".env", ".env.*", "secrets/**", ".git/**"],
            "expected_change_paths": [],
        },
        "verification": {
            "required_commands": ["python -m py_compile src/tao/skills.py"],
            "required_live_checks": [],
            "requires_independent_review": True,
            "evidence_path": ".harness/workflows/runs/test.md",
        },
        "governance": {
            "requires_board_gate": False,
            "allows_push": False,
            "allows_pr": False,
            "allows_secret_change": False,
            "allows_destructive_migration": False,
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _evidence(tmp_path: Path, *, reviewer: str = "reviewer-agent", decision: str = "pass") -> Path:
    path = tmp_path / "run.md"
    path.write_text(
        """# Senior Engineer Workflow Evidence

- Workflow ID: senior-engineer-build-loop
- Date: 2026-06-02
- Operator: test
- Repo: repo
- Branch: test
- Ticket / request: none
- Intent: feature
- Risk: medium

## Scope

Expected change paths:
- src/tao/skills.py

Actual changed files:
- src/tao/skills.py

Denied paths touched: none

## Connections

Touched systems:
- src/tao/skills.py

Data/auth path:
- intent selection loads senior-engineer-workflow before implementation skills.

Existing tests or probes:
- python -m py_compile src/tao/skills.py

## Plan

Minimal plan executed:
- wire the workflow skill into intent routing.

## Verification

Commands run:

```text
python -m py_compile src/tao/skills.py PASS exit_code=0
```

Live checks / browser checks:
- not applicable: routing-only backend change.

## Independent review

Implementer: implementer-agent
Reviewer: {reviewer}
Findings:
- scope, tests, and bloat accepted.
Decision: {decision}

## Token and bloat controls

- Agents used: 1
- Model routing: senior_engineer.planner top; senior_engineer.challenger cheap
- Max changed files budget: 12
- Actual changed files: 1
- Side quests converted to follow-ups: none

## Blockers

None.

## Follow-up tickets

None.

## Final state

complete
""".format(reviewer=reviewer, decision=decision),
        encoding="utf-8",
    )
    return path


def test_validator_accepts_complete_evidence(tmp_path):
    manifest = _manifest(tmp_path)
    evidence = _evidence(tmp_path)
    assert validator.main_for_test(str(manifest), str(evidence), repo=tmp_path) == 0


def test_validator_rejects_template_placeholders(tmp_path):
    manifest = _manifest(tmp_path)
    evidence = _evidence(tmp_path)
    text = evidence.read_text(encoding="utf-8").replace("complete", "complete / blocked / rolled back", 1)
    evidence.write_text(text, encoding="utf-8")
    assert validator.main_for_test(str(manifest), str(evidence), repo=REPO_ROOT) == 1


def test_validator_requires_independent_reviewer(tmp_path):
    manifest = _manifest(tmp_path)
    evidence = _evidence(tmp_path, reviewer="implementer-agent")
    assert validator.main_for_test(str(manifest), str(evidence), repo=REPO_ROOT) == 1


def test_validator_resolves_repo_root_from_nested_harness_manifest():
    manifest_path = REPO_ROOT / ".harness" / "workflows" / "runs" / "example.manifest.json"
    assert validator._repo_from_manifest_path(manifest_path) == REPO_ROOT


def test_validator_uses_evidence_actual_changed_files_as_lane_scope(tmp_path):
    manifest = _manifest(tmp_path, max_changed_files=1)
    evidence = _evidence(tmp_path)
    dirty_repo = tmp_path / "dirty"
    dirty_repo.mkdir()
    subprocess.run(["git", "init"], cwd=dirty_repo, check=True, capture_output=True)
    for index in range(3):
        (dirty_repo / f"unrelated-{index}.txt").write_text("dirty", encoding="utf-8")
    assert validator.main_for_test(str(manifest), str(evidence), repo=dirty_repo) == 0


def test_runner_init_creates_run_files():
    result = subprocess.run(
        [
            "python",
            ".harness/workflows/senior_engineer_workflow.py",
            "init",
            "--intent",
            "feature",
            "--risk",
            "medium",
            "--expected-path",
            ".harness/workflows/**",
            "--required-command",
            "python -m py_compile .harness/workflows/validate_workflow_evidence.py .harness/workflows/senior_engineer_workflow.py",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "manifest=" in result.stdout
    assert "evidence=" in result.stdout
    for line in result.stdout.splitlines():
        if line.startswith(("manifest=", "evidence=")):
            Path(line.split("=", 1)[1]).unlink(missing_ok=True)
