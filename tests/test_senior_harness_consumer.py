"""Isolated fail-closed tests for the durable Senior Harness consumer."""

from __future__ import annotations

import base64
import copy
import importlib.util
import json
import sys
import time
import urllib.error
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.server import senior_harness_consumer as consumer
from app.server.senior_harness_admission import (
    AdmissionVerificationError,
    ConsumerExpectation,
)


def _authority_module():
    path = (
        Path(__file__).parents[1]
        / "skills"
        / "senior-harness"
        / "scripts"
        / "admission_authority.py"
    )
    name = "senior_harness_admission_authority_consumer_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class AuthorityTransport:
    def __init__(self, authority, envelope):
        self.authority = authority
        self.envelope = copy.deepcopy(envelope)
        self.consume_calls = []
        self.assert_calls = []
        self.consume_response = None
        self.assert_response = None
        self.consume_error = None
        self.assert_error = None

    def _row(self):
        claim = self.envelope["claim"]
        expiry = datetime.fromtimestamp(claim["expires_at"], tz=timezone.utc)
        return {
            "admission_ref": claim["admission_ref"],
            "state": "consumed",
            "expires_at": expiry.isoformat().replace("+00:00", "Z"),
            "consumption_session_id": claim["session_id"],
        }

    def consume_child(self, payload):
        self.consume_calls.append(copy.deepcopy(dict(payload)))
        if self.consume_error:
            raise self.consume_error
        if self.consume_response is not None:
            return copy.deepcopy(self.consume_response)
        claim = self.envelope["claim"]
        expectation = ConsumerExpectation(
            **{
                field: claim[field]
                for field in ConsumerExpectation.__dataclass_fields__
            }
        )
        self.authority.consume_child(
            claim["admission_ref"],
            expectation=expectation,
            key_ring=self.authority.public_key_ring(),
        )
        return [self._row()]

    def assert_active(self, payload):
        self.assert_calls.append(copy.deepcopy(dict(payload)))
        if self.assert_error:
            raise self.assert_error
        if self.assert_response is not None:
            return copy.deepcopy(self.assert_response)
        claim = self.envelope["claim"]
        self.authority.assert_active(
            claim["admission_ref"], session_id=claim["session_id"]
        )
        return [self._row()]


@pytest.fixture(autouse=True)
def clean_runtime():
    consumer.clear_runtime()
    yield
    consumer.clear_runtime()


@pytest.fixture
def issued():
    module = _authority_module()
    now = int(time.time())
    authority = module.InMemoryAdmissionAuthority(
        module.generate_private_key(),
        signer_key_id="issuer-2026-08",
        audience="pi-ceo/build",
        clock=lambda: now,
    )
    scope = {"paths": ["app/server/**"], "max_files_modified": 2}
    parent = authority.reserve_parent(
        source_kind="linear",
        source_id="issue-1",
        source_version="2026-08-21T01:02:03Z",
        repository="git@github.com:Unite-Group/Pi-Dev-Ops.git",
        objective="Ship the exact durable consumer",
        scope=scope,
        task_id="task-1",
        plan_id="plan-1",
        base_sha="a" * 40,
        node_contract_digest="sha256:" + "b" * 64,
        ttl_seconds=600,
        admission_ref="parent-1",
    )
    envelope = authority.derive_child(
        parent["claim"]["admission_ref"],
        node_id="1.1",
        reservation_ref="reservation-1",
        worker_id="worker-1",
        worker_context_id="context-1",
        session_id="abcdef012345",
        node_contract_digest="sha256:" + "c" * 64,
        ttl_seconds=300,
        admission_ref="child-1",
    )
    reservation = {
        "schema_version": "1.0",
        "reservation_ref": "reservation-1",
        "task_id": "task-1",
        "plan_id": "plan-1",
        "node_id": "1.1",
        "worker_id": "worker-1",
        "worker_context_id": "context-1",
        "base_sha": "a" * 40,
        "node_contract_digest": "sha256:" + "c" * 64,
    }
    transport = AuthorityTransport(authority, envelope)
    consumer.install_runtime(transport, authority.public_key_ring(), "pi-ceo/build")
    request = {
        "repo_url": "https://github.com/unite-group/pi-dev-ops.git",
        "brief": "Ship the exact durable consumer",
        "scope": scope,
        "reservation": reservation,
        "expected_session_id": "abcdef012345",
    }
    return authority, transport, envelope, request


