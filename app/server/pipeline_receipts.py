"""Executable smoke receipts and best-effort delivery telemetry."""
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
log = logging.getLogger("pi-ceo.pipeline")

def run_smoke(smoke_script, session, test_results):
    server_url = os.environ.get("PI_CEO_URL", "http://127.0.0.1:7777")
    password = os.environ.get("TAO_PASSWORD", "")
    cmd = [sys.executable, str(smoke_script), "--url", server_url,
           "--expected-sha", session.candidate_sha, "--deployment-timeout", "60"]
    if password:
        cmd += ["--password", password]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        test_results["returncode"] = result.returncode
        test_results["raw_output"] = result.stdout[:2000]
        test_results["stderr"] = result.stderr[:2000]
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            # The checked-in smoke runner prints text and reports success via exit status.
            test_results["passed"] = result.returncode == 0
        else:
            test_results["passed"] = (
                result.returncode == 0 and isinstance(parsed, dict)
                and parsed.get("passed") is True
            )
    except subprocess.TimeoutExpired:
        test_results["error"] = "smoke_test.py timed out after 120s"
    except OSError as exc:
        test_results["error"] = f"smoke_test.py could not run: {exc}"



def success_receipt(pipeline_id, state, session, score, gate_checks, linear_ticket_updated):
    return {
        "shipped": True,
        "pipeline_id": pipeline_id,
        "idea": state.idea,
        "delivered_at": datetime.now(timezone.utc).isoformat(),
        "candidate_sha": session.candidate_sha,
        "session_id": state.session_id,
        "review_score": score,
        "gate_checks": gate_checks,
        "rollback_ref": f"git revert {session.candidate_sha}",
        "linear_ticket_updated": linear_ticket_updated,
        "post_ship_actions": [
            "Append pattern to .harness/lessons.jsonl",
        ],
    }


def record_shipped_feature(pipeline_id, state, score, linear_issue_id):
    # RA-689 — Record shipped feature for outcome feedback loop
    try:
        from .agents.feedback_loop import append_shipped_feature as _record_shipped
        _record_shipped(
            pipeline_id=pipeline_id,
            idea=state.idea or "",
            review_score=score,
            linear_ticket_id=linear_issue_id,
        )
    except Exception as _exc:
        log.warning("feedback_loop record failed (non-fatal): %s", _exc)


def log_gate(pipeline_id, session_id, gate_checks, score, shipped):
    try:
        from .supabase_log import log_gate_check
        log_gate_check(pipeline_id=pipeline_id, session_id=session_id,
                       gate_checks=gate_checks, review_score=score, shipped=shipped)
    except Exception as exc:
        log.warning("gate_check Supabase log failed (non-fatal): %s", exc)
