"""RED controls for the typed, privacy-bounded CCW source adapter."""
from __future__ import annotations

import importlib


def _source():
    try:
        return importlib.import_module("tools.ccw_support_watch.source")
    except ModuleNotFoundError as exc:
        raise AssertionError("RED-03 typed source adapter is missing") from exc


def test_red_03_authenticated_empty_is_not_auth_failure():
    result = _source().parse_source_response({"authenticated": True, "ok": True, "items": []})
    assert result.ok is True
    assert result.items == ()
    assert result.error_code is None


def test_red_03_auth_failure_uses_allow_list_without_raw_error():
    result = _source().parse_source_response({
        "authenticated": False, "ok": False, "error": "private provider detail",
    })
    assert result.ok is False
    assert result.error_code == "AUTH_FAILED"
    assert "private" not in repr(result)


def test_red_04_malformed_and_error_envelopes_never_become_empty_success():
    malformed = _source().parse_source_response({"authenticated": True, "ok": True})
    query_error = _source().parse_source_response({
        "authenticated": True, "ok": False, "items": [], "error": "opaque",
    })
    assert malformed.error_code == "MALFORMED_RESPONSE"
    assert query_error.error_code == "QUERY_FAILED"
    assert not malformed.ok and not query_error.ok


def test_red_07_missing_provider_id_is_rejected_before_persistence():
    result = _source().parse_source_response({
        "authenticated": True, "ok": True,
        "items": [{"provider_id": None, "received_at": "2026-07-22T00:00:00Z"}],
    })
    assert result.error_code == "MISSING_SOURCE_ID"
    assert result.items == ()


def test_red_12_prohibited_source_fields_are_rejected_not_snapshotted():
    for field in ("address", "subject", "snippet", "body", "token", "raw_error", "payload"):
        result = _source().parse_source_response({
            "authenticated": True, "ok": True,
            "items": [{
                "provider_id": "message-1",
                "received_at": "2026-07-22T00:00:00Z",
                field: "sensitive",
            }],
        })
        assert result.error_code == "MALFORMED_RESPONSE"
        assert "sensitive" not in repr(result)
