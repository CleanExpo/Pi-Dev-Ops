"""Round 10 P1s: every input that reaches Jev, or that a record claims as its lineage, comes from HEAD.

P1-LIVE-REGISTRY-UNCOMMITTED-DISCLOSURE and P1-CALIBRATION-FALSE-CASE-PROVENANCE, reproduced the way the
reviewer did: edit the tracked file in the working copy, then run with a recording fake transport. Offline.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime

import pytest
from jev_scale_support import git
from test_jev_constitution_eval import Q, make_cases

from evals.jev_constitution import generate
from evals.jev_constitution import harness as h
from evals.jev_constitution import writer_control as wc
from jev_platform import calibration, client, engine, gemini

RULE = "ch3-4-27"
MARKER = "UNREVIEWED_INTERNAL_PROJECT_CONTENT"
REAL_QUESTIONS = engine.ROOT / "evals" / "jev_constitution" / "questions.json"
REL_CASES = f"evals/jev_constitution/cases/{RULE}.jsonl"


def dual(i: int) -> dict:
    label = bool(i % 2)
    return {"state": f"Agent {i} {'honestly reports' if label else 'claims falsely'} step {i}.", "label": label,
            "class": "normal", "labels": {"claude": label, "codex": label}}


def recording(sent: list):
    def post(body, timeout):
        sent.append(body)
        noul = 0.97 if "honestly" in body["state"] else 0.02
        return 200, {"model": "jev-1.13.0", "answers": {q: {"type": "noul", "noul": noul} for q in body["questions"]},
                     "usage": {"input_tokens": 300}}, None
    return post


def budget(usd=5.0):
    return client.Budget(usd, 600)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A temp repo standing in for engine.ROOT, with the real registry and one dual-labelled case file at HEAD."""
    ev = tmp_path / "evals" / "jev_constitution"
    (ev / "cases").mkdir(parents=True)
    shutil.copy(REAL_QUESTIONS, ev / "questions.json")
    (ev / "cases" / f"{RULE}.jsonl").write_text("".join(json.dumps(dual(i)) + "\n" for i in range(400)))
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "inputs")
    monkeypatch.setattr(engine, "ROOT", tmp_path)
    monkeypatch.setattr(engine, "QUESTIONS", ev / "questions.json")
    monkeypatch.setattr(engine, "CASES", ev / "cases")
    monkeypatch.setattr(engine, "RECORDS", tmp_path / "records")
    return tmp_path


def head_blob(root, rel):
    return subprocess.run(["git", "-C", str(root), "rev-parse", f"HEAD:{rel}"],
                          capture_output=True, text=True).stdout.strip()


def test_decide_sends_the_committed_question_never_a_working_copy_edit(repo):
    questions = json.loads(engine.QUESTIONS.read_text())
    committed = next(q for q in questions["questions"] if q["id"] == RULE)["question"]
    for q in questions["questions"]:
        if q["id"] == RULE:
            q.update(question=MARKER, criteria_true=MARKER, criteria_false=MARKER)
    engine.QUESTIONS.write_text(json.dumps(questions))
    sent = []
    engine.decide("The agent writes 'all tests passed' but no test ran.", [RULE], 1, recording(sent), budget(0.5))
    assert len(sent) == 1  # positive control: the request was made
    assert (MARKER in json.dumps(sent), committed in json.dumps(sent)) == (False, True)


def test_an_uncommitted_registry_sends_nothing(repo):
    git(repo, "rm", "-q", "--cached", "evals/jev_constitution/questions.json")
    git(repo, "commit", "-qm", "untrack registry")
    sent = []
    out = engine.decide("x", [RULE], 1, recording(sent), budget(0.5))
    assert sent == [] and out["verdict"] == "escalate"


def test_calibration_scores_committed_cases_and_records_their_blob(repo):
    committed_states = {dual(i)["state"] for i in range(400)}
    (engine.CASES / f"{RULE}.jsonl").write_text(
        "".join(json.dumps({"state": f"{MARKER} {i}", "label": bool(i % 2)}) + "\n" for i in range(400)))
    sent = []
    rec = engine.calibrate(RULE, recording(sent), budget())
    assert len(sent) == 400
    assert {b["state"] for b in sent} == committed_states, "sent states are not the committed cases"
    assert rec["label_provenance"]["cases_blob"] == head_blob(repo, REL_CASES)


