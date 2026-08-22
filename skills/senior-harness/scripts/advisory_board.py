#!/usr/bin/env python3
"""Fail-closed contracts for a post-Grill five-persona advisory board.

This pure module prepares and verifies evidence-bound board runs. It never
calls a provider, chooses a real person, administers a psychometric assessment,
or activates agents.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any, Mapping

from grill_session import GrillSessionError, digest, validate_receipt, validate_session

SCHEMA_VERSION = "board-composition/1.0"
PROPOSAL_STAGE = "board-composition-proposal"
ROUTED_STAGE = "board-composition-routed"
DATA_CLASSES = frozenset({"public", "internal", "confidential", "client"})
CLAIM_CLASSES = frozenset({"FACT", "INFERENCE", "ASSUMPTION", "UNKNOWN"})
ARBITER_OUTCOMES = frozenset({"APPROVE_FOR_NEXT_GATE", "DEFERRED_NEEDS_EVIDENCE", "NO_GO"})
PERSONAS = (
    {"id": "outcome_steward", "lens": "success criteria, decision appetite, and owner outcome", "required_outputs": ["option_ranking", "assumptions", "unknowns", "stop_conditions"]},
    {"id": "systems_steward", "lens": "dependencies, integration boundaries, and operational constraints", "required_outputs": ["constraint_map", "failure_modes", "minimum_viable_seam"]},
    {"id": "customer_value_steward", "lens": "user workflow, value evidence, adoption friction, and experiment design", "required_outputs": ["value_hypothesis", "evidence_gaps", "reversible_experiment"]},
    {"id": "risk_steward", "lens": "security, privacy, legal, abuse, and irreversible effects", "required_outputs": ["red_flags", "required_controls", "no_go_triggers"]},
    {"id": "economics_steward", "lens": "cost, opportunity cost, sequencing, and measurable learning", "required_outputs": ["bounded_cost_option", "expected_learning", "kill_criterion"]},
)
ROUTE_SUBJECTS = tuple(persona["id"] for persona in PERSONAS) + ("arbiter",)
SCORING_WEIGHTS = {"evidence_traceability": 0.20, "grill_alignment": 0.15, "customer_or_operator_value": 0.15, "technical_feasibility": 0.10, "privacy_security_compliance": 0.15, "cost_and_appetite_fit": 0.10, "reversibility_and_learning": 0.10, "dissent_coverage": 0.05}


class AdvisoryBoardError(ValueError):
    """Raised when a board proposal or run cannot be trusted."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AdvisoryBoardError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdvisoryBoardError(f"{label} must be non-empty text")
    return value


def _digest(value: Any, label: str) -> str:
    value = _text(value, label)
    if not value.startswith("sha256:") or len(value) != 71:
        raise AdvisoryBoardError(f"{label} must be a sha256 digest")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise AdvisoryBoardError(f"{label} must be a sha256 digest") from exc
    return value


def _grill_handoff(session: Mapping[str, Any]) -> dict[str, str]:
    try:
        validate_session(session)
        validate_receipt(_mapping(session.get("receipt"), "grill receipt"))
    except GrillSessionError as exc:
        raise AdvisoryBoardError(f"invalid Grill shared-understanding session: {exc}") from exc
    if session.get("state") != "confirmed":
        raise AdvisoryBoardError("advisory board requires a confirmed Grill shared-understanding session")
    receipt = _mapping(session["receipt"], "grill receipt")
    expected_objective = digest({"objective": session.get("objective")})
    if receipt.get("objective_sha256") != expected_objective:
        raise AdvisoryBoardError("Grill receipt objective does not match confirmed session")
    sketch = _mapping(receipt.get("sketch"), "grill receipt.sketch")
    return {
        "session_id": _text(receipt.get("session_id"), "grill receipt.session_id"),
        "objective_sha256": expected_objective,
        "sketch_sha256": _digest(sketch.get("sha256"), "grill receipt.sketch.sha256"),
        "decision_tree_sha256": _digest(receipt.get("decision_tree_sha256"), "grill receipt.decision_tree_sha256"),
        "transcript_sha256": _digest(receipt.get("transcript_sha256"), "grill receipt.transcript_sha256"),
        "receipt_sha256": _digest(receipt.get("receipt_integrity_digest"), "grill receipt.receipt_integrity_digest"),
    }


