from __future__ import annotations

import copy
import json
import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "skills" / "senior-harness" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from grill_session import (  # noqa: E402
    SHARED_UNDERSTANDING_PHRASE,
    answer_pending_question,
    confirm_shared_understanding,
    start_session,
)
from senior_harness import ContractError, digest, validate_contract  # noqa: E402
import setup_driver as setup_driver_module  # noqa: E402
from setup_driver import (  # noqa: E402
    SetupError,
    admit_startup,
    build_setup_contract,
    guard_dispatch,
    handle_hook,
    validate_startup_receipt,
)

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "senior_harness_self_host.json"

__all__ = [
    "ContractError",
    "FIXTURE",
    "Path",
    "REPO_ROOT",
    "SCRIPT_DIR",
    "SHARED_UNDERSTANDING_PHRASE",
    "SetupError",
    "_delivery",
    "_global_hook",
    "_global_hook_result",
    "_grill_command",
    "_hermetic_repository_contract",
    "_init_repo",
    "_observe_adapter",
    "_pending_file",
    "_pretool",
    "_receipt",
    "_rehash_receipt",
    "_start_hook_session",
    "_tamper_env",
    "admit_startup",
    "answer_pending_question",
    "build_setup_contract",
    "confirm_shared_understanding",
    "copy",
    "digest",
    "guard_dispatch",
    "handle_hook",
    "json",
    "os",
    "pytest",
    "setup_driver_module",
    "shlex",
    "start_session",
    "stat",
    "subprocess",
    "sys",
    "validate_contract",
    "validate_startup_receipt",
]


def _receipt(objective: str = "Create the setup driver") -> dict:
    contract = build_setup_contract(objective, REPO_ROOT, surface="codex")
    return admit_startup(contract)


def _checkout_base_sha(head: str) -> str:
    """Use a real parent when available, or HEAD in a shallow checkout."""
    parent = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD~1^{commit}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    resolved = parent.stdout.strip()
    return resolved if parent.returncode == 0 and resolved else head


def _delivery(objective: str = "Create the setup driver") -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["literal_request"] = objective
    payload["authorized_scope"] = [objective]
    payload["task_id"] = digest({"task": objective})[7:23]
    payload["repository"]["worktree"] = str(REPO_ROOT)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    payload["repository"]["candidate_sha"] = head
    payload["repository"]["base_sha"] = _checkout_base_sha(head)
    return payload


def _rehash_receipt(receipt: dict) -> None:
    contract = receipt.get("setup_contract")
    if isinstance(contract, dict):
        unsigned_contract = dict(contract)
        unsigned_contract.pop("setup_contract_digest", None)
        contract["setup_contract_digest"] = digest(unsigned_contract)
    unsigned_receipt = dict(receipt)
    unsigned_receipt.pop("receipt_integrity_digest", None)
    unsigned_receipt.pop("receipt_seal", None)
    receipt["receipt_integrity_digest"] = digest(unsigned_receipt)
    # Tests that intentionally model legitimate control-code drift need a
    # receipt issued by the Harness, not an attacker recomputing public hashes.
    receipt["receipt_seal"] = setup_driver_module._receipt_seal(receipt)


def _start_hook_session(
    state_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_id: str,
    prompt: str = "Develop the Senior Harness",
) -> tuple[dict[str, str], Path]:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(state_root))
    base = {"session_id": session_id, "cwd": str(REPO_ROOT)}
    handle_hook(
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": prompt},
        surface="claude",
        event="UserPromptSubmit",
    )
    state_path = setup_driver_module._state_path(REPO_ROOT.resolve(), session_id)
    assert state_path.is_file()
    return base, state_path


def _observe_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, surface: str = "codex"
) -> Path:
    """Publish observed capacity evidence; hook presence alone proves nothing."""
    receipt_path = tmp_path / f"{surface}-adapter-receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "surface": surface,
                "capacity": True,
                "isolation": True,
                "signed_dispatch": True,
                "cancellation": True,
                "adapter_signature": "test-observed-adapter-signature",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(setup_driver_module.ADAPTER_RECEIPT_ENV, str(receipt_path))
    return receipt_path


def _pretool(base: dict[str, str], tool_name: str) -> dict:
    return handle_hook(
        {
            **base,
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": {},
        },
        surface="claude",
        event="PreToolUse",
    )


def _global_hook(event: str, payload: dict, env: dict[str, str]) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "setup_driver.py"),
            "hook",
            "--surface",
            "claude",
            "--event",
            event,
            "--allow-non-git",
        ],
        input=json.dumps({**payload, "hook_event_name": event}),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)["hookSpecificOutput"]


def _global_hook_result(event: str, payload: dict, env: dict[str, str]) -> dict:
    """Full driver output, including the top-level refusal channel."""
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "setup_driver.py"),
            "hook",
            "--surface",
            "claude",
            "--event",
            event,
            "--allow-non-git",
        ],
        input=json.dumps({**payload, "hook_event_name": event}),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _tamper_env(tmp_path: Path) -> dict[str, str]:
    return dict(
        os.environ,
        SENIOR_HARNESS_STATE_DIR=str(tmp_path / "state"),
        SENIOR_HARNESS_SEAL_KEY_FILE=str(tmp_path / "seal.key"),
    )


def _pending_file(tmp_path: Path) -> Path:
    pending = list((tmp_path / "state" / "pending-project").glob("*.json"))
    assert len(pending) == 1, pending
    return pending[0]


def _grill_command(*argv: str) -> dict:
    return {
        "session_id": "grill-classification",
        "cwd": str(REPO_ROOT),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": shlex.join(
                [sys.executable, str(SCRIPT_DIR / "grill_session.py"), *argv]
            )
        },
    }


def _init_repo(project: Path) -> str:
    """Create a one-commit checkout owned by the caller and return its HEAD."""
    project.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=project, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True)
    (project / "README.md").write_text("# Base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=project, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _hermetic_repository_contract(tmp_path: Path) -> tuple[dict, Path, str, str]:
    """A delivery contract bound to a two-commit checkout the test owns outright."""
    project = tmp_path / "ancestry-project"
    first = _init_repo(project)
    (project / "README.md").write_text("# Candidate\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-qam", "candidate"], cwd=project, check=True)
    second = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    contract = _delivery()
    contract["repository"] = {
        "base_sha": first,
        "candidate_sha": second,
        "worktree": str(project.resolve()),
    }
    return contract, project, first, second
