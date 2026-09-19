"""Malformed, truncated or mismatched CI evidence cannot authorize delivery."""
from urllib.error import HTTPError

import pytest
from app.server.spec_pipeline import ship_gate
from app.server.spec_pipeline.github_ci_evidence import CIVerificationError, all_pages
from test_spec_required_checks import github as github, run, legacy, ship, assert_not_merged


@pytest.mark.parametrize("suites", [{}, {"total_count": None}, {"total_count": -1}, {"total_count": 1001}])
def test_ref_endpoint_suite_truncation_or_unknown_count_blocks(github, suites):
    github.suites = suites
    assert_not_merged(github, ship())


@pytest.mark.parametrize("rows", [
    [run(sha="b" * 40)], [run(ident=True)], [run(ident=1), run(ident=1)],
    [run(app=None)], [run(status="unknown")], [run(name="")],
])
def test_malformed_run_evidence_blocks(github, rows):
    github.runs = rows
    assert_not_merged(github, ship())


def test_duplicate_legacy_status_ids_block(github):
    github.statuses = [legacy(), legacy()]
    assert_not_merged(github, ship())


@pytest.mark.parametrize("policy", [
    {"contexts": None}, {"contexts": [None]}, {"contexts": [""]},
    {"contexts": ["tests"], "checks": None},
    {"contexts": ["tests"], "checks": [{"context": "tests", "app_id": False}]},
])
def test_malformed_classic_policy_blocks(github, policy):
    github.protection = {"required_status_checks": policy}
    assert_not_merged(github, ship())


@pytest.mark.parametrize("rule", [{}, {"type": "required_status_checks"},
    {"type": "required_status_checks", "parameters": {"required_status_checks": None}},
    {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "tests", "integration_id": "1"}]}}])
def test_malformed_effective_rules_cannot_drop_requirements(github, rule):
    github.rules = [rule]
    assert_not_merged(github, ship())


def test_unreadable_rulesets_block_even_with_successful_classic_checks(github, monkeypatch):
    def request(method, path, body=None):
        if "/rules/branches/" in path:
            raise HTTPError("https://example.test", 403, "denied", {}, None)
        return github(method, path, body)
    monkeypatch.setattr(ship_gate, "_github_request", request)
    assert_not_merged(github, ship())


@pytest.mark.parametrize("payload", [{}, {"total_count": 2, "check_runs": [run()]},
    {"total_count": 1, "check_runs": None}, {"total_count": True, "check_runs": []},
    {"total_count": 10001, "check_runs": []}, {"total_count": 1, "check_runs": [None]}])
def test_malformed_or_truncated_check_pages_fail_closed(payload):
    with pytest.raises(CIVerificationError):
        all_pages(lambda *a: payload, "/checks", key="check_runs")


def test_count_changes_between_pages_fail_closed():
    pages = iter([{"total_count": 101, "check_runs": [run(ident=i + 1) for i in range(100)]},
                  {"total_count": 102, "check_runs": [run(ident=101)]}])
    with pytest.raises(CIVerificationError, match="changed"):
        all_pages(lambda *a: next(pages), "/checks", key="check_runs")


def test_full_pages_require_a_final_empty_page():
    calls = []
    def request(method, path):
        calls.append(path)
        return [run(ident=i + 1) for i in range(100)] if len(calls) == 1 else []
    assert len(all_pages(request, "/statuses")) == 100
    assert calls[-1].endswith("page=2")
