#!/usr/bin/env python3
"""Pure, deterministic state transitions for a governed Grill-Me session.

The intake function reads the sketch once so that the session can bind a real
file and its bytes.  Every function after intake treats the session as an
immutable value: it validates the integrity digest, deep-copies the value, and
returns a new one.  In particular, confirmation produces a materialization
payload; this module never writes the transcript to disk.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "1.0"
SHARED_UNDERSTANDING_PHRASE = "I confirm this is our shared understanding."
DECISION_RESOLUTIONS = frozenset({"DECIDED", "RABBIT_HOLE", "NO_GO"})
LEAF_KINDS = frozenset({"human-decision", "evidence-fact"})
EVIDENCE_RESOLUTION = "EVIDENCED"


class GrillSessionError(ValueError):
    """Raised when a Grill-Me transition fails closed."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GrillSessionError(f"{label} must be non-empty text")
    return value


def _without_integrity(session: Mapping[str, Any]) -> dict[str, Any]:
    candidate = copy.deepcopy(dict(session))
    candidate.pop("session_integrity_digest", None)
    return candidate


def _bind_integrity(session: dict[str, Any]) -> dict[str, Any]:
    session["session_integrity_digest"] = digest(_without_integrity(session))
    return session


def validate_session(session: Mapping[str, Any]) -> None:
    if not isinstance(session, Mapping):
        raise GrillSessionError("session must be an object")
    observed = session.get("session_integrity_digest")
    if not isinstance(observed, str) or observed != digest(_without_integrity(session)):
        raise GrillSessionError("session integrity check failed")
    if session.get("schema_version") != SCHEMA_VERSION:
        raise GrillSessionError(f"schema_version must be {SCHEMA_VERSION}")
    _assert_runtime_invariants(session)


def _normalise_domain_updates(updates: Iterable[Mapping[str, Any]] | None) -> list[dict[str, str]]:
    normalised: list[dict[str, str]] = []
    for index, raw in enumerate(updates or ()):
        if not isinstance(raw, Mapping):
            raise GrillSessionError(f"domain_updates[{index}] must be an object")
        term = _nonempty_text(raw.get("term"), f"domain_updates[{index}].term")
        meaning = _nonempty_text(raw.get("meaning"), f"domain_updates[{index}].meaning")
        normalised.append({"term": term, "meaning": meaning})
    return normalised


