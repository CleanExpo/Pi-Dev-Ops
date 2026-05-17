"""Tests for scripts/linear_helpers.py."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import linear_helpers


def _mock_response(payload: dict, status: int = 200):
    m = MagicMock()
    m.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    m.__enter__.return_value.status = status
    return m


def test_create_linear_issue_success():
    payload = {"data": {"issueCreate": {"success": True,
        "issue": {"id": "abc-123", "identifier": "CCW-247", "title": "test"}}}}
    with patch("linear_helpers.urllib.request.urlopen", return_value=_mock_response(payload)) as mock_open:
        ref = linear_helpers.create_linear_issue(
            api_key="lin_api_xxx", title="test", description="body",
            team_id="UNI-team", project_id="ccw-proj", priority=3,
        )
    assert ref is not None
    assert ref.identifier == "CCW-247"
    assert ref.id == "abc-123"
    req = mock_open.call_args[0][0]
    body = json.loads(req.data.decode())
    assert body["variables"]["input"]["teamId"] == "UNI-team"
    assert body["variables"]["input"]["projectId"] == "ccw-proj"
    assert body["variables"]["input"]["title"] == "test"
    assert body["variables"]["input"]["priority"] == 3


def test_create_linear_issue_truncates_long_title():
    long_title = "x" * 500
    payload = {"data": {"issueCreate": {"success": True,
        "issue": {"id": "i", "identifier": "RA-1", "title": "x" * 250}}}}
    with patch("linear_helpers.urllib.request.urlopen", return_value=_mock_response(payload)) as mock_open:
        linear_helpers.create_linear_issue(api_key="k", title=long_title,
            description="d", team_id="t", project_id="p", priority=3)
    req = mock_open.call_args[0][0]
    body = json.loads(req.data.decode())
    assert len(body["variables"]["input"]["title"]) == 250


def test_create_linear_issue_returns_none_on_graphql_error():
    payload = {"errors": [{"message": "Project not found"}]}
    with patch("linear_helpers.urllib.request.urlopen", return_value=_mock_response(payload)):
        ref = linear_helpers.create_linear_issue(api_key="k", title="t",
            description="d", team_id="t", project_id="p", priority=3)
    assert ref is None


def test_create_linear_issue_returns_none_on_http_error():
    import urllib.error
    with patch("linear_helpers.urllib.request.urlopen",
               side_effect=urllib.error.URLError("network down")):
        ref = linear_helpers.create_linear_issue(api_key="k", title="t",
            description="d", team_id="t", project_id="p", priority=3)
    assert ref is None
