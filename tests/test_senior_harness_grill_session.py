from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "skills" / "senior-harness" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from grill_session import (  # noqa: E402
    EVIDENCE_RESOLUTION,
    SHARED_UNDERSTANDING_PHRASE,
    GrillSessionError,
    answer_pending_evidence,
    answer_pending_question,
    confirm_shared_understanding,
    digest,
    start_session,
    validate_receipt,
    validate_session,
)


@pytest.fixture
def sketch(tmp_path: Path) -> Path:
    path = tmp_path / "2nd-brain" / "Sketches" / "07-routing.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Routing sketch\n\nTBD: provider\n", encoding="utf-8")
    return path


def _target(sketch: Path) -> Path:
    return sketch.parent.parent / "Grills" / "07-routing.md"


def _tree() -> list[dict]:
    # Deliberately out of dependency order: intake must stable-topologically order it.
    return [
        {
            "leaf_id": "delivery-mode",
            "kind": "human-decision",
            "depends_on": ["provider-exists"],
            "question": "Should the existing provider remain the default?",
            "recommendation": "Keep the existing provider.",
            "rationale": "It preserves the current integration seam.",
        },
        {
            "leaf_id": "provider-exists",
            "kind": "evidence-fact",
            "depends_on": [],
            "question": "Which provider is configured in the repository?",
        },
        {
            "leaf_id": "fallback",
            "kind": "human-decision",
            "depends_on": ["delivery-mode"],
            "question": "Should fallback be in scope?",
            "recommendation": "Exclude fallback from this slice.",
            "rationale": "It keeps the first delivery reversible and bounded.",
        },
    ]


def test_binds_literal_objective_real_sketch_digest_and_explicit_grills_target(sketch: Path) -> None:
    objective = "  Resolve routing — exactly.  "
    session = start_session(objective, sketch, _tree(), materialization_path=_target(sketch))

    assert session["objective"] == objective
    assert session["sketch"]["path"] == str(sketch.resolve())
    assert session["sketch"]["sha256"].startswith("sha256:")
    assert session["materialization"]["path"] == str(_target(sketch).resolve())
    assert session["materialization"]["content"] is None
    assert [leaf["leaf_id"] for leaf in session["decision_tree"]] == [
        "provider-exists",
        "delivery-mode",
        "fallback",
    ]
    assert session["state"] == "awaiting-evidence"
    assert session["pending_question"] is None
    assert session["pending_evidence"]["leaf_id"] == "provider-exists"
    validate_session(session)


def test_evidence_fact_is_not_asked_as_human_decision_and_only_one_question_is_pending(sketch: Path) -> None:
    original = start_session("Resolve routing", sketch, _tree(), materialization_path=_target(sketch))
    source_sha = digest({"source": "provider_router.py"})
    session = answer_pending_evidence(
        original,
        "The repository configures qwen.",
        [{"source_id": "provider_router.py", "source_digest": source_sha}],
    )

    assert original["state"] == "awaiting-evidence"  # transitions are immutable
    assert session["decision_tree"][0]["status"] == EVIDENCE_RESOLUTION
    assert session["state"] == "interviewing"
    assert session["pending_evidence"] is None
    assert session["pending_question"] == {
        "leaf_id": "delivery-mode",
        "question": "Should the existing provider remain the default?",
        "recommendation": "Keep the existing provider.",
        "rationale": "It preserves the current integration seam.",
    }


def test_answers_are_verbatim_and_terminal_labels_are_exact(sketch: Path) -> None:
    session = start_session("Resolve routing", sketch, _tree(), materialization_path=_target(sketch))
    session = answer_pending_evidence(
        session,
        "qwen is configured",
        [{"source_id": "config", "source_digest": digest("config bytes")}],
    )
    verbatim = "  Yes — retain it exactly as written.  "
    session = answer_pending_question(session, verbatim, "DECIDED")

    assert session["buffer"]["transcript_entries"][1]["answer_verbatim"] == verbatim
    assert session["pending_question"]["leaf_id"] == "fallback"
    with pytest.raises(GrillSessionError, match="verbatim DECIDED"):
        answer_pending_question(session, "later", "rabbit hole")


