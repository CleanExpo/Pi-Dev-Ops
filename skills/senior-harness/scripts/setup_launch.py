"""Sealed session -> launch-root record, so a moved cwd still finds its receipt.

A host can move a session's cwd after admission (a persisted `cd`, or a thread
moved to another worktree). The receipt stays keyed to the root it was admitted
in, so the hook records that root once and PreToolUse falls back to it when the
current cwd's root holds no state. The record only names a root; the receipt
there is still fully validated, so the record can redirect but never admit.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Any

from setup_common import SEAL_PREFIX, SetupError
from setup_receipts import _seal_key
from setup_state import _launch_record_path, _session_key, _state_path, _write_state

LAUNCH_RECORD_KIND = "senior-harness-launch-root"


def _launch_seal(record: dict[str, Any]) -> str:
    unsealed = {key: value for key, value in record.items() if key != "launch_seal"}
    payload = json.dumps(
        unsealed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return SEAL_PREFIX + hmac.new(_seal_key(), payload, hashlib.sha256).hexdigest()


def record_launch_root(session_id: str, surface: str, project_root: Path) -> None:
    """Record the first admitted root for this session; later admissions keep it.

    Callers must hold the session lock, as both admission paths already do.
    """
    path = _launch_record_path(session_id)
    if path.exists():
        return
    record = {
        "kind": LAUNCH_RECORD_KIND,
        "session_key": _session_key(session_id),
        "surface": surface,
        "launch_root": str(project_root),
        "recorded_at_ns": time.time_ns(),
        # The clock can repeat within a tick, so the nonce is what makes each
        # record's seal unique; routing compares seals to spot a replacement.
        "record_nonce": secrets.token_hex(16),
    }
    record["launch_seal"] = _launch_seal(record)
    _write_state(path, record)


def clear_launch_root(session_id: str) -> None:
    _launch_record_path(session_id).unlink(missing_ok=True)


def _read_launch_record(path: Path, session_id: str, surface: str) -> tuple[Path, str]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError([f"launch-root record is invalid: {exc}"]) from exc
    if not isinstance(record, dict):
        raise SetupError(["launch-root record is invalid: not a JSON object"])
    seal = record.get("launch_seal")
    if not isinstance(seal, str) or not hmac.compare_digest(seal, _launch_seal(record)):
        raise SetupError(["launch-root record is invalid: seal mismatch"])
    root = record.get("launch_root")
    if (
        record.get("kind") != LAUNCH_RECORD_KIND
        or record.get("session_key") != _session_key(session_id)
        or record.get("surface") != surface
        or not isinstance(root, str)
        or not Path(root).is_absolute()
    ):
        raise SetupError(
            ["launch-root record is invalid: wrong session, surface or root"]
        )
    return Path(root), seal


def launch_root_state(
    session_id: str, surface: str
) -> tuple[Path, Path, str] | None:
    """Return (launch root, its state path, record seal), or None when nothing is recorded.

    None keeps the caller's existing fail-closed path. A record that exists but
    does not verify raises, so tampering is reported rather than ignored. The
    seal identifies this exact record: a clear and re-admission at the same root
    writes a new one with a fresh nonce, so its seal differs even within one
    clock tick.
    """
    path = _launch_record_path(session_id)
    if not path.exists():
        return None
    root, seal = _read_launch_record(path, session_id, surface)
    state_path = _state_path(root, session_id)
    return (root, state_path, seal) if state_path.is_file() else None
