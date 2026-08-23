"""Startup receipt issuance, integrity, and current-evidence validation."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any

from senior_harness import digest
from setup_common import (
    GRILL_INTERACTIONS,
    REQUIRED_SKILLS,
    SCRIPT_DIR,
    SEAL_KEY_ENV,
    SEAL_PREFIX,
    SETUP_SCHEMA_VERSION,
    STARTUP_ADMISSION,
    STARTUP_AUTHORITY,
    ControlBindingResult,
    SetupError,
    _folder_digest,
    _interaction_for_objective,
    _is_sha256_digest,
)
from setup_repository import _frontmatter_name


def _seal_key_path() -> Path:
    override = os.environ.get(SEAL_KEY_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "senior-harness" / "receipt-seal.key"


def _read_existing_key(path: Path) -> bytes | None:
    try:
        key = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SetupError([f"startup receipt seal key cannot be read: {exc}"]) from exc
    if len(key) < 32:
        raise SetupError([f"startup receipt seal key is too short: {path}"])
    return key


def _seal_key() -> bytes:
    """Read the machine-local seal key, creating it 0600 on first use."""
    path = _seal_key_path()
    existing = _read_existing_key(path)
    if existing is not None:
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    key = os.urandom(32)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raced = _read_existing_key(path)
        if raced is None:
            raise SetupError([f"startup receipt seal key disappeared: {path}"])
        return raced
    try:
        os.write(descriptor, key)
    finally:
        os.close(descriptor)
    return key


def _receipt_seal(receipt: Any) -> str:
    unsealed = {key: value for key, value in dict(receipt).items() if key != "receipt_seal"}
    payload = json.dumps(
        unsealed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return SEAL_PREFIX + hmac.new(_seal_key(), payload, hashlib.sha256).hexdigest()


def _driver_digest() -> str:
    """Bind the facade and every extracted setup module as one control surface."""
    hasher = hashlib.sha256()
    for path in sorted(SCRIPT_DIR.glob("setup_*.py")):
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return "sha256:" + hasher.hexdigest()


def _validate_contract_for_admission(contract: dict[str, Any]) -> None:
    expected = dict(contract)
    observed_digest = expected.pop("setup_contract_digest", None)
    if observed_digest != digest(expected):
        raise SetupError(["setup contract digest is invalid"])
    if contract.get("stage") != "setup-contract":
        raise SetupError(["setup contract stage is invalid"])
    if contract.get("authority") != STARTUP_AUTHORITY:
        raise SetupError(["setup contract cannot grant mutation, business, or irreversible authority"])
    objective = contract.get("literal_objective")
    if not isinstance(objective, str) or not objective.strip():
        raise SetupError(["setup contract literal objective is invalid"])
    if contract.get("task_id") != digest({"task": objective})[7:23]:
        raise SetupError(["setup contract task id is not bound to its literal objective"])
    if contract.get("objective_digest") != digest({"task": objective}):
        raise SetupError(["setup contract objective digest is invalid"])
    if contract.get("interaction") != _interaction_for_objective(objective):
        raise SetupError(["setup contract interaction does not match its frozen literal objective"])
    if contract.get("secondary_objectives") != []:
        raise SetupError(["setup contract cannot pre-authorize secondary objectives"])


def admit_startup(contract: dict[str, Any]) -> dict[str, Any]:
    """Issue an integrity-bound startup receipt; never issue mutation authority."""
    _validate_contract_for_admission(contract)
    receipt: dict[str, Any] = {
        "schema_version": SETUP_SCHEMA_VERSION,
        "stage": "startup-admitted",
        "setup_contract": contract,
        "driver_digest": _driver_digest(),
        "admission": dict(STARTUP_ADMISSION),
        "admission_order_ns": time.time_ns(),
    }
    receipt["receipt_integrity_digest"] = digest(receipt)
    receipt["receipt_seal"] = _receipt_seal(receipt)
    return receipt


def _skill_binding_errors(
    name: str, item: Any, *, verify_current: bool
) -> tuple[list[str], list[str]]:
    integrity: list[str] = []
    drift: list[str] = []
    if not isinstance(item, dict):
        return [f"startup receipt is missing skill {name}"], drift
    if item.get("name") != name:
        integrity.append(f"bound skill name is missing or invalid: {name}")
    path_value = item.get("path")
    path = Path(path_value) if isinstance(path_value, str) and path_value else None
    if path is None or not path.is_absolute():
        integrity.append(f"bound skill path is missing or invalid: {name}")
        path = None
    stored_digest = item.get("folder_digest")
    digest_valid = _is_sha256_digest(stored_digest)
    if not digest_valid:
        integrity.append(f"bound skill folder digest is missing or malformed: {name}")
    if not verify_current or path is None:
        return integrity, drift
    try:
        valid = path.is_dir() and _frontmatter_name(path / "SKILL.md") == name
    except OSError:
        valid = False
    if not valid:
        integrity.append(f"bound skill is unavailable or invalid: {name}")
    elif digest_valid:
        try:
            if stored_digest != _folder_digest(path):
                drift.append(f"bound skill changed after startup admission: {name}")
        except OSError:
            integrity.append(f"bound skill is unavailable or invalid: {name}")
    return integrity, drift


def _driver_binding_errors(receipt: dict[str, Any], verify: bool) -> tuple[list[str], list[str]]:
    stored = receipt.get("driver_digest")
    if not _is_sha256_digest(stored):
        return ["setup driver digest is missing or malformed"], []
    if not verify:
        return [], []
    try:
        current = _driver_digest()
    except OSError:
        return ["setup driver is unavailable or invalid"], []
    if stored != current:
        return [], ["setup driver changed after startup admission"]
    return [], []


def _check_control_bindings(
    receipt: Any, *, verify_current: bool = True
) -> ControlBindingResult:
    if not isinstance(receipt, dict):
        return ControlBindingResult(integrity_failures=("startup receipt must be a JSON object",))
    contract = receipt.get("setup_contract")
    if not isinstance(contract, dict):
        return ControlBindingResult(integrity_failures=("startup receipt is missing its setup contract",))
    skills = contract.get("required_skills")
    if not isinstance(skills, dict):
        return ControlBindingResult(integrity_failures=("startup receipt has no required-skill evidence",))
    interaction = _interaction_for_objective(contract.get("literal_objective"))
    names = REQUIRED_SKILLS + (("grill-me",) if interaction in GRILL_INTERACTIONS else ())
    integrity: list[str] = []
    drift: list[str] = []
    for name in names:
        item_integrity, item_drift = _skill_binding_errors(
            name, skills.get(name), verify_current=verify_current
        )
        integrity.extend(item_integrity)
        drift.extend(item_drift)
    driver_integrity, driver_drift = _driver_binding_errors(receipt, verify_current)
    return ControlBindingResult(
        drift=tuple([*drift, *driver_drift]),
        integrity_failures=tuple([*integrity, *driver_integrity]),
    )


def _control_binding_errors(receipt: dict[str, Any]) -> list[str]:
    result = _check_control_bindings(receipt)
    return [*result.integrity_failures, *result.drift]
