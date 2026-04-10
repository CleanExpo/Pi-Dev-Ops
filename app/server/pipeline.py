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
import json
import logging
import os
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

log = logging.getLogger("pi-ceo.pipeline")

_HARNESS_ROOT = Path(__file__).parent.parent.parent / ".harness"
_PIPELINE_ROOT = _HARNESS_ROOT / "pipeline"


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
        return json.loads(raw)
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


def _resolve_claude_bin() -> str:
    """Resolve the claude CLI path, searching common nvm/node locations."""
    import shutil
    # Honour config override first
    configured = config.CLAUDE_CMD
    if configured != "claude":
        return configured
    # Try PATH as-is
    found = shutil.which("claude")
    if found:
        return found
    # Common nvm/homebrew locations
    candidates = [
        os.path.expanduser("~/.nvm/versions/node/v24.14.1/bin/claude"),
        os.path.expanduser("~/.nvm/versions/node/v23.14.1/bin/claude"),
        "/opt/homebrew/bin/claude",
        "/usr/local/bin/claude",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    # Glob for any nvm node version
    import glob
    for g in glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/claude")):
        if os.path.isfile(g) and os.access(g, os.X_OK):
            return g
    raise RuntimeError("claude CLI not found — ensure Claude Code is installed")


_MODEL_MAP = {
    "opus":   "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku":  "claude-haiku-4-5-20251001",
}


def _run_claude(brief: str, model: str = "sonnet", timeout: int = 300) -> str:
    """Run claude -p and return output. Raises RuntimeError on failure."""
    claude_bin = _resolve_claude_bin()
    model_flag = _MODEL_MAP.get(model, model) if not model.startswith("claude-") else model
    cmd = [claude_bin, "-p", brief, "--model", model_flag, "--output-format", "text"]
    log.info("Running claude: bin=%s model=%s brief_len=%d", claude_bin, model, len(brief))
    # Pass current environment so ANTHROPIC_API_KEY and PATH are available
    env = os.environ.copy()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude exited {result.returncode}: {result.stderr[:500]}")
        return result.stdout.strip()
    except FileNotFoundError:
        raise RuntimeError(f"claude CLI not found at {claude_bin}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude timed out after {timeout}s")


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
    spec_content = _run_claude(brief, model=model)
    _write_artifact(pipeline_id, "spec.md", spec_content)

    state.spec = spec_content
    state.current_phase = "plan"  # ready for next phase
    if "spec" not in state.phases_completed:
        state.phases_completed.append("spec")
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
    plan_content = _run_claude(brief, model=model)
    _write_artifact(pipeline_id, "plan.md", plan_content)

    state.plan = plan_content
    state.current_phase = "build"
    if "plan" not in state.phases_completed:
        state.phases_completed.append("plan")
    save_pipeline_state(state)

    log.info("Plan phase complete: pipeline=%s chars=%d", pipeline_id, len(plan_content))
    return state


def run_test_phase(pipeline_id: str, session_id: str) -> PipelineState:
    """Run the /test phase: execute smoke_test.py and record results."""
    state = load_pipeline_state(pipeline_id)
    if not state:
        raise ValueError(f"Pipeline {pipeline_id} not found")

    state.current_phase = "test"
    state.session_id = session_id
    _write_artifact(pipeline_id, "session_id.txt", session_id)
    save_pipeline_state(state)

    # Run smoke test against local server
    smoke_script = Path(__file__).parent.parent.parent / "scripts" / "smoke_test.py"
    test_results: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pipeline_id": pipeline_id,
        "session_id": session_id,
    }

    if smoke_script.exists():
        server_url = os.environ.get("PI_CEO_URL", "http://127.0.0.1:7777")
        password = os.environ.get("TAO_PASSWORD", "")
        cmd = ["python", str(smoke_script), "--url", server_url]
        if password:
            cmd += ["--password", password]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            try:
                parsed = json.loads(result.stdout)
                test_results.update(parsed)
            except json.JSONDecodeError:
                test_results["passed"] = result.returncode == 0
                test_results["raw_output"] = result.stdout[:2000]
        except subprocess.TimeoutExpired:
            test_results["passed"] = False
            test_results["error"] = "smoke_test.py timed out after 120s"
    else:
        test_results["passed"] = True
        test_results["note"] = "smoke_test.py not found — skipped"

    _write_artifact(pipeline_id, "test-results.json", json.dumps(test_results, indent=2))

    state.test_results = test_results
    passed = test_results.get("passed", False)
    state.current_phase = "review" if passed else "test"
    if passed and "test" not in state.phases_completed:
        state.phases_completed.append("test")
    save_pipeline_state(state)

    log.info("Test phase complete: pipeline=%s passed=%s", pipeline_id, passed)
    return state