def _normalise_tree(raw_leaves: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(raw_leaves, (str, bytes)) or not isinstance(raw_leaves, Sequence) or not raw_leaves:
        raise GrillSessionError("decision tree must contain at least one leaf")

    by_id: dict[str, dict[str, Any]] = {}
    input_order: dict[str, int] = {}
    for index, raw in enumerate(raw_leaves):
        if not isinstance(raw, Mapping):
            raise GrillSessionError(f"decision_tree[{index}] must be an object")
        leaf_id = _nonempty_text(raw.get("leaf_id"), f"decision_tree[{index}].leaf_id")
        if leaf_id in by_id:
            raise GrillSessionError(f"duplicate leaf_id: {leaf_id}")
        kind = raw.get("kind")
        if kind not in LEAF_KINDS:
            raise GrillSessionError(f"leaf {leaf_id} kind must be human-decision or evidence-fact")
        prompt = _nonempty_text(raw.get("question"), f"leaf {leaf_id}.question")
        raw_dependencies = raw.get("depends_on", [])
        if (
            isinstance(raw_dependencies, (str, bytes))
            or not isinstance(raw_dependencies, Sequence)
            or any(not isinstance(value, str) or not value.strip() for value in raw_dependencies)
        ):
            raise GrillSessionError(f"leaf {leaf_id}.depends_on must be a list of non-empty leaf ids")
        dependencies = list(raw_dependencies)
        if len(set(dependencies)) != len(dependencies):
            raise GrillSessionError(f"leaf {leaf_id}.depends_on contains duplicates")
        if kind == "human-decision":
            recommendation = _nonempty_text(raw.get("recommendation"), f"leaf {leaf_id}.recommendation")
            rationale = _nonempty_text(raw.get("rationale"), f"leaf {leaf_id}.rationale")
        else:
            if raw.get("recommendation") not in (None, "") or raw.get("rationale") not in (None, ""):
                raise GrillSessionError(f"evidence leaf {leaf_id} cannot carry a human recommendation")
            recommendation = None
            rationale = None
        input_order[leaf_id] = index
        by_id[leaf_id] = {
            "leaf_id": leaf_id,
            "kind": kind,
            "depends_on": dependencies,
            "question": prompt,
            "recommendation": recommendation,
            "rationale": rationale,
            "status": "UNRESOLVED",
            "answer_verbatim": None,
            "evidence": [],
        }

    known_ids = set(by_id)
    for leaf_id, leaf in by_id.items():
        unknown = [dependency for dependency in leaf["depends_on"] if dependency not in known_ids]
        if unknown:
            raise GrillSessionError(f"leaf {leaf_id} has unknown dependencies: {', '.join(unknown)}")
        if leaf_id in leaf["depends_on"]:
            raise GrillSessionError(f"leaf {leaf_id} cannot depend on itself")

    # Stable Kahn ordering makes the dependency order explicit while retaining
    # the author's order for independent siblings.
    children: dict[str, list[str]] = {leaf_id: [] for leaf_id in by_id}
    remaining = {leaf_id: len(leaf["depends_on"]) for leaf_id, leaf in by_id.items()}
    for leaf_id, leaf in by_id.items():
        for dependency in leaf["depends_on"]:
            children[dependency].append(leaf_id)
    ready = sorted((leaf_id for leaf_id, count in remaining.items() if count == 0), key=input_order.get)
    ordered: list[dict[str, Any]] = []
    while ready:
        leaf_id = ready.pop(0)
        ordered.append(by_id[leaf_id])
        for child in sorted(children[leaf_id], key=input_order.get):
            remaining[child] -= 1
            if remaining[child] == 0:
                ready.append(child)
                ready.sort(key=input_order.get)
    if len(ordered) != len(by_id):
        raise GrillSessionError("decision tree must be acyclic")
    return ordered


def _materialization_target(sketch: Path, requested: str | Path) -> tuple[Path, Path]:
    sketches_root = next((parent for parent in sketch.parents if parent.name == "Sketches"), None)
    if sketches_root is None:
        raise GrillSessionError("sketch must be under a Sketches root")
    grills_root = (sketches_root.parent / "Grills").resolve()
    target = Path(requested).expanduser().resolve()
    try:
        relative = target.relative_to(grills_root)
    except ValueError as exc:
        raise GrillSessionError(f"materialization path must be under the sibling Grills root: {grills_root}") from exc
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
    ready = [leaf for leaf in unresolved if all(statuses[dependency] for dependency in leaf["depends_on"])]
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


def _assert_runtime_invariants(session: Mapping[str, Any]) -> None:
    authority = session.get("authority")
    expected_authority = {
        "mutation_authority": False,
        "business_authority": False,
        "irreversible_authority": False,
    }
    if authority != expected_authority:
        raise GrillSessionError("a Grill-Me session grants zero mutation, business, or irreversible authority")

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
    if state == "awaiting-evidence":
        if not isinstance(pending_evidence, Mapping):
            raise GrillSessionError("awaiting-evidence requires exactly one pending evidence query")
    elif pending_evidence is not None:
        raise GrillSessionError("only an awaiting-evidence session may have a pending evidence query")

    materialization = session.get("materialization")
    if not isinstance(materialization, Mapping):
        raise GrillSessionError("materialization must be an object")
    root_value = materialization.get("grills_root")
    path_value = materialization.get("path")
    if not isinstance(root_value, str) or not isinstance(path_value, str):
        raise GrillSessionError("materialization must bind an explicit Grills root and path")
    root = Path(root_value)
    target = Path(path_value)
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise GrillSessionError("materialization path escaped its bound Grills root") from exc
    if root.name != "Grills" or not relative.parts or target.suffix.lower() != ".md":
        raise GrillSessionError("materialization path must name Markdown below a Grills root")
    if state != "confirmed" and materialization.get("content") is not None:
        raise GrillSessionError("materialization content must remain buffered until confirmation")
    if state == "confirmed" and (not materialization.get("content") or not session.get("receipt")):
        raise GrillSessionError("confirmed session requires materialized content and a receipt")


def start_session(
    objective: str,
    sketch_path: str | Path,
    decision_tree: Sequence[Mapping[str, Any]],
    *,
    materialization_path: str | Path,
) -> dict[str, Any]:
    """Bind a new session to an objective, a real sketch, and a decision tree."""
    objective = _nonempty_text(objective, "objective")
    try:
        sketch = Path(sketch_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise GrillSessionError("sketch path must name a real file") from exc
    if not sketch.is_file():
        raise GrillSessionError("sketch path must name a real file")
    grills_root, target = _materialization_target(sketch, materialization_path)
    leaves = _normalise_tree(decision_tree)
    sketch_sha = file_digest(sketch)
    session: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "session_id": digest(
            {
                "objective": objective,
                "sketch_path": str(sketch),
                "sketch_sha256": sketch_sha,
                "decision_tree": leaves,
                "materialization_path": str(target),
            }
        )[7:23],
        "objective": objective,
        "sketch": {"path": str(sketch), "sha256": sketch_sha},
        "decision_tree": leaves,
        "state": "new",
        "pending_question": None,
        "pending_evidence": None,
        "buffer": {"transcript_entries": [], "domain_updates": []},
        "confirmation": {
            "required_phrase": SHARED_UNDERSTANDING_PHRASE,
            "answer_verbatim": None,
        },
        "materialization": {
            "grills_root": str(grills_root),
            "path": str(target),
            "content": None,
            "content_sha256": None,
        },
        "authority": {
            "mutation_authority": False,
            "business_authority": False,
            "irreversible_authority": False,
        },
        "receipt": None,
    }
    _select_next(session)
    _assert_runtime_invariants(session)
    return _bind_integrity(session)


def _transition_copy(session: Mapping[str, Any]) -> dict[str, Any]:
    validate_session(session)
    if session.get("state") == "confirmed":
        raise GrillSessionError("confirmed sessions are terminal")
    return copy.deepcopy(dict(session))


def answer_pending_question(
    session: Mapping[str, Any],
    answer_verbatim: str,
    resolution: str,
    *,
    domain_updates: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve the sole pending human decision without altering its answer text."""
    updated = _transition_copy(session)
    if updated["state"] != "interviewing":
        raise GrillSessionError("session does not have a pending human question")
    answer = _nonempty_text(answer_verbatim, "answer_verbatim")
    if resolution not in DECISION_RESOLUTIONS:
        raise GrillSessionError("resolution must be verbatim DECIDED, RABBIT_HOLE, or NO_GO")
    pending = updated["pending_question"]
    leaf = next(item for item in updated["decision_tree"] if item["leaf_id"] == pending["leaf_id"])
    leaf["status"] = resolution
    leaf["answer_verbatim"] = answer
    entry = {
        "leaf_id": leaf["leaf_id"],
        "kind": leaf["kind"],
        "question": leaf["question"],
        "recommendation": leaf["recommendation"],
        "rationale": leaf["rationale"],
        "answer_verbatim": answer,
        "resolution": resolution,
        "evidence": [],
    }
    updated["buffer"]["transcript_entries"].append(entry)
    updated["buffer"]["domain_updates"].extend(_normalise_domain_updates(domain_updates))
    _select_next(updated)
    _assert_runtime_invariants(updated)
    return _bind_integrity(updated)


def answer_pending_evidence(
    session: Mapping[str, Any],
    answer_verbatim: str,
    evidence: Sequence[Mapping[str, Any]],
    *,
    domain_updates: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve an evidence-answerable fact without converting it into a human choice."""
    updated = _transition_copy(session)
    if updated["state"] != "awaiting-evidence":
        raise GrillSessionError("session does not have a pending evidence query")
    answer = _nonempty_text(answer_verbatim, "answer_verbatim")
    if isinstance(evidence, (str, bytes)) or not isinstance(evidence, Sequence) or not evidence:
        raise GrillSessionError("evidence must contain at least one source receipt")
    normalised_evidence: list[dict[str, str]] = []
    for index, raw in enumerate(evidence):
        if not isinstance(raw, Mapping):
            raise GrillSessionError(f"evidence[{index}] must be an object")
        source_id = _nonempty_text(raw.get("source_id"), f"evidence[{index}].source_id")
        source_digest = _nonempty_text(raw.get("source_digest"), f"evidence[{index}].source_digest")
        if (
            not source_digest.startswith("sha256:")
            or len(source_digest) != 71
            or any(character not in "0123456789abcdef" for character in source_digest[7:])
        ):
            raise GrillSessionError(f"evidence[{index}].source_digest must be a sha256 digest")
        normalised_evidence.append({"source_id": source_id, "source_digest": source_digest})
    pending = updated["pending_evidence"]
    leaf = next(item for item in updated["decision_tree"] if item["leaf_id"] == pending["leaf_id"])
    leaf["status"] = EVIDENCE_RESOLUTION
    leaf["answer_verbatim"] = answer
    leaf["evidence"] = normalised_evidence
    updated["buffer"]["transcript_entries"].append(
        {
            "leaf_id": leaf["leaf_id"],
            "kind": leaf["kind"],
            "question": leaf["question"],
            "recommendation": None,
            "rationale": None,
            "answer_verbatim": answer,
            "resolution": EVIDENCE_RESOLUTION,
            "evidence": normalised_evidence,
        }
    )
    updated["buffer"]["domain_updates"].extend(_normalise_domain_updates(domain_updates))
    _select_next(updated)
    _assert_runtime_invariants(updated)
    return _bind_integrity(updated)


def _markdown(session: Mapping[str, Any]) -> str:
    lines = [
        "---",
        "type: grill",
        f"session_id: {session['session_id']}",
        f"sketch: {session['sketch']['path']}",
        f"sketch_sha256: {session['sketch']['sha256']}",
        "status: resolved",
        "---",
        "",
        "# Grill transcript",
        "",
        f"**Objective:** {session['objective']}",
        "",
    ]
    for index, entry in enumerate(session["buffer"]["transcript_entries"], start=1):
        lines.extend([f"## Q{index}: {entry['question']}", ""])
        if entry["kind"] == "human-decision":
            lines.extend(
                [
                    f"**My recommendation:** {entry['recommendation']}",
                    f"**Rationale:** {entry['rationale']}",
                ]
            )
        else:
            sources = ", ".join(item["source_id"] for item in entry["evidence"])
            lines.append(f"**Evidence sources:** {sources}")
        lines.extend(
            [
                f"**Answer (verbatim):** {entry['answer_verbatim']}",
                f"**Resolution:** {entry['resolution']}",
                "",
            ]
        )
    lines.extend(["## Domain updates", ""])
    if session["buffer"]["domain_updates"]:
        for item in session["buffer"]["domain_updates"]:
            lines.append(f"- **{item['term']}:** {item['meaning']}")
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Shared understanding",
            "",
            session["confirmation"]["answer_verbatim"],
            "",
        ]
    )
    return "\n".join(lines)