def test_recommendation_and_rationale_are_mandatory(sketch: Path) -> None:
    missing = [{
        "leaf_id": "choice",
        "kind": "human-decision",
        "depends_on": [],
        "question": "Choose?",
        "recommendation": "",
        "rationale": "Because.",
    }]
    with pytest.raises(GrillSessionError, match="recommendation must be non-empty"):
        start_session("Resolve", sketch, missing, materialization_path=_target(sketch))


def test_dependency_cycle_unknown_parent_and_early_answer_fail_closed(sketch: Path) -> None:
    cycle = [
        {"leaf_id": "a", "kind": "evidence-fact", "depends_on": ["b"], "question": "A?"},
        {"leaf_id": "b", "kind": "evidence-fact", "depends_on": ["a"], "question": "B?"},
    ]
    with pytest.raises(GrillSessionError, match="acyclic"):
        start_session("Resolve", sketch, cycle, materialization_path=_target(sketch))

    unknown = [{"leaf_id": "a", "kind": "evidence-fact", "depends_on": ["x"], "question": "A?"}]
    with pytest.raises(GrillSessionError, match="unknown dependencies"):
        start_session("Resolve", sketch, unknown, materialization_path=_target(sketch))

    session = start_session("Resolve", sketch, _tree(), materialization_path=_target(sketch))
    with pytest.raises(GrillSessionError, match="pending human"):
        answer_pending_question(session, "yes", "DECIDED")


def test_confirmation_refuses_unresolved_leaves_and_requires_exact_phrase(sketch: Path) -> None:
    session = start_session("Resolve routing", sketch, _tree(), materialization_path=_target(sketch))
    with pytest.raises(GrillSessionError, match="leaves remain unresolved"):
        confirm_shared_understanding(session, SHARED_UNDERSTANDING_PHRASE)

    session = answer_pending_evidence(
        session,
        "qwen",
        [{"source_id": "config", "source_digest": digest("config")}],
    )
    session = answer_pending_question(session, "keep it", "DECIDED")
    session = answer_pending_question(session, "not in this slice", "NO_GO")
    assert session["state"] == "awaiting-confirmation"
    with pytest.raises(GrillSessionError, match="must exactly equal"):
        confirm_shared_understanding(session, "I agree")


def test_confirmation_materializes_buffers_and_issues_zero_authority_receipt(sketch: Path) -> None:
    session = start_session("Resolve routing", sketch, _tree(), materialization_path=_target(sketch))
    session = answer_pending_evidence(
        session,
        "qwen",
        [{"source_id": "config", "source_digest": digest("config")}],
        domain_updates=[{"term": "provider", "meaning": "The configured model backend."}],
    )
    session = answer_pending_question(session, "keep it", "DECIDED")
    session = answer_pending_question(session, "defer until load evidence exists", "RABBIT_HOLE")
    assert not _target(sketch).exists()
    assert session["materialization"]["content"] is None

    confirmed = confirm_shared_understanding(session, SHARED_UNDERSTANDING_PHRASE)

    assert not _target(sketch).exists()  # pure machine returns bytes; caller owns the write
    assert "**Answer (verbatim):** defer until load evidence exists" in confirmed["materialization"]["content"]
    assert "**provider:** The configured model backend." in confirmed["materialization"]["content"]
    assert confirmed["confirmation"]["answer_verbatim"] == SHARED_UNDERSTANDING_PHRASE
    assert confirmed["receipt"]["authority"] == {
        "mutation_authority": False,
        "business_authority": False,
        "irreversible_authority": False,
    }
    validate_receipt(confirmed["receipt"])


def test_target_must_be_markdown_under_sibling_grills_root(sketch: Path, tmp_path: Path) -> None:
    with pytest.raises(GrillSessionError, match="sibling Grills root"):
        start_session("Resolve", sketch, _tree(), materialization_path=tmp_path / "elsewhere.md")
    with pytest.raises(GrillSessionError, match="Markdown file"):
        start_session("Resolve", sketch, _tree(), materialization_path=_target(sketch).with_suffix(".txt"))


