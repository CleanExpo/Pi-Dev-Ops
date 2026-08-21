"""Cryptographic and canonicalization contract for Senior Harness admissions."""
from __future__ import annotations

import copy
import importlib.util
import math
import sys
import unicodedata
from pathlib import Path

import pytest

from app.server.senior_harness_admission import (
    AdmissionContractError,
    AdmissionVerificationError,
    ConsumerExpectation,
    PublicKeyRing,
    normalize_repository,
    normalize_scope,
    objective_digest,
    scope_digest,
    verify_signed_claim,
)


def _authority_module():
    path = (
        Path(__file__).parents[1]
        / "skills"
        / "senior-harness"
        / "scripts"
        / "admission_authority.py"
    )
    name = "senior_harness_admission_authority_contract_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def issued_child():
    module = _authority_module()
    authority = module.InMemoryAdmissionAuthority(
        module.generate_private_key(),
        signer_key_id="issuer-2026-08",
        audience="pi-ceo/build",
        clock=lambda: 1_800_000_000,
    )
    parent = authority.reserve_parent(
        source_kind="linear",
        source_id="issue-id",
        source_version="2026-08-21T01:02:03.000Z",
        repository="git@GitHub.COM:Unite-Group/RestoreAssist.git",
        objective="Ship the repair\r\nwithout drift",
        scope={"paths": ["app/**"], "max_files": 5},
        task_id="task-1",
        plan_id="plan-1",
        base_sha="a" * 40,
        node_contract_digest="sha256:" + "b" * 64,
        ttl_seconds=120,
        admission_ref="parent-1",
    )
    child = authority.derive_child(
        parent["claim"]["admission_ref"],
        node_id="1.1",
        reservation_ref="reservation-1",
        worker_id="worker-1",
        worker_context_id="context-1",
        session_id="session-1",
        node_contract_digest="sha256:" + "c" * 64,
        ttl_seconds=60,
        admission_ref="child-1",
    )
    claim = child["claim"]
    expectation = ConsumerExpectation(**{
        field: claim[field]
        for field in ConsumerExpectation.__dataclass_fields__
    })
    return authority, child, expectation


@pytest.mark.parametrize(
    "remote",
    [
        "https://user:secret@GitHub.COM/Unite-Group/RestoreAssist.git?token=no#frag",
        "ssh://git@github.com/Unite-Group/RestoreAssist.git/",
        "git@github.com:Unite-Group/RestoreAssist.git",
        "git://github.com/Unite-Group/RestoreAssist",
    ],
)
def test_repository_forms_have_one_credential_free_identity(remote):
    assert normalize_repository(remote) == "https://github.com/unite-group/restoreassist"


@pytest.mark.parametrize(
    "remote",
    [
        "/tmp/repo",
        "file:///tmp/repo",
        "https://github.com/owner",
        "https://github.com/a/b/c",
        "https://github.com/a%2Fb/repo",
    ],
)
def test_repository_rejects_non_remote_or_ambiguous_identity(remote):
    with pytest.raises(AdmissionContractError):
        normalize_repository(remote)


def test_objective_preserves_meaning_while_normalizing_unicode_and_newlines():
    decomposed = "Cafe\u0301\r\n  keep  spacing"
    composed = unicodedata.normalize("NFC", decomposed).replace("\r\n", "\n")

    assert objective_digest(decomposed) == objective_digest(composed)
    assert objective_digest("A  B") != objective_digest("A B")
    assert objective_digest("Case") != objective_digest("case")


def test_scope_is_recursive_sorted_and_rejects_ambiguous_values():
    left = {"z": ["Cafe\u0301\r\n", 1, True, None], "a": {"x": 2.5}}
    right = {"a": {"x": 2.5}, "z": ["Café\n", 1, True, None]}

    assert normalize_scope(left) == normalize_scope(right)
    assert scope_digest(left) == scope_digest(right)
    with pytest.raises(AdmissionContractError):
        scope_digest({"bad": math.inf})
    with pytest.raises(AdmissionContractError):
        scope_digest({1: "not a string key"})
    with pytest.raises(AdmissionContractError):
        scope_digest({"e\u0301": 1, "é": 2})
    with pytest.raises(AdmissionContractError):
        scope_digest(("tuples", "are not JSON arrays"))


