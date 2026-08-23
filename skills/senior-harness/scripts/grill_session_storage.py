"""Secure local persistence for governed Grill sessions and transcripts."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from grill_session_contract import GrillSessionError
from grill_session_transitions import validate_receipt


def _read_object(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GrillSessionError(f"unable to read JSON object from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GrillSessionError(f"JSON input must be an object: {path}")
    return value


def _control_root() -> Path:
    override = os.environ.get("SENIOR_HARNESS_STATE_DIR")
    default = Path.home() / ".local" / "state" / "senior-harness"
    return (Path(override) if override else default).expanduser().resolve()


def _state_path(raw_path: str | Path) -> Path:
    path = Path(raw_path).expanduser().resolve()
    root = _control_root()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise GrillSessionError(f"state path must be below the external control root: {root}") from exc
    if path.suffix.lower() != ".json":
        raise GrillSessionError("state path must end in .json")
    return path


def _write_state(path: Path, session: Mapping[str, Any]) -> None:
    """Publish private session state atomically through a unique 0600 file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(session, indent=2, sort_keys=True) + "\n")
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _open_directory_chain(path: Path) -> int:
    """Open/create an absolute directory path without following any symlink."""
    if not path.is_absolute():
        raise GrillSessionError("materialization root must be absolute")
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise GrillSessionError("this platform cannot enforce no-follow transcript materialization")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(path.anchor, directory_flags)
    try:
        for component in path.parts[1:]:
            try:
                os.mkdir(component, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(component, directory_flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _validated_materialization(
    session: Mapping[str, Any],
) -> tuple[str, Path, Path, Path]:
    receipt = session.get("receipt")
    validate_receipt(receipt)
    receipt_value = receipt.get("materialization")
    session_value = session.get("materialization")
    if not isinstance(receipt_value, Mapping) or not isinstance(session_value, Mapping):
        raise GrillSessionError("confirmed receipt has no materialization binding")
    for field in ("grills_root", "path", "content_sha256"):
        if receipt_value.get(field) != session_value.get(field):
            raise GrillSessionError(f"materialization {field} differs from the confirmed receipt")
    content = session_value.get("content")
    if not isinstance(content, str) or not content:
        raise GrillSessionError("confirmed transcript content is missing")
    observed = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    if observed != receipt_value.get("content_sha256"):
        raise GrillSessionError("transcript content differs from the confirmed receipt")
    root, target = Path(str(receipt_value["grills_root"])), Path(str(receipt_value["path"]))
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise GrillSessionError("receipt-bound transcript escaped its Grills root") from exc
    if not relative.parts or relative.name in {"", ".", ".."}:
        raise GrillSessionError("receipt-bound transcript path is invalid")
    return content, root, target, relative


def _open_transcript_parent(root: Path, relative: Path) -> int:
    descriptor = _open_directory_chain(root)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        for component in relative.parts[:-1]:
            if component in {"", ".", ".."}:
                raise GrillSessionError("receipt-bound transcript path is invalid")
            try:
                os.mkdir(component, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _write_transcript(parent: int, name: str, content: str, target: Path) -> None:
    file_descriptor: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        file_descriptor = os.open(name, flags, 0o600, dir_fd=parent)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            file_descriptor = None
            stream.write(content)
    except FileExistsError as exc:
        raise GrillSessionError(f"refusing to replace existing transcript: {target}") from exc
    except OSError as exc:
        raise GrillSessionError(f"refusing unsafe transcript path: {target} ({exc})") from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)


def _materialize_transcript(session: Mapping[str, Any]) -> None:
    """Exclusively create the receipt-bound transcript without path traversal races."""
    content, root, target, relative = _validated_materialization(session)
    directory_descriptor: int | None = None
    try:
        directory_descriptor = _open_transcript_parent(root, relative)
        _write_transcript(directory_descriptor, relative.name, content, target)
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)
