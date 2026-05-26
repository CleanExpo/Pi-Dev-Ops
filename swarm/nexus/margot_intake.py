"""Margot voice intake → POST /api/nexus/clients/intake.

Phase B / B2. Two-stage:

    parse_voice_intake(transcript, llm, founder_id) -> IntakePayload
    dispatch_intake(payload, http_client, *, api_base, auth_token)
        -> IntakeResult

Stage 1 is pure-logic: redact secrets in the transcript, ask the LLM
to extract structured intake fields, validate required fields (legal
name, display name, intake source), and return a frozen payload.

Stage 2 is a thin HTTP shim around the Phase A POST endpoint. Both
the LLM stage and the HTTP stage are injected via Protocols so this
module never opens a real socket or hits Anthropic in tests.

Consent: voice intake is only authorised when the channel's
`inbound_route` is "margot" — that gate is enforced upstream by the
Margot router (CIP PR3-PR6). This module assumes the caller has
already cleared consent.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

from ..tmux_validator import redact_secrets
from .types import IntakeSource

log = logging.getLogger("pi-ceo.nexus.margot_intake")

INTAKE_ENDPOINT = "/api/nexus/clients/intake"

REQUIRED_FIELDS = ("legal_name", "display_name")
VALID_INTAKE_SOURCES = ("voice", "form", "manual", "referral")

# Empty / nonsense transcript guards
MIN_TRANSCRIPT_CHARS = 10


# ============================================================
# Protocols (injection points — no real I/O in this module)
# ============================================================


class LLMProtocol(Protocol):
    def complete(self, *, system: str, user: str,
                 max_tokens: int = 1024, temperature: float = 0.3) -> str: ...


@dataclass(frozen=True)
class HTTPResponse:
    status_code: int
    body: dict[str, Any] = field(default_factory=dict)


class HTTPProtocol(Protocol):
    def post(self, url: str, *, json_body: dict[str, Any],
             headers: dict[str, str]) -> HTTPResponse: ...


# ============================================================
# Data shapes
# ============================================================


@dataclass(frozen=True)
class IntakePayload:
    """JSON-shaped payload for POST /api/nexus/clients/intake."""
    legal_name: str
    display_name: str
    founder_id: str
    intake_source: IntakeSource = "voice"
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    raw_notes: str | None = None
    voice_transcript: str | None = None


@dataclass(frozen=True)
class IntakeResult:
    result: Literal["ok", "invalid", "transport_error"]
    client_id: str | None = None
    status: str | None = None
    reason: str | None = None
    redaction_counts: dict[str, int] = field(default_factory=dict)


# ============================================================
# Stage 1: parse
# ============================================================


_INTAKE_SYSTEM_PROMPT = """You extract structured client intake fields from a voice transcript.
Return STRICT JSON with these keys only:

  legal_name           (string, required)
  display_name         (string, required; can equal legal_name)
  primary_contact_name (string|null)
  primary_contact_email(string|null)
  notes                (string|null — 1-2 sentence summary)

