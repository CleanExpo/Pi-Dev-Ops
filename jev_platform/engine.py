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


def _committed(path: Path) -> tuple[str, str] | None:
    """(blob id, text) of `path` as committed at HEAD, or None. Round 10 P1s: whatever reaches Jev, or is
    named as a record's lineage, is the reviewed HEAD blob — never the working copy. The blob id is resolved
    once and the bytes are read BY that id, so a HEAD move between the two calls cannot split them."""
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return None
    blob = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "--quiet", f"HEAD:{rel}"],
                          capture_output=True, text=True)
    text = _blob_text(blob.stdout.strip()) if blob.returncode == 0 else None
    return None if text is None else (blob.stdout.strip(), text)


def _blob_text(blob: str) -> str | None:
    out = subprocess.run(["git", "-C", str(ROOT), "cat-file", "blob", blob], capture_output=True, text=True)
    return out.stdout if out.returncode == 0 and blob else None


def registry() -> dict[str, dict]:
    """The committed registry. Not committed or unreadable -> empty, so every rule id is unknown and nothing is sent."""
    committed = _committed(QUESTIONS)
    try:
        return {q["id"]: q for q in json.loads(committed[1])["questions"]} if committed else {}
    except (ValueError, KeyError, TypeError):
        return {}


def _dual_labelled(case: dict) -> bool:
    labels = case.get("labels")
    return isinstance(labels, dict) and labels.get("claude") is not None and \
        labels.get("claude") == labels.get("codex") == case.get("label")


def _lineage_problems(record: dict, scored: list[dict]) -> list[str]:
    """The stored scores must be exactly the cases in the blob the record names, each with two agreeing labels.
    calibration.verify only proves the record is self-consistent; this proves where its inputs came from."""
    blob = (record.get("label_provenance") or {}).get("cases_blob") if isinstance(record, dict) else None
    text = _blob_text(blob) if isinstance(blob, str) else None
    if text is None:
        return ["cases_blob is not a readable committed blob"]
    cases = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not all(_dual_labelled(c) for c in cases):
        return ["cases_blob has cases without two agreeing labels"]
    want = sorted((calibration.case_hash(c["state"]), c["label"], c.get("class", "normal")) for c in cases)
    have = sorted((s["hash"], s["label"], s["class"]) for s in scored)
    return [] if want == have else ["stored scores do not come from cases_blob"]


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
        scored = load_scored(rule["id"])
        problems = calibration.verify(record, scored) or _lineage_problems(record, scored)
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
    rule = registry().get(rule_id)
    committed = _committed(CASES / f"{rule_id}.jsonl") if rule else None
    cases = [json.loads(line) for line in committed[1].splitlines() if line.strip()] if committed else []
    refusal = "rule_not_committed" if not rule else "cases_not_committed" if not committed else \
        None if cases and all(_dual_labelled(c) for c in cases) else "cases_lack_two_agreeing_labels"
    if refusal:
        return {"rule": rule_id, "state": "incomplete", "errors": 0, "models": [], "first_error": refusal,
                "spent_usd": round(budget.spent, 6)}
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
                  "cases_blob": committed[0]}  # the blob actually scored, not a fresh HEAD lookup
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
    scored = load_scored(rule_id)
    problems = calibration.verify(record, scored) or _lineage_problems(record, scored)
    if problems:
        return "FAIL", problems
    paths = [RECORDS / f"{rule_id}.json", RECORDS / f"{rule_id}.scored.jsonl"]
    if not all(p.resolve().is_relative_to(ROOT) for p in paths):
        return "AA", ["records not inside the repository"]
    files = [str(p.resolve().relative_to(ROOT)) for p in paths]
    tracked = all(_git("ls-files", f) for f in files)
    clean = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD", "--", *files]).returncode == 0
    return ("AAA", []) if tracked and clean else ("AA", ["not bound to HEAD"])
