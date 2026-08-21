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
import signal
import sys
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


# Everything the child needs to find an interpreter, resolve packages and behave as CI.
# Nothing else. Deliberately an ALLOW-list: a deny-list of known-secret names silently
# admits the next credential anyone adds.
_ENV_ALLOW = (
    "PATH", "HOME", "USER", "SHELL", "LANG", "LC_ALL", "TMPDIR", "TZ",
    "NODE_PATH", "NVM_DIR", "NPM_CONFIG_CACHE", "NPM_CONFIG_PREFIX",
    "PYTHONPATH", "PYTHONHASHSEED", "VIRTUAL_ENV", "SYSTEMROOT",
)


def _child_env() -> dict:
    """The minimal environment handed to a cloned repo's test command.

    This process holds GITHUB_TOKEN, LINEAR_API_KEY, Stripe, Supabase service-role and
    session secrets. Passing `dict(os.environ)` handed all of them to a third-party
    repository's declared test script on every evaluate phase. Two independent reviewers
    flagged it; the second called it blocking, and it is: the earlier defence — that the
    generator's Claude Code already runs in that workspace with the same exposure — argues
    the boundary was already crossed elsewhere, not that crossing it again deterministically
    and without any judgement in the loop is safe.

    An allow-list, not a deny-list. `CI=1` is set because test runners key non-interactive
    behaviour off it. ANTHROPIC_API_KEY is deliberately absent: the child has no business
    calling a model, and CLAUDE.md records that the claude CLI exports it EMPTY, which
    children then treat as "key mode, empty key" and fail auth on.
    """
    env = {k: os.environ[k] for k in _ENV_ALLOW if k in os.environ}
    env["CI"] = "1"
    return env


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
        return [sys.executable, "-m", "pytest", "-q", "tests/"], "pytest"

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

    env = _child_env()

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            # Own process group, so the timeout below can kill the whole tree. A test
            # script routinely spawns dev servers, watchers and workers; killing only the
            # direct child leaves those orphaned, and on the long-lived Railway container
            # they accumulate across every session that ever timed out.
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        return VerifyResult(NOT_RUN, label, f"could not start: {exc}", "")

    async def kill_and_drain() -> None:
        """Stop the isolated process group and finish pipe cleanup."""
        try:
            # start_new_session=True makes the child's PID the process-group
            # ID. Use that stable ID directly: the leader may already have
            # exited while a descendant still owns stdout.
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass

        # Reap the process and drain its pipes before the caller's event loop
        # closes. The bound prevents an escaped descendant from holding the
        # verifier open indefinitely.
        try:
            await asyncio.wait_for(proc.communicate(), timeout=5)
        except (asyncio.TimeoutError, OSError):
            pass

    timed_out = False
    stdout = b""
    try:
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            timed_out = True
            await kill_and_drain()
        except asyncio.CancelledError:
            # Session aborts and hard stops must not orphan the repo's test
            # process tree. Clean it up, then preserve cancellation semantics.
            await kill_and_drain()
            raise
    finally:
        # `communicate()` waits for exit, but on very short-lived children
        # CPython can retain an open subprocess transport until garbage
        # collection. Close it while its loop is alive. asyncio's Process has
        # no public close method on the supported Python versions.
        transport = getattr(proc, "_transport", None)
        if transport is not None:
            transport.close()

    if timed_out:
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
