from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "skills" / "senior-harness" / "scripts"))

from senior_harness import ContractError, attempt_fingerprint, bind_attempt, intake, ready_moves, validate_contract  # noqa: E402


FIXTURE = REPO_ROOT / "tests" / "fixtures" / "senior_harness_self_host.json"


def contract() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    # The committed contract is deliberately bound to the self-hosting
    # worktree that produced it. Rebind only the runtime identity fields so
    # this validator suite remains meaningful in clean CI clones/worktrees.
    payload["repository"]["worktree"] = str(REPO_ROOT)
    payload["repository"]["base_sha"] = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    return payload


def error_text(payload: dict) -> str:
    with pytest.raises(ContractError) as exc:
        validate_contract(payload)
    return str(exc.value)


def test_self_hosting_contract_is_a_valid_eighteen_move_horizon() -> None:
    result = validate_contract(contract())

    assert result["status"] == "valid"
    assert result["move_count"] == 18
    assert result["longest_path"] == 18
    assert result["horizon_required"] is True
    assert result["contract_digest"].startswith("sha256:")


def test_horizon_and_admission_moves_are_never_returned_as_dispatch_ready() -> None:
    payload = contract()
    assert ready_moves(payload) == []

    for move in payload["move_graph"][:6]:
        move["status"] = "passed"
    payload["move_graph"][6]["status"] = "ready"
    assert ready_moves(payload) == ["M07"]


def test_intake_preserves_literal_request_as_the_only_authorized_scope() -> None:
    payload = intake("  Build the control layer  ", horizon_required=True)

    assert payload["literal_request"] == "  Build the control layer  "
    assert payload["authorized_scope"] == ["  Build the control layer  "]
    assert payload["inferred_outcomes"] == []
    assert payload["classification"]["horizon_required"] is True
    assert payload["limits"]["max_same_path_attempts"] == 2
    assert payload["limits"]["max_minutes_without_new_authoritative_evidence"] == 5


def test_horizon_gate_rejects_short_graphs() -> None:
    payload = contract()
    payload["move_graph"] = payload["move_graph"][:14]

    assert "horizon path must contain 15-20 distinct state-bearing moves; found 14" in error_text(payload)


def test_graph_gate_rejects_cycles() -> None:
    payload = contract()
    payload["move_graph"][0]["parents"] = ["M18"]

    assert "move_graph contains a cycle" in error_text(payload)


def test_graph_gate_rejects_duplicate_state_deltas() -> None:
    payload = contract()
    payload["move_graph"][1]["state_delta"] = payload["move_graph"][0]["state_delta"]

    assert "duplicate state_delta values are not structurally distinct moves" in error_text(payload)


def test_graph_gate_resolves_prerequisites_and_caps_workers() -> None:
    missing = contract()
    missing["move_graph"][1]["prerequisites"] = ["M404"]
    assert "references missing prerequisite M404" in error_text(missing)

    unbounded = contract()
    unbounded["limits"]["max_parallel_workers"] = 101
    assert "max_parallel_workers must be between 1 and 100" in error_text(unbounded)

    not_ready = contract()
    for move in not_ready["move_graph"][:6]:
        move["status"] = "passed"
    not_ready["move_graph"][6]["status"] = "ready"
    not_ready["move_graph"][6]["prerequisites"] = ["M18"]
    assert ready_moves(not_ready) == []


def test_horizon_cannot_execute_or_bypass_admission() -> None:
    payload = contract()
    move = payload["move_graph"][4]
    move["kind"] = "execute"
    move["authority_required"] = "repository-write"
    move["authorization_status"] = "approved"

    errors = error_text(payload)
    assert "kind execute is not allowed on plane horizon" in errors


def test_execution_requires_explicit_authority() -> None:
    payload = contract()
    payload["move_graph"][11]["authorization_status"] = "approved"

    assert "must remain a proposal until an external trusted runtime authenticates authority" in error_text(payload)


def test_mutating_aliases_cannot_evade_authority() -> None:
    payload = contract()
    payload["move_graph"][11]["kind"] = "write-files"
    payload["move_graph"][11]["authorization_status"] = "approved"

    assert "must remain a proposal until an external trusted runtime authenticates authority" in error_text(payload)


def test_schema_v1_rejects_self_authenticating_authority_grants() -> None:
    payload = contract()
    payload["authority_grants"] = [{
        "grant_id": "self-approved",
        "authority": "repository-write",
        "source_type": "literal-request",
        "source_digest": "sha256:" + "0" * 64,
        "move_ids": ["M12"],
    }]

    assert "schema v1 cannot authenticate authority grants" in error_text(payload)


