"""RA-7910: claim and poller queries stay under Linear's complexity ceiling."""
from __future__ import annotations

import io
import urllib.error

import pytest

from app.server import mesh_lanes
from app.server.autonomy_queue import PAGE_SIZE, TODO_ISSUES_QUERY
from app.server.linear_complexity import LINEAR_MAX_COMPLEXITY, error_detail, estimate

# Half of Linear's ceiling: room for the gap between this estimate and Linear's count,
# and for one more guard field before claiming breaks again.
BUDGET = LINEAR_MAX_COMPLEXITY / 2


def test_estimate_follows_linears_published_rule():
    # issues object 1 + 2 nodes x (1 object + 2 properties x 0.1)
    assert round(estimate("query{issues(first:2){nodes{id title}}}"), 1) == 3.4
    # no pagination argument means 50
    assert round(estimate("query{labels{nodes{name}}}"), 1) == 56.0


def test_self_claim_query_is_under_budget():
    assert estimate(mesh_lanes.SELF_CLAIM_QUERY) <= BUDGET


def test_poller_query_is_under_budget():
    assert estimate(TODO_ISSUES_QUERY) <= BUDGET


def test_the_page_size_that_broke_claiming_is_refused():
    """The 04/10 shape: 25 issues a page, each with the three guard connections."""
    broke = mesh_lanes.SELF_CLAIM_QUERY.replace(mesh_lanes._PAGE_ARGS, "first:25", 1)
    assert estimate(broke) > LINEAR_MAX_COMPLEXITY
    poller_broke = TODO_ISSUES_QUERY.replace(f"first: {PAGE_SIZE},", "first: 25,", 1)
    assert estimate(poller_broke) > LINEAR_MAX_COMPLEXITY


def test_error_detail_surfaces_linears_message():
    body = b'{"errors":[{"message":"Query too complex","extensions":{"code":"RATELIMITED"}}]}'
    err = urllib.error.HTTPError("https://api.linear.app/graphql", 400, "Bad Request", {},
                                 io.BytesIO(body))
    assert error_detail(err) == ": Query too complex"
    assert error_detail(ValueError("boom")) == ""


@pytest.mark.parametrize("body", [b'{"errors":7}', b'{"errors":"x"}', b"[1]", b"not json", b""])
def test_malformed_linear_error_body_cannot_crash_the_claim_route(monkeypatch, body):
    """Codex review of RA-7910: {"errors":7} raised TypeError out of the except block."""
    from app.server import config
    from app.server.routes import mesh

    def refuse(*_a, **_k):
        raise urllib.error.HTTPError("https://api.linear.app/graphql", 400, "Bad Request", {},
                                     io.BytesIO(body))

    monkeypatch.setattr(config, "LINEAR_API_KEY", "lin_test_not_a_key", raising=False)
    monkeypatch.setattr(mesh.urllib.request, "urlopen", refuse)
    assert mesh._linear_graphql("query{issues{nodes{id}}}") == {}
