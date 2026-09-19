"""Required CI must be complete, successful, and bound to the reviewed commit."""
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest
from app.server.spec_pipeline import ship_gate

SHA = "a" * 40


def run(name="tests", *, conclusion="success", status="completed", app=1, ident=1, sha=SHA):
    return {"id": ident, "name": name, "head_sha": sha, "status": status,
            "conclusion": conclusion, "app": {"id": app}}


def legacy(context="tests", *, state="success", ident=1):
    return {"id": ident, "context": context, "state": state}


class GitHub:
    def __init__(self):
        self.protection = {"required_status_checks": {"contexts": ["tests"], "checks": []}}
        self.rules, self.statuses, self.runs, self.calls = [], [], [run()], []
        self.head, self.base = SHA, "main"
        self.before = None
        self.suites = {"total_count": 1}

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if self.before:
            self.before(method, path)
        route = urlsplit(path).path
        page = int(parse_qs(urlsplit(path).query).get("page", ["1"])[0])
        start = (page - 1) * 100
        if method == "POST":
            return {"number": 1, "html_url": "https://example.test/pr"}
        if method == "PUT":
            return {"merged": True, "sha": "b" * 40}
        if route.endswith("/pulls/1"):
            return {"head": {"sha": self.head}, "base": {"ref": self.base}}
        if route.endswith("/protection"):
            if isinstance(self.protection, Exception):
                raise self.protection
            return self.protection
        if "/rules/branches/" in route:
            return self.rules[start:start + 100]
        if route.endswith("/check-suites"):
            return self.suites
        if route.endswith("/check-runs"):
            assert f"/commits/{SHA}/" in route
            return {"total_count": len(self.runs), "check_runs": self.runs[start:start + 100]}
        if route.endswith("/statuses"):
            assert f"/commits/{SHA}/" in route
            return self.statuses[start:start + 100]
        raise AssertionError(path)


@pytest.fixture
def github(monkeypatch):
    api = GitHub()
    monkeypatch.setattr(ship_gate, "_github_request", api)
    monkeypatch.setattr(ship_gate, "machine_ship_enabled", lambda: True)
    return api


def ship():
    return ship_gate.open_pr_and_merge(repo="owner/repo", branch="candidate", title="reviewed",
                                      body="checked", candidate_sha=SHA, poll_seconds=0, max_polls=1)


def assert_not_merged(api, result):
    assert result["status"] != "merged"
    assert not any(method == "PUT" for method, _, _ in api.calls)


def test_required_context_missing_cannot_be_replaced_by_arbitrary_success(github):
    github.runs = [run("unrelated")]
    assert_not_merged(github, ship())


@pytest.mark.parametrize("conclusion", ["skipped", "neutral", "failure", "cancelled", None])
def test_required_check_must_actually_succeed(github, conclusion):
    github.runs = [run(conclusion=conclusion)]
    assert_not_merged(github, ship())


@pytest.mark.parametrize("policy", [{}, {"required_status_checks": None},
    {"required_status_checks": {"contexts": [], "checks": []}},
    HTTPError("https://example.test", 403, "denied", {}, None),
    HTTPError("https://example.test", 404, "unknown", {}, None)])
def test_absent_or_unknown_required_policy_blocks(github, policy):
    github.protection = policy
    assert_not_merged(github, ship())


def test_check_pagination_cannot_hide_required_failure(github):
    github.runs = [run(f"other-{i}", ident=i + 1) for i in range(100)] + [run(conclusion="failure", ident=101)]
    assert_not_merged(github, ship())
    assert any("check-runs" in path and "page=2" in path for _, path, _ in github.calls)


def test_legacy_status_on_later_page_satisfies_required_context(github):
    github.runs = []
    github.statuses = [legacy(f"other-{i}", ident=i + 2) for i in range(100)] + [legacy()]
    assert ship()["status"] == "merged"
    assert any("statuses" in path and "page=2" in path for _, path, _ in github.calls)


def test_newest_failed_or_pending_evidence_overrides_old_success(github):
    github.runs = [run(ident=1), run(ident=2, conclusion=None, status="queued")]
    assert_not_merged(github, ship())


def test_successful_rerun_can_replace_old_failure(github):
    github.runs = [run(ident=1, conclusion="failure"), run(ident=2)]
    assert ship()["status"] == "merged"


def test_latest_legacy_failure_overrides_old_success(github):
    github.runs = []
    github.statuses = [legacy(ident=2, state="failure"), legacy(ident=1)]
    assert_not_merged(github, ship())


def test_same_named_status_and_check_must_both_succeed(github):
    github.statuses = [legacy(state="pending")]
    assert_not_merged(github, ship())


def test_required_app_cannot_be_spoofed_by_another_app_or_legacy_status(github):
    github.protection["required_status_checks"]["checks"] = [{"context": "tests", "app_id": 9}]
    github.statuses = [legacy()]
    assert_not_merged(github, ship())


def test_pinned_app_success_satisfies_required_check(github):
    github.protection["required_status_checks"]["checks"] = [{"context": "tests", "app_id": 9}]
    github.runs = [run(app=9)]
    assert ship()["status"] == "merged"


def test_effective_ruleset_checks_are_unioned_and_paginated(github):
    github.rules = [{"type": "deletion"} for _ in range(100)] + [{"type": "required_status_checks",
        "parameters": {"required_status_checks": [{"context": "security", "integration_id": 4}]}}]
    assert_not_merged(github, ship())
    assert any("rules/branches" in path and "page=2" in path for _, path, _ in github.calls)


def test_ruleset_checks_work_when_classic_checks_explicitly_absent(github):
    github.protection = {"required_status_checks": None}
    github.rules = [{"type": "required_status_checks", "parameters": {
        "required_status_checks": [{"context": "tests", "integration_id": 1}]}}]
    assert ship()["status"] == "merged"


@pytest.mark.parametrize("change", ["head", "policy", "check", "base"])
def test_last_moment_changes_prevent_merge(github, change):
    reads = 0
    def before(method, path):
        nonlocal reads
        if "check-runs" not in path:
            return
        reads += 1
        if reads == 2:
            if change == "head":
                github.head = "c" * 40
            elif change == "base":
                github.base = "release"
            elif change == "policy":
                github.protection["required_status_checks"]["contexts"].append("new-required")
            else:
                github.runs = [run(status="in_progress", conclusion=None)]
    github.before = before
    assert_not_merged(github, ship())


def test_green_candidate_is_rechecked_then_merge_uses_sha_precondition(github):
    result = ship()
    assert result["status"] == "merged" and result["candidate_sha"] == SHA
    assert github.calls[-1][0] == "PUT" and github.calls[-1][2]["sha"] == SHA
    assert sum("check-runs" in path for _, path, _ in github.calls) >= 2
