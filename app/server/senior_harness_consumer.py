"""Fail-closed Pi-CEO consumer for externally issued Senior Harness leases.

Signed envelopes are verified and consumed transiently.  Only a four-field,
non-secret handle remains in process memory after the atomic consume succeeds.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit

from .senior_harness_admission import (
    AdmissionContractError,
    AdmissionVerificationError,
    ConsumerExpectation,
    PublicKeyRing,
    SeniorHarnessAdmissionUnavailable,
    deployment_mode,
    normalize_repository,
    objective_digest,
    scope_digest,
    verify_signed_claim,
)


RPC_URL_ENV = "SENIOR_HARNESS_ADMISSION_RPC_URL"
CONSUMER_TOKEN_ENV = "SENIOR_HARNESS_ADMISSION_CONSUMER_TOKEN"
PUBLIC_KEYS_ENV = "SENIOR_HARNESS_ADMISSION_PUBLIC_KEYS"
REVOKED_KEY_IDS_ENV = "SENIOR_HARNESS_ADMISSION_REVOKED_KEY_IDS"
AUDIENCE_ENV = "SENIOR_HARNESS_ADMISSION_AUDIENCE"

_CONSUME_RPC = "senior_harness_consume_child"
_ASSERT_RPC = "senior_harness_assert_active"
_SESSION_ID_RE = re.compile(r"^[0-9a-f]{12}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}$")
_RESERVATION_FIELDS = frozenset(
    {
        "schema_version",
        "reservation_ref",
        "task_id",
        "plan_id",
        "node_id",
        "worker_id",
        "worker_context_id",
        "base_sha",
        "node_contract_digest",
    }
)
_RPC_ROW_FIELDS = frozenset(
    {"admission_ref", "state", "expires_at", "consumption_session_id"}
)


class ConsumerTransport(Protocol):
    """Narrow durable-authority transport used by the consumer runtime."""

    def consume_child(self, payload: Mapping[str, Any]) -> Any:
        """Atomically consume one child and return the RPC response rows."""

    def assert_active(self, payload: Mapping[str, Any]) -> Any:
        """Assert that one previously consumed child remains active."""


@dataclass(frozen=True, slots=True)
class ActiveAdmissionHandle:
    """The complete and deliberately minimal process-local authority handle."""

    admission_ref: str
    claim_digest: str
    worker_context_id: str
    audience: str


@dataclass(frozen=True, slots=True)
class ConsumedAdmissionBinding:
    """Safe values that session wiring may retain after envelope consumption."""

    session_id: str
    admission_ref: str
    reservation: dict[str, str]


class PostgRESTConsumerTransport:
    """Consumer-only client for public PostgREST admission RPC wrappers."""

    __slots__ = ("_rpc_url", "_headers", "_timeout")

    def __init__(self, rpc_url: str, consumer_token: str, *, timeout: float = 8.0) -> None:
        if not isinstance(rpc_url, str) or not rpc_url.strip():
            raise SeniorHarnessAdmissionUnavailable(f"{RPC_URL_ENV} is required")
        parsed = urlsplit(rpc_url.strip())
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise SeniorHarnessAdmissionUnavailable(
                f"{RPC_URL_ENV} must be a credential-free HTTPS URL"
            )
        if parsed.query or parsed.fragment:
            raise SeniorHarnessAdmissionUnavailable(
                f"{RPC_URL_ENV} cannot contain a query or fragment"
            )
        if parsed.path.rstrip("/") != "/rest/v1/rpc":
            raise SeniorHarnessAdmissionUnavailable(
                f"{RPC_URL_ENV} must end at the PostgREST /rest/v1/rpc endpoint"
            )
        if not isinstance(consumer_token, str) or not consumer_token.strip():
            raise SeniorHarnessAdmissionUnavailable(f"{CONSUMER_TOKEN_ENV} is required")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise AdmissionContractError("consumer RPC timeout must be positive")
        self._rpc_url = rpc_url.strip().rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {consumer_token.strip()}",
            "apikey": consumer_token.strip(),
            "Content-Type": "application/json",
        }
        self._timeout = float(timeout)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(rpc_url={self._rpc_url!r}, token=<redacted>)"

    def consume_child(self, payload: Mapping[str, Any]) -> Any:
        return self._call(_CONSUME_RPC, payload)

    def assert_active(self, payload: Mapping[str, Any]) -> Any:
        return self._call(_ASSERT_RPC, payload)

    def _call(self, function_name: str, payload: Mapping[str, Any]) -> Any:
        request = urllib.request.Request(
            f"{self._rpc_url}/{function_name}",
            data=json.dumps(dict(payload), allow_nan=False, separators=(",", ":")).encode(),
            headers=self._headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                status = getattr(response, "status", 200)
                if status < 200 or status >= 300:
                    raise AdmissionVerificationError("admission authority denied the RPC")
                body = response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AdmissionVerificationError("admission authority RPC failed closed") from exc
        try:
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdmissionVerificationError("admission authority returned malformed JSON") from exc


_runtime_lock = threading.RLock()
_transport: ConsumerTransport | None = None
_key_ring: PublicKeyRing | None = None
_base_audience: str | None = None
_active_handles: dict[str, ActiveAdmissionHandle] = {}


def _validate_base_audience(value: Any) -> str:
    if not isinstance(value, str) or not _REF_RE.fullmatch(value):
        raise AdmissionContractError("Senior Harness base audience is invalid")
    return value


def _validate_session_id(value: Any) -> str:
    if not isinstance(value, str) or not _SESSION_ID_RE.fullmatch(value):
        raise AdmissionVerificationError(
            "Senior Harness session_id must be exactly 12 lowercase hexadecimal characters"
        )
    return value


def _safe_reservation(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != _RESERVATION_FIELDS:
        raise AdmissionVerificationError("Senior Harness reservation is missing or malformed")
    if value.get("schema_version") != "1.0":
        raise AdmissionVerificationError("Senior Harness reservation schema is unsupported")
    if any(
        not isinstance(value.get(field), str)
        or not _REF_RE.fullmatch(value[field])
        for field in _RESERVATION_FIELDS - {"schema_version"}
    ):
        raise AdmissionVerificationError("Senior Harness reservation contains an invalid binding")
    return copy.deepcopy(value)


def _epoch_utc(value: int) -> str:
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError) as exc:
        raise AdmissionVerificationError("admission epoch is outside the canonical UTC range") from exc


def _signature_bytea(value: Any) -> str:
    if not isinstance(value, str) or not value or re.search(r"[^A-Za-z0-9_-]", value):
        raise AdmissionVerificationError("admission signature is not canonical base64url")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise AdmissionVerificationError("admission signature is invalid") from exc
    if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != value or len(raw) != 64:
        raise AdmissionVerificationError("admission signature is invalid")
    return "\\x" + raw.hex()


def build_expectation(
    verified_claim: Mapping[str, Any],
    *,
    repo_url: str,
    brief: str,
    scope: Any,
    reservation: Any,
    base_audience: str,
    expected_session_id: str | None = None,
) -> tuple[ConsumerExpectation, dict[str, str]]:
    """Bind a verified child to the exact Pi-CEO request and deployment audience."""
    safe_reservation = _safe_reservation(reservation)
    signed_session_id = _validate_session_id(verified_claim.get("session_id"))
    session_id = (
        signed_session_id
        if expected_session_id is None
        else _validate_session_id(expected_session_id)
    )
    audience = (
        f"{_validate_base_audience(base_audience)}:worker:"
        f"{safe_reservation['worker_context_id']}"
    )
    expected = {
        field: verified_claim.get(field)
        for field in ConsumerExpectation.__dataclass_fields__
    }
    expected.update(
        {
            "repository": normalize_repository(repo_url),
            "objective_digest": objective_digest(brief),
            "scope_digest": scope_digest(scope),
            "task_id": safe_reservation["task_id"],
            "plan_id": safe_reservation["plan_id"],
            "node_id": safe_reservation["node_id"],
            "reservation_ref": safe_reservation["reservation_ref"],
            "worker_id": safe_reservation["worker_id"],
            "worker_context_id": safe_reservation["worker_context_id"],
            "session_id": session_id,
            "base_sha": safe_reservation["base_sha"],
            "node_contract_digest": safe_reservation["node_contract_digest"],
            "audience": audience,
        }
    )
    return ConsumerExpectation(**expected), safe_reservation


def install_runtime(
    transport: ConsumerTransport,
    key_ring: PublicKeyRing,
    base_audience: str,
) -> None:
    """Install an explicit consumer runtime, primarily for startup and tests."""
    if not callable(getattr(transport, "consume_child", None)) or not callable(
        getattr(transport, "assert_active", None)
    ):
        raise AdmissionContractError("consumer transport does not implement the closed protocol")
    if not isinstance(key_ring, PublicKeyRing):
        raise AdmissionContractError("consumer runtime requires a PublicKeyRing")
    audience = _validate_base_audience(base_audience)
    global _transport, _key_ring, _base_audience
    with _runtime_lock:
        _transport = transport
        _key_ring = key_ring
        _base_audience = audience
        _active_handles.clear()


def bootstrap_from_env() -> None:
    """Install the consumer from dedicated deployment configuration.

    The consumer token is removed from ``os.environ`` immediately after the
    single read, including when later configuration validation fails.
    """
    if deployment_mode() != "enforce":
        return
    consumer_token = os.environ.pop(CONSUMER_TOKEN_ENV, None)
    if consumer_token is None:
        raise SeniorHarnessAdmissionUnavailable(f"{CONSUMER_TOKEN_ENV} is required")
    rpc_url = os.environ.get(RPC_URL_ENV)
    public_keys_raw = os.environ.get(PUBLIC_KEYS_ENV)
    revoked_raw = os.environ.get(REVOKED_KEY_IDS_ENV, "[]")
    audience = os.environ.get(AUDIENCE_ENV)
    try:
        public_keys = json.loads(public_keys_raw) if public_keys_raw else None
        revoked = json.loads(revoked_raw)
    except json.JSONDecodeError as exc:
        raise SeniorHarnessAdmissionUnavailable(
            "Senior Harness public-key configuration is malformed"
        ) from exc
    if not isinstance(public_keys, dict) or not public_keys:
        raise SeniorHarnessAdmissionUnavailable(f"{PUBLIC_KEYS_ENV} is required")
    if not isinstance(revoked, list) or any(not isinstance(item, str) for item in revoked):
        raise SeniorHarnessAdmissionUnavailable(f"{REVOKED_KEY_IDS_ENV} must be a JSON array")
    try:
        transport = PostgRESTConsumerTransport(rpc_url or "", consumer_token)
        key_ring = PublicKeyRing(public_keys, revoked_key_ids=frozenset(revoked))
        install_runtime(transport, key_ring, audience or "")
    except (AdmissionContractError, AdmissionVerificationError) as exc:
        raise SeniorHarnessAdmissionUnavailable(
            "Senior Harness consumer configuration is invalid"
        ) from exc


def clear_runtime() -> None:
    """Remove installed runtime state and every process-local active handle."""
    global _transport, _key_ring, _base_audience
    with _runtime_lock:
        _active_handles.clear()
        _transport = None
        _key_ring = None
        _base_audience = None


def runtime_ready() -> bool:
    with _runtime_lock:
        return _transport is not None and _key_ring is not None and _base_audience is not None


def _runtime() -> tuple[ConsumerTransport, PublicKeyRing, str]:
    with _runtime_lock:
        if _transport is None or _key_ring is None or _base_audience is None:
            raise SeniorHarnessAdmissionUnavailable(
                "Senior Harness consumer runtime is not installed"
            )
        return _transport, _key_ring, _base_audience


def _validate_single_row(
    raw: Any,
    *,
    admission_ref: str,
    session_id: str,
) -> dict[str, Any]:
    if not isinstance(raw, list) or len(raw) != 1:
        raise AdmissionVerificationError(
            "admission authority must return exactly one matching row"
        )
    row = raw[0]
    if not isinstance(row, dict) or set(row) != _RPC_ROW_FIELDS:
        raise AdmissionVerificationError("admission authority returned a malformed row")
    if (
        row["admission_ref"] != admission_ref
        or row["state"] != "consumed"
        or row["consumption_session_id"] != session_id
        or not isinstance(row["expires_at"], str)
        or not row["expires_at"]
    ):
        raise AdmissionVerificationError("admission authority returned a mismatched row")
    try:
        expiry = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdmissionVerificationError("admission authority returned an invalid expiry") from exc
    if expiry.tzinfo is None or expiry <= datetime.now(tz=timezone.utc):
        raise AdmissionVerificationError("admission authority returned an inactive expiry")
    return copy.deepcopy(row)


def _consume_payload(claim: Mapping[str, Any], signature: Any) -> dict[str, Any]:
    fields = (
        "admission_ref",
        "parent_ref",
        "claim_digest",
        "source_kind",
        "source_id",
        "source_version",
        "repository",
        "objective_digest",
        "scope_digest",
        "task_id",
        "plan_id",
        "node_id",
        "reservation_ref",
        "worker_id",
        "worker_context_id",
        "base_sha",
        "node_contract_digest",
        "audience",
        "signer_key_id",
        "session_id",
    )
    payload = {f"p_{field}": claim[field] for field in fields}
    payload["p_issued_at"] = _epoch_utc(claim["issued_at"])
    payload["p_expires_at"] = _epoch_utc(claim["expires_at"])
    payload["p_signature"] = _signature_bytea(signature)
    return payload


def consume_for_build(
    envelope: Any,
    *,
    repo_url: str,
    brief: str,
    scope: Any,
    reservation: Any,
    expected_session_id: str | None = None,
) -> ConsumedAdmissionBinding:
    """Verify, exactly bind, atomically consume, and retain no signed envelope."""
    transport, key_ring, _base_audience_value = _runtime()
    envelope_snapshot = copy.deepcopy(envelope)
    binding = verify_for_build(
        envelope_snapshot,
        repo_url=repo_url,
        brief=brief,
        scope=scope,
        reservation=reservation,
        expected_session_id=expected_session_id,
    )
    claim = verify_signed_claim(envelope_snapshot, key_ring)
    session_id = binding.session_id
    handle = ActiveAdmissionHandle(
        admission_ref=claim["admission_ref"],
        claim_digest=claim["claim_digest"],
        worker_context_id=claim["worker_context_id"],
        audience=claim["audience"],
    )
    try:
        rows = transport.consume_child(
            _consume_payload(claim, envelope_snapshot["signature"])
        )
    except AdmissionVerificationError:
        raise
    except Exception as exc:
        raise AdmissionVerificationError("admission authority consume failed closed") from exc
    _validate_single_row(rows, admission_ref=claim["admission_ref"], session_id=session_id)
    with _runtime_lock:
        _active_handles[session_id] = handle
    return binding


def verify_for_build(
    envelope: Any,
    *,
    repo_url: str,
    brief: str,
    scope: Any,
    reservation: Any,
    expected_session_id: str | None = None,
) -> ConsumedAdmissionBinding:
    """Preview exact admission binding without transport or registry side effects."""
    _transport_value, key_ring, base_audience = _runtime()
    if envelope is None:
        raise AdmissionVerificationError("a signed Senior Harness admission is required")
    verified = verify_signed_claim(envelope, key_ring)
    expectation, safe_reservation = build_expectation(
        verified,
        repo_url=repo_url,
        brief=brief,
        scope=scope,
        reservation=reservation,
        base_audience=base_audience,
        expected_session_id=expected_session_id,
    )
    claim = verify_signed_claim(envelope, key_ring, expectation=expectation)
    return ConsumedAdmissionBinding(
        session_id=_validate_session_id(claim["session_id"]),
        admission_ref=claim["admission_ref"],
        reservation=safe_reservation,
    )


def assert_active(session_id: str) -> ActiveAdmissionHandle:
    """Fail closed unless the durable consumed lease still matches the local handle."""
    transport, _key_ring, _base_audience = _runtime()
    sid = _validate_session_id(session_id)
    with _runtime_lock:
        handle = _active_handles.get(sid)
    if handle is None:
        raise AdmissionVerificationError("Senior Harness session has no active handle")
    payload = {
        "p_admission_ref": handle.admission_ref,
        "p_claim_digest": handle.claim_digest,
        "p_consumption_session_id": sid,
        "p_worker_context_id": handle.worker_context_id,
        "p_audience": handle.audience,
    }
    try:
        rows = transport.assert_active(payload)
    except AdmissionVerificationError:
        raise
    except Exception as exc:
        raise AdmissionVerificationError("admission authority assertion failed closed") from exc
    _validate_single_row(rows, admission_ref=handle.admission_ref, session_id=sid)
    return handle


def require_active_for_run(session_id: str) -> ActiveAdmissionHandle | None:
    """Assert durable authority in enforce mode; preserve legacy modes exactly."""
    if deployment_mode() != "enforce":
        return None
    return assert_active(session_id)


__all__ = [
    "ActiveAdmissionHandle",
    "ConsumedAdmissionBinding",
    "ConsumerTransport",
    "PostgRESTConsumerTransport",
    "assert_active",
    "bootstrap_from_env",
    "build_expectation",
    "clear_runtime",
    "consume_for_build",
    "install_runtime",
    "runtime_ready",
    "require_active_for_run",
    "verify_for_build",
]
