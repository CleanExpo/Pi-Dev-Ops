"""
pipeline.py — Ship Chain pipeline state management.

Tracks the 6-phase /spec → /plan → /build → /test → /review → /ship lifecycle.
Artifacts are persisted to .harness/pipeline/{pipeline_id}/.

Phase artifacts:
  spec.md            — /spec output
  plan.md            — /plan output
  session_id.txt     — /build output (links to sessions.py session)
  test-results.json  — /test output
  review-score.json  — /review output (from sessions.py evaluator)
  ship-log.json      — /ship output
  state.json         — full PipelineState (this module)
"""
from __future__ import annotations

import asyncio
from . import pipeline_receipts
import json
import logging
import math
import subprocess  # noqa: F401 - retained public process test seam
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("pi-ceo.pipeline")

_HARNESS_ROOT = Path(__file__).parent.parent.parent / ".harness"

# ── Linear sync helper (pipeline) ─────────────────────────────────────────────

_LINEAR_ISSUE_RE = re.compile(r"^[A-Z]+-\d+$")


def _linear_issue_id_from_pipeline(pipeline_id: str) -> str | None:
    """Return the Linear issue ID if pipeline_id looks like 'RA-XXX', else None."""
    if _LINEAR_ISSUE_RE.match(pipeline_id or ""):
        return pipeline_id
    return None


def _update_linear_state_pipeline(issue_id: str, state_name: str) -> bool:
    from .pipeline_linear import update_state
    return update_state(issue_id, state_name)


_PIPELINE_ROOT = _HARNESS_ROOT / "pipeline"
_PHASE_LOCKS: dict[str, threading.Lock] = {}
_PHASE_LOCKS_GUARD = threading.Lock()


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class PipelineState:
    pipeline_id: str
    idea: str
    repo_url: str
    current_phase: str  # spec | plan | build | test | review | ship | done
    phases_completed: list[str] = field(default_factory=list)
    spec: str | None = None
    plan: str | None = None
    session_id: str | None = None
    test_results: dict[str, Any] | None = None
    review_score: dict[str, Any] | None = None
    ship_log: dict[str, Any] | None = None
    generated_config: dict | None = None  # RA-691: auto-generated harness config
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Directory helpers ─────────────────────────────────────────────────────────

def get_pipeline_dir(pipeline_id: str) -> Path:
    return _PIPELINE_ROOT / pipeline_id


