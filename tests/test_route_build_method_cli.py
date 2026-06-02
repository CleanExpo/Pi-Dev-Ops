from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from scripts.route_build_method import route_command  # noqa: E402


def test_route_command_repo_intake_metadata():
    route = route_command("https://github.com/can1357/oh-my-pi.git 40+ providers Rust core")
    assert route["route"] == "repo-intake"
    assert route["first_gate"] == "build-method-router"
    assert route["workflow"] == "External Repo Intake"
    assert "without code mutation" in route["verification"]


def test_route_command_feature_metadata():
    route = route_command("build a provider registry for Pi-Dev-Ops")
    assert route["route"] == "feature"
    assert route["skills"][:2] == ["build-method-router", "senior-engineer-workflow"]
    assert "workflow evidence" in route["next_action"]


def test_route_build_method_cli_json_output():
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/route_build_method.py",
            "--json",
            "https://github.com/can1357/oh-my-pi.git",
        ],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["route"] == "repo-intake"
    assert payload["first_gate"] == "build-method-router"


def test_route_build_method_cli_text_output():
    completed = subprocess.run(
        [sys.executable, "scripts/route_build_method.py", "ship it when ready"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert "Route: ship-it" in completed.stdout
    assert "Build method: Launch-readiness pre-flight" in completed.stdout


def test_build_router_import_is_side_effect_free():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, 'src'); import tao.build_router as br; print(br.classify_intent('build https://github.com/example/tool.git'))",
        ],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert completed.stdout.strip() == "repo-intake"
    assert completed.stderr == ""