def test_nested_sketch_still_targets_the_vault_grills_sibling(tmp_path: Path) -> None:
    sketch = tmp_path / "vault" / "Sketches" / "components" / "routing.md"
    sketch.parent.mkdir(parents=True)
    sketch.write_text("# Nested sketch\n", encoding="utf-8")
    target = tmp_path / "vault" / "Grills" / "components" / "routing.md"

    session = start_session("Resolve", sketch, _tree(), materialization_path=target)

    assert session["materialization"]["grills_root"] == str((tmp_path / "vault" / "Grills").resolve())
    assert session["materialization"]["path"] == str(target.resolve())


def test_tampered_session_and_receipt_fail_integrity_even_if_authority_is_forged(sketch: Path) -> None:
    session = start_session("Resolve routing", sketch, _tree(), materialization_path=_target(sketch))
    tampered = copy.deepcopy(session)
    tampered["objective"] = "Different objective"
    with pytest.raises(GrillSessionError, match="session integrity"):
        validate_session(tampered)

    session = answer_pending_evidence(
        session,
        "qwen",
        [{"source_id": "config", "source_digest": digest("config")}],
    )
    session = answer_pending_question(session, "keep", "DECIDED")
    session = answer_pending_question(session, "exclude", "NO_GO")
    confirmed = confirm_shared_understanding(session, SHARED_UNDERSTANDING_PHRASE)
    forged = copy.deepcopy(confirmed["receipt"])
    forged["authority"]["mutation_authority"] = True
    with pytest.raises(GrillSessionError, match="receipt integrity"):
        validate_receipt(forged)


def test_cli_persists_only_control_state_then_materializes_after_confirmation(
    sketch: Path, tmp_path: Path
) -> None:
    script = SCRIPT_DIR / "grill_session.py"
    state_root = tmp_path / "control"
    state = state_root / "grills" / "session.json"
    tree_path = tmp_path / "tree.json"
    tree_path.write_text(
        json.dumps({"decision_tree": [_tree()[2] | {"depends_on": []}]}),
        encoding="utf-8",
    )
    target = _target(sketch)
    env = {**os.environ, "SENIOR_HARNESS_STATE_DIR": str(state_root)}

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    run(
        "start",
        "--state", str(state),
        "--objective", "Resolve routing",
        "--sketch", str(sketch),
        "--decision-tree", str(tree_path),
        "--transcript", str(target),
    )
    assert state.is_file()
    assert not target.exists()
    run("answer", "--state", str(state), "--answer", "Exclude it.", "--resolution", "NO_GO")
    run("confirm", "--state", str(state), "--phrase", SHARED_UNDERSTANDING_PHRASE)
    assert not target.exists()
    run("materialize", "--state", str(state))
    assert "**Answer (verbatim):** Exclude it." in target.read_text(encoding="utf-8")

    outside = subprocess.run(
        [sys.executable, str(script), "show", "--state", str(tmp_path / "outside.json")],
        capture_output=True,
        text=True,
        env=env,
    )
    assert outside.returncode == 2
    assert "external control root" in outside.stderr


def test_materialize_rejects_grills_directory_symlink_swap(sketch: Path, tmp_path: Path) -> None:
    script = SCRIPT_DIR / "grill_session.py"
    state_root = tmp_path / "control"
    state = state_root / "session.json"
    tree_path = tmp_path / "tree.json"
    tree_path.write_text(
        json.dumps({"decision_tree": [_tree()[2] | {"depends_on": []}]}),
        encoding="utf-8",
    )
    target = _target(sketch)
    outside = tmp_path / "outside"
    outside.mkdir()
    env = {**os.environ, "SENIOR_HARNESS_STATE_DIR": str(state_root)}

    def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            check=check,
            capture_output=True,
            text=True,
            env=env,
        )

    run(
        "start",
        "--state", str(state),
        "--objective", "Resolve routing",
        "--sketch", str(sketch),
        "--decision-tree", str(tree_path),
        "--transcript", str(target),
    )
    run("answer", "--state", str(state), "--answer", "Exclude it.", "--resolution", "NO_GO")
    run("confirm", "--state", str(state), "--phrase", SHARED_UNDERSTANDING_PHRASE)

    target.parent.symlink_to(outside, target_is_directory=True)
    attempted = run("materialize", "--state", str(state), check=False)

    assert attempted.returncode == 2
    assert "unsafe transcript path" in attempted.stderr
    assert not (outside / target.name).exists()