def test_mutating_moves_cannot_claim_an_authority_source() -> None:
    payload = contract()
    payload["move_graph"][11]["authority_source_id"] = "made-up-self-approval"

    assert "cannot claim an authority source in schema v1" in error_text(payload)


def test_delivery_cannot_remove_or_bypass_the_admission_move() -> None:
    payload = contract()
    payload["move_graph"][5]["kind"] = "route"

    errors = error_text(payload)
    assert "bypasses admission from Horizon to delivery" in errors
    assert "delivery move M07 has no admitted ancestor" in errors


def test_inferred_outcomes_cannot_authorize_themselves() -> None:
    payload = contract()
    payload["inferred_outcomes"][0]["authorization_status"] = "approved"

    assert "inferred_outcomes[0] must remain a proposal" in error_text(payload)


def test_authorized_scope_cannot_silently_expand_beyond_the_literal_request() -> None:
    payload = contract()
    payload["authorized_scope"].append("Commercialise the product")

    assert "authorized_scope must contain only the literal_request" in error_text(payload)


def test_horizon_discovery_must_be_operationally_bounded() -> None:
    payload = contract()
    payload["discovery_runs"][0]["stop_conditions"] = []

    assert "discovery_runs[0].stop_conditions must be non-empty" in error_text(payload)


def test_forecast_contract_requires_probabilities_to_sum_to_one() -> None:
    payload = contract()
    payload["forecasts"][0]["outcomes"][1]["probability"] = 0.3

    assert "forecasts[0] probabilities must sum to 1" in error_text(payload)


def test_builder_verifier_and_arbiter_must_be_independent() -> None:
    payload = contract()
    payload["verification"]["verifier_id"] = payload["verification"]["builder_id"]

    assert "verifier_id must be independent from builder_id" in error_text(payload)


def test_untrusted_receipt_strings_cannot_become_proof() -> None:
    payload = contract()
    payload["verification"]["receipts"] = ["self-asserted"]

    assert "schema v1 cannot authenticate receipts" in error_text(payload)


def test_repository_identity_must_be_exact_git_shas() -> None:
    payload = contract()
    payload["repository"]["base_sha"] = "main"

    assert "repository.base_sha must be a 40-character" in error_text(payload)

    nonexistent = contract()
    nonexistent["repository"]["base_sha"] = "0" * 40
    assert "does not resolve to a commit" in error_text(nonexistent)


