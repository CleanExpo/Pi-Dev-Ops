"""Command-line adapter for the governed Grill session interface."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from grill_session_contract import (
    DECISION_RESOLUTIONS,
    GrillSessionError,
)
from grill_session_model import start_session, validate_session
from grill_session_storage import (
    _materialize_transcript, _read_object, _state_lock, _state_path, _write_state,
)
from grill_session_transitions import (
    answer_pending_evidence,
    answer_pending_question,
    confirm_shared_understanding,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Advance one governed Grill-Me session transition.",
        allow_abbrev=False,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", allow_abbrev=False)
    start.add_argument("--state", required=True)
    start.add_argument("--objective", required=True)
    start.add_argument("--sketch", required=True)
    start.add_argument("--decision-tree", required=True)
    start.add_argument("--transcript", required=True)
    for name in ("show", "validate"):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument("--state", required=True)
    evidence = sub.add_parser("evidence", allow_abbrev=False)
    evidence.add_argument("--state", required=True)
    evidence.add_argument("--expected-integrity", required=True)
    evidence.add_argument("--answer", required=True)
    evidence.add_argument("--sources", required=True)
    answer = sub.add_parser("answer", allow_abbrev=False)
    answer.add_argument("--state", required=True)
    answer.add_argument("--expected-integrity", required=True)
    answer.add_argument("--answer", required=True)
    answer.add_argument("--resolution", choices=sorted(DECISION_RESOLUTIONS), required=True)
    confirm = sub.add_parser("confirm", allow_abbrev=False)
    confirm.add_argument("--state", required=True)
    confirm.add_argument("--expected-integrity", required=True)
    confirm.add_argument("--phrase", required=True)
    materialize = sub.add_parser("materialize", allow_abbrev=False)
    materialize.add_argument("--state", required=True)
    materialize.add_argument("--expected-integrity", required=True)
    return parser


def _start(args: argparse.Namespace, state_path: Path) -> dict[str, Any]:
    tree = _read_object(args.decision_tree).get("decision_tree")
    if not isinstance(tree, list):
        raise GrillSessionError("decision-tree JSON must contain a decision_tree list")
    session = start_session(
        args.objective, args.sketch, tree, materialization_path=args.transcript
    )
    if state_path.exists():
        raise GrillSessionError(f"refusing to replace existing Grill state: {state_path}")
    _write_state(state_path, session)
    return session


def _evidence(args: argparse.Namespace, session: dict[str, Any]) -> dict[str, Any]:
    sources = _read_object(args.sources).get("evidence")
    if not isinstance(sources, list):
        raise GrillSessionError("sources JSON must contain an evidence list")
    return answer_pending_evidence(session, args.answer, sources)


def _advance(args: argparse.Namespace, state_path: Path) -> dict[str, Any]:
    session = _read_object(state_path)
    validate_session(session)
    observed = session.get("session_integrity_digest")
    expected = getattr(args, "expected_integrity", observed)
    if observed != expected:
        raise GrillSessionError("state changed after it was observed; reload before advancing")
    if args.command == "evidence":
        session = _evidence(args, session)
    elif args.command == "answer":
        session = answer_pending_question(session, args.answer, args.resolution)
    elif args.command == "confirm":
        session = confirm_shared_understanding(session, args.phrase)
    elif args.command == "materialize":
        if session.get("state") != "confirmed":
            raise GrillSessionError("transcript cannot materialize before confirmation")
        _materialize_transcript(session)
    if args.command in {"evidence", "answer", "confirm"}:
        _write_state(state_path, session)
    return session


def _execute(args: argparse.Namespace) -> dict[str, Any]:
    state_path = _state_path(args.state)
    if args.command in {"show", "validate"}:
        return _advance(args, state_path)
    with _state_lock(state_path):
        return _start(args, state_path) if args.command == "start" else _advance(args, state_path)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        session = _execute(args)
        print(json.dumps(session, indent=2, sort_keys=True))
        return 0
    except (GrillSessionError, OSError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