def test_preview_is_pure_then_consume_and_assert_keep_only_minimal_handle(issued):
    _authority, transport, envelope, request = issued

    preview = consumer.verify_for_build(envelope, **request)
    assert preview.session_id == "abcdef012345"
    assert preview.admission_ref == "child-1"
    assert transport.consume_calls == []
    with pytest.raises(AdmissionVerificationError, match="no active handle"):
        consumer.assert_active(preview.session_id)

    binding = consumer.consume_for_build(envelope, **request)
    handle = consumer.assert_active(binding.session_id)

    assert binding == preview
    assert asdict(handle) == {
        "admission_ref": "child-1",
        "claim_digest": envelope["claim"]["claim_digest"],
        "worker_context_id": "context-1",
        "audience": "pi-ceo/build:worker:context-1",
    }
    assert set(consumer._active_handles) == {"abcdef012345"}
    assert set(asdict(consumer._active_handles["abcdef012345"])) == {
        "admission_ref",
        "claim_digest",
        "worker_context_id",
        "audience",
    }
    assert "signature" not in repr(handle)
    assert "envelope" not in repr(handle)


def test_consume_converts_signature_and_epochs_for_postgresql(issued):
    _authority, transport, envelope, request = issued
    consumer.consume_for_build(envelope, **request)

    payload = transport.consume_calls[0]
    signature = base64.urlsafe_b64decode(
        envelope["signature"] + "=" * (-len(envelope["signature"]) % 4)
    )
    assert payload["p_signature"] == "\\x" + signature.hex()
    assert payload["p_issued_at"].endswith("Z")
    assert payload["p_expires_at"].endswith("Z")
    assert "+00:00" not in payload["p_issued_at"]
    assert payload["p_session_id"] == "abcdef012345"


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("repo_url", "https://github.com/other/repo"),
        ("brief", "A different objective"),
        ("scope", {"paths": ["different/**"]}),
        ("expected_session_id", "000000000000"),
    ],
)
def test_every_request_binding_mutation_fails_before_transport(
    issued, field, replacement
):
    _authority, transport, envelope, request = issued
    request[field] = replacement

    with pytest.raises(AdmissionVerificationError, match="target mismatch"):
        consumer.consume_for_build(envelope, **request)
    assert transport.consume_calls == []


def test_reservation_and_deployment_audience_mutations_fail_before_transport(issued):
    authority, transport, envelope, request = issued
    request["reservation"]["worker_context_id"] = "other-context"
    with pytest.raises(AdmissionVerificationError, match="target mismatch"):
        consumer.consume_for_build(envelope, **request)
    assert transport.consume_calls == []

    consumer.install_runtime(transport, authority.public_key_ring(), "other-audience")
    request["reservation"]["worker_context_id"] = "context-1"
    with pytest.raises(AdmissionVerificationError, match="target mismatch"):
        consumer.consume_for_build(envelope, **request)
    assert transport.consume_calls == []


def test_signed_envelope_mutation_and_absence_fail_before_transport(issued):
    _authority, transport, envelope, request = issued
    tampered = copy.deepcopy(envelope)
    tampered["claim"]["worker_id"] = "attacker"
    with pytest.raises(AdmissionVerificationError):
        consumer.consume_for_build(tampered, **request)
    with pytest.raises(AdmissionVerificationError, match="signed.*required"):
        consumer.consume_for_build(None, **request)
    assert transport.consume_calls == []


@pytest.mark.parametrize("session_id", ["ABCDEF012345", "abcdef01234", "session-12345"])
def test_signed_session_id_is_strict_lowercase_hex(session_id):
    module = _authority_module()
    now = int(time.time())
    authority = module.InMemoryAdmissionAuthority(
        module.generate_private_key(),
        signer_key_id="issuer-1",
        audience="pi-ceo/build",
        clock=lambda: now,
    )
    parent = authority.reserve_parent(
        source_kind="linear",
        source_id="issue-1",
        source_version="version-1",
        repository="https://github.com/org/repo",
        objective="Brief",
        scope={},
        task_id="task-1",
        plan_id="plan-1",
        base_sha="a" * 40,
        node_contract_digest="sha256:" + "b" * 64,
        ttl_seconds=60,
    )
    envelope = authority.derive_child(
        parent["claim"]["admission_ref"],
        node_id="node-1",
        reservation_ref="reservation-1",
        worker_id="worker-1",
        worker_context_id="context-1",
        session_id=session_id,
        node_contract_digest="sha256:" + "c" * 64,
        ttl_seconds=60,
    )
    claim = envelope["claim"]
    reservation = {
        "schema_version": "1.0",
        **{
            field: claim[field]
            for field in (
                "reservation_ref",
                "task_id",
                "plan_id",
                "node_id",
                "worker_id",
                "worker_context_id",
                "base_sha",
                "node_contract_digest",
            )
        },
    }
    transport = AuthorityTransport(authority, envelope)
    consumer.install_runtime(transport, authority.public_key_ring(), "pi-ceo/build")

    with pytest.raises(AdmissionVerificationError, match="12 lowercase hexadecimal"):
        consumer.consume_for_build(
            envelope,
            repo_url="https://github.com/org/repo",
            brief="Brief",
            scope={},
            reservation=reservation,
        )
    assert transport.consume_calls == []


