"""An unavailable signed control plane must DENY dispatch, not crash.

``_has_signed_dispatch_admission`` imports ``control_plane`` lazily, inside a
``try`` whose ``except`` originally listed only OSError/ValueError/KeyError/
TypeError/SetupError. ``ImportError`` was not among them, so on any checkout
where the control plane is absent the hook raised ``ModuleNotFoundError`` out of
a PreToolUse hook instead of returning a decision.

That matters because this slice deliberately does NOT vendor ``control_plane``:
it reaches ``swarm.unlazy_scheduler``, which is not on main, and the signed
dispatch path it serves is codex-surface only. The correct behaviour for an
unreachable control plane is the fail-closed one — refuse the dispatch.

The probe runs OUT OF PROCESS on purpose. Importing ``setup_driver`` in-process
executes its module-level ``sys.path.insert`` for both the scripts directory and
the repository root, which leaks into every test collected afterwards; doing that
at import time made an unrelated swarm gate test fail on path resolution while
still passing in isolation. A subprocess keeps the interpreter this suite runs in
untouched.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "skills" / "senior-harness" / "scripts"

_PROBE = """
import json, sys
sys.path.insert(0, {script_dir!r})
import setup_driver
payload = json.loads(sys.argv[1])
print(json.dumps(setup_driver._has_signed_dispatch_admission(
    payload, {repo_root!r}, {{"setup_contract": {{}}}}
)))
"""


def _admits(payload: dict) -> bool:
    """Return the driver's dispatch decision, or fail loudly if it crashed."""
    probe = _PROBE.format(script_dir=str(SCRIPT_DIR), repo_root=str(REPO_ROOT))
    result = subprocess.run(
        [sys.executable, "-c", probe, json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        "the dispatch check raised instead of returning a decision:\n" + result.stderr[-2000:]
    )
    return json.loads(result.stdout.strip())


def _dispatch_payload(tmp_path: Path) -> dict:
    """A payload complete enough to reach the lazy control-plane import.

    Every key in the driver's ``required`` tuple must be a non-empty string, or
    the function short-circuits before the import and the test would pass for
    the wrong reason.
    """
    return {
        "tool_name": "senior_harness_dispatch",
        "tool_input": {
            "receipt_path": str(tmp_path / "receipt.json"),
            "plan_path": str(tmp_path / "plan.json"),
            "routing_request_path": str(tmp_path / "route.json"),
            "state_path": str(tmp_path / "state.json"),
            "node_id": "node-1",
            "worker_context_id": "worker-1",
        },
    }


def test_absent_control_plane_denies_dispatch_instead_of_raising(tmp_path: Path) -> None:
    assert _admits(_dispatch_payload(tmp_path)) is False


def test_dispatch_payload_missing_a_required_key_is_denied(tmp_path: Path) -> None:
    """The short-circuit path stays closed too, so the test above is specific."""
    payload = _dispatch_payload(tmp_path)
    del payload["tool_input"]["state_path"]

    assert _admits(payload) is False
