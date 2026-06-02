from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from tao.build_router import classify_intent, get_adw_template  # noqa: E402
from tao.skills import skills_for_intent  # noqa: E402


def _skill_names(intent: str) -> list[str]:
    return [skill["name"] for skill in skills_for_intent(intent)]


def test_bare_github_repo_routes_to_repo_intake():
    brief = (
        "https://github.com/can1357/oh-my-pi.git this repo has 40+ providers, "
        "32 built-in tools, LSP/DAP ops, and Rust core"
    )
    assert classify_intent(brief) == "repo-intake"


def test_repo_intake_template_is_read_only_before_build():
    template = get_adw_template("repo-intake")
    assert template["name"] == "External Repo Intake"
    assert "CLONE-READONLY" in template["instructions"]
    assert "do not code yet" in template["instructions"]


def test_explicit_repo_build_still_routes_to_repo_intake():
    brief = "build an integration using https://github.com/example/tool.git"
    assert classify_intent(brief) == "repo-intake"


def test_ship_it_routes_to_launch_prefight():
    assert classify_intent("ship it when this is ready") == "ship-it"


def test_hotfix_beats_bug_keywords():
    assert classify_intent("urgent fix production down error") == "hotfix"


def test_bug_beats_feature_keywords():
    assert classify_intent("fix broken provider registry feature") == "bug"


def test_video_beats_generic_feature_keywords():
    assert classify_intent("create a linkedin video for release") == "video"


def test_repo_related_words_without_url_route_to_repo_intake():
    assert classify_intent("look at this repo and tell me if useful") == "repo-intake"


def test_repo_url_beats_all_build_action_words():
    assert classify_intent("implement and vendor https://github.com/example/tool.git now") == "repo-intake"


def test_repo_intake_loads_build_method_router_first():
    names = _skill_names("repo-intake")
    assert names[:3] == ["build-method-router", "launch-project-audit", "senior-engineer-workflow"]


def test_feature_loads_router_before_senior_engineer_workflow():
    names = _skill_names("feature")
    assert names[0] == "build-method-router"
    assert names[1] == "senior-engineer-workflow"
