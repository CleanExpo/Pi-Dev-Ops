from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "skills" / "senior-harness" / "scripts"))

from advisory_board import AdvisoryBoardError, PERSONAS, ROUTE_SUBJECTS, bind_routes, create_proposal, validate_proposal, validate_run_receipt  # noqa: E402
from grill_session import SHARED_UNDERSTANDING_PHRASE, answer_pending_question, confirm_shared_understanding, digest, start_session  # noqa: E402


def _grill(tmp_path: Path) -> dict:
    sketch = tmp_path / "Vault" / "Sketches" / "board.md"
    sketch.parent.mkdir(parents=True, exist_ok=True)
    sketch.write_text("# Board\n", encoding="utf-8")
    session = start_session(
        "Choose a board for an important decision.",
        sketch,
        [{"leaf_id": "purpose", "kind": "human-decision", "depends_on": [], "question": "What matters?", "recommendation": "Evidence first.", "rationale": "Prevents invented authority."}],
        materialization_path=sketch.parent.parent / "Grills" / "board.md",
    )
    return confirm_shared_understanding(answer_pending_question(session, "Proof before opinion.", "DECIDED"), SHARED_UNDERSTANDING_PHRASE)


def _proposal(tmp_path: Path) -> dict:
    return create_proposal(_grill(tmp_path), task_id="board-001", decision_question="Which perspectives best stress-test this decision?", data_class="internal", max_cost_usd=20, deadline_seconds=900)


def _routed(proposal: dict) -> dict:
    routes = []
    for index, subject in enumerate(ROUTE_SUBJECTS):
        routes.append({
            "subject": subject,
            "route_id": f"route-{index}",
            "provider_family": "family-a" if index < 3 else "family-b" if index < 5 else "family-c",
            "resolved_model": f"model-{index}",
            "endpoint": f"local://provider-{index}",
            "execution_location": "remote_allowed",
            "provider_registry_id": f"registry-{index}",
            "policy_digest": digest({"policy": index}),
            "reserved_cost_usd": 2.0,
        })
    return bind_routes(proposal, routes)


def _receipt(contract: dict) -> dict:
    runs = []
    for index, persona in enumerate(PERSONAS):
        runs.append({
            "persona_id": persona["id"],
            "provider_family": "family-a" if index < 3 else "family-b",
            "resolved_model": f"model-{index}",
            "endpoint": f"local://provider-{index}",
            "execution_location": "remote_allowed",
            "provider_registry_id": f"registry-{index}",
            "policy_digest": digest({"policy": index}),
            "route_sha256": contract["routes"][index]["route_sha256"],
            "price_snapshot_sha256": digest({"model": index}),
            "cost_status": "observed",
            "billed_cost_usd": 1.0,
            "usage": {"input_tokens": 1, "output_tokens": 1, "reasoning_tokens": 0, "cache_tokens": 0},
            "claims": [{"classification": "FACT", "statement": "The Grill handoff exists.", "evidence_id": "grill-receipt"}],
        })
    return {
        "contract_sha256": contract["contract_sha256"],
        "persona_runs": runs,
        "candidate_benchmarks": [
            {"persona_id": persona["id"], "candidates": [
                {"profile_id": f"{persona['id']}-candidate-a", "functional_profile_only": True, "mandate": "Test the decision.", "known_limits": "Does not execute.", "capability_evidence_ids": ["grill-receipt"], "scores": {"mandate_fit": 3, "capability_evidence": 3, "complementarity": 3, "counter_argument_quality": 3, "known_limits": 3}},
                {"profile_id": f"{persona['id']}-candidate-b", "functional_profile_only": True, "mandate": "Challenge the decision.", "known_limits": "Does not decide.", "capability_evidence_ids": ["grill-receipt"], "scores": {"mandate_fit": 2, "capability_evidence": 2, "complementarity": 2, "counter_argument_quality": 2, "known_limits": 2}},
            ], "ranked_profile_ids": [f"{persona['id']}-candidate-a", f"{persona['id']}-candidate-b"], "selected_profile_id": f"{persona['id']}-candidate-a"}
            for persona in PERSONAS
        ],
        "arbiter": {"outcome": "APPROVE_FOR_NEXT_GATE", "execution_context_id": "fresh-verifier", "authority": "advisory_only", "requested_actions": [], "provider_family": "family-c", "resolved_model": "model-5", "endpoint": "local://provider-5", "execution_location": "remote_allowed", "provider_registry_id": "registry-5", "policy_digest": digest({"policy": 5}), "route_sha256": contract["routes"][5]["route_sha256"], "price_snapshot_sha256": digest({"model": 5}), "cost_status": "observed", "billed_cost_usd": 1.0, "usage": {"input_tokens": 1, "output_tokens": 1, "reasoning_tokens": 0, "cache_tokens": 0}, "confidence": 0.8},
        "activation": "proposal_only",
    }