def test_valid_child_verifies_against_every_consumer_binding(issued_child):
    authority, envelope, expectation = issued_child

    claim = verify_signed_claim(
        envelope,
        authority.public_key_ring(),
        expectation=expectation,
        now=1_800_000_001,
    )

    assert claim["claim_type"] == "child"
    assert claim["task_id"] == "task-1"
    assert claim["session_id"] == "session-1"


@pytest.mark.parametrize("field", list(ConsumerExpectation.__dataclass_fields__))
def test_every_bound_field_mutation_is_denied(issued_child, field):
    authority, envelope, expectation = issued_child
    values = {
        name: getattr(expectation, name)
        for name in ConsumerExpectation.__dataclass_fields__
    }
    values[field] = (
        values[field] + 1
        if isinstance(values[field], int)
        else (
            "https://github.com/another/repo"
            if field == "repository"
            else values[field] + "-different"
        )
    )

    with pytest.raises(AdmissionVerificationError, match="target mismatch"):
        verify_signed_claim(
            envelope,
            authority.public_key_ring(),
            expectation=ConsumerExpectation(**values),
            now=1_800_000_001,
        )


@pytest.mark.parametrize(
    "field",
    [
        "source_version",
        "repository",
        "objective_digest",
        "scope_digest",
        "worker_context_id",
        "expires_at",
    ],
)
def test_signed_claim_mutation_fails_before_target_comparison(issued_child, field):
    authority, envelope, expectation = issued_child
    tampered = copy.deepcopy(envelope)
    current = tampered["claim"][field]
    tampered["claim"][field] = current + 1 if isinstance(current, int) else current + "x"

    with pytest.raises(AdmissionVerificationError, match="digest"):
        verify_signed_claim(
            tampered,
            authority.public_key_ring(),
            expectation=expectation,
            now=1_800_000_001,
        )


def test_digest_rewrite_still_fails_signature(issued_child):
    authority, envelope, expectation = issued_child
    tampered = copy.deepcopy(envelope)
    tampered["claim"]["worker_id"] = "attacker"
    from app.server.senior_harness_admission import claim_digest

    tampered["claim"]["claim_digest"] = claim_digest(tampered["claim"])

    with pytest.raises(AdmissionVerificationError, match="signature"):
        verify_signed_claim(
            tampered,
            authority.public_key_ring(),
            expectation=expectation,
            now=1_800_000_001,
        )


def test_unknown_revoked_expired_and_future_claims_fail_closed(issued_child):
    authority, envelope, expectation = issued_child
    public = authority.public_key_base64url()

    with pytest.raises(AdmissionVerificationError, match="unknown"):
        verify_signed_claim(
            envelope,
            PublicKeyRing({"known-key": public}),
            now=1_800_000_001,
        )
    with pytest.raises(AdmissionVerificationError, match="revoked"):
        verify_signed_claim(
            envelope,
            authority.public_key_ring(revoked=True),
            expectation=expectation,
            now=1_800_000_001,
        )
    with pytest.raises(AdmissionVerificationError, match="expired"):
        verify_signed_claim(
            envelope,
            authority.public_key_ring(),
            expectation=expectation,
            now=1_800_000_060,
        )
    with pytest.raises(AdmissionVerificationError, match="not valid yet"):
        verify_signed_claim(
            envelope,
            authority.public_key_ring(),
            expectation=expectation,
            now=1_799_999_999,
        )


def test_envelope_and_claim_are_closed_objects(issued_child):
    authority, envelope, _expectation = issued_child
    envelope["authority"] = "caller says yes"
    with pytest.raises(AdmissionVerificationError, match="unknown fields"):
        verify_signed_claim(envelope, authority.public_key_ring(), now=1_800_000_001)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("base_sha", "main", "base SHA"),
        ("admission_ref", "child ref with spaces", "admission reference"),
        ("parent_ref", "parent ref with spaces", "parent admission reference"),
    ],
)
def test_claim_identifiers_match_the_durable_store_contract(
    issued_child, field, value, error,
):
    authority, envelope, _expectation = issued_child
    envelope["claim"][field] = value

    with pytest.raises(AdmissionVerificationError, match=error):
        verify_signed_claim(envelope, authority.public_key_ring(), now=1_800_000_001)