def confirm_shared_understanding(session: Mapping[str, Any], phrase_verbatim: str) -> dict[str, Any]:
    """Confirm a fully resolved tree and emit, but do not write, its artifact."""
    updated = _transition_copy(session)
    if updated["state"] != "awaiting-confirmation":
        unresolved = [leaf["leaf_id"] for leaf in updated["decision_tree"] if not _resolved(leaf)]
        detail = f": {', '.join(unresolved)}" if unresolved else ""
        raise GrillSessionError(f"cannot confirm while leaves remain unresolved{detail}")
    if phrase_verbatim != SHARED_UNDERSTANDING_PHRASE:
        raise GrillSessionError(f"confirmation must exactly equal: {SHARED_UNDERSTANDING_PHRASE}")

    updated["confirmation"]["answer_verbatim"] = phrase_verbatim
    updated["state"] = "confirmed"
    content = _markdown(updated)
    updated["materialization"]["content"] = content
    updated["materialization"]["content_sha256"] = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "receipt_type": "grill-shared-understanding",
        "session_id": updated["session_id"],
        "objective_sha256": digest({"objective": updated["objective"]}),
        "sketch": copy.deepcopy(updated["sketch"]),
        "decision_tree_sha256": digest(updated["decision_tree"]),
        "transcript_sha256": digest(updated["buffer"]["transcript_entries"]),
        "domain_updates_sha256": digest(updated["buffer"]["domain_updates"]),
        "confirmation_phrase": phrase_verbatim,
        "materialization": {
            "grills_root": updated["materialization"]["grills_root"],
            "path": updated["materialization"]["path"],
            "content_sha256": updated["materialization"]["content_sha256"],
        },
        "authority": copy.deepcopy(updated["authority"]),
    }
    receipt["receipt_integrity_digest"] = digest(receipt)
    updated["receipt"] = receipt
    _assert_runtime_invariants(updated)
    return _bind_integrity(updated)


