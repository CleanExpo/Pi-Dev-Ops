"""Immutable Grill session transitions, rendering, and receipt validation."""
from __future__ import annotations

import copy
import hashlib
from typing import Any, Iterable, Mapping, Sequence

from grill_session_contract import (
    DECISION_RESOLUTIONS,
    EVIDENCE_RESOLUTION,
    SCHEMA_VERSION,
    SHARED_UNDERSTANDING_PHRASE,
    GrillSessionError,
    _bind_integrity,
    _nonempty_text,
    _normalise_domain_updates,
    digest,
)
from grill_session_model import (
    _assert_runtime_invariants,
    _resolved,
    _select_next,
    validate_session,
)


def _transition_copy(session: Mapping[str, Any]) -> dict[str, Any]:
    validate_session(session)
    if session.get("state") == "confirmed":
        raise GrillSessionError("confirmed sessions are terminal")
    return copy.deepcopy(dict(session))


def _decision_entry(leaf: Mapping[str, Any], answer: str, resolution: str) -> dict[str, Any]:
    return {
        "leaf_id": leaf["leaf_id"],
        "kind": leaf["kind"],
        "question": leaf["question"],
        "recommendation": leaf["recommendation"],
        "rationale": leaf["rationale"],
        "answer_verbatim": answer,
        "resolution": resolution,
        "evidence": [],
    }


def _finish_transition(
    updated: dict[str, Any], domain_updates: Iterable[Mapping[str, Any]] | None
) -> dict[str, Any]:
    updated["buffer"]["domain_updates"].extend(_normalise_domain_updates(domain_updates))
    _select_next(updated)
    _assert_runtime_invariants(updated)
    return _bind_integrity(updated)


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
    updated["buffer"]["transcript_entries"].append(_decision_entry(leaf, answer, resolution))
    return _finish_transition(updated, domain_updates)


def _evidence_item(raw: Mapping[str, Any], index: int) -> dict[str, str]:
    source_id = _nonempty_text(raw.get("source_id"), f"evidence[{index}].source_id")
    source_digest = _nonempty_text(raw.get("source_digest"), f"evidence[{index}].source_digest")
    valid_digest = (
        source_digest.startswith("sha256:")
        and len(source_digest) == 71
        and all(character in "0123456789abcdef" for character in source_digest[7:])
    )
    if not valid_digest:
        raise GrillSessionError(f"evidence[{index}].source_digest must be a sha256 digest")
    return {"source_id": source_id, "source_digest": source_digest}


def _normalise_evidence(evidence: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    if isinstance(evidence, (str, bytes)) or not isinstance(evidence, Sequence) or not evidence:
        raise GrillSessionError("evidence must contain at least one source receipt")
    normalised: list[dict[str, str]] = []
    for index, raw in enumerate(evidence):
        if not isinstance(raw, Mapping):
            raise GrillSessionError(f"evidence[{index}] must be an object")
        normalised.append(_evidence_item(raw, index))
    return normalised


def _evidence_entry(
    leaf: Mapping[str, Any], answer: str, evidence: list[dict[str, str]]
) -> dict[str, Any]:
    return {
        "leaf_id": leaf["leaf_id"],
        "kind": leaf["kind"],
        "question": leaf["question"],
        "recommendation": None,
        "rationale": None,
        "answer_verbatim": answer,
        "resolution": EVIDENCE_RESOLUTION,
        "evidence": evidence,
    }


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
    normalised = _normalise_evidence(evidence)
    pending = updated["pending_evidence"]
    leaf = next(item for item in updated["decision_tree"] if item["leaf_id"] == pending["leaf_id"])
    leaf.update(status=EVIDENCE_RESOLUTION, answer_verbatim=answer, evidence=normalised)
    updated["buffer"]["transcript_entries"].append(_evidence_entry(leaf, answer, normalised))
    return _finish_transition(updated, domain_updates)


def _transcript_header(session: Mapping[str, Any]) -> list[str]:
    return [
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


def _entry_lines(index: int, entry: Mapping[str, Any]) -> list[str]:
    lines = [f"## Q{index}: {entry['question']}", ""]
    if entry["kind"] == "human-decision":
        lines.extend(
            [f"**My recommendation:** {entry['recommendation']}", f"**Rationale:** {entry['rationale']}"]
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
    return lines


def _domain_lines(updates: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = ["## Domain updates", ""]
    if updates:
        lines.extend(f"- **{item['term']}:** {item['meaning']}" for item in updates)
    else:
        lines.append("- None.")
    return lines


def _markdown(session: Mapping[str, Any]) -> str:
    lines = _transcript_header(session)
    for index, entry in enumerate(session["buffer"]["transcript_entries"], start=1):
        lines.extend(_entry_lines(index, entry))
    lines.extend(_domain_lines(session["buffer"]["domain_updates"]))
    lines.extend(
        ["", "## Shared understanding", "", session["confirmation"]["answer_verbatim"], ""]
    )
    return "\n".join(lines)


def _receipt(updated: Mapping[str, Any], phrase_verbatim: str) -> dict[str, Any]:
    materialization = updated["materialization"]
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
            "grills_root": materialization["grills_root"],
            "path": materialization["path"],
            "content_sha256": materialization["content_sha256"],
        },
        "authority": copy.deepcopy(updated["authority"]),
    }
    receipt["receipt_integrity_digest"] = digest(receipt)
    return receipt


def confirm_shared_understanding(
    session: Mapping[str, Any], phrase_verbatim: str
) -> dict[str, Any]:
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
    updated["materialization"]["content_sha256"] = (
        "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    )
    updated["receipt"] = _receipt(updated, phrase_verbatim)
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
    expected = {
        "mutation_authority": False,
        "business_authority": False,
        "irreversible_authority": False,
    }
    if receipt.get("authority") != expected:
        raise GrillSessionError(
            "receipt cannot grant mutation, business, or irreversible authority"
        )