def create_proposal(session: Mapping[str, Any], *, task_id: str, decision_question: str, data_class: str, max_cost_usd: float, deadline_seconds: int) -> dict[str, Any]:
    """Create a non-executable advisory-board proposal from a sealed Grill handoff."""
    if data_class not in DATA_CLASSES:
        raise AdvisoryBoardError("data_class is invalid")
    if not isinstance(max_cost_usd, (int, float)) or not math.isfinite(max_cost_usd) or max_cost_usd <= 0:
        raise AdvisoryBoardError("max_cost_usd must be finite and greater than zero")
    if not isinstance(deadline_seconds, int) or deadline_seconds <= 0:
        raise AdvisoryBoardError("deadline_seconds must be a positive integer")
    contract: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "stage": PROPOSAL_STAGE,
        "task_id": _text(task_id, "task_id"),
        "decision_question": _text(decision_question, "decision_question"),
        "grill_handoff": _grill_handoff(session),
        "task_envelope": {
            "data_class": data_class,
            "allowed_execution_location": "local_only" if data_class in {"client", "confidential"} else "remote_allowed",
            "max_cost_usd": float(max_cost_usd),
            "deadline_seconds": deadline_seconds,
            "sanitised_input_only": True,
            "forbidden_input": ["secrets", "credentials", "unnecessary_client_data", "real_person_profiles", "psychometric_profiles"],
        },
        "personas": copy.deepcopy(list(PERSONAS)),
        "provider_protocol": {"status": "unresolved", "open_model_discovery_required": True, "minimum_distinct_provider_families": 2, "same_model_for_multiple_personas": False, "silent_fallback": False, "required_receipt_fields": ["provider_family", "resolved_model", "price_snapshot_sha256", "usage", "cost_status"]},
        "candidate_benchmark": {
            "functional_profiles_only": True,
            "minimum_candidates_per_persona": 2,
            "criteria": ["mandate_fit", "capability_evidence", "complementarity", "counter_argument_quality", "known_limits"],
            "selection_is_proposal_only": True,
        },
        "debate_protocol": {"blind_first_passes": 5, "anonymised_claim_ledger": True, "cross_examination_rounds": 1, "independent_top_floor_arbiter": True, "arbiter_cannot_execute": True},
        "scoring": {"scale": "0-4", "weights": copy.deepcopy(SCORING_WEIGHTS), "minimum_weighted_score": 3.0, "minimum_critical_risk_score": 3.0},
        "activation": {"status": "proposal", "automatic_activation": False, "owner_approval_required": True, "independent_verifier_required": True},
    }
    contract["contract_sha256"] = digest(contract)
    validate_proposal(contract)
    return contract


