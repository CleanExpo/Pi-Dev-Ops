#!/usr/bin/env python3
"""External Senior Harness issuer and credential-free lifecycle adapter.

Private-key operations deliberately live outside ``app/server``.  The in-memory
adapter exists to exercise the authority contract without Supabase credentials;
the durable database adapter is a separate implementation phase.
"""
from __future__ import annotations

import base64
import copy
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.server.senior_harness_admission import (
    CLAIM_SCHEMA_VERSION,
    AdmissionContractError,
    AdmissionVerificationError,
    ConsumerExpectation,
    PublicKeyRing,
    _canonical_json,
    claim_digest,
    normalize_repository,
    objective_digest,
    scope_digest,
    verify_signed_claim,
)


ACTIVE_STATES = frozenset({"reserved", "consumed"})
TERMINAL_STATES = frozenset({"consumed", "released", "revoked", "expired"})


@dataclass(slots=True)
class AdmissionRecord:
    envelope: dict[str, Any]
    state: str = "reserved"
    consumed_session_id: str | None = None
    consumed_at: int | None = None
    terminal_at: int | None = None
    terminal_reason: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "envelope": copy.deepcopy(self.envelope),
            "state": self.state,
            "consumed_session_id": self.consumed_session_id,
            "consumed_at": self.consumed_at,
            "terminal_at": self.terminal_at,
            "terminal_reason": self.terminal_reason,
        }


