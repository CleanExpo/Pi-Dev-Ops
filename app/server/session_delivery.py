"""Candidate-bound release checks shared by build phases."""
import datetime
import json
import logging
import time
import re
from . import persistence, workspace_verify
from .provider_policy import independent_identity

async def verify_candidate(session):
    """Record check failures, including runner errors, without inventing a pass."""
    session.verified_sha = ""
    try:
        result = await workspace_verify.run_workspace_checks(session.workspace)
    except Exception as exc:
        result = workspace_verify.VerifyResult(workspace_verify.NOT_RUN, "", f"Verification runner failed: {type(exc).__name__}", "")
    session.verification = {
        "status": result.status, "command": result.command,
        "reason": result.reason, "candidate_sha": getattr(session, "candidate_sha", ""),
    }
    if result.status == workspace_verify.PASSED:
        session.verified_sha = getattr(session, "candidate_sha", "")
    return result


async def release_gate(session, *, run_cmd, em) -> bool:
    """Deny delivery unless executable checks and required review cover this commit."""
    candidate = getattr(session, "candidate_sha", "")
    verification = getattr(session, "verification", {})
    adversary = getattr(session, "adversary_verdict", {})
    audits = getattr(session, "audit_evidence", [])
    reason = ""
    if not candidate or getattr(session, "verified_sha", "") != candidate:
        reason = "Missing verification for candidate commit"
    elif verification.get("status") != workspace_verify.PASSED or verification.get("candidate_sha") != candidate:
        reason = "Required workspace checks did not pass for candidate"
    elif session.evaluator_status != "passed":
        reason = f"Required evaluator did not approve: {session.evaluator_status}"
    elif len(audits) != 2 or not independent_identity(audits[0], audits[1]) or any(
        item.get("rc") != 0 or item.get("candidate_sha") != candidate
        for item in audits
    ):
        reason = "Required independent audit evidence is missing for candidate"
    elif adversary.get("verdict") not in {"APPROVE", "APPROVE_WITH_NOTES", "SKIP_DOCS_ONLY", "SKIP_NO_DIFF"} or adversary.get("candidate_sha") != candidate:
        reason = "Required adversary did not approve candidate"
    else:
        rc, head, _ = await run_cmd(session.workspace, "git", "rev-parse", "HEAD")
        status_rc, dirty, _ = await run_cmd(session.workspace, "git", "status", "--porcelain")
        if rc or status_rc or head.strip() != candidate or dirty.strip():
            reason = "Candidate changed after verification; rerun required checks"
    if reason:
        session.status = "blocked"
        session.error = reason
        em(session, "error", reason)
        persistence.save_session(session)
        return False
    return True


async def prepare_candidate(session, *, run_cmd, fail_phase) -> bool:
    """Freeze generated changes so every required check refers to one commit."""
    session.verified_sha = ""
    session.verification = {}
    session.audit_evidence = []
    session.adversary_verdict = {}
    rc, _, err = await run_cmd(session.workspace, "git", "add", "-A")
    if rc:
        fail_phase(session, f"Cannot stage candidate: {err[:200]}")
        return False
    rc, staged, err = await run_cmd(session.workspace, "git", "diff", "--cached", "--name-only")
    if rc:
        fail_phase(session, f"Cannot inspect candidate: {err[:200]}")
        return False
    if staged.strip():
        rc, _, err = await run_cmd(
            session.workspace, "git", "commit", "-m",
            "Preserve a verifiable candidate before release review\n\nConfidence: low\nTested: Pending required release checks",
        )
        if rc:
            fail_phase(session, f"Cannot commit candidate: {err[:200]}")
            return False
    rc, sha, err = await run_cmd(session.workspace, "git", "rev-parse", "HEAD")
    if rc or not re.fullmatch(r"[0-9a-f]{40,64}", sha.strip()):
        fail_phase(session, f"Cannot identify candidate: {err[:200]}")
        return False
    session.candidate_sha = sha.strip()
    persistence.save_session(session)
    return True



_log = logging.getLogger("pi-ceo.sessions")

def record_adversary(runs_dir, session, candidate, verdict, rc, cost, phase_start, files_changed, output_text):
    try:
        runs_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.date.today().isoformat()
        log_path = runs_dir / f"{today}.jsonl"
        with log_path.open("a") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "session_id": session.id,
                "verdict": verdict,
                "candidate_sha": candidate,
                "rc": rc,
                "cost_usd": cost,
                "duration_s": round(time.monotonic() - phase_start, 2),
                "files_changed": files_changed,
                "raw_output": output_text[:4000],
            }) + "\n")
    except Exception as exc:
        _log.warning("RA-1743 adversary log write failed: %s", exc)




async def record_base(session, resume_from, run_cmd, fail_phase):
    if not getattr(session, "base_sha", ""):
        if resume_from not in {"", "claude_check"}:
            fail_phase(session, "Cannot resume without a recorded base commit; start a new build")
            return False
        rc, base, _ = await run_cmd(session.workspace, "git", "rev-parse", "HEAD")
        if rc or not re.fullmatch(r"[0-9a-f]{40,64}", base.strip()):
            fail_phase(session, "Cannot identify base commit")
            return False
        session.base_sha = base.strip()
        persistence.save_session(session)
    return True
