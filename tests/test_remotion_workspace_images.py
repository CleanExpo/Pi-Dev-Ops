from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOTION = ROOT / "remotion-studio"


def test_one_shot_accepts_image_provider_and_scene_assets(tmp_path):
    brief = {
        "brand": "synthex",
        "audience": "founders",
        "channel": "linkedin",
        "durationSec": 60,
        "goal": "explain agentic marketing with generated visuals",
        "cta": "Book a strategy call",
        "brief": "Synthex turns marketing ideas into shipped campaigns using agents.",
        "imageProvider": "nano-banana-2-pro",
        "imagePrompt": "premium editorial image of a marketing command centre",
        "imageAssets": [
            {
                "sceneId": "hook",
                "path": "assets/generated/test-hook.png",
                "alt": "Marketing control room",
                "prompt": "warm cinematic command centre",
            }
        ],
    }
    out_dir = tmp_path / "harness"

    result = subprocess.run(
        [
            "npx",
            "tsx",
            "render/one-shot.ts",
            f"--brief={json.dumps(brief)}",
            "--jobId=test-image-workspace",
            "--dryRun=true",
            f"--outDir={out_dir}",
        ],
        cwd=REMOTION,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    packet = json.loads((out_dir / "test-image-workspace" / "production-packet.json").read_text())
    assert packet["imagePolicy"]["provider"] == "nano-banana-2-pro"
    assert packet["imagePolicy"]["status"] == "dry-run"
    assert packet["props"]["storyboard"][0]["image"]["path"] == "assets/generated/test-hook.png"
    assert "nano-banana-2-pro" in (out_dir / "test-image-workspace" / "image-prompts.md").read_text()


def test_workspace_server_files_exist_and_port_is_3990():
    server = (REMOTION / "workspace" / "server.ts").read_text()
    html = (REMOTION / "workspace" / "public" / "index.html").read_text()
    client = (REMOTION / "workspace" / "public" / "app.js").read_text()
    package = json.loads((REMOTION / "package.json").read_text())

    assert "3990" in server
    assert "nano-banana-2-pro" in html
    assert "chatgpt" in html.lower()
    assert "UNITE_GROUP_API_URL" in html
    assert "Unite-Hub" not in html
    assert "/api/jobs" in server
    assert "EventSource" in client
    assert "AI assist" in html
    assert "projectMatrix" in client
    assert "/api/projects" in server
    assert "RestoreAssist" in client
    assert "Disaster Recovery" in client
    assert "NRPG" in client
    assert "CARSI" in client
    assert "CCW" in client
    assert "Synthex" in client
    assert "Unite Group" in client
    assert "7 projects connected" in html
    assert package["scripts"]["workspace"] == "tsx workspace/server.ts"
