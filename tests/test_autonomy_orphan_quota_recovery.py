"""Recovery after quota at each orphan mutation step."""

import json
import sys

import pytest

from app.server import autonomy, autonomy_linear_rate


@pytest.fixture(autouse=True)
def clear_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr(autonomy_linear_rate, "_rate_limited_until", 0.0)
    monkeypatch.setattr(autonomy, "_logged_orphan_recoveries", set())
    monkeypatch.setattr(autonomy, "_AUTONOMY_LOG", tmp_path / "autonomy.jsonl")


class OrphanScenario:
    def __init__(self, quota_step):
        self.quota_step = quota_step
        self.failed = False
        self.events, self.calls = [], []
        self.project = {"project_id": "p1", "team_id": autonomy._RA_TEAM_ID,
                        "name": "RA", "repo_url": "https://example.test/repo"}
        self.target = autonomy._recovery_state_for(self.project["team_id"])
        self.issue = {"id": "issue-1", "identifier": "RA-1",
                      "state": {"name": "In Progress", "type": "started"},
                      "labels": {"nodes": []},
                      "comments": {"nodes": [{"body": "Session ID: `abc12345abcd`"}]}}

    def maybe_quota(self, step):
        if step == self.quota_step and not self.failed:
            self.failed = True
            raise autonomy._mark_linear_rate_limited()

    def gql(self, _key, query, _variables):
        if "RecoveryTargetPiCeoIssues" in query:
            nodes = [self.issue] if self.issue["state"]["name"] == self.target else []
        else:
            nodes = [self.issue] if self.issue["state"]["name"] == "In Progress" else []
        return {"project": {"issues": {"nodes": nodes}}}

    def transition(self, _key, _iid, state, team_id):
        self.calls.append("transition")
        self.maybe_quota("transition")
        self.issue["state"] = {"name": state, "type": "unstarted"}

    def label(self, _key, _iid, _team, name):
        self.calls.append("label")
        self.maybe_quota("label")
        self.issue["labels"]["nodes"].append({"name": name})
        return True

    def comment(self, _key, _iid, body):
        self.calls.append("comment")
        self.issue["comments"]["nodes"].append({"body": body})
        self.maybe_quota("comment")

    def install(self, monkeypatch):
        fake_mod = type(sys)("app.server.sessions")
        fake_mod._sessions = {}
        monkeypatch.setitem(sys.modules, "app.server.sessions", fake_mod)
        monkeypatch.setattr(autonomy, "_load_portfolio_projects", lambda: [self.project])
        monkeypatch.setattr(autonomy, "_gql", self.gql)
        monkeypatch.setattr(autonomy, "transition_issue", self.transition)
        monkeypatch.setattr(autonomy, "add_label_to_issue", self.label)
        monkeypatch.setattr(autonomy, "comment_on_issue", self.comment)
        monkeypatch.setattr(autonomy, "_log_event", self.events.append)


@pytest.mark.parametrize("quota_step", ["transition", "label", "comment"])
def test_orphan_recovery_completes_after_quota_at_each_mutation(monkeypatch, quota_step):
    scenario = OrphanScenario(quota_step)
    scenario.install(monkeypatch)
    with pytest.raises(autonomy.LinearRateLimitError):
        autonomy._orphan_recovery_sync("test-key")
    assert scenario.events[-1]["action"] == "orphan_recovery_error"
    assert scenario.events[-1]["ticket"] == "RA-1"
    assert "Linear rate limited" in scenario.events[-1]["error"]
    monkeypatch.setattr(autonomy_linear_rate, "_rate_limited_until", 0.0)
    autonomy._orphan_recovery_sync("test-key")
    assert scenario.issue["state"]["name"] == scenario.target
    assert [n["name"] for n in scenario.issue["labels"]["nodes"]] == [
        autonomy._BLOCKED_REASON_SESSION_LOST]
    assert sum(autonomy._ORPHAN_COMMENT_MARKER in n["body"]
               for n in scenario.issue["comments"]["nodes"]) == 1
    recovered = [e["action"] for e in scenario.events].count("orphan_recovered")
    assert recovered == 1
    before = scenario.calls[:]
    autonomy._orphan_recovery_sync("test-key")
    assert scenario.calls == before
    assert [e["action"] for e in scenario.events].count("orphan_recovered") == 1


def test_label_lookup_propagates_quota(monkeypatch):
    def quota(*_args, **_kwargs):
        raise autonomy._mark_linear_rate_limited()
    monkeypatch.setattr(autonomy, "_gql", quota)
    with pytest.raises(autonomy.LinearRateLimitError):
        autonomy.add_label_to_issue("test-key", "issue-1", autonomy._RA_TEAM_ID,
                                    autonomy._BLOCKED_REASON_SESSION_LOST)