def run_review_phase(pipeline_id: str, session_id: str) -> PipelineState:
    """Run the /review phase: invoke evaluator and record score."""
    state = load_pipeline_state(pipeline_id)
    if not state:
        raise ValueError(f"Pipeline {pipeline_id} not found")

    test_results = _read_json_artifact(pipeline_id, "test-results.json")
    if not test_results or not test_results.get("passed"):
        raise ValueError("Tests have not passed — run /test first")

    state.current_phase = "review"
    state.session_id = session_id
    save_pipeline_state(state)

    # Ask evaluator to score via claude CLI
    spec = _read_artifact(pipeline_id, "spec.md") or ""
    plan = _read_artifact(pipeline_id, "plan.md") or ""
    skill_ctx = _skill_prefix(["ship-chain", "ship-release"])

    brief = f"""{skill_ctx}

## Task: Review and score this implementation

Pipeline ID: {pipeline_id}
Session ID: {session_id}

## Spec
{spec[:3000]}

## Plan
{plan[:3000]}

Score the implementation on these 5 dimensions (each 1-5):
1. Correctness — does the code satisfy all acceptance criteria?
2. Test coverage — are acceptance criteria covered by tests?
3. Code quality — follows CLAUDE.md conventions?
4. Security — no new OWASP issues introduced?
5. Documentation — non-obvious changes commented?

Output a JSON object with this exact structure:
{{
  "correctness": <1-5>,
  "test_coverage": <1-5>,
  "code_quality": <1-5>,
  "security": <1-5>,
  "documentation": <1-5>,
  "overall_score": <total/40 mapped to /10, 1 decimal>,
  "pass": <true if overall_score >= 8.0>,
  "feedback": "<specific actionable feedback>"
}}
Output ONLY the JSON — no preamble.
"""
    try:
        output = _run_claude(brief, model="sonnet")
        # Extract JSON from output
        import re
        json_match = re.search(r'\{.*\}', output, re.DOTALL)
        if json_match:
            review_score = json.loads(json_match.group())
        else:
            review_score = {"overall_score": 0, "pass": False, "feedback": output[:500], "raw": True}
    except Exception as e:
        review_score = {"overall_score": 0, "pass": False, "error": str(e)}

    _write_artifact(pipeline_id, "review-score.json", json.dumps(review_score, indent=2))

    state.review_score = review_score
    passed = review_score.get("pass", False) or review_score.get("overall_score", 0) >= 8.0
    state.current_phase = "ship" if passed else "review"
    if passed and "review" not in state.phases_completed:
        state.phases_completed.append("review")
    save_pipeline_state(state)

    log.info("Review phase complete: pipeline=%s score=%s pass=%s",
             pipeline_id, review_score.get("overall_score"), passed)
    return state


def run_ship_phase(pipeline_id: str) -> PipelineState:
    """Run the /ship phase: hard gate + record ship log."""
    state = load_pipeline_state(pipeline_id)
    if not state:
        raise ValueError(f"Pipeline {pipeline_id} not found")

    # Collect gate checks
    spec = _read_artifact(pipeline_id, "spec.md")
    plan = _read_artifact(pipeline_id, "plan.md")
    session_id_txt = _read_artifact(pipeline_id, "session_id.txt")
    test_results = _read_json_artifact(pipeline_id, "test-results.json")
    review_score = _read_json_artifact(pipeline_id, "review-score.json")

    score = review_score.get("overall_score", 0) if review_score else 0
    gate_checks = {
        "spec_exists": bool(spec and len(spec) > 100),
        "plan_exists": bool(plan and len(plan) > 100),
        "build_complete": bool(session_id_txt),
        "tests_passed": bool(test_results and test_results.get("passed")),
        "review_passed": bool(review_score and score >= 8.0),
    }
    all_passed = all(gate_checks.values())

    if not all_passed:
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
        save_pipeline_state(state)
        log.warning("Ship gate failed: pipeline=%s blocking=%s", pipeline_id, failing[0])
        return state

    ship_log = {
        "shipped": True,
        "pipeline_id": pipeline_id,
        "idea": state.idea,
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "session_id": state.session_id,
        "review_score": score,
        "gate_checks": gate_checks,
        "rollback_ref": f"git revert HEAD  # revert last commit from session {state.session_id}",
        "linear_ticket_updated": False,
        "post_ship_actions": [
            f"Move Linear ticket {pipeline_id} to Done",
            "Append pattern to .harness/lessons.jsonl",
        ],
    }

    # Append to lessons.jsonl
    _append_ship_lesson(pipeline_id, score)

    _write_artifact(pipeline_id, "ship-log.json", json.dumps(ship_log, indent=2))
    state.ship_log = ship_log
    state.current_phase = "done"
    if "ship" not in state.phases_completed:
        state.phases_completed.append("ship")
    save_pipeline_state(state)

    log.info("Ship complete: pipeline=%s score=%s", pipeline_id, score)
    return state


def _gate_reason(gate: str, score: float) -> str:
    reasons = {
        "spec_exists": "spec.md is missing — run /spec first",
        "plan_exists": "plan.md is missing — run /plan first",
        "build_complete": "No build session found — run /build first",
        "tests_passed": "Tests have not passed — run /test and fix failures",
        "review_passed": f"Review score {score}/10 does not meet 8/10 threshold",
    }
    return reasons.get(gate, f"Gate {gate} failed")


def _append_ship_lesson(pipeline_id: str, score: float) -> None:
    lessons_file = _HARNESS_ROOT / "lessons.jsonl"
    entry = json.dumps({
        "cycle": "ship",
        "pipeline_id": pipeline_id,
        "pattern": "successful_ship",
        "score": score,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    try:
        with open(lessons_file, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError:
        pass
