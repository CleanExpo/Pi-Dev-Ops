"""The bench keeps Jev's own answer on every row, so the confidence cut-off can be tuned offline."""
from types import SimpleNamespace

from evals.skill_routing import run
from src.tao import skill_router as sr

SKILLS = {"alpha": {"name": "alpha", "body": "alpha body"}, "beta": {"name": "beta", "body": "beta body"}}


def _out(choice: str, confidence: float) -> dict:
    criteria = {"alpha": "a", "beta": "b", sr.NO_MATCH: "none"}
    probs = {k: (1.0 if k == choice else 0.0) for k in criteria}
    answer = {"type": "choice", "choice": choice, "probabilities": probs, "confidence": confidence}
    return {"questions": {"q0": {"type": "choice", "criteria": criteria}}, "result": {"answers": {"q0": answer}}}


def _rows(choice: str, confidence: float) -> list[dict]:
    args = SimpleNamespace(budget=sr.DEFAULT_BUDGET, min_confidence=sr.MIN_CONFIDENCE)
    chunk = [(0, {"text": "t", "expected": "alpha"}, [("alpha", 3.0), ("beta", 1.0)])]
    return run.chunk_rows(_out(choice, confidence), chunk, SKILLS, args, {"errors": 0})


def test_a_low_confidence_answer_loads_nothing_but_keeps_its_label():
    row = _rows("alpha", 0.3)[0]
    assert row["picked"] == []
    assert row["jev_label"] == "alpha"
    assert row["confidence"] == 0.3


def test_a_confident_answer_keeps_its_label_and_loads_it():
    row = _rows("beta", 0.9)[0]
    assert row["picked"] == ["beta"]
    assert row["jev_label"] == "beta"


def test_no_match_is_recorded_as_the_label():
    row = _rows(sr.NO_MATCH, 0.8)[0]
    assert row["picked"] == []
    assert row["jev_label"] == sr.NO_MATCH