def test_committed_cases_without_two_agreeing_labels_send_nothing(repo):
    (engine.CASES / f"{RULE}.jsonl").write_text(
        "".join(json.dumps({"state": f"synthetic {i}", "label": bool(i % 2)}) + "\n" for i in range(400)))
    git(repo, "commit", "-qam", "unlabelled cases")
    sent = []
    rec = engine.calibrate(RULE, recording(sent), budget())
    assert sent == [] and rec["state"] == "incomplete" and not (engine.RECORDS / f"{RULE}.json").exists()


def test_a_record_whose_scores_did_not_come_from_its_cases_blob_is_corrupt(repo):
    engine.calibrate(RULE, recording([]), budget())
    record, scored = engine.load_record(RULE), engine.load_scored(RULE)
    scored[0] = {**scored[0], "hash": calibration.case_hash("a state that is in no committed case")}
    forged = calibration.build_record(RULE, scored, record["bindings"], record["label_provenance"],
                                      now=datetime.fromisoformat(record["created_utc"]))
    forged["eval_sha"] = record["eval_sha"]
    assert calibration.verify(forged, scored) == []  # the forgery is self-consistent: verify alone accepts it
    (engine.RECORDS / f"{RULE}.scored.jsonl").write_text("".join(json.dumps(s) + "\n" for s in scored))
    (engine.RECORDS / f"{RULE}.json").write_text(json.dumps(forged, indent=1) + "\n")
    out = engine.decide("The agent reports tests have not run yet.", [RULE], 1, recording([]), budget(0.5))
    assert out["findings"][0]["state"] == "corrupt"
    assert engine.artifact_rating(RULE)[0] == "FAIL"


def forge_lineage(repo, cases_blob):
    """Rewrite the stored record so it names `cases_blob` and still recomputes (verify alone accepts it)."""
    record, scored = engine.load_record(RULE), engine.load_scored(RULE)
    prov = {**record["label_provenance"], "cases_blob": cases_blob}
    forged = calibration.build_record(RULE, scored, record["bindings"], prov,
                                      now=datetime.fromisoformat(record["created_utc"]))
    assert calibration.verify(forged, scored) == []
    (engine.RECORDS / f"{RULE}.json").write_text(json.dumps({**forged, "eval_sha": record["eval_sha"]}) + "\n")


def test_a_record_naming_an_unreadable_blob_is_corrupt(repo):
    engine.calibrate(RULE, recording([]), budget())
    forge_lineage(repo, "0" * 40)
    out = engine.decide("x", [RULE], 1, recording([]), budget(0.5))
    assert out["findings"][0]["state"] == "corrupt" and engine.artifact_rating(RULE)[0] == "FAIL"


def test_a_record_whose_blob_lacks_two_agreeing_labels_is_corrupt(repo):
    """Same states, same labels, so the scores match the blob; only the dual-label provenance is missing."""
    engine.calibrate(RULE, recording([]), budget())
    unlabelled = "".join(json.dumps({k: v for k, v in dual(i).items() if k != "labels"}) + "\n" for i in range(400))
    (engine.CASES / f"{RULE}.jsonl").write_text(unlabelled)
    git(repo, "commit", "-qam", "strip labels")
    forge_lineage(repo, head_blob(repo, REL_CASES))
    out = engine.decide("x", [RULE], 1, recording([]), budget(0.5))
    assert out["findings"][0]["state"] == "corrupt" and engine.artifact_rating(RULE)[0] == "FAIL"


def test_records_outside_the_repository_are_capped_at_aa(repo, tmp_path_factory, monkeypatch):
    """The fixtures keep records inside ROOT, so this guard needs its own test (the runner found it unkilled)."""
    engine.calibrate(RULE, recording([]), budget())
    outside = tmp_path_factory.mktemp("elsewhere") / "records"
    shutil.copytree(engine.RECORDS, outside)
    monkeypatch.setattr(engine, "RECORDS", outside)
    assert engine.artifact_rating(RULE) == ("AA", ["records not inside the repository"])


def test_an_honest_record_still_verifies(repo):
    """Positive control for the lineage check: an untampered calibration is usable and rates AA."""
    engine.calibrate(RULE, recording([]), budget())
    out = engine.decide("The agent reports tests have not run yet.", [RULE], 1, recording([]), budget(0.5))
    assert out["findings"][0]["state"] == "provisional"
    assert engine.artifact_rating(RULE) == ("AA", ["not bound to HEAD"])


# ---- evals/jev_constitution/harness.py: `run` sends to the same provider, so it takes the same boundary

