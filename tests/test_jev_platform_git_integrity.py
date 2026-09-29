"""Round 11 P1s: a reviewed git id must name the reviewed bytes, and a record's lineage must be a commit in HEAD's history.

P1-LIVE-REGISTRY-UNCOMMITTED-DISCLOSURE: `git replace` re-points an id at other bytes, and `cat-file` serves a
loose object without hashing it, so uncommitted text could be sent under a committed id.
P1-CALIBRATION-FALSE-CASE-PROVENANCE: a record could name any readable blob, even one no commit contains.
Offline, temp repos (fixtures from test_jev_platform_committed_inputs).
"""
from __future__ import annotations

import json
import subprocess
import zlib
from datetime import datetime

import test_jev_platform_committed_inputs as ci
from jev_scale_support import git
from test_jev_platform_committed_inputs import MARKER, REL_CASES, RULE, budget, dual, head_blob, recording, run_recording

from jev_platform import calibration, engine

repo, eval_repo = ci.repo, ci.eval_repo  # the same temp-repo fixtures

REL_QUESTIONS = "evals/jev_constitution/questions.json"


def out(root, *args, stdin=None) -> str:
    return subprocess.run(["git", "-C", str(root), *args], input=stdin, capture_output=True, text=True).stdout.strip()


def marker_registry(root) -> str:
    questions = json.loads((root / REL_QUESTIONS).read_text())
    for q in questions["questions"]:
        if q["id"] == RULE:
            q.update(question=MARKER, criteria_true=MARKER, criteria_false=MARKER)
    return json.dumps(questions)


def overwrite_loose(root, blob: str, text: str) -> None:
    """Store `text` under `blob`'s id, the way a corrupted or hand-written loose object would."""
    path = root / ".git" / "objects" / blob[:2] / blob[2:]
    path.chmod(0o644)
    data = text.encode()
    path.write_bytes(zlib.compress(b"blob %d\0" % len(data) + data))


def sent_by_decide() -> list:
    sent = []
    engine.decide("The agent writes 'all tests passed' but no test ran.", [RULE], 1, recording(sent), budget(0.5))
    return sent


def test_a_replaced_registry_blob_is_not_sent(repo):
    marker = out(repo, "hash-object", "-w", "--stdin", stdin=marker_registry(repo))
    git(repo, "replace", head_blob(repo, REL_QUESTIONS), marker)
    assert MARKER in out(repo, "show", f"HEAD:{REL_QUESTIONS}")  # positive control: the replacement is live
    sent = sent_by_decide()
    assert len(sent) == 1 and MARKER not in json.dumps(sent)


def test_a_replaced_head_commit_is_not_followed(repo):
    original = out(repo, "rev-parse", "HEAD")
    (repo / REL_QUESTIONS).write_text(marker_registry(repo))
    git(repo, "commit", "-qam", "unreviewed")
    replacement = out(repo, "rev-parse", "HEAD")
    git(repo, "reset", "-q", "--hard", original)
    git(repo, "replace", original, replacement)
    assert MARKER in out(repo, "show", f"HEAD:{REL_QUESTIONS}")
    sent = sent_by_decide()
    assert len(sent) == 1 and MARKER not in json.dumps(sent)


def test_a_blob_whose_bytes_do_not_hash_to_its_id_is_not_sent(repo):
    overwrite_loose(repo, head_blob(repo, REL_QUESTIONS), marker_registry(repo))
    assert MARKER in out(repo, "cat-file", "blob", head_blob(repo, REL_QUESTIONS))  # git serves it unchecked
    assert sent_by_decide() == []


def test_harness_run_ignores_a_replaced_blob(eval_repo):
    questions = json.loads((eval_repo / "questions.json").read_text())
    questions["questions"][0]["question"] = MARKER
    marker = out(eval_repo, "hash-object", "-w", "--stdin", stdin=json.dumps(questions))
    git(eval_repo, "replace", out(eval_repo, "rev-parse", "HEAD:questions.json"), marker)
    sent = []
    run_recording(sent)
    assert len(sent) == 1000 and not any(MARKER in json.dumps(b) for b in sent)


