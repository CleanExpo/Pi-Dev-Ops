"""Shared contracts and pure helpers for Senior Harness startup admission."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
CANONICAL_REPO_ROOT = Path(__file__).resolve().parents[3]
for import_root in (SCRIPT_DIR, CANONICAL_REPO_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

SETUP_SCHEMA_VERSION = "1.0"
REQUIRED_SKILLS = ("senior-harness", "model-router", "unlazy")
GRILL_INTERACTIONS = ("grill-me", "grill-with-docs")
GRILL_READ_ONLY_COMMANDS = frozenset({"show", "validate"})
GRILL_STATE_COMMANDS = frozenset(
    {"start", "show", "validate", "evidence", "answer", "confirm", "materialize"}
)
SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
STARTUP_AUTHORITY = {
    "startup_admission": "pending",
    "mutation_authority": False,
    "business_authority": False,
    "irreversible_authority": False,
}
STARTUP_ADMISSION = {
    "startup_only": True,
    "objective_lock_on_mediated_tools": True,
    "dispatch_authority": "nonmutating-only",
    "mutation_authority": False,
    "business_authority": False,
    "irreversible_authority": False,
}
READ_ONLY_GIT = {
    ("rev-parse", "--show-toplevel"),
    ("rev-parse", "HEAD"),
    ("status", "--porcelain=v1", "--untracked-files=all"),
    ("diff", "--binary", "--no-ext-diff", "HEAD", "--"),
    ("ls-files", "--others", "--exclude-standard", "-z"),
}
ADAPTER_RECEIPT_ENV = "SENIOR_HARNESS_ADAPTER_RECEIPT"
REQUIRED_ADAPTER_EVIDENCE = ("capacity", "isolation", "signed_dispatch", "cancellation")
SEAL_PREFIX = "hmac-sha256:"
SEAL_KEY_ENV = "SENIOR_HARNESS_SEAL_KEY_FILE"


class SetupError(ValueError):
    """Raised when startup cannot be admitted safely."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class GitProbeError(SetupError):
    """Raised when a read-only Git probe cannot run against the requested path."""


@dataclass(frozen=True)
class ControlBindingResult:
    """Classify binding evidence without deriving policy from message text."""

    drift: tuple[str, ...] = ()
    integrity_failures: tuple[str, ...] = ()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _is_sha256_digest(value: Any) -> bool:
    return isinstance(value, str) and SHA256_DIGEST_PATTERN.fullmatch(value) is not None


def _interaction_for_objective(literal_objective: Any) -> str | None:
    if not isinstance(literal_objective, str) or not literal_objective.strip():
        return None
    match = re.match(
        r"^\s*[/\$](grill-with-docs|grill-me)", literal_objective, flags=re.IGNORECASE
    )
    return match.group(1).lower() if match else "delivery"


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _folder_digest(root: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        hasher.update(path.relative_to(root).as_posix().encode())
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return "sha256:" + hasher.hexdigest()


def _normalise_tool_name(raw_name: Any) -> str:
    if isinstance(raw_name, dict):
        raw_name = raw_name.get("name", "")
    name = str(raw_name).replace("-", "_").replace(".", "_")
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def _hook_output(event: str, context: str, *, deny: bool = False) -> dict[str, Any]:
    if event == "PreToolUse" and deny:
        return {"hookSpecificOutput": {
            "hookEventName": event,
            "permissionDecision": "deny",
            "permissionDecisionReason": context,
        }}
    if event == "UserPromptSubmit" and deny:
        return {
            "decision": "block",
            "reason": context,
            "hookSpecificOutput": {"hookEventName": event, "additionalContext": context},
        }
    if event in {"SessionStart", "UserPromptSubmit", "PreToolUse"}:
        return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}
    return {"continue": not deny, "stopReason": context if deny else None, "systemMessage": context}


def _tool_command(payload: dict[str, Any]) -> str | None:
    raw_name = payload.get("tool_name") or payload.get("tool") or ""
    tool_name = _normalise_tool_name(raw_name)
    if not any(marker in tool_name for marker in ("bash", "exec", "command", "shell")):
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    command = tool_input.get("cmd") or tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    if re.search(r"[\n;&|<>`]|\$\(", command):
        return None
    return command


def _read_json(path: str) -> dict[str, Any]:
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError([f"unable to read JSON: {exc}"]) from exc
    if not isinstance(value, dict):
        raise SetupError(["top-level JSON must be an object"])
    return value
