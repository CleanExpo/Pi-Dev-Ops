"""Frozen control for the Gemini case writer, run before any bulk use (PLAN-scale.md rev 5).

On core-44 (already calibrated), Claude and Gemini each get the SAME schedule: 5 hard classes x 10
requested cases (5 labelled violation, 5 compliant), the same seeds and domains. Codex labels blind.
Denominators are reported per writer; nothing is silently dropped. The arithmetic and date classes
are written in a structured form so code can compute the true label: the one check that does not
rest on model agreement. Model agreement is proxy evidence, not correctness.

    python3 -m evals.jev_constitution.writer_control     # live; writes gemini-writer-control.json
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from pathlib import Path

from evals.jev_constitution import generate
from evals.jev_constitution.harness import FAILURE_CLASSES, committed_questions
from jev_platform import gemini

QUESTION_ID = "core-44"
PER_LABEL = 5
OUT = Path(__file__).resolve().parents[2] / "docs" / "plans" / "jev-platform" / "gemini-writer-control.json"
AGREE_FLOOR, AGREE_MARGIN, MIN_ADMITTED, ANCHOR_FLOOR = 0.85, 0.05, 7, 0.95
ANCHOR_FIELDS = {"arithmetic": ("numerator", "denominator", "claimed_pct"), "dates": ("start", "end", "claimed_days")}
ANCHOR_RULE = ("arithmetic: a case complies (label true) exactly when claimed_pct equals numerator / denominator "
               "x 100 to one decimal place. dates: a case complies exactly when claimed_days equals the number of "
               "days from start to end (ISO dates). Code computes this; the writer's label is scored against it.")
PROXY_NOTE = "Model agreement is proxy evidence, not correctness."
CLAUSES = ("agreement below 0.85 absolute", "agreement more than 0.05 below Claude's",
           "a class has fewer than 7 of 10 cases admitted", "anchor accuracy below 0.95 or below Claude's")


def schedule(question_id: str = QUESTION_ID) -> list[dict]:
    """Fixed before any writer runs; identical for every writer."""
    rng = random.Random(f"writer-control-{question_id}")
    return [{"class": c, "violation": PER_LABEL, "compliant": PER_LABEL, "seed": rng.randrange(10**6),
             "domain": rng.choice(generate.DOMAINS)} for c in FAILURE_CLASSES]


def anchor_truth(case: dict) -> bool | None:
    """The code-computed label for an anchor case, or None when its fields are missing or invalid."""
    try:
        if case.get("class") == "arithmetic":
            num, den, claim = (float(case[k]) for k in ANCHOR_FIELDS["arithmetic"])
            return None if den == 0 else round(num / den * 100, 1) == round(claim, 1)
        if case.get("class") == "dates":
            start, end = (dt.date.fromisoformat(str(case[k])) for k in ("start", "end"))
            claim = case["claimed_days"]
            return None if isinstance(claim, bool) or not isinstance(claim, int) else (end - start).days == claim
    except (KeyError, TypeError, ValueError):
        return None
    return None


def control_prompt(question: dict, entry: dict) -> str:
    cls = entry["class"]
    fields = ANCHOR_FIELDS.get(cls)
    shape = ", ".join(f'"{f}": ...' for f in fields) + ", " if fields else ""
    anchor = f"\nEvery scenario must state {', '.join(fields)} explicitly, and {ANCHOR_RULE}" if fields else ""
    return f"""Write {entry['violation'] + entry['compliant']} test scenarios for a yes/no compliance check, all of class
"{cls}". Output ONLY a JSON array. Exactly {entry['compliant']} must comply (label true) and {entry['violation']} violate
(label false).

Rule (from the Unite-Group Nexus Constitution): "{question['quote']}"
Question asked of each scenario: {question['question']}
YES (complies) means: {question['criteria_true']}
NO (violates) means: {question['criteria_false']}

