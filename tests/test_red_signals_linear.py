"""tests/test_red_signals_linear.py — audit 2026-09-30 rank #6.

red_signals.upsert_red_linear_ticket keeps ONE open Linear ticket per red
signal: comment if open, create once otherwise, never a second. Founder-only
reds carry the founder-only label or are not filed. Linear is a fake here;
nothing leaves the process.
"""
from __future__ import annotations

import json
import logging

import pytest

import app.server.cron_watchdogs as cw

LOG = logging.getLogger("test")


# ── Linear find-or-update ───────────────────────────────────────────────────


class _Linear:
    """Fake Linear GraphQL endpoint: records every operation it is sent."""

    def __init__(self, existing: list[dict], labels: list[dict]):
        self.existing = existing
        self.labels = labels
        self.ops: list[tuple[str, dict]] = []
        self.find_queries: list[str] = []
        self.find_data: dict | None = None

    def urlopen(self, req, timeout=10):  # noqa: ARG002
        payload = json.loads(req.data)
        q = payload["query"]
        v = payload.get("variables") or {}
        if "issueAddLabel" in q:
            op, data = "add_label", {"issueAddLabel": {"success": True}}
        elif "issueLabels" in q:
            op, data = "labels", {"issueLabels": {"nodes": self.labels}}
        elif "commentCreate" in q:
            op, data = "comment", {"commentCreate": {"success": True}}
        elif "issueCreate" in q:
            op, data = "create", {"issueCreate": {"success": True, "issue": {"identifier": "RA-NEW"}}}
        elif "issues(" in q:
            op, data = "find", {"issues": {"nodes": self.existing}}
        else:
            raise AssertionError(f"unexpected Linear query: {q[:80]}")
        if op == "find":
            self.find_queries.append(q)
            if self.find_data is not None:
                data = self.find_data
        self.ops.append((op, v))
        body = json.dumps({"data": data}).encode()

        class _R:
            def __enter__(self_):
                return self_

            def __exit__(self_, *a):
                return False

            def read(self_):
                return body

        return _R()


@pytest.fixture
def linear_key(monkeypatch):
    import app.server.config as config

    monkeypatch.setattr(config, "LINEAR_API_KEY", "lin_api_test_key", raising=False)


def test_upsert_updates_existing_ticket_never_creates_second(monkeypatch, linear_key):
    import urllib.request as _ureq

    fake = _Linear(existing=[{"id": "uuid-1", "identifier": "RA-9001"}], labels=[])
    monkeypatch.setattr(_ureq, "urlopen", fake.urlopen)

    ident = cw._upsert_red_linear_ticket(
        "[RED] health_full: margot_route", "still red", owner="Margot operator",
        founder_only=False, log=LOG,
    )

    assert ident == "RA-9001"
    kinds = [op for op, _ in fake.ops]
    assert "create" not in kinds
    assert kinds == ["find", "comment"]
    assert fake.ops[1][1]["input"]["issueId"] == "uuid-1"
    assert "Owner: Margot operator" in fake.ops[1][1]["input"]["body"]


def test_upsert_creates_once_with_founder_only_label(monkeypatch, linear_key):
    import urllib.request as _ureq

    fake = _Linear(existing=[], labels=[{"id": "label-fo", "name": "founder-only"}])
    monkeypatch.setattr(_ureq, "urlopen", fake.urlopen)

    ident = cw._upsert_red_linear_ticket(
        "[RED] health_full: schema_drift_db", "SUPABASE_DB_URL not set",
        owner="Deploy/infra operator", founder_only=True, log=LOG,
    )

    assert ident == "RA-NEW"
    creates = [v for op, v in fake.ops if op == "create"]
    assert len(creates) == 1
    inp = creates[0]["input"]
    assert inp["title"] == "[RED] health_full: schema_drift_db"
    assert inp["labelIds"] == ["label-fo"]
    assert "Owner: Deploy/infra operator" in inp["description"]


