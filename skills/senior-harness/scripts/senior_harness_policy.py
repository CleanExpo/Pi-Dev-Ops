"""Authority, discovery, forecast, and verification policy validation."""
from __future__ import annotations

from typing import Any

from senior_harness_core import require_mapping, require_nonempty
from senior_harness_moves import ALLOWED_AUTHORIZATION, MUTATING_KINDS


REQUIRED_SKILLS = {"model-router", "unlazy"}


def _validate_outcomes(outcomes: Any, errors: list[str]) -> None:
    if not isinstance(outcomes, list):
        errors.append("inferred_outcomes must be a list")
        return
    for index, outcome in enumerate(outcomes):
        item = require_mapping(outcome, f"inferred_outcomes[{index}]", errors)
        for field in ("statement", "provenance", "confidence", "authorization_status"):
            require_nonempty(item.get(field), f"inferred_outcomes[{index}].{field}", errors)
        confidence = item.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append(f"inferred_outcomes[{index}].confidence must be between 0 and 1")
        if item.get("authorization_status") != "proposal":
            errors.append(f"inferred_outcomes[{index}] must remain a proposal")


def _validate_move_authority(move: dict[str, Any], errors: list[str]) -> None:
    move_id = move.get("move_id")
    authorization = move.get("authorization_status")
    if authorization not in ALLOWED_AUTHORIZATION:
        errors.append(f"move {move_id} has invalid authorization_status")
    if move.get("authority_required") == "none" and authorization != "not-required":
        errors.append(f"move {move_id} requires authorization_status=not-required")
    if move.get("kind") not in MUTATING_KINDS:
        return
    if move.get("authority_required") == "none":
        errors.append(f"mutating move {move_id} must name its authority requirement")
    if authorization != "proposal":
        errors.append(
            f"move {move_id} must remain a proposal until an external trusted runtime authenticates authority"
        )
    if move.get("authority_source_id") is not None:
        errors.append(f"move {move_id} cannot claim an authority source in schema v1")


def validate_authority(contract: dict[str, Any], moves: list[dict[str, Any]], errors: list[str]) -> None:
    literal_request = contract.get("literal_request")
    require_nonempty(literal_request, "literal_request", errors)
    if contract.get("authorized_scope") != [literal_request]:
        errors.append("authorized_scope must contain only the literal_request in schema v1")
    if contract.get("authority_grants") != []:
        errors.append("schema v1 cannot authenticate authority grants; authority_grants must remain empty")
    _validate_outcomes(contract.get("inferred_outcomes", []), errors)
    for move in moves:
        _validate_move_authority(move, errors)


