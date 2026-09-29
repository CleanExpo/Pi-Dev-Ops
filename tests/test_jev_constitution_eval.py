"""Offline controls for the Jev constitution eval (evals/jev_constitution/harness.py).

No network: every Jev call goes through a fake `post`. These prove the harness
refuses to report a score it has not earned.
"""
from __future__ import annotations

import argparse
import json

import pytest
from jev_scale_support import git

from evals.jev_constitution import harness as h

Q = {"id": "t-01", "quote": "q", "question": "Does it comply?", "criteria_true": "yes", "criteria_false": "no",
     "quote_verbatim": True}


def make_cases(n: int = 1000, comply_share: float = 0.5) -> list[dict]:
    classes = list(h.FAILURE_CLASSES) + ["normal"] * 5
    cases = []
    for i in range(n):
        label = i < n * comply_share
        cases.append({"state": f"scenario {i}", "label": label, "class": classes[i % len(classes)],
                      "labels": {"claude": label, "codex": label}})
    return cases


def test_valid_set_passes():
    assert h.validate_question("t-01", make_cases()) == []


@pytest.mark.parametrize("mutate, reason", [
    (lambda c: c.pop(), "need 1000"),
    (lambda c: c[0]["labels"].update(codex=not c[0]["label"]), "lack two agreeing labels"),
    (lambda c: c[1].update(state=c[0]["state"]), "duplicate"),
    (lambda c: [x.update(**{"class": "normal"}) for x in c if x["class"] == "dates"], "class dates"),
])
def test_corrupted_set_is_refused(mutate, reason):
    cases = make_cases(1001) if reason == "lack two agreeing labels" else make_cases()
    mutate(cases)
    problems = h.validate_question("t-01", cases)
    assert any(reason in p for p in problems), problems


def test_one_sided_labels_are_refused():
    assert any("comply share" in p for p in h.validate_question("t-01", make_cases(comply_share=0.9)))


def test_score_counts_missed_violations_and_abstentions():
    cases = [{"label": False, "class": "dates"}, {"label": True}, {"label": True}, {"label": False}]
    s = h.score(cases, [0.9, 0.55, None, 0.1])
    assert s["missed_violations"] == 1 and s["abstain"] == 1 and s["errors"] == 1
    assert s["correct"] == 2 and s["accuracy"] == round(2 / 3, 4)
    assert s["by_threshold"]["0.95"] == {"missed_violations": 0, "false_alarms": 1}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "cases").mkdir()
    (tmp_path / "questions.json").write_text(json.dumps({"questions": [Q]}))
    monkeypatch.setattr(h, "QUESTIONS", tmp_path / "questions.json")
    monkeypatch.setattr(h, "CASES", tmp_path / "cases")
    monkeypatch.setattr(h, "RESULTS", tmp_path / "results")
    git(tmp_path, "init", "-q")
    commit(tmp_path)
    return tmp_path


def commit(ws):
    """`run` sends only what is committed at HEAD, so the fixture commits what it writes."""
    git(ws, "add", "-A")
    git(ws, "commit", "-qm", "inputs", "--allow-empty")


def write_cases(ws, cases):
    (ws / "cases" / "t-01.jsonl").write_text("\n".join(json.dumps(c) for c in cases))
    commit(ws)


ARGS = argparse.Namespace(question=None, limit=0, workers=4)


def test_no_key_is_blocked_not_zero(workspace):
    calls = []
    rc = h.run(ARGS, env={}, post=lambda b, k: calls.append(k) or (200, {}))
    assert rc == h.EXIT_BLOCKED and calls == []


def test_control_accepting_a_fake_key_stops_the_run(workspace):
    write_cases(workspace, make_cases())
    rc = h.run(ARGS, env={"TYPESAFE_API_KEY": "real"}, post=lambda b, k: (200, {}))
    assert rc == h.EXIT_CONTROL
    assert not (workspace / "results").exists()


def test_under_1000_cases_is_refused_even_with_a_working_key(workspace):
    write_cases(workspace, make_cases(999 + 1)[:999])
    def post(body, key):
        return (401, "") if key != "real" else (200, {"answers": {"q": {"type": "noul", "noul": 1.0}}})

    assert h.run(ARGS, env={"TYPESAFE_API_KEY": "real"}, post=post) == h.EXIT_INVALID
    report = json.loads(next((workspace / "results").iterdir()).read_text())
    assert report["scored"] == {} and "t-01" in report["refused"]


def test_full_run_scores_every_case(workspace):
    cases = make_cases()
    write_cases(workspace, cases)
    truth = {c["state"]: c["label"] for c in cases}

    def post(body, key):
        if key != "real":
            return 401, "Missing or invalid API key"
        return 200, {"answers": {"q": {"type": "noul", "noul": 1.0 if truth[body["state"]] else 0.0}}}

    assert h.run(ARGS, env={"TYPESAFE_API_KEY": "real"}, post=post) == h.EXIT_OK
    scored = json.loads(next((workspace / "results").iterdir()).read_text())["scored"]["t-01"]
    assert scored["n"] == 1000 and scored["accuracy"] == 1.0 and scored["missed_violations"] == 0


def test_paraphrased_rule_is_refused(workspace):
    (workspace / "questions.json").write_text(json.dumps({"questions": [{**Q, "quote_verbatim": False}]}))
    write_cases(workspace, make_cases())
    assert h.validate_all(h.load_questions())["t-01"] == ["rule quote is not verbatim in the Constitution"]


@pytest.mark.parametrize("answer", [
    {"type": "noul", "noul": 2.0}, {"type": "noul", "noul": -1.0}, {"type": "noul", "noul": float("nan")},
    {"type": "noul", "noul": True}, {"type": "noul", "noul": "0.9"}, {"type": "choice", "noul": 1.0}, {"noul": 1.0},
])
def test_a_malformed_noul_is_an_error_never_a_judgment(answer):
    """Release review r3 P1: out-of-range Nouls produced a perfect report instead of errors."""
    status, noul, _ = h.ask_jev({"question": "q", "criteria_true": "t", "criteria_false": "f"}, "s", "k",
                                post=lambda body, key: (200, {"answers": {"q": answer}}))
    assert status == 200 and noul is None
    assert h.score([{"label": True}], [noul])["errors"] == 1
