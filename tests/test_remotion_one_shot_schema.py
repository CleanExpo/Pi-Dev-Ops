from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOTION = ROOT / "remotion-studio"


def test_one_shot_brief_schema_defines_required_fields():
    text = (REMOTION / "render" / "brief-schema.ts").read_text()

    for token in [
        "brand",
        "audience",
        "channel",
        "durationSec",
        "goal",
        "cta",
        "voiceProfile",
        "renderMode",
        "RemotionOneShotBrief",
    ]:
        assert token in text


def test_one_shot_dry_run_generates_packet_without_tts(tmp_path):
    brief = {
        "brand": "synthex",
        "audience": "founders",
        "channel": "linkedin",
        "durationSec": 60,
        "goal": "explain agentic marketing",
        "cta": "Book a strategy call",
        "brief": "Synthex turns marketing ideas into shipped campaigns using agents.",
    }
    out_dir = tmp_path / "harness"

    result = subprocess.run(
        [
            "npx",
            "tsx",
            "render/one-shot.ts",
            f"--brief={json.dumps(brief)}",
            "--jobId=test-synthex-one-shot",
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
    job_dir = out_dir / "test-synthex-one-shot"
    packet = json.loads((job_dir / "production-packet.json").read_text())
    assert packet["voicePolicy"]["voiceCount"] == 1
    assert packet["voicePolicy"]["source"] == "Synthex"
    assert packet["composition"] == "Explainer"
    assert len(packet["props"]["storyboard"]) >= 5
    assert (job_dir / "script.md").exists()
    assert (job_dir / "preflight-report.md").exists()
    assert (job_dir / "render-command.sh").exists()
    assert "ELEVENLABS_API_KEY" not in result.stdout