def _validate_discovery_run(run: dict[str, Any], index: int, errors: list[str]) -> float:
    fields = (
        "question", "source_allowlist", "privacy_allowlist", "max_minutes", "max_cost_usd",
        "retention_days", "value_of_information_threshold", "stop_conditions",
    )
    for field in fields:
        require_nonempty(run.get(field), f"discovery_runs[{index}].{field}", errors)
    for field in ("source_allowlist", "privacy_allowlist", "stop_conditions"):
        value = run.get(field)
        if not isinstance(value, list):
            errors.append(f"discovery_runs[{index}].{field} must be a list")
        elif not value or any(not isinstance(item, str) or not item for item in value):
            errors.append(f"discovery_runs[{index}].{field} must contain non-empty strings")
    max_minutes = run.get("max_minutes")
    if isinstance(max_minutes, bool) or not isinstance(max_minutes, (int, float)) or max_minutes <= 0:
        errors.append(f"discovery_runs[{index}].max_minutes must be positive")
    max_cost = run.get("max_cost_usd")
    if isinstance(max_cost, bool) or not isinstance(max_cost, (int, float)) or max_cost < 0:
        errors.append(f"discovery_runs[{index}].max_cost_usd must be non-negative")
        cost = 0.0
    else:
        cost = float(max_cost)
    retention = run.get("retention_days")
    if isinstance(retention, bool) or not isinstance(retention, int) or retention < 0:
        errors.append(f"discovery_runs[{index}].retention_days must be a non-negative integer")
    threshold = run.get("value_of_information_threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        errors.append(f"discovery_runs[{index}].value_of_information_threshold must be between 0 and 1")
    return cost


def _validate_forecast_outcomes(outcomes: Any, index: int, errors: list[str]) -> None:
    if not isinstance(outcomes, list) or len(outcomes) < 2:
        errors.append(f"forecasts[{index}].outcomes must contain at least two outcomes")
        return
    names: list[str] = []
    probabilities: list[float] = []
    for outcome_index, raw in enumerate(outcomes):
        label = f"forecasts[{index}].outcomes[{outcome_index}]"
        outcome = require_mapping(raw, label, errors)
        require_nonempty(outcome.get("name"), f"{label}.name", errors)
        probability = outcome.get("probability")
        if isinstance(probability, bool) or not isinstance(probability, (int, float)) or not 0 <= probability <= 1:
            errors.append(f"{label}.probability must be between 0 and 1")
        else:
            probabilities.append(float(probability))
        if isinstance(outcome.get("name"), str):
            names.append(outcome["name"])
    if len(names) != len(set(names)):
        errors.append(f"forecasts[{index}] outcome names must be unique")
    if len(probabilities) == len(outcomes) and abs(sum(probabilities) - 1.0) > 1e-9:
        errors.append(f"forecasts[{index}] probabilities must sum to 1")


def _validate_forecast(forecast: dict[str, Any], index: int, errors: list[str]) -> None:
    fields = (
        "forecast_id", "mutual_exclusivity_rationale", "resolution_criterion",
        "resolution_source", "resolution_date", "scoring_rule_version", "freeze_time",
    )
    for field in fields:
        require_nonempty(forecast.get(field), f"forecasts[{index}].{field}", errors)
    _validate_forecast_outcomes(forecast.get("outcomes"), index, errors)


def validate_discovery_and_forecasts(contract: dict[str, Any], moves: list[dict[str, Any]], errors: list[str]) -> None:
    runs = contract.get("discovery_runs")
    classification = contract.get("classification")
    horizon_required = classification.get("horizon_required") if isinstance(classification, dict) else None
    if not isinstance(runs, list):
        errors.append("discovery_runs must be a list")
        runs = []
    if horizon_required and not runs:
        errors.append("horizon-bearing work requires at least one bounded discovery run")
    discovery_cost = sum(
        _validate_discovery_run(require_mapping(raw, f"discovery_runs[{index}]", errors), index, errors)
        for index, raw in enumerate(runs)
    )
    limits = contract.get("limits")
    total_cost = limits.get("max_cost_usd") if isinstance(limits, dict) else None
    if isinstance(total_cost, (int, float)) and not isinstance(total_cost, bool) and discovery_cost > total_cost:
        errors.append("discovery run budgets exceed limits.max_cost_usd")
    forecasts = contract.get("forecasts")
    if not isinstance(forecasts, list):
        errors.append("forecasts must be a list")
        forecasts = []
    if any(move.get("kind") == "forecast" for move in moves) and not forecasts:
        errors.append("forecast moves require a ForecastContract")
    for index, raw in enumerate(forecasts):
        _validate_forecast(require_mapping(raw, f"forecasts[{index}]", errors), index, errors)


def validate_routing_and_verification(contract: dict[str, Any], errors: list[str]) -> None:
    skills = contract.get("required_skills")
    invalid_skills = (
        not isinstance(skills, list)
        or any(not isinstance(skill, str) for skill in skills)
        or not REQUIRED_SKILLS.issubset(set(skills))
    )
    if invalid_skills:
        errors.append("required_skills must include model-router and unlazy")
    verification = require_mapping(contract.get("verification"), "verification", errors)
    principals = {field: verification.get(field) for field in ("builder_id", "verifier_id", "arbiter_id")}
    for field, value in principals.items():
        require_nonempty(value, f"verification.{field}", errors)
    if principals["builder_id"] and principals["verifier_id"] == principals["builder_id"]:
        errors.append("verifier_id must be independent from builder_id")
    if principals["arbiter_id"] and principals["arbiter_id"] in {principals["builder_id"], principals["verifier_id"]}:
        errors.append("arbiter_id must be independent from builder_id and verifier_id")
    receipt_types = verification.get("required_receipt_types")
    if not isinstance(receipt_types, list) or not receipt_types or any(not isinstance(item, str) or not item for item in receipt_types):
        errors.append("verification.required_receipt_types must be a non-empty list of strings")
    if verification.get("receipts") != []:
        errors.append("schema v1 cannot authenticate receipts; verification.receipts must remain empty")


def validate_capability_pack(contract: dict[str, Any], errors: list[str]) -> None:
    pack = require_mapping(contract.get("capability_pack"), "capability_pack", errors)
    require_nonempty(pack.get("pack_id"), "capability_pack.pack_id", errors)
    if pack.get("status") != "candidate":
        errors.append("schema v1 accepts candidate packs only; promotion requires a trusted signed exact-SHA adapter")
    if pack.get("independent_verification_receipt") is not None or pack.get("qualified_replay_receipt") is not None:
        errors.append("candidate packs cannot claim verification or replay receipts")
    if not isinstance(pack.get("revalidate_on"), list) or not pack.get("revalidate_on"):
        errors.append("capability_pack.revalidate_on must be a non-empty list")
