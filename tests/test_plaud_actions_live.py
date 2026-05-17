"""Live integration test — calls REAL Anthropic + REAL Linear. Opt-in via
RUN_PLAUD_LIVE=1. Requires ANTHROPIC_API_KEY + LINEAR_API_KEY +
PLAUD_LIVE_TEST_PROJECT_ID env vars to be set. Files ONE ticket to the
designated test project; ticket is NOT archived (no archive support in
linear_helpers); user clears it periodically.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import plaud_actions


def _load_env(path: Path) -> dict:
    env: dict = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip("'\"")
    return env


TEST_PAGE = """---
type: plaud-recording
plaud_id: live-test
duration_human: 1m00s
---

# Live test recording — please ignore

Quick note: Sarah from RestoreAssist needs the new compliance UI by next
Tuesday. Also, send John the IICRC content draft.
"""


@pytest.mark.skipif(os.environ.get("RUN_PLAUD_LIVE") != "1",
                    reason="set RUN_PLAUD_LIVE=1 to run live Anthropic + Linear test")
def test_live_extract_and_file_one_ticket(tmp_path):
    env = _load_env(Path.home() / ".hermes" / ".env")
    anthropic_key = env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    linear_key = env.get("LINEAR_API_KEY") or os.environ.get("LINEAR_API_KEY")
    test_project_id = env.get("PLAUD_LIVE_TEST_PROJECT_ID") or os.environ.get("PLAUD_LIVE_TEST_PROJECT_ID")

    assert anthropic_key, "ANTHROPIC_API_KEY not in ~/.hermes/.env"
    assert linear_key, "LINEAR_API_KEY not in ~/.hermes/.env"
    assert test_project_id, (
        "PLAUD_LIVE_TEST_PROJECT_ID not set. Create a 'Plaud Actions Test' "
        "project in Linear, paste its UUID into ~/.hermes/.env."
    )

    # Step 1 — Anthropic extraction (real API call)
    ex = plaud_actions.extract_actions(page_md=TEST_PAGE, anthropic_api_key=anthropic_key)
    assert isinstance(ex, plaud_actions.ActionExtraction), \
        f"expected ActionExtraction, got {type(ex).__name__}"
    assert ex.portfolio in {"restoreassist", "carsi", "unknown", "pi-dev-ops"}, \
        f"unexpected portfolio: {ex.portfolio}"
    assert 0.0 <= ex.confidence <= 1.0
    assert len(ex.actions) >= 1, "expected at least one action from the test page"

    # Step 2 — File ONE Linear ticket (real API call)
    from linear_helpers import create_linear_issue
    ref = create_linear_issue(
        api_key=linear_key,
        title=f"[live-test] {ex.actions[0].title}",
        description=f"{ex.actions[0].description}\n\n---\n_Created by plaud-actions live test._",
        team_id="a8a52f07-63cf-4ece-9ad2-3e3bd3c15673",  # RA team
        project_id=test_project_id,
        priority=4,  # Low — this is a test ticket
    )
    assert ref is not None, "Linear create_issue returned None — check key + project_id"
    assert ref.identifier
    print(f"\nCreated test ticket: {ref.identifier} ({ref.url})")
    print(f"REMINDER: delete this ticket manually in Linear when convenient.")
