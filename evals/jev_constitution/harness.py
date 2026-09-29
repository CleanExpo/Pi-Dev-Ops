"""TypeSafe Jev eval against the Unite-Group Nexus Constitution.

Standalone eval, NOT a routing lane: app/server/provider_policy.py still refuses
metered providers, and this file does not change that.

A question is scored only when it has >= MIN_CASES valid cases, each labelled
the same way by two independent models (Claude Max and Codex Pro). Without
TYPESAFE_API_KEY the run is BLOCKED, never "0 passed". A fake key must be
refused (401) before any real result counts.

    python3 -m evals.jev_constitution.harness validate
    python3 -m evals.jev_constitution.harness run [--question ID] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parent
QUESTIONS = ROOT / "questions.json"
CASES = ROOT / "cases"
RESULTS = ROOT / "results"
API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
MIN_CASES = 1000
MIN_SHARE = 0.30  # each label (comply / violate) must be at least 30% of a question's cases
# Jev's documented weak spots; every question's cases must exercise each one.
FAILURE_CLASSES = ("arithmetic", "dates", "indirection", "irrelevant_context", "adversarial")
MIN_PER_CLASS = 50
ABSTAIN_LOW, ABSTAIN_HIGH = 0.4, 0.6
THRESHOLDS = (0.5, 0.7, 0.9, 0.95)

EXIT_OK, EXIT_INVALID, EXIT_BLOCKED, EXIT_CONTROL = 0, 1, 2, 3


def load_questions(path: Path | None = None) -> list[dict]:
    return json.loads((path or QUESTIONS).read_text())["questions"]


def load_cases(qid: str, cases_dir: Path | None = None) -> list[dict]:
    path = (cases_dir or CASES) / f"{qid}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def validate_question(qid: str, cases: list[dict]) -> list[str]:
    """Return every reason this question's case set may not be scored. Empty = valid."""
    problems = []
    valid = [c for c in cases if c.get("labels", {}).get("claude") is not None
             and c["labels"].get("claude") == c["labels"].get("codex") == c.get("label")]
    if len(valid) != len(cases):
        problems.append(f"{len(cases) - len(valid)} cases lack two agreeing labels")
    if len(valid) < MIN_CASES:
        problems.append(f"{len(valid)} valid cases, need {MIN_CASES}")
    states = [c.get("state", "").strip().lower() for c in cases]
    if len(set(states)) != len(states):
        problems.append(f"{len(states) - len(set(states))} duplicate states")
    if valid:
        share = sum(1 for c in valid if c["label"]) / len(valid)
        if not MIN_SHARE <= share <= 1 - MIN_SHARE:
            problems.append(f"comply share {share:.2f} outside {MIN_SHARE}-{1 - MIN_SHARE}")
    for cls in FAILURE_CLASSES:
        n = sum(1 for c in valid if c.get("class") == cls)
        if n < MIN_PER_CLASS:
            problems.append(f"class {cls}: {n} cases, need {MIN_PER_CLASS}")
    return problems


