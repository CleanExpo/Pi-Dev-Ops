"""Best-effort Linear state synchronization for the serialized ship phase."""
import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("pi-ceo.pipeline")


def request(api_key, query, variables):
    req = urllib.request.Request(
        "https://api.linear.app/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": api_key}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def state_id(api_key, issue_id, state_name):
    result = request(api_key, "query GetIssueTeam($id: String!) { issue(id: $id) { team { id } } }", {"id": issue_id})
    team_id = (result.get("data") or {}).get("issue", {}).get("team", {}).get("id")
    if not team_id:
        log.warning("Linear: could not resolve team for issue %s", issue_id)
        return None
    result = request(api_key, "query GetTeamStates($teamId: String!) { team(id: $teamId) { states { nodes { id name } } } }", {"teamId": team_id})
    nodes = (result.get("data") or {}).get("team", {}).get("states", {}).get("nodes", [])
    return next((node["id"] for node in nodes if node.get("name", "").lower() == state_name.lower()), None)


def update_state(issue_id, state_name):
    """Report actual mutation success; missing credentials or states never pass."""
    api_key = os.environ.get("LINEAR_API_KEY", "")
    if not api_key:
        log.warning("LINEAR_API_KEY not set; cannot update issue %s", issue_id)
        return False
    try:
        target = state_id(api_key, issue_id, state_name)
        if not target:
            return False
        result = request(api_key,
            "mutation UpdateIssueState($id: String!, $stateId: String!) { issueUpdate(id: $id, input: { stateId: $stateId }) { success issue { id title state { name } } } }",
            {"id": issue_id, "stateId": target})
        return (result.get("data") or {}).get("issueUpdate", {}).get("success") is True
    except Exception as exc:
        log.warning("Linear state update failed for %s (%s)", issue_id, type(exc).__name__)
        return False
