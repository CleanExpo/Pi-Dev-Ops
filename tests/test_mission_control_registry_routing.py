"""
The Linear project "Mission Control" must be routable from the real registry.

UNI-2726, UNI-2638 and UNI-2661 sit in that project in Ready for Pi-Dev with
pi-dev:autonomous, yet none could reach the /control Linear queue or the poller:
config/harness/projects.json had no row for the project, so issue_is_claimable
rejected them on the project axis. These tests read the committed registry, not
a fixture — the registry is the thing that was stale.
"""
from app.server import autonomy
from app.server.autonomy_eligibility import filter_claimable_issues

MISSION_CONTROL_PROJECT_ID = "16797f9e-aca7-43d1-9090-5b134be99064"
UNITE_GROUP_TEAM_ID = "ab9c7810-4dd6-4ce2-8e8f-e1fc94c6b88b"
PI_DEV_OPS_PROJECT_ID = "f45212be-3259-4bfb-89b1-54c122c939a7"


def _ready_issue(project_id: str) -> dict:
    return {
        "id": "x",
        "identifier": "UNI-2726",
        "title": "t",
        "priority": 1,
        "state": {"id": "st", "name": "Ready for Pi-Dev", "type": "unstarted"},
        "labels": {"nodes": [{"name": "pi-dev:autonomous"}]},
        "project": {"id": project_id},
    }


def test_mission_control_ready_issue_reaches_the_claimable_queue():
    registered = {p["project_id"] for p in autonomy._load_portfolio_projects()}
    kept = filter_claimable_issues(
        [_ready_issue(MISSION_CONTROL_PROJECT_ID)],
        registered_project_ids=registered,
    )
    assert [i["identifier"] for i in kept] == ["UNI-2726"]


def test_mission_control_routes_to_pi_dev_ops_on_the_unite_group_team():
    rows = [p for p in autonomy._load_portfolio_projects() if p["project_id"] == MISSION_CONTROL_PROJECT_ID]
    assert len(rows) == 1
    assert rows[0]["repo_url"] == "https://github.com/CleanExpo/Pi-Dev-Ops"
    assert rows[0]["team_id"] == UNITE_GROUP_TEAM_ID


def test_pi_dev_ops_project_is_still_registered():
    registered = {p["project_id"] for p in autonomy._load_portfolio_projects()}
    assert PI_DEV_OPS_PROJECT_ID in registered
