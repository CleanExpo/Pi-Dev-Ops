"""RA-7252: the manifest generator must refuse the script-path invocation.

Run as `python3 swarm/agentskills_manifest.py` the module is not inside a package,
so its relative imports fail. The old behaviour was a bare ImportError naming a
relative-import problem — after writing nothing and leaving a clean tree.

That combination is what makes a CI guard useless rather than merely noisy: a
regenerate-then-`git diff --exit-code` gate passes on stale content whenever the
generator no-ops. A guard whose generator no-ops is a guard that always passes.

These tests are deliberately side-effect free. The refusal happens before any
write, so nothing here regenerates the manifest or touches the working tree.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "swarm" / "agentskills_manifest.py"


def _run_script_path() -> subprocess.CompletedProcess[str]:
    """Invoke the generator the wrong way — by script path."""
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )


def test_script_path_invocation_is_refused() -> None:
    """It must exit non-zero rather than appear to succeed."""
    result = _run_script_path()
    assert result.returncode != 0, "a no-op generator must not report success"


def test_refusal_names_the_working_command() -> None:
    """The message has to be actionable, not a relative-import red herring."""
    result = _run_script_path()
    assert "python3 -m swarm.agentskills_manifest" in result.stderr
    assert "ImportError" not in result.stderr, (
        "the bare ImportError names the wrong problem; the guard should preempt it"
    )


def test_refusal_writes_nothing() -> None:
    """The refusal must not mutate the manifest it declined to regenerate."""
    before = (REPO_ROOT / "agentskills.json").read_bytes()
    _run_script_path()
    assert (REPO_ROOT / "agentskills.json").read_bytes() == before