def test_board_requires_a_confirmed_sealed_grill_handoff(tmp_path: Path) -> None:
    session = _grill(tmp_path)
    session["state"] = "awaiting-confirmation"
    with pytest.raises(AdvisoryBoardError, match="invalid Grill"):
        create_proposal(session, task_id="board-001", decision_question="Choose", data_class="internal", max_cost_usd=1, deadline_seconds=60)


def test_proposal_has_five_complementary_personas_and_zero_activation_authority(tmp_path: Path) -> None:
    proposal = _proposal(tmp_path)
    assert [item["id"] for item in proposal["personas"]] == [item["id"] for item in PERSONAS]
    assert validate_proposal(proposal)["activation"] == "proposal_only"
    assert proposal["activation"]["automatic_activation"] is False


def test_proposal_rejects_silent_fallback_remote_client_data_and_activation(tmp_path: Path) -> None:
    proposal = _proposal(tmp_path)
    proposal["provider_protocol"]["silent_fallback"] = True
    with pytest.raises(AdvisoryBoardError, match="silent fallback"):
        validate_proposal(proposal)

    proposal = _proposal(tmp_path)
    proposal["task_envelope"].update({"data_class": "client", "allowed_execution_location": "remote_allowed"})
    with pytest.raises(AdvisoryBoardError, match="local_only"):
        validate_proposal(proposal)

    proposal = _proposal(tmp_path)
    proposal["activation"]["automatic_activation"] = True
    with pytest.raises(AdvisoryBoardError, match="activation authority"):
        validate_proposal(proposal)


def test_run_receipt_requires_diversity_evidence_cost_and_independent_arbiter(tmp_path: Path) -> None:
    routed = _routed(_proposal(tmp_path))
    receipt = _receipt(routed)
    assert validate_run_receipt(routed, receipt)["status"] == "verified"

    same_model = copy.deepcopy(receipt)
    same_model["persona_runs"][1]["resolved_model"] = "model-0"
    with pytest.raises(AdvisoryBoardError, match="distinct resolved model"):
        validate_run_receipt(routed, same_model)

    same_arbiter = copy.deepcopy(receipt)
    same_arbiter["arbiter"]["provider_family"] = "family-a"
    with pytest.raises(AdvisoryBoardError, match="observed provider_family differs"):
        validate_run_receipt(routed, same_arbiter)

    fact_without_evidence = copy.deepcopy(receipt)
    del fact_without_evidence["persona_runs"][0]["claims"][0]["evidence_id"]
    with pytest.raises(AdvisoryBoardError, match="FACT claim.evidence_id"):
        validate_run_receipt(routed, fact_without_evidence)

    one_candidate = copy.deepcopy(receipt)
    one_candidate["candidate_benchmarks"][0]["candidates"] = one_candidate["candidate_benchmarks"][0]["candidates"][:1]
    with pytest.raises(AdvisoryBoardError, match="at least two functional candidate"):
        validate_run_receipt(routed, one_candidate)

    route_mismatch = copy.deepcopy(receipt)
    route_mismatch["persona_runs"][0]["execution_location"] = "local_only"
    with pytest.raises(AdvisoryBoardError, match="observed execution_location differs"):
        validate_run_receipt(routed, route_mismatch)

    missing_usage = copy.deepcopy(receipt)
    del missing_usage["persona_runs"][0]["usage"]
    with pytest.raises(AdvisoryBoardError, match="usage must be an object"):
        validate_run_receipt(routed, missing_usage)


def test_route_manifest_blocks_remote_client_lanes_before_dispatch(tmp_path: Path) -> None:
    client_proposal = create_proposal(
        _grill(tmp_path),
        task_id="client-board-001",
        decision_question="Which perspectives safely review this client decision?",
        data_class="client",
        max_cost_usd=20,
        deadline_seconds=900,
    )
    routes = copy.deepcopy(_routed(_proposal(tmp_path))["routes"])
    for route in routes:
        route.pop("route_sha256")
    with pytest.raises(AdvisoryBoardError, match="all be local_only"):
        bind_routes(client_proposal, routes)