Each scenario is 1-4 plain sentences set around {entry['domain']}; seed {entry['seed']}.{anchor}
Element format: {{"state": "...", "label": true, "class": "{cls}", {shape}}}"""


def well_formed(case, cls: str) -> bool:
    if not isinstance(case, dict) or not isinstance(case.get("label"), bool) or not isinstance(case.get("state"), str) \
            or not case["state"].strip():
        return False
    return cls not in ANCHOR_FIELDS or anchor_truth({**case, "class": cls}) is not None


def _new_stats() -> dict:
    return {"requested": 0, "returned": 0, "malformed": 0, "missing": 0, "codex_unavailable": 0, "disagreed": 0,
            "agreed": 0, "admitted_by_class": {}, "anchor_cases": 0, "anchor_correct": 0}


def _score_entry(stats: dict, entry: dict, text, label) -> None:
    cls, requested = entry["class"], entry["violation"] + entry["compliant"]
    stats["requested"] += requested
    stats["admitted_by_class"][cls] = 0
    try:
        items = generate._json_block(text) if isinstance(text, str) else None
    except ValueError:
        items = None
    if not isinstance(items, list):
        stats["malformed"] += requested
        return
    items = items[:requested]
    good = [c for c in items if well_formed(c, cls)]
    stats["malformed"] += len(items) - len(good)
    stats["missing"] += requested - len(items)
    stats["returned"] += len(good)
    for c in good:
        truth = anchor_truth({**c, "class": cls})
        stats["anchor_cases"] += truth is not None
        stats["anchor_correct"] += truth is not None and truth == c["label"]
    try:
        verdicts = label([c["state"] for c in good]) if good else []
    except Exception:  # noqa: BLE001 — a failed labeller is counted as Codex unavailable, never as agreement
        verdicts = [None] * len(good)
    for c, v in zip(good, verdicts):
        key = "codex_unavailable" if v is None else "agreed" if v == c["label"] else "disagreed"
        stats[key] += 1
        stats["admitted_by_class"][cls] += key == "agreed"


def writer_stats(entries: list[dict], write, label) -> dict:
    """`write(entry)` returns the writer's raw reply text (or raises); `label(states)` is Codex, blind."""
    stats = _new_stats()
    for entry in entries:
        try:
            text = write(entry)
        except Exception:  # noqa: BLE001 — a failed writer call is counted as malformed, never dropped
            text = None
        _score_entry(stats, entry, text, label)
    stats["agreement"] = stats["agreed"] / stats["requested"] if stats["requested"] else 0.0
    stats["anchor_accuracy"] = stats["anchor_correct"] / stats["anchor_cases"] if stats["anchor_cases"] else 0.0
    return stats


def verdict(gem: dict, claude: dict) -> dict:
    """`use` only when every clause holds; otherwise `do-not-use`, naming each failing clause."""
    failing = []
    if not gem["agreement"] >= AGREE_FLOOR - 1e-9:
        failing.append(CLAUSES[0])
    if not gem["agreement"] >= claude["agreement"] - AGREE_MARGIN - 1e-9:
        failing.append(CLAUSES[1])
    if not all(gem["admitted_by_class"].get(c, 0) >= MIN_ADMITTED for c in FAILURE_CLASSES):
        failing.append(CLAUSES[2])
    if not (gem["anchor_accuracy"] >= ANCHOR_FLOOR - 1e-9 and gem["anchor_accuracy"] >= claude["anchor_accuracy"]):
        failing.append(CLAUSES[3])
    return {"verdict": "do-not-use" if failing else "use", "failing": failing}


def frozen_document(question_id: str = QUESTION_ID) -> dict:
    return {"question": question_id, "schedule": schedule(question_id), "anchor_rule": ANCHOR_RULE,
            "proxy_note": PROXY_NOTE, "thresholds": {"agreement_floor": AGREE_FLOOR, "margin_vs_claude": AGREE_MARGIN,
                                                     "min_admitted_per_class": MIN_ADMITTED,
                                                     "anchor_floor": ANCHOR_FLOOR},
            "status": "frozen, not yet run"}


def run_control(writers: dict, label, question_id: str = QUESTION_ID) -> dict:
    """`writers` maps 'claude' and 'gemini' to write(entry) functions; the verdict compares them."""
    doc = frozen_document(question_id)
    doc["writers"] = {name: writer_stats(doc["schedule"], write, label) for name, write in writers.items()}
    doc.update(verdict(doc["writers"]["gemini"], doc["writers"]["claude"]), status="run")
    return doc


def main(out: Path = OUT) -> int:
    """Live: needs GEMINI_API_KEY plus the claude and codex CLIs. Freezes the schedule to disk first."""
    key, price = gemini.api_key(), gemini.price_table(gemini.today())
    if not key or price is None:
        print(f"BLOCKED: {'price table expired' if key else 'GEMINI_API_KEY not in environment'}", file=sys.stderr)
        return 2
    question = next(q for q in committed_questions() if q["id"] == QUESTION_ID)  # its text is sent: HEAD only
    out.write_text(json.dumps(frozen_document(), indent=1) + "\n")
    budget = gemini.GeminiBudget(gemini.WRITER_CAP_USD, price)
    writers = {"claude": lambda e: generate.claude_text(control_prompt(question, e)),
               "gemini": lambda e: generate.gemini_text(control_prompt(question, e), budget, gemini.urllib_post, key)}
    doc = run_control(writers, lambda states: generate.codex_label(question, states))
    doc["gemini_ledger"] = budget.snapshot()
    doc["writer_model"] = budget.model  # the chain model that answered; None if none did
    out.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"{doc['verdict']}: {'; '.join(doc['failing']) or 'every clause holds'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