def _ensure_pipeline_dir(pipeline_id: str) -> Path:
    d = get_pipeline_dir(pipeline_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── State persistence ─────────────────────────────────────────────────────────

def save_pipeline_state(state: PipelineState) -> None:
    state.updated_at = datetime.now(timezone.utc).isoformat()
    d = _ensure_pipeline_dir(state.pipeline_id)
    tmp = d / "state.json.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(asdict(state), f, indent=2)
    os.replace(tmp, d / "state.json")


def load_pipeline_state(pipeline_id: str) -> PipelineState | None:
    state_file = get_pipeline_dir(pipeline_id) / "state.json"
    if not state_file.exists():
        return None
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PipelineState(**data)
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def list_pipelines() -> list[dict[str, Any]]:
    """Return summary of all pipeline states."""
    if not _PIPELINE_ROOT.exists():
        return []
    results = []
    for entry in sorted(_PIPELINE_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        state = load_pipeline_state(entry.name)
        if state:
            results.append({
                "pipeline_id": state.pipeline_id,
                "idea": state.idea[:80],
                "current_phase": state.current_phase,
                "phases_completed": state.phases_completed,
                "updated_at": state.updated_at,
            })
    return results


# ── Artifact helpers ──────────────────────────────────────────────────────────

def _write_artifact(pipeline_id: str, filename: str, content: str) -> None:
    d = _ensure_pipeline_dir(pipeline_id)
    tmp = d / (filename + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, d / filename)


def _read_artifact(pipeline_id: str, filename: str) -> str | None:
    p = get_pipeline_dir(pipeline_id) / filename
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def _read_json_artifact(pipeline_id: str, filename: str) -> dict | None:
    raw = _read_artifact(pipeline_id, filename)
    if raw is None:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


# ── Claude subprocess invocation ──────────────────────────────────────────────

def _skill_prefix(skill_names: list[str]) -> str:
    """Build a skill context preamble from loaded skills."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from src.tao.skills import get_skill
        parts = []
        for name in skill_names:
            sk = get_skill(name)
            if sk:
                parts.append(f"## Skill: {sk['name']}\n{sk['body']}")
        return "\n\n".join(parts)
    except Exception:
        return ""


# RA-1094B — _resolve_claude_bin / _run_claude_subprocess removed.
# The Agent SDK is the only execution path (SDK-only mandate, RA-576).


def _pipeline_transport_block():
    from .provider_policy import ProviderPolicyError, require_transport
    try:
        require_transport("anthropic_agent_sdk")
    except ProviderPolicyError as exc:
        log.warning("Pipeline model execution blocked: %s", exc)
        return str(exc)
    return ""


def _pipeline_sdk_options(option_type, model):
    from .session_sdk import _child_environment
    return option_type(model=model, tools=[], permission_mode="default",
                       setting_sources=[], strict_mcp_config=True, env=_child_environment())


async def _run_claude_via_sdk_async(
    prompt: str,
    model: str = "sonnet",
    timeout: int = 300,
    phase: str = "",
) -> tuple[bool, str]:
    """Run Claude via agent SDK (text-only, no file writes).

    Returns (success, output_text). On any import/runtime error returns (False, "").
    Emits one row to .harness/agent-sdk-metrics/ on every invocation.
    """
    blocked = _pipeline_transport_block()
    if blocked:
        return False, blocked
    try:
        from claude_agent_sdk import (  # noqa: PLC0415
            AssistantMessage,
            ClaudeAgentOptions,
            ClaudeSDKClient,
            ResultMessage,
            TextBlock,
        )
    except ImportError:
        log.debug("claude_agent_sdk not available — falling back to subprocess")
        return (False, "")

    t0 = time.monotonic()
    error_msg: Optional[str] = None
    output_text = ""
    try:
        options = _pipeline_sdk_options(ClaudeAgentOptions, model)
        client = ClaudeSDKClient(options)
        text_parts: list[str] = []
        try:
            await client.connect()
            await client.query(prompt)
            async for msg in client.receive_messages():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
                elif isinstance(msg, ResultMessage):
                    break
        finally:
            await client.disconnect()
        output_text = "\n".join(text_parts)
        _write_pipeline_sdk_metric(phase=phase, model=model, success=True,
                                   latency_s=time.monotonic() - t0, output_len=len(output_text))
        return (True, output_text)

    except asyncio.TimeoutError:
        error_msg = f"timeout after {timeout}s"
        log.warning("SDK pipeline timed out after %ds (phase=%s)", timeout, phase)
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        log.warning("SDK pipeline failed: %s (phase=%s)", exc, phase)

    _write_pipeline_sdk_metric(phase=phase, model=model, success=False,
                               latency_s=time.monotonic() - t0, output_len=0,
                               error=error_msg)
    return (False, "")


def _write_pipeline_sdk_metric(
    *,
    phase: str,
    model: str,
    success: bool,
    latency_s: float,
    output_len: int,
    error: Optional[str] = None,
) -> None:
    """Append one pipeline SDK metric row to .harness/agent-sdk-metrics/."""
    import datetime as _dt  # local import to avoid name clash with module-level datetime
    try:
        metrics_dir = Path(__file__).parent.parent.parent / ".harness" / "agent-sdk-metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        today = _dt.date.today().isoformat()
        row = json.dumps({
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "session_id": "",
            "phase": f"pipeline.{phase}",
            "model": model,
            "sdk_enabled": True,
            "success": success,
            "latency_s": round(latency_s, 3),
            "output_len": output_len,
            "error": error,
        })
        with open(metrics_dir / f"{today}.jsonl", "a") as fh:
            fh.write(row + "\n")
    except Exception:
        pass  # metrics must never break the pipeline


def _run_claude(brief: str, model: str = "sonnet", timeout: int = 300, phase: str = "") -> str:
    """Run Claude via the Agent SDK and return output. Raises RuntimeError on failure.

    SDK-only path since RA-576 / RA-1094B.
    """
    try:
        success, output = asyncio.run(
            _run_claude_via_sdk_async(brief, model=model, timeout=timeout, phase=phase)
        )
    except Exception as exc:
        raise RuntimeError(f"Agent SDK call failed for phase={phase}: {exc}") from exc
    if not success:
        raise RuntimeError(f"Agent SDK returned failure for phase={phase}: {output[:500]}")
    if not output.strip():
        raise RuntimeError(f"Agent SDK returned empty output for phase={phase}")
    log.info("Pipeline SDK call succeeded: phase=%s model=%s chars=%d",
             phase, model, len(output))
    return output


# ── Phase implementations ─────────────────────────────────────────────────────

def run_spec_phase(
    idea: str,
    repo_url: str,
    pipeline_id: str | None = None,
    model: str = "sonnet",
) -> PipelineState:
    """Run the /spec phase: produce spec.md from raw idea."""
    if not pipeline_id:
        pipeline_id = uuid.uuid4().hex[:8]

    state = load_pipeline_state(pipeline_id) or PipelineState(
        pipeline_id=pipeline_id,
        idea=idea,
        repo_url=repo_url,
        current_phase="spec",
    )
    state.current_phase = "spec"
    save_pipeline_state(state)

    skill_ctx = _skill_prefix(["ship-chain", "define-spec"])
    brief = f"""{skill_ctx}

---
TASK: Write a specification document. Return ONLY raw markdown. No file writes. No explanations. No preamble. Start your response with "# Spec:" on the first line.

Pipeline: {pipeline_id}
Repo: {repo_url}
Idea: {idea}

Use the define-spec skill format (Summary, Goals, Non-Goals, Acceptance Criteria, Constraints, Out of Scope).
"""
    spec_content = _run_claude(brief, model=model, phase="spec")
    _write_artifact(pipeline_id, "spec.md", spec_content)

    state.spec = spec_content
    state.current_phase = "plan"  # ready for next phase
    if "spec" not in state.phases_completed:
        state.phases_completed.append("spec")

    # RA-691 — auto-generate harness config for new projects (non-fatal)
    try:
        from .agents.auto_generator import generate_project_config, config_to_yaml  # noqa: PLC0415
        cfg = generate_project_config(repo_url=repo_url, brief=idea)
        state.generated_config = cfg
        _write_artifact(pipeline_id, "config.yaml", config_to_yaml(cfg))
        log.info(
            "auto_generator: config written pipeline=%s tier=%s",
            pipeline_id, cfg.get("complexity_tier", "?"),
        )
    except Exception as _exc:
        log.warning("auto_generator failed (non-fatal): %s", _exc)

    save_pipeline_state(state)

    log.info("Spec phase complete: pipeline=%s chars=%d", pipeline_id, len(spec_content))
    return state


def run_plan_phase(pipeline_id: str, model: str = "sonnet") -> PipelineState:
    """Run the /plan phase: produce plan.md from spec.md."""
    state = load_pipeline_state(pipeline_id)
    if not state:
        raise ValueError(f"Pipeline {pipeline_id} not found")

    spec = _read_artifact(pipeline_id, "spec.md")
    if not spec or len(spec) < 200:
        raise ValueError("spec.md is missing or too short — run /spec first")

    state.current_phase = "plan"
    save_pipeline_state(state)

    skill_ctx = _skill_prefix(["ship-chain", "technical-plan"])
    brief = f"""{skill_ctx}

---
TASK: Write a technical implementation plan. Return ONLY raw markdown. No file writes. No explanations. No preamble. Start your response with "# Plan:" on the first line.

Pipeline: {pipeline_id}
Repo: {state.repo_url}

## Spec
{spec}

Use the technical-plan skill format (Approach, Files Changed, Effort, Dependencies, Risks, Test Plan).
"""
    plan_content = _run_claude(brief, model=model, phase="plan")
    _write_artifact(pipeline_id, "plan.md", plan_content)

    state.plan = plan_content
    state.current_phase = "build"
    if "plan" not in state.phases_completed:
        state.phases_completed.append("plan")
    save_pipeline_state(state)

    log.info("Plan phase complete: pipeline=%s chars=%d", pipeline_id, len(plan_content))
    return state


def _delivered_session(state: PipelineState, session_id: str):
    """Resolve delivery from the build lifecycle, never from a text artifact alone."""
    from .session_model import get_session

    session = get_session(session_id)
    if (
        session is None
        or session.repo_url != state.repo_url
        or session.status != "complete"
        or session.last_completed_phase != "push"
        or not isinstance(session.candidate_sha, str)
        or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", session.candidate_sha)
    ):
        return None
    return session


def _matches_candidate(evidence: dict | None, state: PipelineState, session) -> bool:
    return bool(
        evidence and session
        and evidence.get("pipeline_id") == state.pipeline_id
        and evidence.get("session_id") == session.id
        and evidence.get("candidate_sha") == session.candidate_sha
    )


def _review_passed(evidence: dict | None) -> bool:
    score = evidence.get("overall_score") if evidence else None
    return bool(
        evidence and evidence.get("pass") is True
        and type(score) in (int, float) and math.isfinite(score) and 8 <= score <= 10
    )


def _pipeline_lock(pipeline_id: str):
    with _PHASE_LOCKS_GUARD:
        return _PHASE_LOCKS.setdefault(pipeline_id, threading.Lock())


def run_test_phase(pipeline_id: str, session_id: str) -> PipelineState:
    """Serialize retest invalidation with review and shipping for this pipeline."""
    with _pipeline_lock(pipeline_id):
        return _run_test_phase(pipeline_id, session_id)


def _run_test_phase(pipeline_id: str, session_id: str) -> PipelineState:
    state = load_pipeline_state(pipeline_id)
    if not state:
        raise ValueError(f"Pipeline {pipeline_id} not found")

    session = _delivered_session(state, session_id)
    state.current_phase = "test"
    state.session_id = session_id
    state.review_score = None
    state.ship_log = None
    state.phases_completed = [p for p in state.phases_completed if p not in {"test", "review", "ship"}]
    _write_artifact(pipeline_id, "session_id.txt", session_id)
    _write_artifact(pipeline_id, "review-score.json", "{}")
    _write_artifact(pipeline_id, "ship-log.json", '{"shipped": false}')
    save_pipeline_state(state)

    smoke_script = Path(__file__).parent.parent.parent / "scripts" / "smoke_test.py"
    test_results: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pipeline_id": pipeline_id,
        "session_id": session_id,
        "candidate_sha": session.candidate_sha if session else "",
        "passed": False,
    }
    if session is None:
        test_results["error"] = "No completed, delivered build session for this pipeline"
    elif not smoke_script.is_file():
        test_results["error"] = "smoke_test.py not found; required tests were not run"
    else:
        pipeline_receipts.run_smoke(smoke_script, session, test_results)

    _write_artifact(pipeline_id, "test-results.json", json.dumps(test_results, indent=2))
    state.test_results = test_results
    passed = test_results["passed"]
    state.current_phase = "review" if passed else "test"
    if passed:
        state.phases_completed.append("test")
    save_pipeline_state(state)
    log.info("Test phase complete: pipeline=%s passed=%s", pipeline_id, passed)
    return state


def run_review_phase(pipeline_id: str, session_id: str) -> PipelineState:
    """Serialize review evidence updates with retesting and shipping."""
    with _pipeline_lock(pipeline_id):
        return _run_review_phase(pipeline_id, session_id)


def _candidate_release_approved(session):
    from .session_phases import _release_gate
    try:
        return asyncio.run(_release_gate(session))
    except Exception as exc:
        log.warning("Required pipeline release check failed: %s", exc)
        return False


def _run_review_phase(pipeline_id: str, session_id: str) -> PipelineState:
    """Record the build's required review; a prompt-only score is not release evidence."""
    from .persistence import release_evidence
    state = load_pipeline_state(pipeline_id)
    if not state:
        raise ValueError(f"Pipeline {pipeline_id} not found")
    session = _delivered_session(state, session_id)
    test_results = _read_json_artifact(pipeline_id, "test-results.json")
    if (
        state.session_id != session_id
        or not _matches_candidate(test_results, state, session)
        or test_results.get("passed") is not True
    ):
        raise ValueError("Tests have not passed for this delivered candidate; run /test first")

    approved = _candidate_release_approved(session)
    review_score = {
        "pipeline_id": pipeline_id,
        "session_id": session_id,
        **release_evidence(session),
        "overall_score": session.evaluator_score,
        "pass": approved,
        "feedback": session.error or "Required build review evidence recorded",
    }
    review_score["pass"] = _review_passed(review_score)
    _write_artifact(pipeline_id, "review-score.json", json.dumps(review_score, indent=2))
    _write_artifact(pipeline_id, "ship-log.json", '{"shipped": false}')
    state.review_score = review_score
    state.ship_log = None
    state.phases_completed = [p for p in state.phases_completed if p not in {"review", "ship"}]
    state.current_phase = "ship" if review_score["pass"] else "review"
    if review_score["pass"]:
        state.phases_completed.append("review")
    save_pipeline_state(state)
    log.info("Review phase complete: pipeline=%s score=%s pass=%s",
             pipeline_id, review_score.get("overall_score"), review_score["pass"])
    return state


def run_ship_phase(pipeline_id: str) -> PipelineState:
    """Serialize delivery receipts and their external effects for each pipeline."""
    with _pipeline_lock(pipeline_id):
        return _run_ship_phase(pipeline_id)


def _ship_checks(state, pipeline_id):
    # Collect gate checks
    spec = _read_artifact(pipeline_id, "spec.md")
    plan = _read_artifact(pipeline_id, "plan.md")
    session_id_txt = _read_artifact(pipeline_id, "session_id.txt")
    test_results = _read_json_artifact(pipeline_id, "test-results.json")
    review_score = _read_json_artifact(pipeline_id, "review-score.json")

    from .session_phases import _release_gate

    session_id = (session_id_txt or "").strip()
    session = _delivered_session(state, session_id) if state.session_id == session_id else None
    score = review_score.get("overall_score", 0) if review_score else 0
    gate_checks = {
        "spec_exists": bool(spec and len(spec) > 100),
        "plan_exists": bool(plan and len(plan) > 100),
        "build_complete": session is not None,
        "tests_passed": bool(
            _matches_candidate(test_results, state, session) and test_results.get("passed") is True
        ),
        "review_passed": bool(
            _matches_candidate(review_score, state, session) and _review_passed(review_score)
            and _review_passed({"pass": session.evaluator_status == "passed", "overall_score": session.evaluator_score})
            and score == session.evaluator_score
        ),
        "release_evidence": False,
    }
    if session:
        try:
            gate_checks["release_evidence"] = asyncio.run(_release_gate(session))
        except Exception as exc:
            log.warning("Required pipeline release check failed: %s", exc)
    return session, score, gate_checks



def _ship_denied(state, pipeline_id, gate_checks, score):
    failing = [k for k, v in gate_checks.items() if not v]
    ship_log: dict[str, Any] = {
        "shipped": False,
        "pipeline_id": pipeline_id,
        "gate_checks": gate_checks,
        "blocking_gate": failing[0],
        "blocking_reason": _gate_reason(failing[0], score),
    }
    _write_artifact(pipeline_id, "ship-log.json", json.dumps(ship_log, indent=2))
    state.ship_log = ship_log
    state.current_phase = "ship"
    state.phases_completed = [p for p in state.phases_completed if p != "ship"]
    save_pipeline_state(state)
    log.warning("Ship gate failed: pipeline=%s blocking=%s", pipeline_id, failing[0])
    pipeline_receipts.log_gate(pipeline_id, state.session_id, gate_checks, score, False)
    return state


def _save_shipped_receipt(state, pipeline_id, ship_log):
    _write_artifact(pipeline_id, "ship-log.json", json.dumps(ship_log, indent=2))
    state.ship_log = ship_log
    state.current_phase = "done"
    if "ship" not in state.phases_completed:
        state.phases_completed.append("ship")
    save_pipeline_state(state)



def _run_ship_phase(pipeline_id: str) -> PipelineState:
    """Run the /ship phase: hard gate + record ship log."""
    state = load_pipeline_state(pipeline_id)
    if not state:
        raise ValueError(f"Pipeline {pipeline_id} not found")

    session, score, gate_checks = _ship_checks(state, pipeline_id)

    if not all(gate_checks.values()):
        return _ship_denied(state, pipeline_id, gate_checks, score)

    # Revalidate on retries, but do not repeat external effects for this receipt.
    if (
        state.ship_log and state.ship_log.get("shipped") is True
        and _matches_candidate(state.ship_log, state, session)
    ):
        return state

    # A pushed candidate awaits review; no merge or deployment has been established.
    linear_issue_id = _linear_issue_id_from_pipeline(pipeline_id)
    linear_ticket_updated = False
    if linear_issue_id:
        log.info("Ship: updating Linear issue %s to In Review", linear_issue_id)
        linear_ticket_updated = _update_linear_state_pipeline(linear_issue_id, "In Review")

    ship_log = pipeline_receipts.success_receipt(pipeline_id, state, session, score, gate_checks, linear_ticket_updated)

    # Append to lessons.jsonl
    _append_ship_lesson(pipeline_id, score)

    pipeline_receipts.record_shipped_feature(pipeline_id, state, score, linear_issue_id)

    _save_shipped_receipt(state, pipeline_id, ship_log)

    pipeline_receipts.log_gate(pipeline_id, state.session_id, gate_checks, score, True)

    log.info("Ship complete: pipeline=%s score=%s linear_updated=%s", pipeline_id, score, linear_ticket_updated)
    return state


def _gate_reason(gate: str, score: float) -> str:
    reasons = {
        "spec_exists": "spec.md is missing — run /spec first",
        "plan_exists": "plan.md is missing — run /plan first",
        "build_complete": "No build session found — run /build first",
        "tests_passed": "Tests have not passed — run /test and fix failures",
        "review_passed": f"Review score {score}/10 lacks matching required candidate approval",
        "release_evidence": "Required release evidence is missing or the candidate changed",
    }
    return reasons.get(gate, f"Gate {gate} failed")


def _append_ship_lesson(pipeline_id: str, score: float) -> None:
    # Seed before appending. This writer creates the store if it is absent, and an existing
    # store suppresses seeding for good, so appending first would silently cost the 49
    # curated lessons on a clean clone.
    from .lessons import ensure_seeded  # noqa: PLC0415 — local, avoids an import cycle
    ensure_seeded()
    # Append to the SAME path the seeder installs. config.LESSONS_FILE honours the
    # TAO_LESSONS override; a hardcoded _HARNESS_ROOT path here appended to a different
    # file from the seeded one under an override deployment, splitting the store.
    from . import config  # noqa: PLC0415 — local, mirrors the lessons import above
    lessons_file = config.LESSONS_FILE
    entry = {
        "cycle": "ship",
        "pipeline_id": pipeline_id,
        "pattern": "successful_ship",
        "score": score,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(lessons_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        return
    # RA-7111: durable copy — this writer bypasses lessons.append_lesson, so it
    # writes through explicitly. Local append above already succeeded.
    from .lessons import record_external_append  # noqa: PLC0415
    record_external_append(entry)
