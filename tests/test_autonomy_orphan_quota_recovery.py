"""Recovery after quota at each orphan mutation step."""

import sys

import pytest

from app.server import autonomy, autonomy_linear_rate


@pytest.fixture(autouse=True)
def clear_cooldown(monkeypatch):
    monkeypatch.setattr(autonomy_linear_rate, "_rate_limited_until", 0.0)


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
    assert recovered == (0 if quota_step == "comment" else 1)
    before = scenario.calls[:]
    autonomy._orphan_recovery_sync("test-key")
    assert scenario.calls == before


def test_label_lookup_propagates_quota(monkeypatch):
    def quota(*_args, **_kwargs):
        raise autonomy._mark_linear_rate_limited()
    monkeypatch.setattr(autonomy, "_gql", quota)
    with pytest.raises(autonomy.LinearRateLimitError):
        autonomy.add_label_to_issue("test-key", "issue-1", autonomy._RA_TEAM_ID,
                                    autonomy._BLOCKED_REASON_SESSION_LOST)
