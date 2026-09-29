"""Offline contract tests; no TypeSafe key or network is needed."""

import json
import sqlite3

import pytest

from scripts import mission_control_jev_shadow as shadow


def snapshot(index=0, **overrides):
    return {
        "run_id": f"run-{index}",
        "sha": "ded1a54e24f547861c89e85c5056e8b77176bb59",
        "surface": "/control",
        "visible_text": f"Project {index}: no scan evidence",
        "network_calls": [{"method": "GET", "path": "/api/projects/health", "status": 200}],
        "data_classification": "synthetic",
        **overrides,
    }


def test_offline_replay_of_1000_varied_snapshots_never_calls_network(tmp_path):
    source = tmp_path / "snapshots.jsonl"
    output = tmp_path / "receipts.jsonl"
    with source.open("w") as stream:
        for index in range(1000):
            record = snapshot(index, visible_text=f"Project {index}: {'empty' if index % 2 else 'unavailable'}")
            if index % 3 == 0:
                record["failure"] = f"Assertion failed on Project {index}"
            if index % 5 == 0:
                record["action"] = "GO"
            if index % 7 == 0:
                record["assertions"] = ["Status visible", "No 500 responses"]
            stream.write(json.dumps(record) + "\n")
    assert shadow.main([str(source), str(output)]) == 0
    receipts = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(receipts) == 1000
    assert {item["run_id"] for item in receipts} == {f"run-{index}" for index in range(1000)}
    assert all(item["mode"] == "offline" and set(item["labels"].values()) == {"NOT_EVALUATED"} for item in receipts)
    assert "Project 999" not in output.read_text()


def test_allowlist_and_redaction_exclude_credentials_contacts_and_query_values():
    fake_key = "ghp_" + "A" * 36
    record = snapshot(
        visible_text=f"Call admin@example.com with Bearer {'b' * 40} or {fake_key}, password=topsecret and \"token\":\"secret123\" RA-1234",
        network_calls=[{"method": "POST", "path": "/api/idea?token=topsecret", "status": 500, "headers": {"Authorization": fake_key}, "body": fake_key}],
        cookies=fake_key,
    )
    payload, receipt = shadow.prepare(record)
    serial = json.dumps(payload) + json.dumps(receipt)
    for raw in (fake_key, "admin@example.com", "topsecret", "secret123", "RA-1234", "cookies", "Authorization"):
        assert raw not in serial
    assert "[REDACTED_SECRET]" in serial
    assert payload["state"]["network_calls"][0]["path"] == "/api/idea"


def test_real_data_is_not_sent_even_with_a_key(tmp_path):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network call attempted")

    receipt = shadow.run_line(
        snapshot(data_classification="real"), live=True, key="synthetic-key", ledger=tmp_path / "budget.sqlite", opener=forbidden
    )
    assert receipt["reason"] == "REAL_DATA_EGRESS_NOT_APPROVED"
    assert receipt["labels"] == {"J1": "NOT_EVALUATED"}
    assert not (tmp_path / "budget.sqlite").exists()


def test_local_dirty_provenance_is_preserved_without_entering_model_state():
    payload, receipt = shadow.prepare(snapshot(workspace_dirty=True))
    assert receipt["workspace_dirty"] is True
    assert "workspace_dirty" not in payload["state"]


def test_live_synthetic_response_is_advisory_and_redacted(tmp_path):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps({
                "model": "jev-1.13.0",
                "answers": {"J1": {"type": "choice", "choice": "EXPLICIT_EMPTY_STATE", "confidence": 0.8,
                                    "probabilities": {name: 1 if name == "EXPLICIT_EMPTY_STATE" else 0 for name in shadow.J1_OPTIONS}}},
                "usage": {"input_tokens": 300, "output_tokens": 20},
            }).encode()

    def opener(req, timeout):
        assert timeout == 15
        assert b"synthetic@example.com" not in req.data
        assert req.full_url == shadow.API_URL
        return Response()

    receipt = shadow.run_line(
        snapshot(visible_text="synthetic@example.com: No projects"), live=True,
        key="synthetic-key", ledger=tmp_path / "budget.sqlite", opener=opener,
    )
    assert receipt["labels"]["J1"]["label"] == "EXPLICIT_EMPTY_STATE"
    assert receipt["model"] == "jev-1.13.0"
    assert receipt["input_tokens"] == 300
    assert "synthetic@example.com" not in json.dumps(receipt)


def test_1000_varied_shadow_calls_are_each_ledgered_without_a_default_cap(tmp_path):
    class Response:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps(self.body).encode()

    seen = 0

    def opener(req, timeout):
        nonlocal seen
        seen += 1
        assert timeout == 15
        state = json.loads(req.data)["state"]
        assert state["visible_text"] == f"Project {seen - 1}: synthetic state"
        label = "REAL_DATA" if seen % 2 else "EXPLICIT_EMPTY_STATE"
        return Response({
            "model": "jev-1.13.0",
            "answers": {"J1": {"type": "choice", "choice": label, "confidence": 0.9,
                                "probabilities": {name: 1 if name == label else 0 for name in shadow.J1_OPTIONS}}},
            "usage": {"input_tokens": 300 + seen % 10, "output_tokens": 20},
        })

    ledger = tmp_path / "shared.sqlite"
    for index in range(1000):
        receipt = shadow.run_line(
            snapshot(index, visible_text=f"Project {index}: synthetic state"), live=True,
            key="synthetic-key", ledger=ledger, opener=opener,
        )
        assert receipt["labels"]["J1"]["label"] == ("REAL_DATA" if (index + 1) % 2 else "EXPLICIT_EMPTY_STATE")
    assert seen == 1000
    with sqlite3.connect(ledger) as db:
        count, reserved, actual, minimum, maximum = db.execute(
            "SELECT COUNT(*), SUM(reserved_usd), SUM(actual_usd), MIN(input_tokens), MAX(input_tokens) FROM calls WHERE status='answered'"
        ).fetchone()
    assert count == 1000
    assert reserved == pytest.approx(1000 * 64_000 * 0.042 / 1_000_000)
    assert actual < reserved
    assert minimum == 300 and maximum == 309


def test_budget_reservation_stops_before_an_overrun(tmp_path):
    ledger = tmp_path / "budget.sqlite"
    assert shadow.reserve_call(ledger, 1000, cap=0.000042) is not None
    assert shadow.reserve_call(ledger, 1000, cap=0.000042) is None
    with sqlite3.connect(ledger) as db:
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 1


@pytest.mark.parametrize("change", [
    {"sha": "unknown"},
    {"network_calls": [{"method": "GET", "path": "https://example.com?token=x", "status": 200}]},
    {"surface": "https://example.com/control"},
    {"failure": 42},
])
def test_invalid_snapshots_fail_closed(change):
    with pytest.raises(ValueError):
        shadow.prepare(snapshot(**change))


def test_invalid_model_response_never_becomes_a_label(tmp_path):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps({"answers": {"J1": {"type": "choice", "choice": "PASSED"}}}).encode()

    receipt = shadow.run_line(snapshot(), live=True, key="synthetic-key", ledger=tmp_path / "budget.sqlite", opener=lambda *_a, **_kw: Response())
    assert receipt["labels"]["J1"] == "NOT_EVALUATED"


def test_unexpected_model_version_does_not_silently_change_reviewed_contract():
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b'{"model":"jev-2.0.0","answers":{},"usage":{"input_tokens":300}}'

    with pytest.raises(TypeError, match="invalid API response"):
        shadow.evaluate({"state": "synthetic", "model": shadow.MODEL, "questions": {}}, "synthetic-key", lambda *_a, **_kw: Response())