def test_replay_is_denied_and_does_not_replace_registry_handle(issued):
    _authority, _transport, envelope, request = issued
    first = consumer.consume_for_build(envelope, **request)
    first_handle = consumer.assert_active(first.session_id)

    with pytest.raises(AdmissionVerificationError, match="consumed"):
        consumer.consume_for_build(envelope, **request)
    assert consumer.assert_active(first.session_id) == first_handle


@pytest.mark.parametrize(
    "bad_response",
    [
        [],
        [
            {
                "admission_ref": "child-1",
                "state": "consumed",
                "expires_at": "2099-01-01T00:00:00Z",
                "consumption_session_id": "abcdef012345",
            },
            {
                "admission_ref": "child-1",
                "state": "consumed",
                "expires_at": "2099-01-01T00:00:00Z",
                "consumption_session_id": "abcdef012345",
            },
        ],
        {"admission_ref": "child-1"},
        [{"admission_ref": "child-1"}],
    ],
)
def test_consume_fails_closed_on_zero_multiple_or_malformed_rows(issued, bad_response):
    _authority, transport, envelope, request = issued
    transport.consume_response = bad_response

    with pytest.raises(AdmissionVerificationError):
        consumer.consume_for_build(envelope, **request)
    assert consumer._active_handles == {}


def test_consume_and_assert_transport_errors_fail_closed(issued):
    _authority, transport, envelope, request = issued
    transport.consume_error = OSError("network down")
    with pytest.raises(AdmissionVerificationError, match="failed closed"):
        consumer.consume_for_build(envelope, **request)
    assert consumer._active_handles == {}

    transport.consume_error = None
    binding = consumer.consume_for_build(envelope, **request)
    transport.assert_error = RuntimeError("RPC unavailable")
    with pytest.raises(AdmissionVerificationError, match="failed closed"):
        consumer.assert_active(binding.session_id)


def test_assert_fails_closed_on_zero_multiple_and_malformed_rows(issued):
    _authority, transport, envelope, request = issued
    binding = consumer.consume_for_build(envelope, **request)

    for response in ([], [{"state": "consumed"}], [transport._row(), transport._row()]):
        transport.assert_response = response
        with pytest.raises(AdmissionVerificationError):
            consumer.assert_active(binding.session_id)


def test_bootstrap_removes_dedicated_token_and_never_uses_service_role(
    monkeypatch, issued
):
    authority, transport, _envelope, _request = issued
    public = authority.public_key_base64url()
    captured = {}

    def transport_factory(url, token):
        captured.update(url=url, token=token)
        return transport

    consumer.clear_runtime()
    monkeypatch.setenv("SENIOR_HARNESS_ADMISSION_MODE", "enforce")
    monkeypatch.setattr(consumer, "PostgRESTConsumerTransport", transport_factory)
    monkeypatch.setenv(consumer.RPC_URL_ENV, "https://example.supabase.co/rest/v1/rpc")
    monkeypatch.setenv(consumer.CONSUMER_TOKEN_ENV, "consumer-only-token")
    monkeypatch.setenv(
        consumer.PUBLIC_KEYS_ENV, json.dumps({"issuer-2026-08": public})
    )
    monkeypatch.setenv(consumer.AUDIENCE_ENV, "pi-ceo/build")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "must-not-be-used")

    consumer.bootstrap_from_env()

    assert consumer.runtime_ready()
    assert consumer.CONSUMER_TOKEN_ENV not in __import__("os").environ
    assert captured == {
        "url": "https://example.supabase.co/rest/v1/rpc",
        "token": "consumer-only-token",
    }
    assert __import__("os").environ["SUPABASE_SERVICE_ROLE_KEY"] == "must-not-be-used"


