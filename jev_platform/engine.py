"""Glue: registry, bindings, shadow decisions and calibration runs (PLAN.md rev 5)."""
from __future__ import annotations

import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jev_platform import calibration, client, policy

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "evals" / "jev_constitution" / "questions.json"
CASES = ROOT / "evals" / "jev_constitution" / "cases"
RECORDS = Path(__file__).resolve().parent / "calibration"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "synthetic_actions.json"
MAX_RULES = 25
PROVENANCE = {
    "writer": "Claude sonnet via `claude -p` (Max plan), evals/jev_constitution/generate.py",
    "labeller": "Codex CLI (ChatGPT Pro), model_reasoning_effort=medium, labels blind",
    "procedure": "kept only cases where Claude and Codex labels agreed; disagreement count unknown",
    "adjudication": "none (no human review)",
}


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def registry() -> dict[str, dict]:
    return {q["id"]: q for q in json.loads(QUESTIONS.read_text())["questions"]}


def bindings(rule: dict, model: str) -> dict:
    config = {"candidates": calibration.CANDIDATES, "abstain": [policy.ABSTAIN_LOW, policy.ABSTAIN_HIGH],
              "fail_below": policy.FAIL_BELOW, "policy": policy.POLICY_VERSION, "redaction": client.REDACTION_VERSION}
    question = {k: rule[k] for k in ("quote", "question", "criteria_true", "criteria_false")}
    return {"rule_sha256": _sha(question), "config_sha256": _sha(config), "model": model}


def load_record(rule_id: str) -> dict | None:
    path = RECORDS / f"{rule_id}.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None if not path.exists() else {"corrupt": True}


def load_scored(rule_id: str) -> list[dict]:
    path = RECORDS / f"{rule_id}.scored.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def _decision_state(rule: dict, record: dict | None, model: str) -> str:
    """evaluate_state, plus: a usable record must recompute from its stored cases (PLAN.md `corrupt`)."""
    state = calibration.evaluate_state(record, bindings(rule, model))
    if state != policy.USABLE_STATE:
        return state
    try:
        problems = calibration.verify(record, load_scored(rule["id"]))
    except (OSError, ValueError, KeyError, TypeError):
        return "corrupt"
    return "corrupt" if problems else state


def _rule_findings(rules, answer, altered) -> list[dict]:
    findings = []
    for rule in rules:
        noul = answer.get("nouls", {}).get(rule["id"])
        record = load_record(rule["id"])
        state = _decision_state(rule, record, answer.get("model", "none"))
        result, reason = policy.classify_rule(noul, (record or {}).get("threshold"), state, "error" not in answer)
        if altered and result != policy.UNCERTAIN:
            result, reason = policy.UNCERTAIN, "altered_input"
        findings.append({"rule": rule["id"], "result": result, "reason": reason, "noul": noul,
                         "state": state, "source": rule["source"], "quote": rule["quote"]})
    return findings


def decide(action_text: str, rule_ids: list[str], claimed_class, post, budget) -> dict:
    reg = registry()
    problems = policy.selection_problems(rule_ids, set(reg))
    if len(rule_ids) > MAX_RULES:
        problems.append(f"too_many_rules:{len(rule_ids)}>{MAX_RULES}")
    rules = [reg[r] for r in dict.fromkeys(rule_ids) if r in reg]
    text, altered = client.redact(action_text)
    answer = client.ask(text, rules, post, budget) if rules and not problems else {"error": "not_sent"}
    findings = _rule_findings(rules, answer, altered)
    rec = policy.recommend(findings, claimed_class, problems + ([answer["error"]] if "error" in answer else []))
    rec.update(findings=findings, model=answer.get("model"), action_sha256=hashlib.sha256(text.encode()).hexdigest(),
               spent_usd=round(budget.spent, 6))
    return rec


def _git(*args) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True).stdout.strip()


def _score_case(case, rule, post, budget):
    text, _ = client.redact(case["state"])
    answer = client.ask(text, [rule], post, budget)
    return case, answer


def calibrate(rule_id: str, post, budget, workers: int = 8) -> dict:
    rule = registry()[rule_id]
    cases = [json.loads(line) for line in (CASES / f"{rule_id}.jsonl").read_text().splitlines() if line.strip()]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda c: _score_case(c, rule, post, budget), cases))
    errors = [a["error"] for _, a in results if "error" in a]
    models = {a["model"] for _, a in results if "model" in a}
    if errors or len(models) != 1:
        return {"rule": rule_id, "state": "incomplete", "errors": len(errors), "models": sorted(models),
                "first_error": errors[0] if errors else None, "spent_usd": round(budget.spent, 6)}
    scored = [{"hash": calibration.case_hash(c["state"]), "label": c["label"], "class": c.get("class", "normal"),
               "noul": a["nouls"][rule_id]} for c, a in results]
    provenance = {**PROVENANCE, "generate_py_blob": _git("rev-parse", "HEAD:evals/jev_constitution/generate.py"),
                  "cases_blob": _git("rev-parse", f"HEAD:evals/jev_constitution/cases/{rule_id}.jsonl")}
    record = calibration.build_record(rule_id, scored, bindings(rule, models.pop()), provenance)
    record["eval_sha"] = _git("rev-parse", "HEAD")
    RECORDS.mkdir(exist_ok=True)
    (RECORDS / f"{rule_id}.scored.jsonl").write_text("".join(json.dumps(s) + "\n" for s in scored))
    (RECORDS / f"{rule_id}.json").write_text(json.dumps(record, indent=1) + "\n")
    record["spent_usd"] = round(budget.spent, 6)
    return record


def artifact_rating(rule_id: str) -> tuple[str, list[str]]:
    """AAA: recomputes and the files match HEAD; AA: recomputes only; FAIL: absent or not reproducible."""
    record = load_record(rule_id)
    if record is None:
        return "FAIL", ["absent"]
    problems = calibration.verify(record, load_scored(rule_id))
    if problems:
        return "FAIL", problems
    paths = [RECORDS / f"{rule_id}.json", RECORDS / f"{rule_id}.scored.jsonl"]
    if not all(p.resolve().is_relative_to(ROOT) for p in paths):
        return "AA", ["records not inside the repository"]
    files = [str(p.resolve().relative_to(ROOT)) for p in paths]
    tracked = all(_git("ls-files", f) for f in files)
    clean = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD", "--", *files]).returncode == 0
    return ("AAA", []) if tracked and clean else ("AA", ["not bound to HEAD"])
