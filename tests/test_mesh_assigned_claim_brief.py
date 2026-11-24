"""A dispatcher-assigned claim gets its brief before it is worked, or it is refused.

`mesh_work_claims` has no text columns, so a claim the dispatcher assigns reaches the
runner as `{linear_id, id, machine, state}` and nothing else. Before this change
`next_work` handed that straight to `build_prompt`, whose refusal path stopped every
dispatched run without working it (the KNOWN GAP in mesh/fleet_state.py).

The runner now asks the server for the brief of the ticket named on the claim. The
server reads Linear with its own key; the node stays credential-free (mesh/prompt.py
says why). A claim the runner cannot brief is failed with a named code, so the ticket
returns to the pool instead of staying locked under a claim nobody will work.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "mesh"))

from fleet_state import next_work  # noqa: E402

HOST = "unite-mac-mini"
BRIEF = {"linear_id": "UNI-7", "title": "Fix the header", "description": "Make it sticky.",
         "lane": "build", "repo": "CleanExpo/Pi-Dev-Ops"}


class FakeApi:
    """Answers the three calls next_work makes, and records every call."""

    def __init__(self, claims, brief=None):
        self.claims = claims
        self.brief = brief if brief is not None else BRIEF
        self.calls: list[tuple[str, str, object]] = []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.startswith("/api/mesh/fleet"):
            return {"claims": self.claims, "agents": [], "degraded": False, "errors": []}
        if path.startswith("/api/mesh/claim/brief"):
            return self.brief
        if path == "/api/mesh/claim/update":
            return {"ok": True}
        if path == "/api/mesh/claim/self":
            return {"claimed": None}
        raise AssertionError(f"unexpected call {method} {path}")

    def updates(self):
        return [body for method, path, body in self.calls if path == "/api/mesh/claim/update"]

    def brief_calls(self):
        return [path for _, path, _ in self.calls if path.startswith("/api/mesh/claim/brief")]


def _assigned(**extra):
    return {"linear_id": "UNI-7", "id": "claim-1", "machine": HOST, "state": "claimed", **extra}


def test_assigned_claim_arrives_with_the_tickets_brief():
    api = FakeApi([_assigned()])
    work = next_work(api, HOST)
    assert len(work) == 1
    claim = work[0]
    assert claim["title"] == "Fix the header"
    assert claim["description"] == "Make it sticky."
    assert claim["lane"] == "build"
    assert claim["repo"] == "CleanExpo/Pi-Dev-Ops"
    assert claim["id"] == "claim-1", "the claim row id must survive hydration"
    assert api.updates() == [], "a briefed claim is worked, not failed"


def test_brief_request_names_the_ticket_the_host_and_the_claim_row():
    api = FakeApi([_assigned()])
    next_work(api, HOST)
    [path] = api.brief_calls()
    assert "linear_id=UNI-7" in path and f"host={HOST}" in path and "claim_id=claim-1" in path


def test_plan_lane_from_the_ticket_reaches_the_claim():
    api = FakeApi([_assigned()], brief={**BRIEF, "lane": "plan", "repo": None})
    [claim] = next_work(api, HOST)
    assert claim["lane"] == "plan", "an idea:plan ticket must be reviewed, never built"


def test_self_claimed_brief_is_not_fetched_again():
    api = FakeApi([_assigned(title="Already here", description="x")])
    [claim] = next_work(api, HOST)
    assert claim["title"] == "Already here"
    assert api.brief_calls() == []


@pytest.mark.parametrize("response, code", [
    ({"error": "HTTP 503", "detail": "Linear could not be read"}, "brief_unreadable"),
    ({"error": "timed out"}, "brief_unreadable"),
    ({"error": "HTTP 409", "detail": "no open claim"}, "brief_refused"),
    ({"linear_id": "UNI-7", "title": "", "description": "  ", "lane": "build", "repo": None}, "brief_empty"),
    ("not a dict", "brief_unreadable"),
])
def test_unbriefable_claim_is_failed_with_a_named_reason(response, code):
    api = FakeApi([_assigned()], brief=response)
    assert next_work(api, HOST) == [], "an unbriefed claim must never reach an agent"
    [update] = api.updates()
    assert update["state"] == "failed"
    assert update["error_code"] == code
    assert update["linear_id"] == "UNI-7"
    assert update["host"] == HOST and update["claim_id"] == "claim-1"


def test_brief_for_another_ticket_is_refused():
    api = FakeApi([_assigned()], brief={**BRIEF, "linear_id": "UNI-8"})
    assert next_work(api, HOST) == []
    [update] = api.updates()
    assert update["error_code"] == "brief_refused"


def test_claim_with_no_ticket_is_refused_and_never_briefed():
    api = FakeApi([_assigned(linear_id="")])
    outcomes: list[str] = []
    assert next_work(api, HOST, outcomes.append) == []
    assert api.brief_calls() == []
    assert outcomes[-1] == "refused"


def test_one_bad_claim_does_not_block_a_good_one():
    good = _assigned()
    bad = {**_assigned(linear_id="UNI-9"), "id": "claim-2"}

    class Mixed(FakeApi):
        def __call__(self, method, path, body=None):
            if path.startswith("/api/mesh/claim/brief") and "UNI-9" in path:
                self.calls.append((method, path, body))
                return {"error": "HTTP 503"}
            return super().__call__(method, path, body)

    api = Mixed([good, bad])
    work = next_work(api, HOST)
    assert [c["linear_id"] for c in work] == ["UNI-7"]
    assert [u["linear_id"] for u in api.updates()] == ["UNI-9"]


def test_refusal_does_not_self_claim_in_the_same_poll():
    api = FakeApi([_assigned()], brief={"error": "HTTP 503"})
    next_work(api, HOST)
    assert not any(path == "/api/mesh/claim/self" for _, path, _ in api.calls)


def test_dispatched_claim_builds_a_prompt_containing_the_brief():
    """UNI-2799 done-condition: a dispatched (briefless) claim reaches the agent's prompt with its brief."""
    from prompt import build_prompt
    [claim] = next_work(FakeApi([_assigned()]), HOST)
    prompt = build_prompt(claim, claim["linear_id"], "mesh/x/uni-7", nonce="n0")
    assert "Title: Fix the header" in prompt and "Make it sticky." in prompt
    assert "brief did not arrive" not in prompt


@pytest.mark.parametrize("partial", [
    {k: v for k, v in BRIEF.items() if k != "lane"},
    {**BRIEF, "lane": "deploy"},
    {k: v for k, v in BRIEF.items() if k != "repo"},
    {**BRIEF, "repo": 7},
    {**BRIEF, "title": ["not", "text"]},
])
def test_partial_brief_never_reaches_an_agent(partial):
    """A brief missing its lane or repo contract could build a plan ticket, or build in the default repo."""
    api = FakeApi([_assigned()], brief=partial)
    assert next_work(api, HOST) == []
    [update] = api.updates()
    assert update["error_code"] == "brief_unreadable"