def test_bootstrap_removes_token_even_when_later_configuration_is_invalid(monkeypatch):
    monkeypatch.setenv("SENIOR_HARNESS_ADMISSION_MODE", "enforce")
    monkeypatch.setenv(consumer.CONSUMER_TOKEN_ENV, "consumer-only-token")
    monkeypatch.delenv(consumer.PUBLIC_KEYS_ENV, raising=False)

    with pytest.raises(Exception):
        consumer.bootstrap_from_env()
    assert consumer.CONSUMER_TOKEN_ENV not in __import__("os").environ
    assert not consumer.runtime_ready()


@pytest.mark.parametrize("mode", ["off", "observe"])
def test_bootstrap_is_immediate_noop_outside_enforce(monkeypatch, mode):
    monkeypatch.setenv("SENIOR_HARNESS_ADMISSION_MODE", mode)
    monkeypatch.setenv(consumer.CONSUMER_TOKEN_ENV, "must-remain-unread")

    consumer.bootstrap_from_env()

    assert __import__("os").environ[consumer.CONSUMER_TOKEN_ENV] == "must-remain-unread"
    assert not consumer.runtime_ready()


def test_postgrest_transport_calls_only_public_wrapper_names(monkeypatch):
    calls = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"[]"

    def urlopen(request, timeout):
        calls.append((request, timeout))
        return Response()

    monkeypatch.setattr(consumer.urllib.request, "urlopen", urlopen)
    transport = consumer.PostgRESTConsumerTransport(
        "https://example.supabase.co/rest/v1/rpc", "consumer-token"
    )
    transport.consume_child({"p_value": "consume"})
    transport.assert_active({"p_value": "assert"})

    assert calls[0][0].full_url.endswith("/senior_harness_consume_child")
    assert calls[1][0].full_url.endswith("/senior_harness_assert_active")
    assert all("private" not in request.full_url for request, _timeout in calls)
    assert calls[0][0].headers["Authorization"] == "Bearer consumer-token"


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.URLError("network down"),
        urllib.error.HTTPError("https://example.invalid", 403, "denied", {}, None),
        TimeoutError("timed out"),
    ],
)
def test_postgrest_transport_network_and_http_errors_fail_closed(monkeypatch, failure):
    def urlopen(_request, timeout):
        assert timeout == 8.0
        raise failure

    monkeypatch.setattr(consumer.urllib.request, "urlopen", urlopen)
    transport = consumer.PostgRESTConsumerTransport(
        "https://example.supabase.co/rest/v1/rpc", "consumer-token"
    )

    with pytest.raises(AdmissionVerificationError, match="failed closed"):
        transport.consume_child({"p_value": "consume"})


def test_postgrest_transport_malformed_json_fails_closed(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"not-json"

    monkeypatch.setattr(
        consumer.urllib.request, "urlopen", lambda _request, timeout: Response()
    )
    transport = consumer.PostgRESTConsumerTransport(
        "https://example.supabase.co/rest/v1/rpc", "consumer-token"
    )

    with pytest.raises(AdmissionVerificationError, match="malformed JSON"):
        transport.assert_active({"p_value": "assert"})


def test_runtime_lifecycle_is_explicit(issued):
    assert consumer.runtime_ready()
    consumer.clear_runtime()
    assert not consumer.runtime_ready()
    with pytest.raises(Exception, match="not installed"):
        consumer.assert_active("abcdef012345")


@pytest.mark.parametrize("mode", ["off", "observe"])
def test_require_active_for_run_is_noop_in_legacy_modes(monkeypatch, mode):
    monkeypatch.setenv("SENIOR_HARNESS_ADMISSION_MODE", mode)
    assert consumer.require_active_for_run("not-even-a-session-id") is None


def test_require_active_for_run_delegates_in_enforce(monkeypatch, issued):
    _authority, _transport, envelope, request = issued
    monkeypatch.setenv("SENIOR_HARNESS_ADMISSION_MODE", "enforce")
    binding = consumer.consume_for_build(envelope, **request)

    assert consumer.require_active_for_run(binding.session_id) == consumer.assert_active(
        binding.session_id
    )
