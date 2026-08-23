#!/usr/bin/env python3
"""Stable import and executable facade for governed Grill-Me sessions.

The public interface remains here for callers and lifecycle controls. Domain
invariants, transitions, secure storage, and command adaptation live in focused
sibling modules behind this seam.
"""
from __future__ import annotations

import grill_session_cli as _cli
import grill_session_contract as _contract
import grill_session_model as _model
import grill_session_storage as _storage
import grill_session_transitions as _transitions
import grill_session_tree as _tree

DECISION_RESOLUTIONS = _contract.DECISION_RESOLUTIONS
EVIDENCE_RESOLUTION = _contract.EVIDENCE_RESOLUTION
SCHEMA_VERSION = _contract.SCHEMA_VERSION
SHARED_UNDERSTANDING_PHRASE = _contract.SHARED_UNDERSTANDING_PHRASE
GrillSessionError = _contract.GrillSessionError
digest = _contract.digest
file_digest = _contract.file_digest
start_session = _model.start_session
validate_session = _model.validate_session
answer_pending_evidence = _transitions.answer_pending_evidence
answer_pending_question = _transitions.answer_pending_question
confirm_shared_understanding = _transitions.confirm_shared_understanding
validate_receipt = _transitions.validate_receipt
main = _cli.main

# Preserve the tested legacy internal seam while implementations live in focused modules.
_canonical_json = _contract._canonical_json
_nonempty_text = _contract._nonempty_text
_without_integrity = _contract._without_integrity
_bind_integrity = _contract._bind_integrity
_normalise_domain_updates = _contract._normalise_domain_updates
_normalise_tree = _tree.normalise_tree
_materialization_target = _model._materialization_target
_resolved = _model._resolved
_select_next = _model._select_next
_assert_runtime_invariants = _model._assert_runtime_invariants
_transition_copy = _transitions._transition_copy
_markdown = _transitions._markdown
_read_object = _storage._read_object
_control_root = _storage._control_root
_state_path = _storage._state_path
_write_state = _storage._write_state
_open_directory_chain = _storage._open_directory_chain
_materialize_transcript = _storage._materialize_transcript
_parser = _cli._parser

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


if __name__ == "__main__":
    raise SystemExit(main())
