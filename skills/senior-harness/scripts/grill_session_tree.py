"""Decision-tree normalization for governed Grill sessions."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from grill_session_contract import GrillSessionError, LEAF_KINDS, _nonempty_text


def _normalise_dependencies(raw: Any, leaf_id: str) -> list[str]:
    if (
        isinstance(raw, (str, bytes))
        or not isinstance(raw, Sequence)
        or any(not isinstance(value, str) or not value.strip() for value in raw)
    ):
        raise GrillSessionError(
            f"leaf {leaf_id}.depends_on must be a list of non-empty leaf ids"
        )
    dependencies = list(raw)
    if len(set(dependencies)) != len(dependencies):
        raise GrillSessionError(f"leaf {leaf_id}.depends_on contains duplicates")
    return dependencies


def _leaf_guidance(
    raw: Mapping[str, Any], leaf_id: str, kind: Any
) -> tuple[str | None, str | None]:
    if kind == "human-decision":
        return (
            _nonempty_text(raw.get("recommendation"), f"leaf {leaf_id}.recommendation"),
            _nonempty_text(raw.get("rationale"), f"leaf {leaf_id}.rationale"),
        )
    if raw.get("recommendation") not in (None, "") or raw.get("rationale") not in (None, ""):
        raise GrillSessionError(f"evidence leaf {leaf_id} cannot carry a human recommendation")
    return None, None


def _normalise_leaf(raw: Mapping[str, Any], index: int) -> dict[str, Any]:
    leaf_id = _nonempty_text(raw.get("leaf_id"), f"decision_tree[{index}].leaf_id")
    kind = raw.get("kind")
    if kind not in LEAF_KINDS:
        raise GrillSessionError(f"leaf {leaf_id} kind must be human-decision or evidence-fact")
    recommendation, rationale = _leaf_guidance(raw, leaf_id, kind)
    return {
        "leaf_id": leaf_id,
        "kind": kind,
        "depends_on": _normalise_dependencies(raw.get("depends_on", []), leaf_id),
        "question": _nonempty_text(raw.get("question"), f"leaf {leaf_id}.question"),
        "recommendation": recommendation,
        "rationale": rationale,
        "status": "UNRESOLVED",
        "answer_verbatim": None,
        "evidence": [],
    }


def _leaf_index(
    raw_leaves: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    by_id: dict[str, dict[str, Any]] = {}
    input_order: dict[str, int] = {}
    for index, raw in enumerate(raw_leaves):
        if not isinstance(raw, Mapping):
            raise GrillSessionError(f"decision_tree[{index}] must be an object")
        leaf = _normalise_leaf(raw, index)
        leaf_id = leaf["leaf_id"]
        if leaf_id in by_id:
            raise GrillSessionError(f"duplicate leaf_id: {leaf_id}")
        by_id[leaf_id] = leaf
        input_order[leaf_id] = index
    return by_id, input_order


def _validate_dependencies(by_id: Mapping[str, Mapping[str, Any]]) -> None:
    known_ids = set(by_id)
    for leaf_id, leaf in by_id.items():
        unknown = [item for item in leaf["depends_on"] if item not in known_ids]
        if unknown:
            raise GrillSessionError(
                f"leaf {leaf_id} has unknown dependencies: {', '.join(unknown)}"
            )
        if leaf_id in leaf["depends_on"]:
            raise GrillSessionError(f"leaf {leaf_id} cannot depend on itself")


def _topological_order(
    by_id: dict[str, dict[str, Any]], input_order: Mapping[str, int]
) -> list[dict[str, Any]]:
    children: dict[str, list[str]] = {leaf_id: [] for leaf_id in by_id}
    remaining = {leaf_id: len(leaf["depends_on"]) for leaf_id, leaf in by_id.items()}
    for leaf_id, leaf in by_id.items():
        for dependency in leaf["depends_on"]:
            children[dependency].append(leaf_id)
    ready = sorted((key for key, count in remaining.items() if count == 0), key=input_order.get)
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


def normalise_tree(raw_leaves: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(raw_leaves, (str, bytes)) or not isinstance(raw_leaves, Sequence) or not raw_leaves:
        raise GrillSessionError("decision tree must contain at least one leaf")
    by_id, input_order = _leaf_index(raw_leaves)
    _validate_dependencies(by_id)
    return _topological_order(by_id, input_order)
