"""cron_fire_script.py — the generic script-subprocess trigger.

Extracted from ``cron_triggers.py`` so that module keeps shrinking as new
trigger types are added to its dispatcher (CLAUDE.md § Conventions: extract when
you touch a file over the length ceiling; never add to it).

Handles the trigger types that are "run this script and log the outcome":
``analyse_lessons``, ``fallback_dryrun``, ``zte_v2_score``, ``script`` and
``capability_loop``.

    grep -n "_fire_script_trigger" app/server/cron_handler_registry.py
"""
import asyncio
import sys
from pathlib import Path

SCRIPT_TIMEOUT_SECONDS = 300
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _python() -> str:
    """The interpreter to run trigger scripts with.

    Never bare ``python3``: the machine default may be too old to import this
    repo at all (CLAUDE.md records 3.9.6 failing on `str | None` syntax), so a
    trigger would die on an import error that looks like a broken script. Prefer
    the repo venv, and fall back to the interpreter already running this server
    — which is the correct one in a container, where no `.venv` exists.
    """
    venv = _REPO_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def _command_for(script: str) -> list[str]:
    """Build the argv for a trigger's `script` field, normalising the interpreter.

    A script may be written either as a bare path ("scripts/foo.py args") or with
    its own leading interpreter ("python scripts/foo.py"). Both are rewritten to
    run under `_python()`, so neither form can escape into a stray interpreter.
    """
    parts = script.split()
    if parts and Path(parts[0]).name.startswith("python"):
        parts = parts[1:]
    return [_python(), *parts]


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    """Kill a timed-out child and reap it.

    `asyncio.wait_for` cancels the `communicate()` coroutine; it does NOT stop
    the process. Without this the script keeps running unsupervised after the
    trigger has given up on it, and every subsequent fire adds another orphan.
    """
    try:
        proc.kill()
    except ProcessLookupError:
        return  # already exited between the timeout and the kill
    await proc.wait()


async def _fire_script_trigger(trigger: dict, log_) -> None:
    """Fire a script-based trigger (analyse_lessons, etc.) as a subprocess."""
    script = trigger.get("script", "")
    if not script:
        log_.warning("Script trigger id=%s has no 'script' field — skipped", trigger["id"])
        return
    log_.info("Firing script trigger id=%s script=%s", trigger["id"], script)
    proc = await asyncio.create_subprocess_exec(
        *_command_for(script),
        cwd=str(_REPO_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=SCRIPT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        await _terminate(proc)
        log_.error(
            "Script trigger id=%s timed out after %ds — child killed",
            trigger["id"], SCRIPT_TIMEOUT_SECONDS,
        )
        raise
    if proc.returncode != 0:
        log_.error(
            "Script trigger id=%s exited %d: %s",
            trigger["id"], proc.returncode,
            stderr.decode("utf-8", errors="replace")[:500],
        )
    else:
        log_.info("Script trigger id=%s complete (rc=0)", trigger["id"])