def test_retry_finds_recovery_comment_after_first_five(monkeypatch):
    scenario = OrphanScenario("comment")
    scenario.issue["comments"]["nodes"].extend(
        {"body": f"earlier comment {i}"} for i in range(4))
    scenario.install(monkeypatch)
    page_requests = []

    def gql(_key, query, variables):
        comments = scenario.issue["comments"]["nodes"]
        if "OrphanCommentPage" in query:
            page_requests.append(variables["after"])
            return {"issue": {"comments": {"nodes": comments[5:],
                    "pageInfo": {"hasNextPage": False, "endCursor": None}}}}
        target = "RecoveryTargetPiCeoIssues" in query
        visible = scenario.issue["state"]["name"] == (
            scenario.target if target else "In Progress")
        item = {**scenario.issue, "comments": {"nodes": comments[:5],
                "pageInfo": {"hasNextPage": len(comments) > 5,
                             "endCursor": "comment-5"}}}
        return {"project": {"issues": {"nodes": [item] if visible else []}}}

    monkeypatch.setattr(autonomy, "_gql", gql)
    with pytest.raises(autonomy.LinearRateLimitError):
        autonomy._orphan_recovery_sync("test-key")
    monkeypatch.setattr(autonomy_linear_rate, "_rate_limited_until", 0.0)
    autonomy._orphan_recovery_sync("test-key")
    assert page_requests == ["comment-5"]
    assert sum(autonomy._ORPHAN_COMMENT_MARKER in n["body"]
               for n in scenario.issue["comments"]["nodes"]) == 1
    assert [e["action"] for e in scenario.events].count("orphan_recovered") == 1


def test_target_scan_finds_partial_ticket_on_second_page(monkeypatch):
    scenario = OrphanScenario("never")
    scenario.issue["state"] = {"name": scenario.target, "type": "unstarted"}
    scenario.issue["labels"]["nodes"] = [{"name": autonomy._BLOCKED_REASON_SESSION_LOST}]
    scenario.install(monkeypatch)
    complete = [{"id": f"done-{i}", "identifier": f"RA-{i + 2}",
                 "state": {"name": scenario.target},
                 "labels": {"nodes": [{"name": autonomy._BLOCKED_REASON_SESSION_LOST}]},
                 "comments": {"nodes": [
                     {"body": "Session ID: `abc12345abcd`"},
                     {"body": autonomy._ORPHAN_COMMENT_MARKER}]}}
                for i in range(30)]
    cursors = []

    def gql(_key, query, variables):
        if "RecoveryTargetPiCeoIssues" not in query:
            return {"project": {"issues": {"nodes": []}}}
        cursors.append(variables.get("after"))
        second = variables.get("after") == "issue-30"
        return {"project": {"issues": {
            "nodes": [scenario.issue] if second else complete,
            "pageInfo": {"hasNextPage": not second,
                         "endCursor": "issue-30" if not second else None}}}}

    monkeypatch.setattr(autonomy, "_gql", gql)
    autonomy._AUTONOMY_LOG.write_text("\n".join(
        json.dumps({"action": "orphan_recovered", "ticket": item["identifier"]})
        for item in complete) + "\n")
    autonomy._orphan_recovery_sync("test-key")
    assert cursors == [None, "issue-30"]
    assert scenario.calls == ["comment"]
    assert [n["name"] for n in scenario.issue["labels"]["nodes"]] == [
        autonomy._BLOCKED_REASON_SESSION_LOST]
    assert [e["action"] for e in scenario.events] == ["orphan_recovered"]


def test_manual_target_state_with_old_session_is_not_recovered(monkeypatch):
    scenario = OrphanScenario("never")
    scenario.issue["state"] = {"name": scenario.target, "type": "unstarted"}
    scenario.issue["labels"]["nodes"] = [{"name": "manual-reset"}]
    scenario.install(monkeypatch)
    autonomy._orphan_recovery_sync("test-key")
    assert scenario.calls == []
    assert scenario.issue["labels"]["nodes"] == [{"name": "manual-reset"}]
    assert scenario.events == []


def test_ambiguous_comment_success_reconciles_after_restart(monkeypatch, tmp_path):
    scenario = OrphanScenario("comment")
    real_log_event = autonomy._log_event
    monkeypatch.setattr(autonomy, "_AUTONOMY_LOG", tmp_path / "autonomy.jsonl")
    monkeypatch.setattr(autonomy, "_recent_events", [])
    scenario.install(monkeypatch)

    def persist_and_capture(event):
        real_log_event(event)
        scenario.events.append(event)

    monkeypatch.setattr(autonomy, "_log_event", persist_and_capture)
    with pytest.raises(autonomy.LinearRateLimitError):
        autonomy._orphan_recovery_sync("test-key")
    assert [e["action"] for e in scenario.events] == ["orphan_recovery_error"]
    monkeypatch.setattr(autonomy, "_logged_orphan_recoveries", set())
    monkeypatch.setattr(autonomy_linear_rate, "_rate_limited_until", 0.0)
    autonomy._orphan_recovery_sync("test-key")
    assert [e["action"] for e in scenario.events].count("orphan_recovered") == 1
    assert scenario.calls == ["label", "transition", "comment"]
    monkeypatch.setattr(autonomy, "_logged_orphan_recoveries", set())
    autonomy._orphan_recovery_sync("test-key")
    persisted = [json.loads(line) for line in autonomy._AUTONOMY_LOG.read_text().splitlines()]
    assert [e["action"] for e in persisted] == [
        "orphan_recovery_error", "orphan_recovered"]
    assert scenario.calls == ["label", "transition", "comment"]
