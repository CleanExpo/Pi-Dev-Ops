"""Credential-free lifecycle tests for the external admission authority."""
from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.server.senior_harness_admission import (
    AdmissionVerificationError,
    ConsumerExpectation,
    PublicKeyRing,
)


def _authority_module():
    path = (
        Path(__file__).parents[1]
        / "skills"
        / "senior-harness"
        / "scripts"
        / "admission_authority.py"
    )
    name = "senior_harness_admission_authority_service_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Clock:
    def __init__(self, value=1_800_000_000):
        self.value = value

    def __call__(self):
        return self.value


def _setup(*, parent_ttl=120, child_ttl=60):
    module = _authority_module()
    clock = Clock()
    authority = module.InMemoryAdmissionAuthority(
        module.generate_private_key(),
        signer_key_id="issuer-1",
        audience="pi-ceo/build",
        clock=clock,
    )
    parent = authority.reserve_parent(
        source_kind="linear",
        source_id="linear-id-1",
        source_version="updated-at-1",
        repository="https://github.com/Org/Repo.git",
        objective="Build this exact thing",
        scope={"paths": ["app/**"], "max_files": 4},
        task_id="task-1",
        plan_id="plan-1",
        base_sha="a" * 40,
        node_contract_digest="sha256:" + "b" * 64,
        ttl_seconds=parent_ttl,
        admission_ref="parent-1",
    )
    child = authority.derive_child(
        "parent-1",
        node_id="1.2",
        reservation_ref="reservation-1",
        worker_id="worker-1",
        worker_context_id="context-1",
        session_id="session-1",
        node_contract_digest="sha256:" + "c" * 64,
        ttl_seconds=child_ttl,
        admission_ref="child-1",
    )
    expectation = ConsumerExpectation(**{
        field: child["claim"][field]
        for field in ConsumerExpectation.__dataclass_fields__
    })
    assert child["claim"]["task_id"] == "task-1"
    return module, clock, authority, parent, child, expectation


def test_parent_and_child_are_signed_immutable_lineage():
    _module, _clock, authority, parent, child, _expectation = _setup(
        parent_ttl=30,
        child_ttl=90,
    )

    assert parent["claim"]["claim_type"] == "parent"
    assert child["claim"]["claim_type"] == "child"
    assert child["claim"]["parent_ref"] == "parent-1"
    assert child["claim"]["repository"] == parent["claim"]["repository"]
    assert child["claim"]["source_version"] == parent["claim"]["source_version"]
    assert child["claim"]["expires_at"] == parent["claim"]["expires_at"]

    child["claim"]["worker_id"] = "caller-mutated-copy"
    assert authority.get("child-1")["envelope"]["claim"]["worker_id"] == "worker-1"


def test_atomic_consume_has_exactly_one_winner():
    _module, _clock, authority, _parent, _child, expectation = _setup()
    barrier = threading.Barrier(8)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def consume():
        barrier.wait()
        try:
            authority.consume_child(
                "child-1",
                expectation=expectation,
                key_ring=authority.public_key_ring(),
            )
            result = "won"
        except AdmissionVerificationError:
            result = "denied"
        with outcomes_lock:
            outcomes.append(result)

    threads = [threading.Thread(target=consume) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert outcomes.count("won") == 1
    assert outcomes.count("denied") == 7
    assert authority.get("child-1")["state"] == "consumed"


def test_consumed_lease_cannot_replay_but_can_be_asserted_for_exact_session():
    _module, _clock, authority, _parent, _child, expectation = _setup()
    authority.consume_child(
        "child-1",
        expectation=expectation,
        key_ring=authority.public_key_ring(),
    )

    assert authority.assert_active("child-1", session_id="session-1")["worker_id"] == "worker-1"
    with pytest.raises(AdmissionVerificationError):
        authority.assert_active("child-1", session_id="another-session")
    with pytest.raises(AdmissionVerificationError, match="consumed"):
        authority.consume_child(
            "child-1",
            expectation=expectation,
            key_ring=authority.public_key_ring(),
        )
    with pytest.raises(AdmissionVerificationError, match="consumed"):
        authority.release("child-1")


def test_parent_revoke_invalidates_reserved_and_consumed_children():
    _module, _clock, authority, _parent, _child, expectation = _setup()
    authority.derive_child(
        "parent-1",
        node_id="1.3",
        reservation_ref="reservation-2",
        worker_id="worker-2",
        worker_context_id="context-2",
        session_id="session-2",
        node_contract_digest="sha256:" + "d" * 64,
        ttl_seconds=60,
        admission_ref="child-2",
    )
    authority.consume_child(
        "child-1",
        expectation=expectation,
        key_ring=authority.public_key_ring(),
    )

    authority.revoke("parent-1", reason="source version changed")

    assert authority.get("parent-1")["state"] == "revoked"
    assert authority.get("child-1")["state"] == "revoked"
    assert authority.get("child-2")["state"] == "revoked"
    with pytest.raises(AdmissionVerificationError, match="not active"):
        authority.assert_active("child-1", session_id="session-1")


def test_released_parent_revokes_children_and_never_reactivates():
    _module, _clock, authority, _parent, _child, _expectation = _setup()

    authority.release("parent-1", reason="operator cancelled")

    assert authority.get("parent-1")["state"] == "released"
    assert authority.get("child-1")["state"] == "revoked"
    with pytest.raises(AdmissionVerificationError):
        authority.derive_child(
            "parent-1",
            node_id="1.3",
            reservation_ref="reservation-2",
            worker_id="worker-2",
            worker_context_id="context-2",
            session_id="session-2",
            node_contract_digest="sha256:" + "d" * 64,
            ttl_seconds=60,
        )
    with pytest.raises(AdmissionVerificationError, match="released"):
        authority.release("parent-1")


def test_expiry_denies_consume_and_parent_derivation():
    _module, clock, authority, _parent, _child, expectation = _setup(
        parent_ttl=10,
        child_ttl=5,
    )
    clock.value += 5

    with pytest.raises(AdmissionVerificationError, match="expired"):
        authority.consume_child(
            "child-1",
            expectation=expectation,
            key_ring=authority.public_key_ring(),
        )
    assert authority.get("child-1")["state"] == "expired"

    clock.value += 5
    with pytest.raises(AdmissionVerificationError):
        authority.derive_child(
            "parent-1",
            node_id="1.3",
            reservation_ref="reservation-2",
            worker_id="worker-2",
            worker_context_id="context-2",
            session_id="session-2",
            node_contract_digest="sha256:" + "d" * 64,
            ttl_seconds=60,
        )
    assert authority.get("parent-1")["state"] == "expired"


def test_wrong_public_key_cannot_consume():
    _module, _clock, authority, _parent, _child, expectation = _setup()
    wrong_key = Ed25519PrivateKey.generate().public_key()

    with pytest.raises(AdmissionVerificationError, match="signature"):
        authority.consume_child(
            "child-1",
            expectation=expectation,
            key_ring=PublicKeyRing({"issuer-1": wrong_key}),
        )
    assert authority.get("child-1")["state"] == "reserved"