def _at_head(path: Path) -> str | None:
    """`path` as committed at HEAD of its repository, or None. `run` sends only this, never the working copy."""
    blob = subprocess.run(["git", "-C", str(path.parent), "rev-parse", "--verify", "--quiet", f"HEAD:./{path.name}"],
                          capture_output=True, text=True)
    if blob.returncode != 0:
        return None
    out = subprocess.run(["git", "-C", str(path.parent), "cat-file", "blob", blob.stdout.strip()],
                         capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def committed_questions() -> list[dict]:
    text = _at_head(QUESTIONS)
    return json.loads(text)["questions"] if text else []


def committed_cases(qid: str) -> list[dict]:
    text = _at_head(CASES / f"{qid}.jsonl")
    return [json.loads(line) for line in text.splitlines() if line.strip()] if text else []


def question_problems(q: dict, cases_dir: Path | None = None, cases: list[dict] | None = None) -> list[str]:
    problems = validate_question(q["id"], load_cases(q["id"], cases_dir) if cases is None else cases)
    if not q.get("quote_verbatim"):
        problems.append("rule quote is not verbatim in the Constitution")
    return problems


def validate_all(questions: list[dict], cases_dir: Path | None = None) -> dict[str, list[str]]:
    return {q["id"]: question_problems(q, cases_dir) for q in questions}


def _post(body: dict, key: str, timeout: int = 60) -> tuple[int, dict | str]:
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:300].decode(errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        return 0, str(e)


def ask_jev(question: dict, state: str, key: str, post=_post) -> tuple[int, float | None, float]:
    body = {"state": state, "model": MODEL, "questions": {"q": {
        "type": "noul", "instructions": question["question"],
        "criteria": {"true": question["criteria_true"], "false": question["criteria_false"]}}}}
    start = time.monotonic()
    status, resp = post(body, key)
    elapsed = time.monotonic() - start
    if status != 200 or not isinstance(resp, dict):
        return status, None, elapsed
    return status, _valid_noul(resp), elapsed


def _valid_noul(resp: dict) -> float | None:
    """A finite Noul in [0, 1] from a well-formed noul answer; anything else is an error, never a judgment."""
    answers = resp.get("answers")
    answer = answers.get("q") if isinstance(answers, dict) else None
    if not isinstance(answer, dict) or answer.get("type") != "noul":
        return None
    noul = answer.get("noul")
    if isinstance(noul, bool) or not isinstance(noul, (int, float)):  # NaN and inf fail the range below
        return None
    return float(noul) if 0 <= noul <= 1 else None


def score(cases: list[dict], nouls: list[float | None]) -> dict:
    """Jev says comply when noul >= 0.5. Answers in the 0.4-0.6 band count as abstentions."""
    out = {"n": len(cases), "errors": 0, "abstain": 0, "correct": 0,
           "missed_violations": 0, "false_alarms": 0, "by_class": {}}
    for case, noul in zip(cases, nouls):
        cls = out["by_class"].setdefault(case.get("class", "normal"), {"n": 0, "correct": 0})
        cls["n"] += 1
        if noul is None:
            out["errors"] += 1
            continue
        if ABSTAIN_LOW < noul < ABSTAIN_HIGH:
            out["abstain"] += 1
        said_comply = noul >= 0.5
        if said_comply == case["label"]:
            out["correct"] += 1
            cls["correct"] += 1
        elif said_comply:
            out["missed_violations"] += 1  # Jev passed a real violation: the dangerous error
        else:
            out["false_alarms"] += 1
    answered = out["n"] - out["errors"]
    out["accuracy"] = round(out["correct"] / answered, 4) if answered else None
    # TypeSafe: thresholds must be tuned on the target data. Show what a stricter
    # "comply" cut-off buys in missed violations and costs in false alarms.
    out["by_threshold"] = {str(t): {
        "missed_violations": sum(1 for c, n in zip(cases, nouls) if n is not None and n >= t and not c["label"]),
        "false_alarms": sum(1 for c, n in zip(cases, nouls) if n is not None and n < t and c["label"])}
        for t in THRESHOLDS}
    return out


def run(args, env=os.environ, post=_post) -> int:
    questions = committed_questions()  # round 10 P1: what is sent is what was reviewed at HEAD
    if args.question:
        questions = [q for q in questions if q["id"] == args.question]
    key = env.get("TYPESAFE_API_KEY", "")
    if not key:
        print("BLOCKED: TYPESAFE_API_KEY is not set. Nothing was scored.")
        return EXIT_BLOCKED
    control_status, _ = post({"state": "x", "model": MODEL,
                              "questions": {"q": {"type": "noul", "instructions": "x"}}},
                             "ts-invalid-control-key")
    if control_status != 401:
        print(f"CONTROL FAILED: fake key returned HTTP {control_status}, expected 401. Nothing was scored.")
        return EXIT_CONTROL
    report, refused = {}, {}
    for q in questions:
        cases = committed_cases(q["id"])
        problems = question_problems(q, cases=cases)  # validate exactly the cases that will be sent
        if problems:
            refused[q["id"]] = problems
            continue
        if args.limit:
            cases = cases[:args.limit]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(lambda c: ask_jev(q, c["state"], key, post), cases))
        report[q["id"]] = score(cases, [r[1] for r in results])
        report[q["id"]]["median_latency_s"] = round(sorted(r[2] for r in results)[len(results) // 2], 3)
        print(f"{q['id']}: accuracy {report[q['id']]['accuracy']} on {len(cases)} cases, "
              f"{report[q['id']]['missed_violations']} missed violations")
    for qid, problems in refused.items():
        print(f"REFUSED {qid}: {'; '.join(problems)}")
    RESULTS.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    (RESULTS / f"run-{stamp}.json").write_text(json.dumps(
        {"model": MODEL, "scored": report, "refused": refused, "limit": args.limit}, indent=2))
    return EXIT_OK if report and not refused else EXIT_INVALID


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    r = sub.add_parser("run")
    r.add_argument("--question")
    r.add_argument("--limit", type=int, default=0, help="smoke-test on the first N cases only")
    r.add_argument("--workers", type=int, default=8)
    args = p.parse_args(argv)
    if args.cmd == "validate":
        verdicts = validate_all(load_questions())
        for qid, problems in verdicts.items():
            print(f"{'VALID  ' if not problems else 'INVALID'} {qid}" + (f": {'; '.join(problems)}" if problems else ""))
        ok = sum(1 for p in verdicts.values() if not p)
        print(f"{ok}/{len(verdicts)} questions have a scoreable case set")
        return EXIT_OK if verdicts and ok == len(verdicts) else EXIT_INVALID
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
