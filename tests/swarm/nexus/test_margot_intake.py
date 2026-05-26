"""Focused tests for swarm.nexus.margot_intake — voice → intake binding.

No real network, no real LLM. Stubs implement the two Protocols
exposed by the module under test.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from swarm.nexus.margot_intake import (
    INTAKE_ENDPOINT,
    HTTPResponse,
    IntakePayload,
    dispatch_intake,
    nexus_intake_from_voice,
    parse_voice_intake,
)


# ============================================================
# Stubs
# ============================================================


class StubLLM:
    def __init__(self, response: dict | str | Exception):
        self._resp = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 1024,
                 temperature: float = 0.3) -> str:
        self.calls.append((system, user))
        if isinstance(self._resp, Exception):
            raise self._resp
        if isinstance(self._resp, str):
            return self._resp
        return json.dumps(self._resp)


class StubHTTP:
    def __init__(self, response: HTTPResponse | Exception):
        self._resp = response
        self.calls: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    def post(self, url: str, *, json_body: dict[str, Any],
             headers: dict[str, str]) -> HTTPResponse:
        self.calls.append((url, json_body, headers))
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


GOOD_LLM_FIELDS = {
    "legal_name": "ACME Pty Ltd",
    "display_name": "Acme",
    "primary_contact_name": "Jane Smith",
    "primary_contact_email": "jane@acme.example",
    "notes": "Restoration company, looking for GEO.",
}


# ============================================================
# parse_voice_intake
# ============================================================


class TestParseVoiceIntake:
    def test_happy_path_returns_payload(self):
        llm = StubLLM(GOOD_LLM_FIELDS)
        payload = parse_voice_intake(
            "Hi Margot, I'd like to onboard ACME Pty Ltd to the platform.",
            llm=llm, founder_id="phill",
        )
        assert isinstance(payload, IntakePayload)
        assert payload.legal_name == "ACME Pty Ltd"
        assert payload.display_name == "Acme"
        assert payload.founder_id == "phill"
        assert payload.intake_source == "voice"

    def test_short_transcript_raises(self):
        with pytest.raises(ValueError, match="transcript too short"):
            parse_voice_intake("hi", llm=StubLLM(GOOD_LLM_FIELDS), founder_id="phill")

    def test_missing_founder_id_raises(self):
        with pytest.raises(ValueError, match="founder_id required"):
            parse_voice_intake(
                "Long enough transcript here mate.",
                llm=StubLLM(GOOD_LLM_FIELDS),
                founder_id="",
            )

    def test_llm_returns_non_json_raises(self):
        with pytest.raises(ValueError, match="non-JSON intake payload"):
            parse_voice_intake(
                "Long enough transcript here mate.",
                llm=StubLLM("not json at all"),
                founder_id="phill",
            )

    def test_llm_missing_required_field_raises(self):
        bad = {**GOOD_LLM_FIELDS, "legal_name": ""}
        with pytest.raises(ValueError, match="did not extract required field 'legal_name'"):
            parse_voice_intake(
                "Long enough transcript here mate.",
                llm=StubLLM(bad), founder_id="phill",
            )

    def test_redacts_secrets_before_llm_call(self):
        """A secret in the transcript must NEVER reach the LLM in cleartext."""
        llm = StubLLM(GOOD_LLM_FIELDS)
        leaky = (
            "Onboard ACME. By the way the API key is "
            "sk-ant-api03-LONGSECRETOFREALSHAPE000000000000000000000000000000000000000-XYZ "
            "for testing."
        )
        payload = parse_voice_intake(leaky, llm=llm, founder_id="phill")
        assert llm.calls, "LLM should have been called"
        _system, user_msg = llm.calls[0]
        assert "sk-ant" not in user_msg, "secret leaked into LLM prompt"
        assert "[REDACTED:" in user_msg
        # And the persisted voice_transcript is also redacted:
        assert "sk-ant" not in (payload.voice_transcript or "")


# ============================================================
# dispatch_intake
# ============================================================


def _basic_payload() -> IntakePayload:
    return IntakePayload(
        legal_name="ACME Pty Ltd",
        display_name="Acme",
        founder_id="phill",
        intake_source="voice",
        voice_transcript="hello there mate",
    )


class TestDispatchIntake:
    def test_happy_path_returns_ok(self):
        http = StubHTTP(HTTPResponse(
            status_code=201,
            body={"client_id": "c-1", "status": "intake"},
        ))
        result = dispatch_intake(
            _basic_payload(),
            http_client=http,
            api_base="https://pi-ceo.example",
        )
        assert result.result == "ok"
        assert result.client_id == "c-1"
        assert result.status == "intake"
        assert http.calls[0][0] == f"https://pi-ceo.example{INTAKE_ENDPOINT}"

    def test_auth_token_attaches_bearer_header(self):
        http = StubHTTP(HTTPResponse(
            status_code=201, body={"client_id": "c", "status": "intake"},
        ))
        dispatch_intake(
            _basic_payload(),
            http_client=http,
            api_base="https://pi-ceo.example",
            auth_token="t0k3n",
        )
        _, _, headers = http.calls[0]
        assert headers.get("Authorization") == "Bearer t0k3n"

    def test_4xx_returns_invalid_with_reason(self):
        http = StubHTTP(HTTPResponse(
            status_code=422, body={"detail": "legal_name missing"},
        ))
        result = dispatch_intake(
            _basic_payload(), http_client=http, api_base="https://pi-ceo.example",
        )
        assert result.result == "invalid"
        assert result.reason == "legal_name missing"
        assert result.client_id is None

    def test_5xx_returns_transport_error(self):
        http = StubHTTP(HTTPResponse(status_code=503, body={}))
        result = dispatch_intake(
            _basic_payload(), http_client=http, api_base="https://pi-ceo.example",
        )
        assert result.result == "transport_error"

    def test_transport_exception_does_not_raise(self):
        http = StubHTTP(ConnectionError("DNS failure"))
        result = dispatch_intake(
            _basic_payload(), http_client=http, api_base="https://pi-ceo.example",
        )
        assert result.result == "transport_error"
        assert "DNS failure" in (result.reason or "")

    def test_re_redacts_freetext_at_transmission(self):
        """Belt-and-braces: even if upstream forgot to redact, dispatch does."""
        payload = IntakePayload(
            legal_name="ACME Pty Ltd",
            display_name="Acme",
            founder_id="phill",
            intake_source="voice",
            voice_transcript="API key sk-ant-api03-LONGSECRETOFREALSHAPE000000000000000000000000000000000000000-XYZ",
            raw_notes="another sk-ant-api03-LONGSECRETOFREALSHAPE000000000000000000000000000000000000000-XYZ",
        )
        http = StubHTTP(HTTPResponse(
            status_code=201, body={"client_id": "c", "status": "intake"},
        ))
        result = dispatch_intake(
            payload, http_client=http, api_base="https://pi-ceo.example",
        )
        _, body, _ = http.calls[0]
        assert "sk-ant" not in (body.get("voice_transcript") or "")
        assert "sk-ant" not in (body.get("raw_notes") or "")
        # Redaction counts surfaced on the result:
        assert sum(result.redaction_counts.values()) >= 2


# ============================================================
# nexus_intake_from_voice (tool entry-point)
# ============================================================


class TestToolEntryPoint:
    def test_end_to_end_happy_path(self):
        llm = StubLLM(GOOD_LLM_FIELDS)
        http = StubHTTP(HTTPResponse(
            status_code=201, body={"client_id": "c-7", "status": "intake"},
        ))
        result = nexus_intake_from_voice(
            "Onboard ACME Pty Ltd please.",
            founder_id="phill",
            llm=llm,
            http_client=http,
            api_base="https://pi-ceo.example",
        )
        assert result["result"] == "ok"
        assert result["client_id"] == "c-7"

    def test_parse_error_surfaces_as_invalid(self):
        result = nexus_intake_from_voice(
            "Onboard ACME Pty Ltd please.",
            founder_id="phill",
            llm=StubLLM("garbage not json"),
            http_client=StubHTTP(HTTPResponse(status_code=201)),
            api_base="https://pi-ceo.example",
        )
        assert result["result"] == "invalid"
        assert "non-JSON" in result["reason"]
