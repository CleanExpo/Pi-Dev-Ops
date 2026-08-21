"""Senior Harness admission correlation and public-only claim verification.

The private issuer is intentionally absent from Pi-CEO. Existing ``off`` and
``observe`` modes remain non-authorizing; this module only gives the later
enforcement integration the public-key verification half of the contract.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


MODE_ENV = "SENIOR_HARNESS_ADMISSION_MODE"
_VALID_MODES = frozenset({"off", "observe", "enforce"})
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}$")
_RESERVATION_KEYS = frozenset({
    "schema_version",
    "reservation_ref",
    "task_id",
    "plan_id",
    "node_id",
    "worker_id",
    "worker_context_id",
    "base_sha",
    "node_contract_digest",
})
_REQUIRED_RESERVATION_KEYS = _RESERVATION_KEYS
CLAIM_SCHEMA_VERSION = "1.0"
CLAIM_TYPES = frozenset({"parent", "child"})
CLAIM_FIELDS = frozenset({
    "schema_version",
    "claim_type",
    "admission_ref",
    "parent_ref",
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
    "session_id",
    "base_sha",
    "node_contract_digest",
    "audience",
    "issued_at",
    "expires_at",
    "signer_key_id",
    "claim_digest",
})
CLAIM_DIGEST_FIELDS = CLAIM_FIELDS - {"claim_digest"}
SIGNED_ENVELOPE_FIELDS = frozenset({"schema_version", "claim", "signature"})
CONSUMER_BOUND_FIELDS = (
    "admission_ref",
    "parent_ref",
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
    "session_id",
    "base_sha",
    "node_contract_digest",
    "audience",
    "issued_at",
    "expires_at",
    "signer_key_id",
)
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_BASE_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class SeniorHarnessAdmissionUnavailable(RuntimeError):
    """Raised when the reserved enforcement mode is selected."""


class AdmissionContractError(ValueError):
    """Raised when an admission value cannot be represented canonically."""


class AdmissionVerificationError(SeniorHarnessAdmissionUnavailable):
    """Raised when a signed admission is not valid for the exact consumer target."""


@dataclass(frozen=True, slots=True)
class ConsumerExpectation:
    """Every immutable value Pi-CEO must compare before accepting one child."""

    admission_ref: str
    parent_ref: str
    source_kind: str
    source_id: str
    source_version: str
    repository: str
    objective_digest: str
    scope_digest: str
    task_id: str
    plan_id: str
    node_id: str
    reservation_ref: str
    worker_id: str
    worker_context_id: str
    session_id: str
    base_sha: str
    node_contract_digest: str
    audience: str
    issued_at: int
    expires_at: int
    signer_key_id: str


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def normalize_text(value: str) -> str:
    """Normalize human-authored text without changing its semantic whitespace."""
    if not isinstance(value, str):
        raise AdmissionContractError("text must be a string")
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def normalize_repository(value: str) -> str:
    """Return one credential-free HTTPS identity for supported Git remotes."""
    if not isinstance(value, str) or not value.strip():
        raise AdmissionContractError("repository must be a non-empty HTTPS or SSH URL")
    raw = value.strip()
    scp_match = re.fullmatch(r"(?:[^@/:\s]+@)?([^/:\s]+):(.+)", raw)
    if scp_match and "://" not in raw:
        host, path = scp_match.groups()
    else:
        parsed = urlsplit(raw)
        if parsed.scheme.lower() not in {"http", "https", "ssh", "git"}:
            raise AdmissionContractError("repository scheme must be HTTPS or SSH compatible")
        host = parsed.hostname or ""
        path = parsed.path
    host = host.rstrip(".").lower()
    segments = [unquote(part) for part in path.strip("/").split("/") if part]
    if len(segments) != 2 or not host:
        raise AdmissionContractError("repository must identify exactly owner/repository")
    owner, repository = segments
    if repository.lower().endswith(".git"):
        repository = repository[:-4]
    if not owner or not repository or any(part in {".", ".."} for part in (owner, repository)):
        raise AdmissionContractError("repository owner and name must be non-empty")
    if any(character.isspace() or character in "/\\" for character in owner + repository):
        raise AdmissionContractError("repository owner and name contain an unsafe character")
    return f"https://{host}/{owner.lower()}/{repository.lower()}"


def normalize_scope(value: Any) -> Any:
    """Recursively produce the closed JSON value used for scope hashing."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AdmissionContractError("scope numbers must be finite")
        return value
    if isinstance(value, list):
        return [normalize_scope(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise AdmissionContractError("scope object keys must be strings")
        normalized: dict[str, Any] = {}
        for key, item in sorted(value.items(), key=lambda pair: normalize_text(pair[0])):
            normalized_key = normalize_text(key)
            if normalized_key in normalized:
                raise AdmissionContractError("scope keys collide after Unicode normalization")
            normalized[normalized_key] = normalize_scope(item)
        return normalized
    raise AdmissionContractError(f"unsupported scope value: {type(value).__name__}")


def objective_digest(value: str) -> str:
    return _sha256(normalize_text(value).encode("utf-8"))


def scope_digest(value: Any) -> str:
    return _sha256(_canonical_json(normalize_scope(value)))


def claim_digest(claim: Mapping[str, Any]) -> str:
    """Hash every immutable claim field except the self-describing digest."""
    fields = frozenset(claim)
    if fields not in {CLAIM_FIELDS, CLAIM_DIGEST_FIELDS}:
        raise AdmissionContractError("claim has missing or unknown fields")
    unsigned = {name: claim[name] for name in CLAIM_DIGEST_FIELDS}
    return _sha256(_canonical_json(unsigned))


def _decode_base64url(value: str, *, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise AdmissionVerificationError(f"{label} must be non-empty base64url")
    if re.search(r"[^A-Za-z0-9_-]", value):
        raise AdmissionVerificationError(f"{label} is not canonical base64url")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise AdmissionVerificationError(f"{label} is not valid base64url") from exc
    if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value:
        raise AdmissionVerificationError(f"{label} is not canonical base64url")
    return decoded


class PublicKeyRing:
    """Closed public-only verifier set with explicit key revocation."""

    def __init__(
        self,
        keys: Mapping[str, str | bytes | Ed25519PublicKey],
        *,
        revoked_key_ids: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        if not isinstance(keys, Mapping) or not keys:
            raise AdmissionContractError("public key ring cannot be empty")
        parsed: dict[str, Ed25519PublicKey] = {}
        for key_id, public_key in keys.items():
            if not isinstance(key_id, str) or not _KEY_ID_RE.fullmatch(key_id):
                raise AdmissionContractError("public key IDs must use the closed key-id syntax")
            if isinstance(public_key, Ed25519PublicKey):
                parsed[key_id] = public_key
                continue
            raw = (
                _decode_base64url(public_key, label="public key")
                if isinstance(public_key, str)
                else public_key
            )
            if not isinstance(raw, bytes) or len(raw) != 32:
                raise AdmissionContractError("Ed25519 public keys must contain exactly 32 bytes")
            parsed[key_id] = Ed25519PublicKey.from_public_bytes(raw)
        unknown_revocations = set(revoked_key_ids) - set(parsed)
        if unknown_revocations:
            raise AdmissionContractError("revoked key IDs must exist in the key ring")
        self._keys = parsed
        self._revoked = frozenset(revoked_key_ids)

    def resolve(self, key_id: str) -> Ed25519PublicKey:
        if key_id in self._revoked:
            raise AdmissionVerificationError("admission signer key is revoked")
        try:
            return self._keys[key_id]
        except KeyError as exc:
            raise AdmissionVerificationError("admission signer key is unknown") from exc


def _validate_claim_shape(claim: Any) -> dict[str, Any]:
    if not isinstance(claim, dict) or set(claim) != CLAIM_FIELDS:
        raise AdmissionVerificationError("admission claim has missing or unknown fields")
    if claim["schema_version"] != CLAIM_SCHEMA_VERSION:
        raise AdmissionVerificationError("admission claim schema is unsupported")
    if claim["claim_type"] not in CLAIM_TYPES:
        raise AdmissionVerificationError("admission claim type is invalid")
    string_fields = CLAIM_FIELDS - {
        "parent_ref", "node_id", "reservation_ref", "worker_id",
        "worker_context_id", "session_id", "issued_at", "expires_at",
    }
    if any(not isinstance(claim[field], str) or not claim[field] for field in string_fields):
        raise AdmissionVerificationError("admission claim contains an invalid string field")
    nullable_fields = {
        "parent_ref", "node_id", "reservation_ref", "worker_id", "worker_context_id", "session_id",
    }
    if any(claim[field] is not None and (not isinstance(claim[field], str) or not claim[field]) for field in nullable_fields):
        raise AdmissionVerificationError("admission claim contains an invalid nullable field")
    for field in ("issued_at", "expires_at"):
        if isinstance(claim[field], bool) or not isinstance(claim[field], int):
            raise AdmissionVerificationError(f"admission {field} must be an integer epoch second")
    if claim["expires_at"] <= claim["issued_at"]:
        raise AdmissionVerificationError("admission expiry must follow issue time")
    if not _DIGEST_RE.fullmatch(claim["objective_digest"]):
        raise AdmissionVerificationError("objective digest is invalid")
    if not _DIGEST_RE.fullmatch(claim["scope_digest"]):
        raise AdmissionVerificationError("scope digest is invalid")
    if not _DIGEST_RE.fullmatch(claim["node_contract_digest"]):
        raise AdmissionVerificationError("node contract digest is invalid")
    if not _DIGEST_RE.fullmatch(claim["claim_digest"]):
        raise AdmissionVerificationError("claim digest is invalid")
    if not _BASE_SHA_RE.fullmatch(claim["base_sha"]):
        raise AdmissionVerificationError("base SHA is invalid")
    if not _REF_RE.fullmatch(claim["admission_ref"]):
        raise AdmissionVerificationError("admission reference is invalid")
    if claim["parent_ref"] is not None and not _REF_RE.fullmatch(claim["parent_ref"]):
        raise AdmissionVerificationError("parent admission reference is invalid")
    try:
        canonical_repository = normalize_repository(claim["repository"])
    except AdmissionContractError as exc:
        raise AdmissionVerificationError("repository is not canonical") from exc
    if claim["repository"] != canonical_repository:
        raise AdmissionVerificationError("repository is not canonical")
    if claim["claim_type"] == "parent":
        if claim["parent_ref"] is not None or any(claim[field] is not None for field in nullable_fields - {"parent_ref"}):
            raise AdmissionVerificationError("parent claim cannot carry child bindings")
    elif claim["parent_ref"] is None or any(claim[field] is None for field in nullable_fields - {"parent_ref"}):
        raise AdmissionVerificationError("child claim is missing a required binding")
    return copy.deepcopy(claim)


def verify_signed_claim(
    envelope: Any,
    key_ring: PublicKeyRing,
    *,
    expectation: ConsumerExpectation | None = None,
    now: int | datetime | None = None,
) -> dict[str, Any]:
    """Verify signature, freshness, digest and every supplied consumer binding."""
    if not isinstance(envelope, dict) or set(envelope) != SIGNED_ENVELOPE_FIELDS:
        raise AdmissionVerificationError("signed admission has missing or unknown fields")
    if envelope["schema_version"] != CLAIM_SCHEMA_VERSION:
        raise AdmissionVerificationError("signed admission schema is unsupported")
    claim = _validate_claim_shape(envelope["claim"])
    if claim_digest(claim) != claim["claim_digest"]:
        raise AdmissionVerificationError("admission claim digest does not match its fields")
    signature = _decode_base64url(envelope["signature"], label="admission signature")
    if len(signature) != 64:
        raise AdmissionVerificationError("Ed25519 signature must contain exactly 64 bytes")
    public_key = key_ring.resolve(claim["signer_key_id"])
    try:
        public_key.verify(signature, _canonical_json(claim))
    except InvalidSignature as exc:
        raise AdmissionVerificationError("admission signature is invalid") from exc
    current = now
    if isinstance(current, datetime):
        if current.tzinfo is None:
            raise AdmissionContractError("verification datetime must be timezone-aware")
        current = int(current.timestamp())
    if current is None:
        current = int(datetime.now(tz=timezone.utc).timestamp())
    if isinstance(current, bool) or not isinstance(current, int):
        raise AdmissionContractError("verification time must be an integer epoch second")
    if current < claim["issued_at"]:
        raise AdmissionVerificationError("admission is not valid yet")
    if current >= claim["expires_at"]:
        raise AdmissionVerificationError("admission is expired")
    if expectation is not None:
        if claim["claim_type"] != "child":
            raise AdmissionVerificationError("Pi-CEO can consume only child admissions")
        expected = asdict(expectation)
        expected["repository"] = normalize_repository(expected["repository"])
        mismatches = [field for field in CONSUMER_BOUND_FIELDS if claim[field] != expected[field]]
        if mismatches:
            raise AdmissionVerificationError(
                "admission target mismatch: " + ", ".join(sorted(mismatches))
            )
    return claim


def deployment_mode() -> str:
    """Return the deployment-controlled mode, failing closed on bad config."""
    mode = os.environ.get(MODE_ENV, "off").strip().lower()
    if mode not in _VALID_MODES:
        raise SeniorHarnessAdmissionUnavailable(
            f"invalid {MODE_ENV}; expected off, observe, or enforce"
        )
    return mode


def require_runtime_available() -> str:
    """Reject unavailable enforcement before a caller can trigger side effects."""
    mode = deployment_mode()
    if mode == "enforce":
        raise SeniorHarnessAdmissionUnavailable(
            "Senior Harness enforcement is unavailable until an external validator is installed"
        )
    return mode


def _valid_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(_REF_RE.fullmatch(value))


def _safe_reservation(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    if set(raw) != _REQUIRED_RESERVATION_KEYS:
        return None
    if raw.get("schema_version") != "1.0":
        return None
    if not all(_valid_ref(raw.get(key)) for key in _RESERVATION_KEYS - {"schema_version"}):
        return None
    return copy.deepcopy(raw)


def observe(
    admission_ref: Any,
    reservation: Any,
) -> tuple[str, str | None, dict[str, str] | None]:
    """Return ``(status, safe_ref, safe_reservation)`` for a new request.

    ``off`` discards all caller input.  ``observe`` records only a complete,
    closed projection.  Missing or malformed input remains non-blocking and is
    never promoted into an authority claim.
    """
    mode = require_runtime_available()
    if mode == "off":
        return "off", None, None
    if admission_ref is None and reservation is None:
        return "missing", None, None
    safe_reservation = _safe_reservation(reservation)
    if not _valid_ref(admission_ref) or safe_reservation is None:
        return "malformed", None, None
    return "observed", str(admission_ref), safe_reservation


def restore_projection(
    status: Any,
    admission_ref: Any,
    reservation: Any,
) -> tuple[str, str | None, dict[str, str] | None]:
    """Sanitize a persisted projection without treating it as fresh authority."""
    if status == "off":
        return "off", None, None
    if status in {"missing", "malformed"}:
        return str(status), None, None
    # Persisted enforce metadata is correlation only. Rehydration deliberately
    # downgrades it to observed; a process restart never reconstructs authority.
    if status == "enforced":
        status = "observed"
    if status != "observed":
        return "malformed", None, None
    safe_reservation = _safe_reservation(reservation)
    if not _valid_ref(admission_ref) or safe_reservation is None:
        return "malformed", None, None
    return "observed", str(admission_ref), safe_reservation


def api_projection(session: Any) -> dict[str, Any]:
    """Build a deep-copied, non-authorizing API projection for one session."""
    raw_status = getattr(session, "senior_harness_observation_status", "off")
    status, admission_ref, reservation = restore_projection(
        raw_status,
        getattr(session, "senior_harness_admission_ref", None),
        getattr(session, "senior_harness_reservation", None),
    )
    if raw_status == "enforced" and status == "observed":
        status = "enforced"
    return {
        "status": status,
        "admission_ref": admission_ref,
        "reservation": copy.deepcopy(reservation),
    }