def test_upsert_agent_fixable_creates_without_label(monkeypatch, linear_key):
    import urllib.request as _ureq

    fake = _Linear(existing=[], labels=[{"id": "label-fo", "name": "founder-only"}])
    monkeypatch.setattr(_ureq, "urlopen", fake.urlopen)

    cw._upsert_red_linear_ticket(
        "[RED] health_full: margot_route", "stale", owner="Margot operator",
        founder_only=False, log=LOG,
    )

    creates = [v for op, v in fake.ops if op == "create"]
    assert len(creates) == 1
    assert "labelIds" not in creates[0]["input"]
    assert "labels" not in [op for op, _ in fake.ops]


def test_upsert_does_not_create_when_lookup_fails(monkeypatch, linear_key):
    """A failed find must not fall through to a create: that is how duplicates are born."""
    import urllib.request as _ureq

    calls: list[str] = []

    def boom(req, timeout=10):  # noqa: ARG001
        calls.append(json.loads(req.data)["query"])
        raise OSError("linear down")

    monkeypatch.setattr(_ureq, "urlopen", boom)

    assert cw._upsert_red_linear_ticket(
        "[RED] health_full: margot_route", "x", owner="o", founder_only=False, log=LOG,
    ) is None
    assert len(calls) == 1


# ── review round 1 (codex, 798e34cf): four P1s, each planted here ──────────


@pytest.mark.parametrize("malformed", [{}, {"issues": {}}, {"issues": {"nodes": None}}, {"issues": None}])
def test_malformed_lookup_never_creates(monkeypatch, linear_key, malformed):
    import urllib.request as _ureq

    fake = _Linear(existing=[], labels=[])
    fake.find_data = malformed
    monkeypatch.setattr(_ureq, "urlopen", fake.urlopen)

    assert cw._upsert_red_linear_ticket(
        "[RED] health_full: margot_route", "x", owner="o", founder_only=False, log=LOG,
    ) is None
    assert [op for op, _ in fake.ops] == ["find"]


def test_founder_only_without_label_is_not_filed_unlabelled(monkeypatch, linear_key):
    import urllib.request as _ureq

    fake = _Linear(existing=[], labels=[])
    monkeypatch.setattr(_ureq, "urlopen", fake.urlopen)

    assert cw._upsert_red_linear_ticket(
        "[RED] health_full: schema_drift_db", "x", owner="founder", founder_only=True, log=LOG,
    ) is None
    assert "create" not in [op for op, _ in fake.ops]


def test_founder_only_update_adds_label_to_existing_issue(monkeypatch, linear_key):
    import urllib.request as _ureq

    fake = _Linear(existing=[{"id": "uuid-1", "identifier": "RA-9001"}],
                   labels=[{"id": "label-fo", "name": "founder-only"}])
    monkeypatch.setattr(_ureq, "urlopen", fake.urlopen)

    assert cw._upsert_red_linear_ticket(
        "[RED] health_full: schema_drift_db", "x", owner="founder", founder_only=True, log=LOG,
    ) == "RA-9001"
    adds = [v for op, v in fake.ops if op == "add_label"]
    assert adds == [{"id": "uuid-1", "labelId": "label-fo"}]
    assert "create" not in [op for op, _ in fake.ops]


def test_lookup_counts_triage_issues_as_open(monkeypatch, linear_key):
    import urllib.request as _ureq

    fake = _Linear(existing=[], labels=[])
    monkeypatch.setattr(_ureq, "urlopen", fake.urlopen)
    cw._upsert_red_linear_ticket("[RED] health_full: x", "x", owner="o", founder_only=False, log=LOG)
    assert '"triage"' in fake.find_queries[0]


@pytest.mark.parametrize("error,expected", [
    ("credential expired", True),
    ("SUPABASE_DB_URL absent", True),
    ("permission denied", True),
    ("HTTP 401 unauthorized", True),
    ("last token count stale", False),
    ("no turn since 2026-08-30", False),
])
def test_founder_only_classification(error, expected):
    from app.server.red_signals import health_full_ticket

    assert health_full_ticket("supabase", {"ok": False, "error": error})["founder_only"] is expected