def test_harness_run_sends_nothing_from_a_blob_whose_bytes_do_not_hash_to_its_id(eval_repo):
    questions = json.loads((eval_repo / "questions.json").read_text())
    questions["questions"][0]["question"] = MARKER
    overwrite_loose(eval_repo, out(eval_repo, "rev-parse", "HEAD:questions.json"), json.dumps(questions))
    sent = []
    run_recording(sent)
    assert sent == []


# ---- lineage: cases_blob must be the cases file at eval_sha, and eval_sha must be in HEAD's history

ALT = [{**dual(i), "state": f"Alternative agent {i} {'honestly reports' if i % 2 else 'claims falsely'} step {i}."}
       for i in range(400)]


def forge(repo, eval_sha: str, cases: list[dict], cases_blob: str) -> None:
    """A self-consistent record whose scores come from `cases` (verify alone accepts it)."""
    record = engine.load_record(RULE)
    scored = [{"hash": calibration.case_hash(c["state"]), "label": c["label"], "class": "normal",
               "noul": 0.97 if c["label"] else 0.02} for c in cases]
    prov = {**record["label_provenance"], "cases_blob": cases_blob}
    forged = calibration.build_record(RULE, scored, record["bindings"], prov,
                                      now=datetime.fromisoformat(record["created_utc"]))
    assert calibration.verify(forged, scored) == []
    (engine.RECORDS / f"{RULE}.scored.jsonl").write_text("".join(json.dumps(s) + "\n" for s in scored))
    (engine.RECORDS / f"{RULE}.json").write_text(json.dumps({**forged, "eval_sha": eval_sha}) + "\n")


def state_and_rating(problem: str) -> None:
    out_ = engine.decide("x", [RULE], 1, recording([]), budget(0.5))
    assert out_["findings"][0]["state"] == "corrupt"
    assert engine.artifact_rating(RULE) == ("FAIL", [problem])


def alt_text() -> str:
    return "".join(json.dumps(c) + "\n" for c in ALT)


def test_a_record_naming_a_blob_no_commit_contains_is_corrupt(repo):
    engine.calibrate(RULE, recording([]), budget())
    loose = out(repo, "hash-object", "-w", "--stdin", stdin=alt_text())
    forge(repo, out(repo, "rev-parse", "HEAD"), ALT, loose)
    state_and_rating("cases_blob is not the cases file committed at eval_sha")


def test_a_record_whose_eval_sha_is_outside_heads_history_is_corrupt(repo):
    engine.calibrate(RULE, recording([]), budget())
    blob = out(repo, "hash-object", "-w", "--stdin", stdin=alt_text())
    tree = out(repo, "mktree", stdin=f"100644 blob {blob}\t{RULE}.jsonl\n")
    for sub in ("cases", "jev_constitution", "evals"):
        tree = out(repo, "mktree", stdin=f"040000 tree {tree}\t{sub}\n")
    orphan = out(repo, "commit-tree", tree, "-m", "never merged")
    assert out(repo, "rev-parse", f"{orphan}:{REL_CASES}") == blob  # positive control: the orphan holds the blob
    forge(repo, orphan, ALT, blob)
    state_and_rating("eval_sha is not in the history of HEAD")


def test_a_record_whose_eval_sha_is_not_a_full_commit_id_is_corrupt(repo):
    engine.calibrate(RULE, recording([]), budget())
    record = engine.load_record(RULE)
    (engine.RECORDS / f"{RULE}.json").write_text(json.dumps({**record, "eval_sha": "HEAD"}) + "\n")
    state_and_rating("eval_sha is not a full commit id")


def test_a_record_whose_cases_blob_bytes_were_tampered_is_corrupt(repo):
    engine.calibrate(RULE, recording([]), budget())
    overwrite_loose(repo, head_blob(repo, REL_CASES), alt_text())
    forge(repo, engine.load_record(RULE)["eval_sha"], ALT, head_blob(repo, REL_CASES))
    state_and_rating("cases_blob is not the cases file committed at eval_sha")  # the blob fails its rehash


def test_calibrate_records_the_commit_whose_cases_it_scored(repo):
    rec = engine.calibrate(RULE, recording([]), budget())
    assert rec["eval_sha"] == out(repo, "rev-parse", "HEAD")
    assert out(repo, "rev-parse", f"{rec['eval_sha']}:{REL_CASES}") == rec["label_provenance"]["cases_blob"]
    assert engine.decide("x", [RULE], 1, recording([]), budget(0.5))["findings"][0]["state"] == "provisional"