def validate_receipt(receipt: Mapping[str, Any]) -> None:
    """Validate receipt integrity and its deliberately empty authority grant."""
    if not isinstance(receipt, Mapping):
        raise GrillSessionError("receipt must be an object")
    candidate = copy.deepcopy(dict(receipt))
    observed = candidate.pop("receipt_integrity_digest", None)
    if not isinstance(observed, str) or observed != digest(candidate):
        raise GrillSessionError("receipt integrity check failed")
    if receipt.get("receipt_type") != "grill-shared-understanding":
        raise GrillSessionError("unexpected receipt type")
    if receipt.get("confirmation_phrase") != SHARED_UNDERSTANDING_PHRASE:
        raise GrillSessionError("receipt does not bind the shared-understanding phrase")
    expected_authority = {
        "mutation_authority": False,
        "business_authority": False,
        "irreversible_authority": False,
    }
    if receipt.get("authority") != expected_authority:
        raise GrillSessionError("receipt cannot grant mutation, business, or irreversible authority")


__all__ = [
    "DECISION_RESOLUTIONS",
    "EVIDENCE_RESOLUTION",
    "GrillSessionError",
    "SHARED_UNDERSTANDING_PHRASE",
    "answer_pending_evidence",
    "answer_pending_question",
    "confirm_shared_understanding",
    "digest",
    "file_digest",
    "start_session",
    "validate_receipt",
    "validate_session",
]


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
    return (Path(override) if override else Path.home() / ".local" / "state" / "senior-harness").expanduser().resolve()


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
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(session, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


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


def _materialize_transcript(session: Mapping[str, Any]) -> None:
    """Exclusively create the receipt-bound transcript without path traversal races."""
    receipt = session.get("receipt")
    validate_receipt(receipt)
    receipt_materialization = receipt.get("materialization")
    session_materialization = session.get("materialization")
    if not isinstance(receipt_materialization, Mapping) or not isinstance(session_materialization, Mapping):
        raise GrillSessionError("confirmed receipt has no materialization binding")
    for field in ("grills_root", "path", "content_sha256"):
        if receipt_materialization.get(field) != session_materialization.get(field):
            raise GrillSessionError(f"materialization {field} differs from the confirmed receipt")

    content = session_materialization.get("content")
    if not isinstance(content, str) or not content:
        raise GrillSessionError("confirmed transcript content is missing")
    observed_digest = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    if observed_digest != receipt_materialization.get("content_sha256"):
        raise GrillSessionError("transcript content differs from the confirmed receipt")

    root = Path(str(receipt_materialization["grills_root"]))
    target = Path(str(receipt_materialization["path"]))
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise GrillSessionError("receipt-bound transcript escaped its Grills root") from exc
    if not relative.parts or relative.name in {"", ".", ".."}:
        raise GrillSessionError("receipt-bound transcript path is invalid")

    directory_descriptor: int | None = None
    file_descriptor: int | None = None
    try:
        directory_descriptor = _open_directory_chain(root)
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        for component in relative.parts[:-1]:
            if component in {"", ".", ".."}:
                raise GrillSessionError("receipt-bound transcript path is invalid")
            try:
                os.mkdir(component, mode=0o700, dir_fd=directory_descriptor)
            except FileExistsError:
                pass
            child = os.open(component, directory_flags, dir_fd=directory_descriptor)
            os.close(directory_descriptor)
            directory_descriptor = child

        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        file_descriptor = os.open(relative.name, file_flags, 0o600, dir_fd=directory_descriptor)
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
        if directory_descriptor is not None:
            os.close(directory_descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Advance one governed Grill-Me session transition.")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--state", required=True)
    start.add_argument("--objective", required=True)
    start.add_argument("--sketch", required=True)
    start.add_argument("--decision-tree", required=True)
    start.add_argument("--transcript", required=True)
    for name in ("show", "validate"):
        command = sub.add_parser(name)
        command.add_argument("--state", required=True)
    evidence = sub.add_parser("evidence")
    evidence.add_argument("--state", required=True)
    evidence.add_argument("--answer", required=True)
    evidence.add_argument("--sources", required=True)
    answer = sub.add_parser("answer")
    answer.add_argument("--state", required=True)
    answer.add_argument("--answer", required=True)
    answer.add_argument("--resolution", choices=sorted(DECISION_RESOLUTIONS), required=True)
    confirm = sub.add_parser("confirm")
    confirm.add_argument("--state", required=True)
    confirm.add_argument("--phrase", required=True)
    materialize = sub.add_parser("materialize")
    materialize.add_argument("--state", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        state_path = _state_path(args.state)
        if args.command == "start":
            tree = _read_object(args.decision_tree).get("decision_tree")
            if not isinstance(tree, list):
                raise GrillSessionError("decision-tree JSON must contain a decision_tree list")
            session = start_session(
                args.objective,
                args.sketch,
                tree,
                materialization_path=args.transcript,
            )
            if state_path.exists():
                raise GrillSessionError(f"refusing to replace existing Grill state: {state_path}")
            _write_state(state_path, session)
        else:
            session = _read_object(state_path)
            validate_session(session)
            if args.command == "evidence":
                sources = _read_object(args.sources).get("evidence")
                if not isinstance(sources, list):
                    raise GrillSessionError("sources JSON must contain an evidence list")
                session = answer_pending_evidence(session, args.answer, sources)
                _write_state(state_path, session)
            elif args.command == "answer":
                session = answer_pending_question(session, args.answer, args.resolution)
                _write_state(state_path, session)
            elif args.command == "confirm":
                session = confirm_shared_understanding(session, args.phrase)
                _write_state(state_path, session)
            elif args.command == "materialize":
                if session.get("state") != "confirmed":
                    raise GrillSessionError("transcript cannot materialize before confirmation")
                _materialize_transcript(session)
        print(json.dumps(session, indent=2, sort_keys=True))
        return 0
    except GrillSessionError as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
