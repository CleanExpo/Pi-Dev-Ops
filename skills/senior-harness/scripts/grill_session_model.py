"""State selection and invariants for governed Grill sessions."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from grill_session_contract import (
    DECISION_RESOLUTIONS,
    EVIDENCE_RESOLUTION,
    SCHEMA_VERSION,
    SHARED_UNDERSTANDING_PHRASE,
    GrillSessionError,
    _bind_integrity,
    _nonempty_text,
    _without_integrity,
    digest,
    file_digest,
)
from grill_session_tree import normalise_tree


def _materialization_target(sketch: Path, requested: str | Path) -> tuple[Path, Path]:
    sketches_root = next((parent for parent in sketch.parents if parent.name == "Sketches"), None)
    if sketches_root is None:
        raise GrillSessionError("sketch must be under a Sketches root")
    grills_root = (sketches_root.parent / "Grills").resolve()
    target = Path(requested).expanduser().resolve()
    try:
        relative = target.relative_to(grills_root)
    except ValueError as exc:
        raise GrillSessionError(
            f"materialization path must be under the sibling Grills root: {grills_root}"
        ) from exc
    if not relative.parts or target.suffix.lower() != ".md":
        raise GrillSessionError("materialization path must name a Markdown file under the Grills root")
    return grills_root, target


def _resolved(leaf: Mapping[str, Any]) -> bool:
    if leaf.get("kind") == "evidence-fact":
        return leaf.get("status") == EVIDENCE_RESOLUTION
    return leaf.get("status") in DECISION_RESOLUTIONS


def _select_next(session: dict[str, Any]) -> None:
    session["pending_question"] = None
    session["pending_evidence"] = None
    leaves = session["decision_tree"]
    statuses = {leaf["leaf_id"]: _resolved(leaf) for leaf in leaves}
    unresolved = [leaf for leaf in leaves if not _resolved(leaf)]
    if not unresolved:
        session["state"] = "awaiting-confirmation"
        return
    ready = [leaf for leaf in unresolved if all(statuses[item] for item in leaf["depends_on"])]
    if not ready:
        raise GrillSessionError("decision tree has no dependency-ready unresolved leaf")
    leaf = ready[0]
    if leaf["kind"] == "evidence-fact":
        session["state"] = "awaiting-evidence"
        session["pending_evidence"] = {"leaf_id": leaf["leaf_id"], "question": leaf["question"]}
        return
    session["state"] = "interviewing"
    session["pending_question"] = {
        "leaf_id": leaf["leaf_id"],
        "question": leaf["question"],
        "recommendation": leaf["recommendation"],
        "rationale": leaf["rationale"],
    }


def _assert_authority(session: Mapping[str, Any]) -> None:
    expected = {
        "mutation_authority": False,
        "business_authority": False,
        "irreversible_authority": False,
    }
    if session.get("authority") != expected:
        raise GrillSessionError(
            "a Grill-Me session grants zero mutation, business, or irreversible authority"
        )


def _assert_pending_state(session: Mapping[str, Any]) -> None:
    pending_question = session.get("pending_question")
    pending_evidence = session.get("pending_evidence")
    state = session.get("state")
    if state == "interviewing":
        if not isinstance(pending_question, Mapping) or pending_evidence is not None:
            raise GrillSessionError("interviewing requires exactly one pending human question")
        _nonempty_text(pending_question.get("recommendation"), "pending_question.recommendation")
        _nonempty_text(pending_question.get("rationale"), "pending_question.rationale")
    elif pending_question is not None:
        raise GrillSessionError("only an interviewing session may have a pending human question")
    if state == "awaiting-evidence" and not isinstance(pending_evidence, Mapping):
        raise GrillSessionError("awaiting-evidence requires exactly one pending evidence query")
    if state != "awaiting-evidence" and pending_evidence is not None:
        raise GrillSessionError("only an awaiting-evidence session may have a pending evidence query")


def _assert_materialization(session: Mapping[str, Any]) -> None:
    materialization = session.get("materialization")
    if not isinstance(materialization, Mapping):
        raise GrillSessionError("materialization must be an object")
    root_value, path_value = materialization.get("grills_root"), materialization.get("path")
    if not isinstance(root_value, str) or not isinstance(path_value, str):
        raise GrillSessionError("materialization must bind an explicit Grills root and path")
    root, target = Path(root_value), Path(path_value)
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise GrillSessionError("materialization path escaped its bound Grills root") from exc
    if root.name != "Grills" or not relative.parts or target.suffix.lower() != ".md":
        raise GrillSessionError("materialization path must name Markdown below a Grills root")
    state = session.get("state")
    if state != "confirmed" and materialization.get("content") is not None:
        raise GrillSessionError("materialization content must remain buffered until confirmation")
    if state == "confirmed" and (not materialization.get("content") or not session.get("receipt")):
        raise GrillSessionError("confirmed session requires materialized content and a receipt")


def _assert_runtime_invariants(session: Mapping[str, Any]) -> None:
    _assert_authority(session)
    _assert_pending_state(session)
    _assert_materialization(session)


def validate_session(session: Mapping[str, Any]) -> None:
    if not isinstance(session, Mapping):
        raise GrillSessionError("session must be an object")
    observed = session.get("session_integrity_digest")
    if not isinstance(observed, str) or observed != digest(_without_integrity(session)):
        raise GrillSessionError("session integrity check failed")
    if session.get("schema_version") != SCHEMA_VERSION:
        raise GrillSessionError(f"schema_version must be {SCHEMA_VERSION}")
    _assert_runtime_invariants(session)


def _resolve_sketch(sketch_path: str | Path) -> Path:
    try:
        sketch = Path(sketch_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise GrillSessionError("sketch path must name a real file") from exc
    if not sketch.is_file():
        raise GrillSessionError("sketch path must name a real file")
    return sketch


def _new_session(
    objective: str, sketch: Path, leaves: list[dict[str, Any]], grills_root: Path, target: Path
) -> dict[str, Any]:
    sketch_sha = file_digest(sketch)
    identity = {
        "objective": objective, "sketch_path": str(sketch), "sketch_sha256": sketch_sha,
        "decision_tree": leaves, "materialization_path": str(target),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": digest(identity)[7:23],
        "objective": objective,
        "sketch": {"path": str(sketch), "sha256": sketch_sha},
        "decision_tree": leaves,
        "state": "new",
        "pending_question": None,
        "pending_evidence": None,
        "buffer": {"transcript_entries": [], "domain_updates": []},
        "confirmation": {"required_phrase": SHARED_UNDERSTANDING_PHRASE, "answer_verbatim": None},
        "materialization": {
            "grills_root": str(grills_root), "path": str(target), "content": None,
            "content_sha256": None,
        },
        "authority": {
            "mutation_authority": False, "business_authority": False,
            "irreversible_authority": False,
        },
        "receipt": None,
    }


def start_session(
    objective: str,
    sketch_path: str | Path,
    decision_tree: Sequence[Mapping[str, Any]],
    *,
    materialization_path: str | Path,
) -> dict[str, Any]:
    """Bind a new session to an objective, a real sketch, and a decision tree."""
    objective = _nonempty_text(objective, "objective")
    sketch = _resolve_sketch(sketch_path)
    grills_root, target = _materialization_target(sketch, materialization_path)
    session = _new_session(objective, sketch, normalise_tree(decision_tree), grills_root, target)
    _select_next(session)
    _assert_runtime_invariants(session)
    return _bind_integrity(session)