def validate_proposal(contract: Mapping[str, Any]) -> dict[str, Any]:
    contract = _mapping(contract, "board contract")
    if contract.get("schema_version") != SCHEMA_VERSION or contract.get("stage") != PROPOSAL_STAGE:
        raise AdvisoryBoardError("board contract schema or stage is invalid")
    _text(contract.get("task_id"), "task_id")
    _text(contract.get("decision_question"), "decision_question")
    handoff = _mapping(contract.get("grill_handoff"), "grill_handoff")
    _text(handoff.get("session_id"), "grill_handoff.session_id")
    for field in ("objective_sha256", "sketch_sha256", "decision_tree_sha256", "transcript_sha256", "receipt_sha256"):
        _digest(handoff.get(field), f"grill_handoff.{field}")
    envelope = _mapping(contract.get("task_envelope"), "task_envelope")
    if envelope.get("data_class") not in DATA_CLASSES:
        raise AdvisoryBoardError("task_envelope.data_class is invalid")
    if envelope.get("allowed_execution_location") not in {"local_only", "remote_allowed"}:
        raise AdvisoryBoardError("task_envelope.allowed_execution_location is invalid")
    if envelope.get("data_class") in {"client", "confidential"} and envelope.get("allowed_execution_location") != "local_only":
        raise AdvisoryBoardError("client or confidential board composition must be local_only")
    if not isinstance(envelope.get("max_cost_usd"), (int, float)) or not math.isfinite(envelope["max_cost_usd"]) or envelope["max_cost_usd"] <= 0:
        raise AdvisoryBoardError("task_envelope.max_cost_usd must be finite and greater than zero")
    if not isinstance(envelope.get("deadline_seconds"), int) or envelope["deadline_seconds"] <= 0 or envelope.get("sanitised_input_only") is not True:
        raise AdvisoryBoardError("task envelope deadline or sanitisation contract is invalid")
    personas = contract.get("personas")
    if personas != list(PERSONAS):
        raise AdvisoryBoardError("personas must contain exactly the five complementary functional roles")
    protocol = _mapping(contract.get("provider_protocol"), "provider_protocol")
    if protocol.get("status") != "unresolved" or protocol.get("silent_fallback") is not False or protocol.get("minimum_distinct_provider_families") != 2 or protocol.get("same_model_for_multiple_personas") is not False:
        raise AdvisoryBoardError("provider protocol must remain unresolved and prohibit silent fallback")
    benchmark = _mapping(contract.get("candidate_benchmark"), "candidate_benchmark")
    if benchmark != {"functional_profiles_only": True, "minimum_candidates_per_persona": 2, "criteria": ["mandate_fit", "capability_evidence", "complementarity", "counter_argument_quality", "known_limits"], "selection_is_proposal_only": True}:
        raise AdvisoryBoardError("candidate benchmark must select functional profiles without activation authority")
    debate = _mapping(contract.get("debate_protocol"), "debate_protocol")
    if debate.get("blind_first_passes") != 5 or debate.get("anonymised_claim_ledger") is not True or debate.get("independent_top_floor_arbiter") is not True:
        raise AdvisoryBoardError("debate protocol must require blind passes, anonymous claims, and an independent arbiter")
    if _mapping(contract.get("activation"), "activation") != {"status": "proposal", "automatic_activation": False, "owner_approval_required": True, "independent_verifier_required": True}:
        raise AdvisoryBoardError("board proposal cannot carry activation authority")
    scoring = _mapping(contract.get("scoring"), "scoring")
    if scoring.get("weights") != SCORING_WEIGHTS or scoring.get("minimum_weighted_score") != 3.0 or scoring.get("minimum_critical_risk_score") != 3.0:
        raise AdvisoryBoardError("board scoring thresholds are invalid")
    candidate = dict(contract)
    observed = candidate.pop("contract_sha256", None)
    if observed != digest(candidate):
        raise AdvisoryBoardError("board contract integrity digest is invalid")
    return {"status": "valid", "stage": PROPOSAL_STAGE, "contract_sha256": observed, "activation": "proposal_only"}


def _validate_route(route: Mapping[str, Any], subject: str) -> dict[str, Any]:
    route = _mapping(route, f"route {subject}")
    if route.get("subject") != subject:
        raise AdvisoryBoardError(f"route subject must be {subject}")
    for field in ("route_id", "provider_family", "resolved_model", "endpoint", "execution_location", "provider_registry_id", "policy_digest"):
        _text(route.get(field), f"route {subject}.{field}")
    if route["execution_location"] not in {"local_only", "remote_allowed"}:
        raise AdvisoryBoardError(f"route {subject}.execution_location is invalid")
    if not isinstance(route.get("reserved_cost_usd"), (int, float)) or not math.isfinite(route["reserved_cost_usd"]) or route["reserved_cost_usd"] < 0:
        raise AdvisoryBoardError(f"route {subject}.reserved_cost_usd must be finite and non-negative")
    candidate = dict(route)
    observed = candidate.pop("route_sha256", None)
    if observed != digest(candidate):
        raise AdvisoryBoardError(f"route {subject} integrity digest is invalid")
    return dict(route)