Do NOT include any other keys. Do NOT explain. Output JSON only."""


def parse_voice_intake(
    transcript: str,
    *,
    llm: LLMProtocol,
    founder_id: str,
    intake_source: IntakeSource = "voice",
) -> IntakePayload:
    """Pure logic: transcript → IntakePayload.

    Raises ValueError when the transcript is empty/short or when the
    LLM fails to extract a required field.
    """
    if not isinstance(transcript, str) or len(transcript.strip()) < MIN_TRANSCRIPT_CHARS:
        raise ValueError(
            f"transcript too short (<{MIN_TRANSCRIPT_CHARS} chars) — refusing intake"
        )
    if not founder_id:
        raise ValueError("founder_id required")

    # Redact secrets BEFORE the LLM sees the transcript.
    redacted_transcript, _counts = redact_secrets(transcript)

    raw = llm.complete(
        system=_INTAKE_SYSTEM_PROMPT,
        user=f"Voice transcript:\n{redacted_transcript}",
        max_tokens=512,
        temperature=0.1,
    )
    try:
        fields = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"LLM returned non-JSON intake payload: {exc}") from exc
    if not isinstance(fields, dict):
        raise ValueError(f"LLM returned non-object intake payload: {type(fields).__name__}")

    for required in REQUIRED_FIELDS:
        value = fields.get(required)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"LLM did not extract required field '{required}'")

    if intake_source not in VALID_INTAKE_SOURCES:
        raise ValueError(f"invalid intake_source: {intake_source!r}")

    # Persist the redacted transcript only (raw transcript NEVER leaves
    # this function in cleartext if it contained secrets).
    return IntakePayload(
        legal_name=fields["legal_name"].strip(),
        display_name=fields["display_name"].strip(),
        founder_id=founder_id,
        intake_source=intake_source,
        primary_contact_name=_optional_str(fields.get("primary_contact_name")),
        primary_contact_email=_optional_str(fields.get("primary_contact_email")),
        raw_notes=_optional_str(fields.get("notes")),
        voice_transcript=redacted_transcript,
    )


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    return s or None


# ============================================================
# Stage 2: dispatch
# ============================================================


def dispatch_intake(
    payload: IntakePayload,
    *,
    http_client: HTTPProtocol,
    api_base: str,
    auth_token: str | None = None,
) -> IntakeResult:
    """POST the payload to Pi-CEO. Never raises on transport errors —
    callers receive IntakeResult(result='transport_error', reason=...).
    """
    body = asdict(payload)
    # Belt-and-braces: re-redact any free-text fields just before transmission.
    redaction_counts: dict[str, int] = {}
    for key in ("raw_notes", "voice_transcript"):
        original = body.get(key)
        if isinstance(original, str) and original:
            redacted, counts = redact_secrets(original)
            body[key] = redacted
            for k, v in counts.items():
                redaction_counts[k] = redaction_counts.get(k, 0) + v

    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    url = f"{api_base.rstrip('/')}{INTAKE_ENDPOINT}"
    try:
        resp = http_client.post(url, json_body=body, headers=headers)
    except Exception as exc:
        log.warning("intake dispatch transport error: %s", exc)
        return IntakeResult(
            result="transport_error",
            reason=str(exc),
            redaction_counts=redaction_counts,
        )

    if 200 <= resp.status_code < 300:
        return IntakeResult(
            result="ok",
            client_id=resp.body.get("client_id"),
            status=resp.body.get("status"),
            redaction_counts=redaction_counts,
        )

    # 4xx / 5xx — surface the upstream reason without raising.
    reason = (
        resp.body.get("detail")
        or resp.body.get("error")
        or f"http {resp.status_code}"
    )
    return IntakeResult(
        result="invalid" if 400 <= resp.status_code < 500 else "transport_error",
        reason=str(reason),
        redaction_counts=redaction_counts,
    )


# ============================================================
# Flow-engine tool binding (Margot side)
# ============================================================


def nexus_intake_from_voice(
    transcript: str,
    *,
    founder_id: str,
    llm: LLMProtocol,
    http_client: HTTPProtocol,
    api_base: str,
    auth_token: str | None = None,
    intake_source: IntakeSource = "voice",
) -> dict[str, Any]:
    """Margot-facing tool: full transcript → result. One call site.

    Returns a JSON-shaped dict — Margot serialises that back to the
    operator via the standard tool-response channel.
    """
    try:
        payload = parse_voice_intake(
            transcript, llm=llm, founder_id=founder_id, intake_source=intake_source,
        )
    except ValueError as exc:
        return {
            "result": "invalid",
            "reason": str(exc),
        }
    outcome = dispatch_intake(
        payload, http_client=http_client, api_base=api_base, auth_token=auth_token,
    )
    return asdict(outcome)