@pytest.fixture
def eval_repo(tmp_path, monkeypatch):
    (tmp_path / "cases").mkdir()
    (tmp_path / "questions.json").write_text(json.dumps({"questions": [Q]}))
    (tmp_path / "cases" / "t-01.jsonl").write_text("\n".join(json.dumps(c) for c in make_cases()))
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "eval inputs")
    monkeypatch.setattr(h, "QUESTIONS", tmp_path / "questions.json")
    monkeypatch.setattr(h, "CASES", tmp_path / "cases")
    monkeypatch.setattr(h, "RESULTS", tmp_path / "results")
    return tmp_path


def run_recording(sent):
    def post(body, key):
        if key != "real":
            return 401, ""
        sent.append(body)
        return 200, {"answers": {"q": {"type": "noul", "noul": 1.0}}}
    return h.run(argparse.Namespace(question=None, limit=0, workers=4), env={"TYPESAFE_API_KEY": "real"}, post=post)


def test_harness_run_sends_the_committed_question_not_a_working_copy_edit(eval_repo):
    (eval_repo / "questions.json").write_text(json.dumps({"questions": [{**Q, "question": MARKER}]}))
    sent = []
    run_recording(sent)
    assert len(sent) == 1000
    assert not any(MARKER in json.dumps(b) for b in sent)


def test_harness_run_sends_the_committed_cases_not_a_working_copy_edit(eval_repo):
    edited = [{**c, "state": f"{MARKER} {i}"} for i, c in enumerate(make_cases())]
    (eval_repo / "cases" / "t-01.jsonl").write_text("\n".join(json.dumps(c) for c in edited))
    sent = []
    run_recording(sent)
    assert len(sent) == 1000
    assert not any(MARKER in json.dumps(b) for b in sent)


class Stop(Exception):
    pass


def test_the_case_writer_sends_the_committed_question(eval_repo, monkeypatch):
    """generate.py sends the question text to Gemini or `claude -p`: it must be HEAD's, not a working-copy edit."""
    (eval_repo / "questions.json").write_text(json.dumps({"questions": [{**Q, "question": MARKER}]}))
    seen = []

    def first_round(question, *rest):
        seen.append(question)
        raise Stop
    monkeypatch.setattr(generate, "_writer", lambda a: (None, "gemini", eval_repo / "x.jsonl"))
    monkeypatch.setattr(generate, "CASES", eval_repo / "cases")
    monkeypatch.setattr(generate, "_round", first_round)
    with pytest.raises(Stop):
        generate.main(["--question", "t-01", "--target", "10"])
    assert seen and seen[0]["question"] == Q["question"]


def test_the_writer_control_sends_the_committed_question(eval_repo, monkeypatch, tmp_path):
    (eval_repo / "questions.json").write_text(json.dumps({"questions": [{**Q, "id": wc.QUESTION_ID}]}))
    git(eval_repo, "commit", "-qam", "control question")
    (eval_repo / "questions.json").write_text(json.dumps({"questions": [{**Q, "id": wc.QUESTION_ID, "question": MARKER}]}))
    seen = []

    def prompt(question, example):
        seen.append(question)
        raise Stop
    monkeypatch.setattr(gemini, "api_key", lambda: "gk-test-not-a-real-key")
    monkeypatch.setattr(gemini, "price_table", lambda day: {"any": 1})
    monkeypatch.setattr(gemini, "GeminiBudget", lambda *a: None)
    monkeypatch.setattr(wc, "control_prompt", prompt)
    monkeypatch.setattr(wc, "run_control", lambda writers, label: writers["claude"]("e"))
    with pytest.raises(Stop):
        wc.main(tmp_path / "out.json")
    assert seen and seen[0]["question"] == Q["question"]


def test_calibrating_a_rule_absent_from_the_committed_registry_sends_nothing(repo):
    git(repo, "rm", "-q", "--cached", "evals/jev_constitution/questions.json")
    git(repo, "commit", "-qm", "untrack registry")
    sent = []
    rec = engine.calibrate(RULE, recording(sent), budget())
    assert sent == [] and rec["state"] == "incomplete" and rec["first_error"] == "rule_not_committed"


def test_harness_run_validates_the_cases_it_sends(eval_repo):
    """Committed cases invalid (999), working copy valid: the run must refuse, not validate one and send the other."""
    path = eval_repo / "cases" / "t-01.jsonl"
    path.write_text("\n".join(json.dumps(c) for c in make_cases()[:999]))
    git(eval_repo, "commit", "-qam", "999 cases")
    path.write_text("\n".join(json.dumps(c) for c in make_cases()))
    sent = []
    assert run_recording(sent) == h.EXIT_INVALID and sent == []
