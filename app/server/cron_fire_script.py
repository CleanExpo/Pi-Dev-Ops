"""cron_fire_script.py — the generic script-subprocess trigger.

Extracted from ``cron_triggers.py`` so that module keeps shrinking as new
trigger types are added to its dispatcher (CLAUDE.md § Conventions: extract when
you touch a file over the length ceiling; never add to it).

Handles the trigger types that are "run this script and log the outcome":
``analyse_lessons``, ``fallback_dryrun``, ``zte_v2_score``, ``script`` and
``capability_loop``.

    grep -n "_fire_script_trigger" app/server/cron_triggers.py
"""
import asyncio
import os


async def _fire_script_trigger(trigger: dict, log) -> None:
    """Fire a script-based trigger (analyse_lessons, etc.) as a subprocess."""
    script = trigger.get("script", "")
    if not script:
        log.warning("Script trigger id=%s has no 'script' field — skipped", trigger["id"])
        return
    log.info("Firing script trigger id=%s script=%s", trigger["id"], script)
    _repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
    cmd = ["python3"] + script.split() if not script.startswith("python") else script.split()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=_repo_root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    if proc.returncode != 0:
        log.error(
            "Script trigger id=%s exited %d: %s",
            trigger["id"], proc.returncode,
            stderr.decode("utf-8", errors="replace")[:500],
        )
    else:
        log.info("Script trigger id=%s complete (rc=0)", trigger["id"])
