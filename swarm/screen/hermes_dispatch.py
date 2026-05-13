"""swarm/screen/hermes_dispatch.py — Phase 5 (plan 2026-05-13): bridge to Hermes
Agent v0.13.0 `computer_use` toolset.

Any swarm component (Margot, Pi-CEO Board, senior agents, cron jobs) calls
`screen_dispatch(intent)` to delegate a real-screen task (open Finder, fill
a form in Chrome, screenshot the empire dashboard, etc.) to Hermes. We
subprocess `hermes chat -q ... -t computer_use,browser,web --yolo` and
capture the structured result.

Kill-switch: TAO_SCREEN_DISABLED=1 makes screen_dispatch a no-op (returns
ScreenResult.disabled with a reason). Required for the kill-switch policy
in [[pathway-to-2b-2026-2028]].

Audit log: every call appends to ~/.hermes/screen_audit.jsonl with the
intent, toolsets, exit code, stdout snippet, session_id (extracted from
Hermes' output), screenshot paths, wall-time. Required for non-repudiation
+ replay if a screen task goes sideways.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("swarm.screen.hermes_dispatch")

# ── Paths (override via env for tests) ──────────────────────────────────────

HERMES_BIN = os.environ.get(
    "TAO_HERMES_BIN",
    str(Path.home() / ".local" / "bin" / "hermes"),
)
SCREENSHOT_DIR = Path(os.environ.get(
    "TAO_HERMES_SCREENSHOT_DIR",
    str(Path.home() / ".hermes" / "cache" / "screenshots"),
))
AUDIT_LOG_PATH = Path(os.environ.get(
    "TAO_SCREEN_AUDIT_LOG",
    str(Path.home() / ".hermes" / "screen_audit.jsonl"),
))

DEFAULT_TOOLSETS = ("computer_use", "browser", "web")

# Hermes prints `Session:        <session_id>` after a chat exits. The id
# follows the pattern `YYYYMMDD_HHMMSS_<hex>` (see ~/.hermes/sessions/).
# Match both forms — explicit label OR bare id — so we recover the id
# regardless of which way Hermes printed it.
_SESSION_LABEL_RE = re.compile(r"Session\s*:\s*([A-Za-z0-9_\-]+)")
_SESSION_ID_RE = re.compile(r"\b(\d{8}_\d{6}_[a-f0-9]+)\b")

_STDOUT_SNIPPET_LIMIT = 4000


@dataclass
class ScreenResult:
    """Outcome of one Hermes computer_use dispatch.

    Fields:
      ok            — True iff Hermes exited 0 AND we got non-empty stdout
      disabled      — True iff TAO_SCREEN_DISABLED=1 short-circuited the call
      intent        — original one-sentence intent string from the caller
      final_text    — Hermes stdout (truncated for audit) / disabled reason
      session_id    — parsed from stdout when present; None otherwise
      screenshots   — new files in ~/.hermes/cache/screenshots/ during the run
      error         — non-None when ok is False (rc, timeout, exception text)
      wall_seconds  — elapsed time for the subprocess call (0 when disabled)
    """
    ok: bool
    disabled: bool
    intent: str
    final_text: str
    session_id: str | None
    screenshots: list[str] = field(default_factory=list)
    error: str | None = None
    wall_seconds: float = 0.0


# ── Internal helpers ────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _list_screenshots(dir_path: Path) -> set[str]:
    """Return absolute paths of every file currently in the screenshots dir."""
    try:
        return {str(p) for p in dir_path.iterdir() if p.is_file()}
    except FileNotFoundError:
        return set()
    except Exception as exc:  # noqa: BLE001
        log.debug("screen: list screenshots failed (%s)", exc)
        return set()


def _parse_session_id(stdout: str) -> str | None:
    """Extract the Hermes session_id from stdout, preferring the labelled form."""
    m = _SESSION_LABEL_RE.search(stdout)
    if m:
        return m.group(1).strip()
    m = _SESSION_ID_RE.search(stdout)
    if m:
        return m.group(1).strip()
    return None


def _audit_write(row: dict) -> None:
    """Append one JSONL row to the audit log. Failure is non-fatal."""
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("screen: audit write failed (%s)", exc)


def _is_disabled() -> bool:
    return os.environ.get("TAO_SCREEN_DISABLED", "0") == "1"


# ── Public API ──────────────────────────────────────────────────────────────


async def screen_dispatch(
    intent: str,
    *,
    toolsets: list[str] | None = None,
    max_turns: int = 12,
    timeout_s: float = 600.0,
) -> ScreenResult:
    """Delegate a real-screen task to Hermes v0.13.0 `computer_use`.

    Spawns `hermes chat -q <intent> -t <toolsets> --yolo --max-turns N`
    non-interactively, captures stdout, parses the session_id, and lists
    any new files in ~/.hermes/cache/screenshots/ that appeared during
    the run. Every call (success, failure, disabled) is appended as a
    single JSONL row to ~/.hermes/screen_audit.jsonl.

    Honours TAO_SCREEN_DISABLED=1 — when set the call short-circuits and
    no subprocess is spawned.

    Returns a ScreenResult.
    """
    used_toolsets = list(toolsets or DEFAULT_TOOLSETS)
    started_iso = _now_iso()

    # ── Kill-switch ────────────────────────────────────────────────────────
    if _is_disabled():
        reason = "TAO_SCREEN_DISABLED=1 — screen automation kill-switch engaged."
        result = ScreenResult(
            ok=False, disabled=True, intent=intent,
            final_text=reason, session_id=None,
            screenshots=[], error=None, wall_seconds=0.0,
        )
        _audit_write({
            "ts": started_iso, "type": "screen_dispatch_disabled",
            "intent": intent, "toolsets": used_toolsets,
            "max_turns": max_turns, "timeout_s": timeout_s,
            **{k: v for k, v in asdict(result).items() if k != "intent"},
        })
        log.info("screen_dispatch: skipped (kill-switch)")
        return result

    # ── Subprocess ─────────────────────────────────────────────────────────
    before_shots = _list_screenshots(SCREENSHOT_DIR)
    t0 = time.monotonic()
    rc: int = -1
    stdout_text = ""
    stderr_text = ""
    err: str | None = None
    timed_out = False

    cmd = [
        HERMES_BIN, "chat",
        "-q", intent,
        "-t", ",".join(used_toolsets),
        "--yolo",
        "--max-turns", str(int(max_turns)),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s,
            )
            rc = int(proc.returncode or 0)
            stdout_text = (stdout_b or b"").decode("utf-8", errors="replace")
            stderr_text = (stderr_b or b"").decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            timed_out = True
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                await proc.wait()
            except Exception:  # noqa: BLE001
                pass
            err = f"timeout after {timeout_s:.0f}s"
    except FileNotFoundError:
        err = f"hermes binary not found at {HERMES_BIN}"
    except Exception as exc:  # noqa: BLE001
        err = f"subprocess_raised: {exc}"

    wall = time.monotonic() - t0
    after_shots = _list_screenshots(SCREENSHOT_DIR)
    new_shots = sorted(after_shots - before_shots)

    session_id = _parse_session_id(stdout_text) if stdout_text else None
    snippet = stdout_text[:_STDOUT_SNIPPET_LIMIT]

    if err is None and rc != 0:
        err = f"hermes rc={rc}: {stderr_text[:500].strip() or 'no stderr'}"

    ok = err is None and rc == 0 and bool(stdout_text.strip())

    result = ScreenResult(
        ok=ok, disabled=False, intent=intent,
        final_text=snippet, session_id=session_id,
        screenshots=new_shots, error=err, wall_seconds=round(wall, 3),
    )

    _audit_write({
        "ts": started_iso, "type": "screen_dispatch",
        "intent": intent, "toolsets": used_toolsets,
        "max_turns": max_turns, "timeout_s": timeout_s,
        "rc": rc, "timed_out": timed_out,
        "stdout_snippet": snippet,
        "session_id": session_id,
        "screenshots": new_shots,
        "wall_seconds": round(wall, 3),
        "error": err, "ok": ok,
    })

    if ok:
        log.info(
            "screen_dispatch: ok session=%s shots=%d wall=%.1fs",
            session_id, len(new_shots), wall,
        )
    else:
        log.warning(
            "screen_dispatch: failed (%s) rc=%s session=%s",
            err, rc, session_id,
        )
    return result


__all__ = ["ScreenResult", "screen_dispatch", "AUDIT_LOG_PATH",
           "SCREENSHOT_DIR", "HERMES_BIN", "DEFAULT_TOOLSETS"]