def test_repository_identity_is_bound_to_the_declared_worktree() -> None:
    missing = contract()
    missing["repository"]["worktree"] = "/definitely/not/a/real/senior-harness-worktree"
    assert "repository.worktree must exist" in error_text(missing)

    wrong_head = contract()
    wrong_head["repository"]["candidate_sha"] = subprocess.run(
        ["git", "rev-list", "--max-parents=0", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()[0]
    # The declared candidate must describe this exact checkout, not merely any resolvable commit.
    assert "candidate_sha must equal repository.worktree HEAD" in error_text(wrong_head)


def test_repository_ancestry_ignores_local_replace_and_grafts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )

    assert git("init", "-q").returncode == 0
    assert git("config", "user.name", "Senior Harness Test").returncode == 0
    assert git("config", "user.email", "senior-harness@example.invalid").returncode == 0
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    assert git("add", "base.txt").returncode == 0
    assert git("commit", "-q", "-m", "base").returncode == 0
    base_sha = git("rev-parse", "HEAD").stdout.strip()

    assert git("checkout", "--orphan", "unrelated").returncode == 0
    (repo / "base.txt").unlink()
    (repo / "candidate.txt").write_text("candidate\n", encoding="utf-8")
    assert git("add", "-A").returncode == 0
    assert git("commit", "-q", "-m", "candidate").returncode == 0
    candidate_sha = git("rev-parse", "HEAD").stdout.strip()

    assert git("merge-base", "--is-ancestor", base_sha, candidate_sha).returncode == 1
    assert git("replace", "--graft", candidate_sha, base_sha).returncode == 0
    assert git("merge-base", "--is-ancestor", base_sha, candidate_sha).returncode == 0

    payload = contract()
    payload["repository"] = {
        "worktree": str(repo),
        "base_sha": base_sha,
        "candidate_sha": candidate_sha,
    }

    assert "repository.base_sha must be an ancestor" in error_text(payload)


def test_task_id_is_derived_from_the_exact_literal_request() -> None:
    payload = contract()
    payload["task_id"] = "made-up"

    assert "task_id must be derived from the exact literal_request" in error_text(payload)


def test_attempt_fingerprint_rejects_relabelled_same_pathway() -> None:
    payload = contract()
    base = {
        "route_id": "route-sql",
        "input_sha256": "sha256:" + "a" * 64,
        "problem_id": "P-sql",
        "hypothesis": "migration drift",
        "method": "inspect-generated-file",
        "tool_path": "filesystem",
        "source_set": ["migration.sql"],
        "model_class": "senior",
        "status": "failed",
        "started_at": "2026-08-21T15:28:00+10:00",
        "last_authoritative_evidence_at": "2026-08-21T15:29:00+10:00",
        "new_authoritative_evidence_ids": [],
    }
    first = bind_attempt(payload, {**base, "attempt_id": "A1"})
    second = bind_attempt(payload, {**base, "attempt_id": "A2"})
    payload["attempts"] = [first, second]

    assert "repeats an already attempted pathway" in error_text(payload)


def test_attempt_fingerprint_normalizes_source_order() -> None:
    first = {
        "route_id": "route-order",
        "input_sha256": "sha256:" + "b" * 64,
        "problem_id": "P-order",
        "hypothesis": "same",
        "method": "same",
        "tool_path": "same",
        "source_set": ["source-b", "source-a"],
        "model_class": "senior",
    }
    second = {
        **first,
        "hypothesis": "a paraphrased label cannot evade the gate",
        "source_set": ["source-a", "source-b"],
    }

    assert attempt_fingerprint(first) == attempt_fingerprint(second)


def test_attempt_route_and_input_labels_are_bound_to_the_frozen_task() -> None:
    payload = contract()
    attempt = bind_attempt(
        payload,
        {
            "problem_id": "P-bind",
            "hypothesis": "binding",
            "method": "inspect",
            "tool_path": "filesystem",
            "source_set": ["source"],
            "model_class": "senior",
            "status": "active",
            "started_at": "2026-08-21T15:28:00+10:00",
            "last_authoritative_evidence_at": "2026-08-21T15:29:00+10:00",
            "new_authoritative_evidence_ids": [],
        },
    )
    attempt["route_id"] = "sha256:" + "f" * 64
    attempt["fingerprint"] = attempt_fingerprint(attempt)
    payload["attempts"] = [attempt]

    assert "route_id is not bound to the frozen route handle" in error_text(payload)


def test_two_distinct_failures_require_an_independent_uncertainty_case() -> None:
    payload = contract()
    attempts = []
    for method in ("inspect-file", "query-source"):
        attempt = {
            "route_id": "route-runtime",
            "input_sha256": "sha256:" + "c" * 64,
            "problem_id": "P-runtime",
            "hypothesis": "configuration drift",
            "method": method,
            "tool_path": method,
            "source_set": ["authoritative-source"],
            "model_class": "senior",
            "status": "failed",
            "started_at": "2026-08-21T15:28:00+10:00",
            "last_authoritative_evidence_at": "2026-08-21T15:29:00+10:00",
            "new_authoritative_evidence_ids": [],
        }
        attempts.append(bind_attempt(payload, attempt))
    payload["attempts"] = attempts

    assert "requires an open independent uncertainty case after two failures" in error_text(payload)

    payload["uncertainty_cases"] = [
        {
            "problem_id": "P-runtime",
            "status": "open",
            "stop_current_path": True,
            "specialist_ids": ["specialist-a", "specialist-b"],
            "arbiter_id": "arbiter-c",
            "evidence_ids": ["E-failure-a", "E-failure-b"],
            "experiment": "Replay against the authoritative runtime source.",
            "resolution_criterion": "The source and runtime replay agree.",
        }
    ]
    assert validate_contract(payload)["status"] == "valid"


def test_runner_errors_count_toward_the_two_attempt_stop() -> None:
    payload = contract()
    attempts = []
    for method in ("runner-a", "runner-b"):
        attempt = {
            "route_id": "route-runner",
            "input_sha256": "sha256:" + "d" * 64,
            "problem_id": "P-runner",
            "hypothesis": "runner cannot reach source",
            "method": method,
            "tool_path": method,
            "source_set": ["runtime"],
            "model_class": "senior",
            "status": "runner-error",
            "started_at": "2026-08-21T15:28:00+10:00",
            "last_authoritative_evidence_at": "2026-08-21T15:29:00+10:00",
            "new_authoritative_evidence_ids": [],
        }
        attempts.append(bind_attempt(payload, attempt))
    payload["attempts"] = attempts

    assert "requires an open independent uncertainty case after two failures" in error_text(payload)


def test_five_minutes_without_new_evidence_opens_a_case() -> None:
    payload = contract()
    attempt = {
        "route_id": "route-stale",
        "input_sha256": "sha256:" + "e" * 64,
        "problem_id": "P-stale",
        "hypothesis": "source unavailable",
        "method": "query-source",
        "tool_path": "connector",
        "source_set": ["runtime"],
        "model_class": "senior",
        "status": "active",
        "started_at": "2026-08-21T15:20:00+10:00",
        "last_authoritative_evidence_at": "2026-08-21T15:20:00+10:00",
        "new_authoritative_evidence_ids": [],
    }
    payload["attempts"] = [bind_attempt(payload, attempt)]

    assert "requires an open uncertainty case after evidence freshness expired" in error_text(payload)


def test_future_evidence_timestamps_cannot_evade_the_freshness_gate() -> None:
    payload = contract()
    attempt = bind_attempt(
        payload,
        {
            "problem_id": "P-future",
            "hypothesis": "clock skew",
            "method": "inspect",
            "tool_path": "filesystem",
            "source_set": ["source"],
            "model_class": "senior",
            "status": "active",
            "started_at": "2026-08-21T15:31:00+10:00",
            "last_authoritative_evidence_at": "2026-08-21T15:32:00+10:00",
            "new_authoritative_evidence_ids": [],
        },
    )
    payload["attempts"] = [attempt]

    errors = error_text(payload)
    assert "started_at cannot be later than observed_at" in errors
    assert "last_authoritative_evidence_at cannot be later than observed_at" in errors


def test_uncertainty_case_rejects_a_missing_arbiter_and_experiment() -> None:
    payload = contract()
    payload["uncertainty_cases"] = [
        {
            "problem_id": "P-empty",
            "status": "open",
            "stop_current_path": True,
            "specialist_ids": ["specialist-a", "specialist-b"],
            "arbiter_id": None,
            "evidence_ids": [],
            "experiment": "",
            "resolution_criterion": "",
        }
    ]

    errors = error_text(payload)
    assert "arbiter_id must be a non-empty string" in errors
    assert "evidence_ids must contain evidence ids" in errors


def test_provisional_and_durable_promotion_require_receipts() -> None:
    provisional = contract()
    provisional["capability_pack"]["status"] = "provisional"
    assert "schema v1 accepts candidate packs only" in error_text(provisional)

    durable = copy.deepcopy(provisional)
    durable["capability_pack"]["status"] = "durable"
    durable["capability_pack"]["independent_verification_receipt"] = "yes"
    durable["capability_pack"]["qualified_replay_receipt"] = "yes"
    assert "schema v1 accepts candidate packs only" in error_text(durable)


def test_documented_cli_lints_the_self_hosting_contract(tmp_path: Path) -> None:
    bound_fixture = tmp_path / "senior_harness_self_host.json"
    bound_fixture.write_text(json.dumps(contract()), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "skills/senior-harness/scripts/senior_harness.py",
            "lint",
            str(bound_fixture),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["longest_path"] == 18


def test_cli_fails_closed_with_machine_readable_errors(tmp_path: Path) -> None:
    payload = contract()
    payload["verification"]["arbiter_id"] = payload["verification"]["verifier_id"]
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "skills/senior-harness/scripts/senior_harness.py", "lint", str(invalid)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    error = json.loads(result.stderr)
    assert error["status"] == "invalid"
    assert any("arbiter_id must be independent" in message for message in error["errors"])


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda payload: payload.update(required_skills=[{"bad": "type"}]), "required_skills must include"),
        (lambda payload: payload["move_graph"][1].update(parents=[{"bad": "type"}]), "parent ids must be strings"),
        (lambda payload: payload["move_graph"][1].update(parents=None), "parents must be a list"),
        (lambda payload: payload.update(classification=[]), "classification must be an object"),
        (
            lambda payload: payload.update(
                uncertainty_cases=[
                    {
                        "problem_id": "P-bad",
                        "status": "open",
                        "stop_current_path": True,
                        "specialist_ids": [{"bad": "type"}],
                        "arbiter_id": "arbiter",
                        "evidence_ids": ["E-bad"],
                        "experiment": "Controlled replay",
                        "resolution_criterion": "Evidence converges",
                    }
                ]
            ),
            "specialist_ids must be a list of strings",
        ),
    ],
)
def test_invalid_nested_types_fail_closed_without_a_traceback(mutator, expected: str) -> None:
    payload = contract()
    mutator(payload)

    assert expected in error_text(payload)