class InMemoryAdmissionAuthority:
    """Thread-safe reference adapter for parent/child authority semantics."""

    def __init__(
        self,
        private_key: Ed25519PrivateKey,
        *,
        signer_key_id: str,
        audience: str,
        clock: Callable[[], int | float] = time.time,
    ) -> None:
        if not isinstance(private_key, Ed25519PrivateKey):
            raise AdmissionContractError("authority requires an Ed25519 private key")
        if not isinstance(signer_key_id, str) or not signer_key_id:
            raise AdmissionContractError("signer key ID cannot be empty")
        if not isinstance(audience, str) or not audience:
            raise AdmissionContractError("audience cannot be empty")
        self._private_key = private_key
        self._signer_key_id = signer_key_id
        self._audience = audience
        self._clock = clock
        self._records: dict[str, AdmissionRecord] = {}
        self._children: dict[str, set[str]] = {}
        self._lock = threading.RLock()

    def public_key_ring(self, *, revoked: bool = False) -> PublicKeyRing:
        public_key = self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        revoked_ids = {self._signer_key_id} if revoked else set()
        return PublicKeyRing({self._signer_key_id: public_key}, revoked_key_ids=revoked_ids)

    def public_key_base64url(self) -> str:
        raw = self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    def _now(self) -> int:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AdmissionContractError("authority clock must return epoch seconds")
        return int(value)

    @staticmethod
    def _ttl(ttl_seconds: int) -> int:
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise AdmissionContractError("admission TTL must be a positive integer")
        return ttl_seconds

    @staticmethod
    def _ref(value: str | None) -> str:
        if value is None:
            return str(uuid.uuid4())
        if not isinstance(value, str) or not value:
            raise AdmissionContractError("admission reference cannot be empty")
        return value

    def _sign(self, claim: dict[str, Any]) -> dict[str, Any]:
        claim["claim_digest"] = claim_digest(claim)
        signature = self._private_key.sign(_canonical_json(claim))
        return {
            "schema_version": CLAIM_SCHEMA_VERSION,
            "claim": copy.deepcopy(claim),
            "signature": base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii"),
        }

    def reserve_parent(
        self,
        *,
        source_kind: str,
        source_id: str,
        source_version: str,
        repository: str,
        objective: str,
        scope: Any,
        task_id: str,
        plan_id: str,
        base_sha: str,
        node_contract_digest: str,
        ttl_seconds: int,
        admission_ref: str | None = None,
    ) -> dict[str, Any]:
        """Reserve one immutable root from external source and plan evidence."""
        now = self._now()
        ttl = self._ttl(ttl_seconds)
        ref = self._ref(admission_ref)
        claim = {
            "schema_version": CLAIM_SCHEMA_VERSION,
            "claim_type": "parent",
            "admission_ref": ref,
            "parent_ref": None,
            "source_kind": source_kind,
            "source_id": source_id,
            "source_version": source_version,
            "repository": normalize_repository(repository),
            "objective_digest": objective_digest(objective),
            "scope_digest": scope_digest(scope),
            "task_id": task_id,
            "plan_id": plan_id,
            "node_id": None,
            "reservation_ref": None,
            "worker_id": None,
            "worker_context_id": None,
            "session_id": None,
            "base_sha": base_sha,
            "node_contract_digest": node_contract_digest,
            "audience": self._audience,
            "issued_at": now,
            "expires_at": now + ttl,
            "signer_key_id": self._signer_key_id,
        }
        envelope = self._sign(claim)
        # Verify before making the reservation visible. This also validates the
        # closed claim shape and prevents malformed issuer inputs from storage.
        verify_signed_claim(envelope, self.public_key_ring(), now=now)
        with self._lock:
            if ref in self._records:
                raise AdmissionContractError("admission reference already exists")
            self._records[ref] = AdmissionRecord(envelope=envelope)
            self._children[ref] = set()
        return copy.deepcopy(envelope)

    def derive_child(
        self,
        parent_ref: str,
        *,
        node_id: str,
        reservation_ref: str,
        worker_id: str,
        worker_context_id: str,
        session_id: str,
        node_contract_digest: str,
        ttl_seconds: int,
        admission_ref: str | None = None,
    ) -> dict[str, Any]:
        """Derive one session-bound leaf whose lifetime cannot exceed its parent."""
        now = self._now()
        ttl = self._ttl(ttl_seconds)
        ref = self._ref(admission_ref)
        with self._lock:
            parent = self._record(parent_ref)
            self._expire(parent_ref, parent, now)
            if parent.state != "reserved":
                raise AdmissionVerificationError("parent admission is not reservable")
            parent_claim = parent.envelope["claim"]
            expiry = min(now + ttl, parent_claim["expires_at"])
            if expiry <= now:
                raise AdmissionVerificationError("parent admission is expired")
            if ref in self._records:
                raise AdmissionContractError("admission reference already exists")
            claim = {
                "schema_version": CLAIM_SCHEMA_VERSION,
                "claim_type": "child",
                "admission_ref": ref,
                "parent_ref": parent_ref,
                "source_kind": parent_claim["source_kind"],
                "source_id": parent_claim["source_id"],
                "source_version": parent_claim["source_version"],
                "repository": parent_claim["repository"],
                "objective_digest": parent_claim["objective_digest"],
                "scope_digest": parent_claim["scope_digest"],
                "task_id": parent_claim["task_id"],
                "plan_id": parent_claim["plan_id"],
                "node_id": node_id,
                "reservation_ref": reservation_ref,
                "worker_id": worker_id,
                "worker_context_id": worker_context_id,
                "session_id": session_id,
                "base_sha": parent_claim["base_sha"],
                "node_contract_digest": node_contract_digest,
                "audience": f"{parent_claim['audience']}:worker:{worker_context_id}",
                "issued_at": now,
                "expires_at": expiry,
                "signer_key_id": self._signer_key_id,
            }
            envelope = self._sign(claim)
            verify_signed_claim(envelope, self.public_key_ring(), now=now)
            self._records[ref] = AdmissionRecord(envelope=envelope)
            self._children[parent_ref].add(ref)
            return copy.deepcopy(envelope)

    def consume_child(
        self,
        admission_ref: str,
        *,
        expectation: ConsumerExpectation,
        key_ring: PublicKeyRing,
    ) -> dict[str, Any]:
        """Atomically consume one verified child; a second caller always loses."""
        now = self._now()
        with self._lock:
            record = self._record(admission_ref)
            self._expire(admission_ref, record, now)
            if record.state != "reserved":
                raise AdmissionVerificationError(f"child admission is {record.state}")
            claim = verify_signed_claim(
                record.envelope,
                key_ring,
                expectation=expectation,
                now=now,
            )
            parent = self._record(claim["parent_ref"])
            self._expire(claim["parent_ref"], parent, now)
            if parent.state != "reserved":
                raise AdmissionVerificationError("parent admission is not active")
            record.state = "consumed"
            record.consumed_session_id = claim["session_id"]
            record.consumed_at = now
            record.terminal_at = now
            return copy.deepcopy(claim)

    def assert_active(self, admission_ref: str, *, session_id: str) -> dict[str, Any]:
        """Assert that a consumed lease and its parent remain valid for the session."""
        now = self._now()
        with self._lock:
            record = self._record(admission_ref)
            self._expire(admission_ref, record, now)
            if record.state != "consumed" or record.consumed_session_id != session_id:
                raise AdmissionVerificationError("child admission is not active for this session")
            parent_ref = record.envelope["claim"]["parent_ref"]
            parent = self._record(parent_ref)
            self._expire(parent_ref, parent, now)
            if parent.state != "reserved":
                raise AdmissionVerificationError("parent admission is not active")
            return copy.deepcopy(record.envelope["claim"])

    def release(self, admission_ref: str, *, reason: str = "released") -> None:
        """Release an unused reservation without permitting later reactivation."""
        now = self._now()
        with self._lock:
            record = self._record(admission_ref)
            self._expire(admission_ref, record, now)
            if record.state != "reserved":
                raise AdmissionVerificationError(f"admission cannot be released from {record.state}")
            record.state = "released"
            record.terminal_at = now
            record.terminal_reason = reason
            if record.envelope["claim"]["claim_type"] == "parent":
                self._revoke_children(admission_ref, now, "parent released")

    def revoke(self, admission_ref: str, *, reason: str = "revoked") -> None:
        """Revoke a record and every still-active descendant of a parent."""
        now = self._now()
        with self._lock:
            record = self._record(admission_ref)
            self._expire(admission_ref, record, now)
            if record.state in {"released", "revoked", "expired"}:
                raise AdmissionVerificationError(f"admission cannot be revoked from {record.state}")
            record.state = "revoked"
            record.terminal_at = now
            record.terminal_reason = reason
            if record.envelope["claim"]["claim_type"] == "parent":
                self._revoke_children(admission_ref, now, "parent revoked")

    def get(self, admission_ref: str) -> dict[str, Any]:
        with self._lock:
            record = self._record(admission_ref)
            self._expire(admission_ref, record, self._now())
            return record.snapshot()

    def _record(self, admission_ref: str) -> AdmissionRecord:
        try:
            return self._records[admission_ref]
        except KeyError as exc:
            raise AdmissionVerificationError("admission is unknown") from exc

    @staticmethod
    def _expire(admission_ref: str, record: AdmissionRecord, now: int) -> None:
        if record.state in ACTIVE_STATES and now >= record.envelope["claim"]["expires_at"]:
            record.state = "expired"
            record.terminal_at = now
            record.terminal_reason = f"TTL expired for {admission_ref}"

    def _revoke_children(self, parent_ref: str, now: int, reason: str) -> None:
        for child_ref in self._children.get(parent_ref, set()):
            child = self._records[child_ref]
            if child.state in ACTIVE_STATES:
                child.state = "revoked"
                child.terminal_at = now
                child.terminal_reason = reason


def generate_private_key() -> Ed25519PrivateKey:
    """Generate an ephemeral issuer key; persistence is the host's responsibility."""
    return Ed25519PrivateKey.generate()
