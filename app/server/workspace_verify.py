"""workspace_verify.py — run the target repo's own checks so the grade is not a guess.

`_phase_evaluate` grades a diff on COMPLETENESS / CORRECTNESS / CONCISENESS / FORMAT, and
its prompt asks "any bugs, logic errors, type issues, null refs, security vulnerabilities,
or broken tests?" — while having run nothing. The verdict is inference over a diff. That is
the RA-1109 failure the repo hardwired against ("HTTP 200, types compiling, and green lint
are not shipping") pointed at Pi-CEO's own generator: a session can be graded 9/10 on
CORRECTNESS with a suite that does not start.

This runs the repo's own checks in the workspace and hands the result to the evaluator as
evidence. It is deliberately NOT a gate:

  * A failing suite does not stop the session. It becomes context, so the evaluator can
    weigh a real failure instead of inferring correctness from shape.
  * It never fabricates a pass. "No runnable check" is reported as its own outcome,
    distinct from "checks passed" — the same distinction that made the vendored-file and
    git-enumeration bugs invisible when they were collapsed into one value.

The trust boundary is unchanged: the generator already runs Claude Code in this same
workspace with bypassPermissions, so executing the repo's declared test script grants no
capability that was not already granted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass

log = logging.getLogger("pi-ceo.workspace_verify")

# Bounded so a hung suite cannot hold a session open. Overridable for slow repos.
DEFAULT_TIMEOUT_S = int(os.environ.get("TAO_VERIFY_TIMEOUT_S", "300"))

NOT_RUN = "not_run"
PASSED = "passed"
FAILED = "failed"
TIMED_OUT = "timed_out"


@dataclass
class VerifyResult:
    status: str          # one of NOT_RUN / PASSED / FAILED / TIMED_OUT
    command: str         # "" when nothing runnable was found
    reason: str          # why, when status is NOT_RUN
    output_tail: str     # trailing output, for the evaluator to read

    @property
    def ran(self) -> bool:
        return self.status in (PASSED, FAILED, TIMED_OUT)


def detect_check(workspace: str) -> tuple[list[str], str]:
    """Return (argv, label) for the repo's own check, or ([], reason) when there is none.

    Only the repo's DECLARED check is run — a `test` script it defines, or pytest when the
    repo is laid out for it. Nothing is inferred beyond that.
    """
    pkg = os.path.join(workspace, "package.json")
    if os.path.isfile(pkg):
        try:
            with open(pkg, encoding="utf-8") as fh:
                scripts = (json.load(fh) or {}).get("scripts") or {}
            if scripts.get("test"):
                if os.path.isdir(os.path.join(workspace, "node_modules")):
                    return ["npm", "test", "--silent"], "npm test"
                return [], "package.json declares a test script but node_modules is absent"
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            log.debug("workspace_verify: package.json unreadable: %s", exc)

    has_tests_dir = os.path.isdir(os.path.join(workspace, "tests"))
    has_py_cfg = any(
        os.path.isfile(os.path.join(workspace, f))
        for f in ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")
    )
    if has_tests_dir and has_py_cfg:
        return ["python3", "-m", "pytest", "-q", "tests/"], "pytest"

    return [], "no declared test script and no pytest layout"


async def run_workspace_checks(
    workspace: str, timeout_s: int = DEFAULT_TIMEOUT_S
) -> VerifyResult:
    """Run the repo's own checks. Never raises — a broken check is data, not a crash."""
    if not workspace or not os.path.isdir(workspace):
        return VerifyResult(NOT_RUN, "", "workspace missing", "")

    argv, label = detect_check(workspace)
    if not argv:
        return VerifyResult(NOT_RUN, "", label, "")

    env = dict(os.environ)
    # Same hazard CLAUDE.md records: the claude CLI exports an EMPTY ANTHROPIC_API_KEY,
    # which children treat as "key mode, empty key" and fail auth on.
    if not env.get("ANTHROPIC_API_KEY"):
        env.pop("ANTHROPIC_API_KEY", None)
    env["CI"] = "1"

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
    except (OSError, ValueError) as exc:
        return VerifyResult(NOT_RUN, label, f"could not start: {exc}", "")

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return VerifyResult(TIMED_OUT, label, "", f"exceeded {timeout_s}s")

    tail = (stdout or b"").decode("utf-8", errors="replace")[-2000:]

    # "The runner is absent" is not "the tests failed". A cloned repo need not have pytest
    # installed, and `python3 -m pytest` exits non-zero either way — so reporting FAILED
    # here would hand the evaluator a fabricated test failure and pull CORRECTNESS down
    # for a change that was never exercised. Misattribution is worse than no signal.
    if proc.returncode != 0 and "No module named pytest" in tail:
        return VerifyResult(NOT_RUN, label, "pytest is not installed in this workspace", "")

    status = PASSED if proc.returncode == 0 else FAILED
    return VerifyResult(status, label, "", tail)


def format_for_evaluator(result: VerifyResult) -> str:
    """Render the result for the evaluator prompt.

    The NOT_RUN wording is deliberate. Saying nothing would let the evaluator keep scoring
    CORRECTNESS as though tests had passed; saying "no check ran" tells it the axis is
    unevidenced, which is the honest input to a grade.
    """
    if result.status == NOT_RUN:
        return (
            "VERIFICATION EVIDENCE: none. No check was run "
            f"({result.reason}). You have NOT seen this code execute — do not score "
            "CORRECTNESS as though a suite passed. Say so in your reason.\n\n"
        )
    if result.status == TIMED_OUT:
        return (
            f"VERIFICATION EVIDENCE: `{result.command}` TIMED OUT ({result.output_tail}). "
            "Treat correctness as unevidenced.\n\n"
        )
    verdict = "PASSED" if result.status == PASSED else "FAILED"
    return (
        f"VERIFICATION EVIDENCE: `{result.command}` {verdict}. This was actually executed "
        f"in the workspace. Output tail:\n{result.output_tail}\n\n"
    )