def bind_routes(proposal: Mapping[str, Any], routes: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Bind pre-dispatch, policy-resolved routes to an immutable proposal."""
    validated = validate_proposal(proposal)
    if not isinstance(routes, list) or [route.get("subject") if isinstance(route, Mapping) else None for route in routes] != list(ROUTE_SUBJECTS):
        raise AdvisoryBoardError("routes must contain one ordered pre-dispatch route for every persona and arbiter")
    normalized: list[dict[str, Any]] = []
    for route, subject in zip(routes, ROUTE_SUBJECTS, strict=True):
        candidate = dict(_mapping(route, f"route {subject}"))
        candidate.pop("route_sha256", None)
        candidate["route_sha256"] = digest(candidate)
        normalized.append(_validate_route(candidate, subject))
    envelope = _mapping(proposal["task_envelope"], "task_envelope")
    if sum(float(route["reserved_cost_usd"]) for route in normalized) > float(envelope["max_cost_usd"]):
        raise AdvisoryBoardError("route reservations exceed the proposal cost cap")
    if envelope["data_class"] in {"client", "confidential"} and any(route["execution_location"] != "local_only" for route in normalized):
        raise AdvisoryBoardError("client or confidential board routes must all be local_only")
    persona_routes = normalized[:-1]
    if len({route["provider_family"] for route in persona_routes}) < 2:
        raise AdvisoryBoardError("persona routes require at least two provider families")
    if len({route["resolved_model"] for route in persona_routes}) != len(persona_routes):
        raise AdvisoryBoardError("persona routes require distinct resolved models")
    if normalized[-1]["provider_family"] in {route["provider_family"] for route in persona_routes}:
        raise AdvisoryBoardError("arbiter route must use a provider family independent from persona routes")
    routed: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "stage": ROUTED_STAGE, "proposal": copy.deepcopy(dict(proposal)), "proposal_sha256": validated["contract_sha256"], "routes": normalized}
    routed["contract_sha256"] = digest(routed)
    validate_routed_contract(routed)
    return routed


def validate_routed_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    contract = _mapping(contract, "routed board contract")
    if contract.get("schema_version") != SCHEMA_VERSION or contract.get("stage") != ROUTED_STAGE:
        raise AdvisoryBoardError("routed board contract schema or stage is invalid")
    proposal = _mapping(contract.get("proposal"), "routed proposal")
    proposal_result = validate_proposal(proposal)
    if contract.get("proposal_sha256") != proposal_result["contract_sha256"]:
        raise AdvisoryBoardError("routed board contract is not bound to its proposal")
    routes = contract.get("routes")
    if not isinstance(routes, list) or [route.get("subject") if isinstance(route, Mapping) else None for route in routes] != list(ROUTE_SUBJECTS):
        raise AdvisoryBoardError("routed board contract has incomplete routes")
    for route, subject in zip(routes, ROUTE_SUBJECTS, strict=True):
        _validate_route(route, subject)
    envelope = _mapping(proposal["task_envelope"], "task_envelope")
    if sum(float(route["reserved_cost_usd"]) for route in routes) > float(envelope["max_cost_usd"]):
        raise AdvisoryBoardError("route reservations exceed the proposal cost cap")
    if envelope["data_class"] in {"client", "confidential"} and any(route["execution_location"] != "local_only" for route in routes):
        raise AdvisoryBoardError("client or confidential board routes must all be local_only")
    persona_routes = routes[:-1]
    if len({route["provider_family"] for route in persona_routes}) < 2:
        raise AdvisoryBoardError("persona routes require at least two provider families")
    if len({route["resolved_model"] for route in persona_routes}) != len(persona_routes):
        raise AdvisoryBoardError("persona routes require distinct resolved models")
    if routes[-1]["provider_family"] in {route["provider_family"] for route in persona_routes}:
        raise AdvisoryBoardError("arbiter route must use a provider family independent from persona routes")
    candidate = dict(contract)
    observed = candidate.pop("contract_sha256", None)
    if observed != digest(candidate):
        raise AdvisoryBoardError("routed board contract integrity digest is invalid")
    return {"status": "valid", "stage": ROUTED_STAGE, "contract_sha256": observed}


def _validate_usage(value: Any, label: str) -> None:
    usage = _mapping(value, label)
    for field in ("input_tokens", "output_tokens", "reasoning_tokens", "cache_tokens"):
        token_count = usage.get(field)
        if not isinstance(token_count, int) or token_count < 0:
            raise AdvisoryBoardError(f"{label}.{field} must be a non-negative integer")


def _assert_route_observed(run: Mapping[str, Any], route: Mapping[str, Any], label: str) -> float:
    if run.get("route_sha256") != route.get("route_sha256"):
        raise AdvisoryBoardError(f"{label} route digest does not match the pre-dispatch manifest")
    for field in ("provider_family", "resolved_model", "endpoint", "execution_location", "provider_registry_id", "policy_digest"):
        if run.get(field) != route.get(field):
            raise AdvisoryBoardError(f"{label} observed {field} differs from the pre-dispatch route")
    _digest(run.get("price_snapshot_sha256"), f"{label}.price_snapshot_sha256")
    _validate_usage(run.get("usage"), f"{label}.usage")
    billed = run.get("billed_cost_usd")
    if run.get("cost_status") != "observed" or not isinstance(billed, (int, float)) or not math.isfinite(billed) or billed < 0:
        raise AdvisoryBoardError(f"{label} must include observed finite cost")
    if float(billed) > float(route["reserved_cost_usd"]):
        raise AdvisoryBoardError(f"{label} exceeded its pre-dispatch reservation")
    return float(billed)


def _validate_candidate_benchmark(selection: Mapping[str, Any], persona_id: str) -> None:
    if selection.get("persona_id") != persona_id:
        raise AdvisoryBoardError(f"candidate benchmark persona must be {persona_id}")
    candidates = selection.get("candidates")
    if not isinstance(candidates, list) or len(candidates) < 2:
        raise AdvisoryBoardError("each persona needs at least two functional candidate profiles")
    candidate_ids: list[str] = []
    for candidate in candidates:
        candidate = _mapping(candidate, "functional candidate profile")
        candidate_ids.append(_text(candidate.get("profile_id"), "candidate profile_id"))
        if candidate.get("functional_profile_only") is not True:
            raise AdvisoryBoardError("candidate profile cannot represent or assess a real person")
        _text(candidate.get("mandate"), "candidate mandate")
        _text(candidate.get("known_limits"), "candidate known_limits")
        evidence = candidate.get("capability_evidence_ids")
        if not isinstance(evidence, list) or not evidence or any(not isinstance(item, str) or not item for item in evidence):
            raise AdvisoryBoardError("candidate profiles require capability evidence IDs")
        scores = _mapping(candidate.get("scores"), "candidate scores")
        if set(scores) != {"mandate_fit", "capability_evidence", "complementarity", "counter_argument_quality", "known_limits"}:
            raise AdvisoryBoardError("candidate benchmark scores must cover the fixed composition criteria")
        if any(not isinstance(score, (int, float)) or not 0 <= score <= 4 for score in scores.values()):
            raise AdvisoryBoardError("candidate benchmark scores must be between zero and four")
    if len(set(candidate_ids)) != len(candidate_ids):
        raise AdvisoryBoardError("candidate profile IDs must be unique")
    ranking = selection.get("ranked_profile_ids")
    if not isinstance(ranking, list) or ranking != candidate_ids or selection.get("selected_profile_id") != ranking[0]:
        raise AdvisoryBoardError("candidate benchmark must retain a complete ordered ranking and select its top profile")


def validate_run_receipt(contract: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_routed_contract(contract)
    receipt = _mapping(receipt, "board run receipt")
    if receipt.get("contract_sha256") != validated["contract_sha256"]:
        raise AdvisoryBoardError("board run receipt is not bound to this proposal")
    runs = receipt.get("persona_runs")
    expected_ids = [persona["id"] for persona in PERSONAS]
    if not isinstance(runs, list) or [item.get("persona_id") if isinstance(item, Mapping) else None for item in runs] != expected_ids:
        raise AdvisoryBoardError("board run receipt must contain one ordered run for each canonical persona")
    routes = _mapping(contract, "routed board contract")["routes"]
    route_by_subject = {route["subject"]: route for route in routes}
    families: set[str] = set()
    models: set[str] = set()
    cost = 0.0
    for run in runs:
        persona_id = run["persona_id"]
        family = _text(run.get("provider_family"), "persona provider_family")
        model = _text(run.get("resolved_model"), "persona resolved_model")
        if model in models:
            raise AdvisoryBoardError("each persona must use a distinct resolved model")
        models.add(model)
        families.add(family)
        cost += _assert_route_observed(run, route_by_subject[persona_id], f"persona {persona_id}")
        claims = run.get("claims")
        if not isinstance(claims, list) or not claims:
            raise AdvisoryBoardError("every persona must return non-empty claims")
        for claim in claims:
            claim = _mapping(claim, "persona claim")
            if claim.get("classification") not in CLAIM_CLASSES:
                raise AdvisoryBoardError("every claim must be FACT, INFERENCE, ASSUMPTION, or UNKNOWN")
            _text(claim.get("statement"), "claim.statement")
            if claim.get("classification") == "FACT":
                _text(claim.get("evidence_id"), "FACT claim.evidence_id")
    if len(families) < 2:
        raise AdvisoryBoardError("board run requires at least two distinct provider families")
    selections = receipt.get("candidate_benchmarks")
    if not isinstance(selections, list) or [item.get("persona_id") if isinstance(item, Mapping) else None for item in selections] != expected_ids:
        raise AdvisoryBoardError("board run receipt must benchmark candidates for every canonical persona")
    for selection, persona in zip(selections, expected_ids, strict=True):
        _validate_candidate_benchmark(_mapping(selection, "candidate benchmark"), persona)
    proposal = _mapping(contract, "routed board contract")["proposal"]
    if cost > float(_mapping(proposal["task_envelope"], "task_envelope")["max_cost_usd"]):
        raise AdvisoryBoardError("board run exceeded its reserved cost cap")
    arbiter = _mapping(receipt.get("arbiter"), "arbiter")
    if arbiter.get("outcome") not in ARBITER_OUTCOMES:
        raise AdvisoryBoardError("arbiter outcome is invalid")
    _text(arbiter.get("execution_context_id"), "arbiter.execution_context_id")
    if arbiter.get("authority") != "advisory_only" or arbiter.get("requested_actions") != []:
        raise AdvisoryBoardError("arbiter must have advisory-only authority and no execution actions")
    cost += _assert_route_observed(arbiter, route_by_subject["arbiter"], "arbiter")
    if _text(arbiter.get("provider_family"), "arbiter.provider_family") in families:
        raise AdvisoryBoardError("arbiter must be independent from all persona provider families")
    if not isinstance(arbiter.get("confidence"), (int, float)) or not 0 <= arbiter["confidence"] <= 1:
        raise AdvisoryBoardError("arbiter.confidence must be between zero and one")
    if receipt.get("activation") not in {None, "proposal_only"}:
        raise AdvisoryBoardError("board run receipt cannot activate personas or agents")
    return {"status": "verified", "outcome": arbiter["outcome"], "activation": "owner_approval_required", "observed_cost_usd": cost}


def _read_json(path: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdvisoryBoardError(f"unable to read JSON object from {path}: {exc}") from exc
    return dict(_mapping(value, f"JSON input {path}"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare and validate a governed five-persona advisory-board proposal.")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--grill-session", required=True)
    init.add_argument("--task-id", required=True)
    init.add_argument("--decision-question", required=True)
    init.add_argument("--data-class", required=True, choices=sorted(DATA_CLASSES))
    init.add_argument("--max-cost-usd", required=True, type=float)
    init.add_argument("--deadline-seconds", required=True, type=int)
    lint = commands.add_parser("lint")
    lint.add_argument("--contract", required=True)
    bind = commands.add_parser("bind-routes")
    bind.add_argument("--proposal", required=True)
    bind.add_argument("--routes", required=True)
    verify = commands.add_parser("verify-run")
    verify.add_argument("--contract", required=True)
    verify.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = create_proposal(_read_json(args.grill_session), task_id=args.task_id, decision_question=args.decision_question, data_class=args.data_class, max_cost_usd=args.max_cost_usd, deadline_seconds=args.deadline_seconds)
        elif args.command == "lint":
            result = validate_proposal(_read_json(args.contract))
        elif args.command == "bind-routes":
            routes = _read_json(args.routes).get("routes")
            if not isinstance(routes, list):
                raise AdvisoryBoardError("routes JSON must contain a routes list")
            result = bind_routes(_read_json(args.proposal), routes)
        else:
            result = validate_run_receipt(_read_json(args.contract), _read_json(args.receipt))
    except AdvisoryBoardError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
