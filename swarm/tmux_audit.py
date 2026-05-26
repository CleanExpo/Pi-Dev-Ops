"""Append-only audit ledger for the Terminal Orchestrator agent.

Every state-changing tmux operation (and every read in observer mode, since
"who looked at what" is forensically valuable) routes through `append()`.

Invariants (load-bearing — DO NOT relax):

  1. Append-only by filesystem flag where supported.
     - macOS: chflags uappend (set best-effort at startup)
     - Linux: chattr +a (requires root; skipped with WARN, deferred to T1-linux sub-issue)
  2. Each row is atomic: single write() under PIPE_BUF (≤512 bytes on macOS).
  3. Each row carries an HMAC keyed by ~/.hermes/audit-key.
  4. Caller MUST refuse the action if `append()` raises — fail-closed posture.
  5. Audit row redaction is the caller's responsibility (the validator's
     `redact_secrets` runs first on any captured output).

Public surface:
    AuditUnwritableError              — raise on any write failure
    AuditRowTooLargeError              — raise if 512-byte cap can't be met
    append(event_dict) -> audit_id     — returns the HMAC-prefixed audit id
    ensure_append_only(audit_dir=None) — idempotent startup hook
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

# ---------------------------------------------------------------------------

# Default audit dir; tests override via env or function arg.
DEFAULT_AUDIT_DIR = Path(os.environ.get(
    "HERMES_TMUX_AUDIT_DIR",
    str(Path.home() / "Pi-CEO" / ".harness" / "audit"),
))
AUDIT_KEY_PATH = Path(os.environ.get(
    "HERMES_AUDIT_KEY",
    str(Path.home() / ".hermes" / "audit-key"),
))

# Atomic-write byte cap. macOS POSIX guarantees writes <= 512 bytes are atomic.
ATOMIC_WRITE_CAP_BYTES = 512

# Fields that may be truncated (in order) when a row exceeds the cap.
_TRUNCATABLE_FIELDS = ("captured_text", "args", "pane_ids_observed")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AuditUnwritableError(RuntimeError):
    """Audit row could not be written — caller must refuse the action."""


class AuditRowTooLargeError(RuntimeError):
    """Audit row exceeds 512 bytes even after truncation — refuse the action."""


# ---------------------------------------------------------------------------
# Audit key (HMAC)
# ---------------------------------------------------------------------------


def _load_or_create_audit_key() -> bytes:
    """Read the HMAC audit key, generating it on first run."""
    p = AUDIT_KEY_PATH
    if p.exists():
        st = p.stat()
        # Reject if mode is too permissive (must be 0o600 / owner-only)
        if (st.st_mode & 0o077) != 0:
            raise AuditUnwritableError(
                f"audit key {p} has insecure mode {oct(st.st_mode)}; "
                "expected 0o600"
            )
        return p.read_bytes()
    p.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    # Write with 0o600 from the start.
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, key)
    finally:
        os.close(fd)
    return key


def _hmac_audit_id(event: dict, key: bytes) -> str:
    """Stable id = 'tmx-' + first 12 hex chars of HMAC-SHA256."""
    canonical = json.dumps(
        {k: event.get(k) for k in ("ts_realtime", "command", "actor")},
        sort_keys=True,
    ).encode("utf-8")
    digest = hmac.new(key, canonical, sha256).hexdigest()
    return f"tmx-{digest[:12]}"


# ---------------------------------------------------------------------------
# Append-only filesystem flag
# ---------------------------------------------------------------------------


def _set_append_only_macos(path: Path) -> bool:
    """Apply chflags uappend on macOS. Returns True on success, False otherwise."""
    try:
        result = subprocess.run(
            ["chflags", "uappend", str(path)],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def ensure_append_only(audit_dir: Path | None = None) -> dict:
    """Idempotent startup: create audit dir + today's file + set append-only flag.

    Returns a status dict the caller can log. Does NOT raise on flag-set
    failure (that's WARN-level); DOES raise if the dir can't be created.
    """
    audit_dir = audit_dir or DEFAULT_AUDIT_DIR
    audit_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_path = audit_dir / f"tmux-{today}.jsonl"
    today_path.touch(exist_ok=True)

    flag_set = False
    flag_skipped_reason: str | None = None
    if sys.platform == "darwin":
        flag_set = _set_append_only_macos(today_path)
        if not flag_set:
            flag_skipped_reason = "chflags uappend failed (best-effort; fsync still hard-fails)"
    else:
        flag_skipped_reason = f"unsupported platform {sys.platform} (Linux port deferred)"

    return {
        "audit_dir": str(audit_dir),
        "today_file": str(today_path),
        "append_only_flag_set": flag_set,
        "flag_skipped_reason": flag_skipped_reason,
    }


# ---------------------------------------------------------------------------
# Row construction + truncation
# ---------------------------------------------------------------------------


def _truncate_row(event: dict) -> dict:
    """If serialised row > ATOMIC_WRITE_CAP_BYTES, truncate fields in order.

    Mandatory-keep fields: audit_id, ts_realtime, actor, command, result, error_code.
    """
    out = dict(event)
    for field_name in _TRUNCATABLE_FIELDS:
        if len(json.dumps(out)) + 1 <= ATOMIC_WRITE_CAP_BYTES:
            return out
        if field_name in out and out[field_name]:
            if isinstance(out[field_name], str):
                marker = "[…truncated]"
                # Keep some prefix so the row remains informative
                available = ATOMIC_WRITE_CAP_BYTES - len(json.dumps({
                    **out,
                    field_name: marker,
                })) - 1
                if available > len(marker):
                    out[field_name] = out[field_name][: max(0, available - len(marker))] + marker
                else:
                    out[field_name] = marker
            elif isinstance(out[field_name], list):
                out[field_name] = [f"[{len(out[field_name])} items truncated]"]
            elif isinstance(out[field_name], dict):
                out[field_name] = {"_truncated": True, "_n_keys": len(out[field_name])}
    if len(json.dumps(out)) + 1 > ATOMIC_WRITE_CAP_BYTES:
        raise AuditRowTooLargeError(
            f"audit row {len(json.dumps(out))} > {ATOMIC_WRITE_CAP_BYTES} after truncation"
        )
    return out


# ---------------------------------------------------------------------------
# Public append
# ---------------------------------------------------------------------------


def append(event: dict, *, audit_dir: Path | None = None) -> str:
    """Append a single audit event. Returns the assigned audit_id.

    Raises:
        AuditUnwritableError — dir missing, fsync failure, permission denied
        AuditRowTooLargeError — row exceeds 512 bytes after truncation

    Caller MUST refuse the state-changing action if this raises.
    """
    audit_dir = audit_dir or DEFAULT_AUDIT_DIR
    if not audit_dir.exists():
        raise AuditUnwritableError(f"audit dir {audit_dir} does not exist")
    if not audit_dir.is_dir():
        raise AuditUnwritableError(f"audit path {audit_dir} is not a directory")

    # Stamp the event
    now = datetime.now(timezone.utc)
    enriched = {
        "ts_realtime": now.isoformat().replace("+00:00", "Z"),
        "ts_monotonic_ns": time.monotonic_ns(),
        **event,
    }

    # HMAC audit id
    try:
        key = _load_or_create_audit_key()
    except (OSError, AuditUnwritableError) as exc:
        raise AuditUnwritableError(f"audit key unavailable: {exc}") from exc
    enriched["audit_id"] = _hmac_audit_id(enriched, key)

    # Truncate if needed
    row = _truncate_row(enriched)
    line = json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n"
    line_bytes = line.encode("utf-8")
    if len(line_bytes) > ATOMIC_WRITE_CAP_BYTES:
        raise AuditRowTooLargeError(
            f"row {len(line_bytes)} bytes > {ATOMIC_WRITE_CAP_BYTES}"
        )

    # Atomic append + fsync
    today = now.strftime("%Y-%m-%d")
    today_path = audit_dir / f"tmux-{today}.jsonl"
    try:
        fd = os.open(str(today_path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            n = os.write(fd, line_bytes)
            if n != len(line_bytes):
                raise AuditUnwritableError(
                    f"short write: {n} of {len(line_bytes)} bytes"
                )
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise AuditUnwritableError(f"audit write failed: {exc}") from exc

    return enriched["audit_id"]
