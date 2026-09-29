"""Advisory Jev triage for synthetic Mission Control browser receipts.

Offline by default. No result from this script changes a browser assertion or release gate.
Live mode accepts synthetic snapshots only until real-data egress has a separate review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib import error, request

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"  # Pinned so the reviewed price/context and evaluation remain comparable.
USD_PER_MILLION_INPUT = 0.042
MAX_TEXT = 24_000
MAX_REQUEST_BYTES = 32_000
RESERVED_INPUT_TOKENS_PER_CALL = 64_000  # Model maximum in the reviewed Mission Control contract.
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
J1_OPTIONS = {
    "REAL_DATA": "A signed-in user sees actual project data.",
    "EXPLICIT_EMPTY_STATE": "The page plainly says that no records exist.",
    "ERROR_SHOWN": "The page plainly shows a failed operation or unavailable source.",
    "STUCK_LOADING": "The page remains in a loading state.",
    "AUTH_WALL": "The user sees a sign-in or access-denied screen.",
    "NO_MATCH": "The available evidence does not support another option.",
}
J2_OPTIONS = {
    "PRODUCT_BUG": "The application behaved incorrectly.",
    "TEST_BUG": "The assertion or test setup is wrong.",
    "ENVIRONMENT": "A dependency, deployment, credential or network failed.",
    "TIMING": "The observed ordering or wait is the likely cause.",
    "NO_MATCH": "The evidence cannot distinguish these causes.",
}
SECRET = re.compile(
    r"(?:sk-ant-api[\w-]{30,}|ghp_[A-Za-z0-9]{36}|lin_api_[A-Za-z0-9]{40}|"
    r"AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9]{48}|(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}|"
    r"\b\d{8,10}:AA[A-Za-z0-9_-]{32,}|\bBearer\s+[A-Za-z0-9._~+/-]{20,}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{20,})",
    re.IGNORECASE,
)
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", re.DOTALL)
ASSIGNMENT = re.compile(r"\b(password|passwd|pwd|secret|api_key|apikey|token)[\"']?\s*[:=]\s*[\"']?[^\s,}\"']+", re.IGNORECASE)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
IDENTIFIER = re.compile(r"\b(?:RA-\d+|[A-Z]{2,8}-\d+|gh_(?:issue|pr)_\d+)\b")


def redact(value: str) -> str:
    """Mask known credentials and contact details; input is still synthetic-only for egress."""
    value = PRIVATE_KEY.sub("[REDACTED_SECRET]", value)
    value = SECRET.sub("[REDACTED_SECRET]", value)
    value = ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED_SECRET]", value)
    value = EMAIL.sub("[REDACTED_EMAIL]", value)
    return IDENTIFIER.sub(
        lambda match: "[ID:" + hashlib.sha256(match.group().encode()).hexdigest()[:12] + "]", value
    )


def clean_network_calls(snapshot: dict) -> list[dict]:
    """Keep only method, path without query, and status from observed calls."""
    calls = snapshot.get("network_calls", [])
    if not isinstance(calls, list) or len(calls) > 200:
        raise ValueError("invalid network_calls")
    clean_calls = []
    for call in calls:
        if not isinstance(call, dict) or call.get("method") not in ALLOWED_METHODS:
            raise ValueError("invalid network call")
        path, status = call.get("path"), call.get("status")
        if not isinstance(path, str) or not path.startswith("/") or type(status) is not int or not 100 <= status <= 599:
            raise ValueError("invalid network call")
        clean_calls.append({"method": call["method"], "path": redact(path.split("?", 1)[0])[:200], "status": status})
    return clean_calls


def build_questions(snapshot: dict, state: dict) -> dict:
    """Select typed advisory questions from allowlisted snapshot fields."""
    questions = {
        "J1": {"type": "choice", "instructions": "What does the signed-in user visibly see?", "criteria": J1_OPTIONS}
    }
    failure = snapshot.get("failure")
    if failure is not None:
        if not isinstance(failure, str) or len(failure) > 4000:
            raise ValueError("invalid failure")
        state["failure"] = redact(failure)
        questions["J2"] = {"type": "choice", "instructions": "What most likely caused `failure`?", "criteria": J2_OPTIONS}
    action = snapshot.get("action")
    if action is not None:
        if not isinstance(action, str) or len(action) > 200:
            raise ValueError("invalid action")
        state["action"] = redact(action)
        questions["J3"] = {
            "type": "noul",
            "instructions": "Did the control labelled `action` cause exactly its described effect, given `network_calls`?",
            "criteria": {"true": "The label and observed effect agree.", "false": "The effect differs or evidence is missing."},
        }
    assertions = snapshot.get("assertions")
    if assertions is not None:
        if not isinstance(assertions, list) or len(assertions) > 30 or any(not isinstance(x, str) or len(x) > 250 for x in assertions):
            raise ValueError("invalid assertions")
        state["assertions"] = [redact(item) for item in assertions]
        questions["J4"] = {
            "type": "score", "instructions": "How well do `assertions` cover the visible features?",
            "criteria": [
                "Almost no visible features are asserted.",
                "Only a few key features are asserted.",
                "Most key features are asserted, with gaps.",
                "All visible features have meaningful assertions.",
                "All visible features and important failure paths have meaningful assertions.",
            ],
        }
    return questions


def prepare(snapshot: dict) -> tuple[dict, dict]:
    """Allowlist fields so browser headers, cookies and request bodies never enter state."""
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be an object")
    for field in ("run_id", "sha", "surface", "visible_text"):
        if not isinstance(snapshot.get(field), str) or not snapshot[field]:
            raise ValueError(f"missing or invalid {field}")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", snapshot["run_id"]):
        raise ValueError("invalid run_id")
    if not re.fullmatch(r"[a-fA-F0-9]{7,40}", snapshot["sha"]):
        raise ValueError("invalid sha")
    if not re.fullmatch(r"/(?:[A-Za-z0-9_-]+/?)*", snapshot["surface"]) or len(snapshot["surface"]) > 150:
        raise ValueError("invalid surface")
    state = {"visible_text": redact(snapshot["visible_text"][:MAX_TEXT]), "network_calls": clean_network_calls(snapshot)}
    questions = build_questions(snapshot, state)
    payload = {"model": MODEL, "state": state, "questions": questions}
    if len(json.dumps(payload, ensure_ascii=False).encode()) > MAX_REQUEST_BYTES:
        raise ValueError("redacted request exceeds size limit")
    dirty = snapshot.get("workspace_dirty")
    if dirty is not None and type(dirty) is not bool:
        raise ValueError("invalid workspace_dirty")
    return payload, {
        "run_id": snapshot["run_id"], "sha": snapshot["sha"], "surface": snapshot["surface"],
        "workspace_dirty": dirty,
    }


def validate_answer(name: str, answer: object, question: dict) -> dict | None:
    if not isinstance(answer, dict) or answer.get("type") != question["type"]:
        return None
    if question["type"] == "noul":
        value = answer.get("noul")
        return {"probability": value} if type(value) in (float, int) and 0 <= value <= 1 else None
    probabilities, confidence = answer.get("probabilities"), answer.get("confidence")
    if not isinstance(probabilities, dict) or type(confidence) not in (float, int) or not 0 <= confidence <= 1:
        return None
    expected = set(question["criteria"] if question["type"] == "choice" else map(str, range(len(question["criteria"]))))
    if set(probabilities) != expected or any(type(value) not in (float, int) or not 0 <= value <= 1 for value in probabilities.values()):
        return None
    if abs(sum(probabilities.values()) - 1) > 0.02:
        return None
    if question["type"] == "choice":
        choice = answer.get("choice")
        if choice not in expected:
            return None
        return {"label": choice, "probabilities": probabilities, "confidence": confidence}
    score = answer.get("score")
    if type(score) not in (float, int) or not 0 <= score <= len(expected) - 1:
        return None
    return {"score": score, "probabilities": probabilities, "confidence": confidence}


def reserve_call(ledger: Path, estimated_tokens: int, cap: float | None = None) -> int | None:
    """Record each attempted call before egress; optionally enforce a daily ceiling."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    day = datetime.now(UTC).date().isoformat()
    charge = estimated_tokens * USD_PER_MILLION_INPUT / 1_000_000
    with sqlite3.connect(ledger, timeout=30, isolation_level=None) as db:
        db.execute("CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, day TEXT NOT NULL, reserved_usd REAL NOT NULL, actual_usd REAL, input_tokens INTEGER, status TEXT NOT NULL, created_at TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT COALESCE(SUM(reserved_usd), 0) FROM calls WHERE day=?", (day,)).fetchone()[0]
        if cap is not None and current + charge > cap:
            db.execute("ROLLBACK")
            return None
        call_id = db.execute(
            "INSERT INTO calls(day, reserved_usd, status, created_at) VALUES (?, ?, ?, ?)",
            (day, charge, "attempted", datetime.now(UTC).isoformat()),
        ).lastrowid
        db.execute("COMMIT")
    return call_id


def finish_call(ledger: Path, call_id: int, status: str, input_tokens: int | None = None) -> None:
    actual = input_tokens * USD_PER_MILLION_INPUT / 1_000_000 if input_tokens is not None else None
    with sqlite3.connect(ledger, timeout=30) as db:
        db.execute(
            "UPDATE calls SET status=?, input_tokens=?, actual_usd=? WHERE id=?",
            (status, input_tokens, actual, call_id),
        )


def evaluate(payload: dict, api_key: str, opener=request.urlopen) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode()
    req = request.Request(API_URL, data=body, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    with opener(req, timeout=15) as response:
        result = json.loads(response.read(128_000))
    usage = result.get("usage") if isinstance(result, dict) else None
    if (not isinstance(result, dict) or result.get("model") != MODEL
            or not isinstance(result.get("answers"), dict) or not isinstance(usage, dict)
            or type(usage.get("input_tokens")) is not int
            or not 0 <= usage["input_tokens"] <= RESERVED_INPUT_TOKENS_PER_CALL):
        raise TypeError("invalid API response")
    return result


def run_line(snapshot: dict, *, live: bool, key: str | None = None, ledger: Path | None = None, cap: float | None = None, opener=request.urlopen) -> dict:
    payload, receipt = prepare(snapshot)
    receipt.update({
        "mode": "shadow" if live else "offline", "contract": "mission-control-jev-r1",
        "evaluated_at": datetime.now(UTC).isoformat(), "model": None,
        "labels": {name: "NOT_EVALUATED" for name in payload["questions"]},
    })
    if not live:
        return receipt
    if snapshot.get("data_classification") != "synthetic":
        receipt["reason"] = "REAL_DATA_EGRESS_NOT_APPROVED"
        return receipt
    if not key or ledger is None:
        receipt["reason"] = "KEY_OR_LEDGER_UNAVAILABLE"
        return receipt
    # Reserve the reviewed model maximum when an optional cap is configured.
    call_id = reserve_call(ledger, RESERVED_INPUT_TOKENS_PER_CALL, cap)
    if call_id is None:
        receipt["reason"] = "DAILY_BUDGET_EXHAUSTED"
        return receipt
    try:
        result = evaluate(payload, key, opener)
        receipt["model"] = result.get("model") if isinstance(result.get("model"), str) else None
        usage = result.get("usage", {})
        if isinstance(usage, dict) and type(usage.get("input_tokens")) is int:
            receipt["input_tokens"] = usage["input_tokens"]
            receipt["input_cost_usd"] = round(usage["input_tokens"] * USD_PER_MILLION_INPUT / 1_000_000, 10)
        finish_call(ledger, call_id, "answered", receipt.get("input_tokens"))
        for name, question in payload["questions"].items():
            receipt["labels"][name] = validate_answer(name, result["answers"].get(name), question) or "NOT_EVALUATED"
    except (error.URLError, TimeoutError, TypeError, ValueError, json.JSONDecodeError):
        finish_call(ledger, call_id, "unverified")
        receipt["reason"] = "JEV_UNAVAILABLE_OR_INVALID"
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSONL browser snapshots")
    parser.add_argument("output", type=Path, help="JSONL advisory receipts (no source text)")
    parser.add_argument("--live-synthetic", action="store_true", help="Send synthetic snapshots only to TypeSafe")
    parser.add_argument("--ledger", type=Path, help="Persistent per-call cost ledger required for live calls")
    parser.add_argument("--daily-cap", type=float, default=None, help="Optional USD/day stop; default is uncapped")
    args = parser.parse_args(argv)
    env_cap = os.getenv("JEV_DAILY_CAP_USD", "").strip()
    try:
        cap = args.daily_cap if args.daily_cap is not None else (float(env_cap) if env_cap else None)
    except ValueError:
        parser.error("JEV_DAILY_CAP_USD must be a positive finite number")
    if cap is not None and (not math.isfinite(cap) or cap <= 0):
        parser.error("daily cap must be a positive finite number")
    key = os.getenv("TYPESAFE_API_KEY")
    if args.live_synthetic and (not key or args.ledger is None):
        parser.error("live synthetic mode requires TYPESAFE_API_KEY and --ledger")
    if args.input.resolve() == args.output.resolve():
        parser.error("input and output paths must differ")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    counts = {"records": 0, "evaluated": 0, "not_evaluated": 0}
    with args.input.open(encoding="utf-8") as source, args.output.open("w", encoding="utf-8") as target:
        for line in source:
            if not line.strip():
                continue
            receipt = run_line(json.loads(line), live=args.live_synthetic, key=key, ledger=args.ledger, cap=cap)
            target.write(json.dumps(receipt, sort_keys=True) + "\n")
            counts["records"] += 1
            if any(value != "NOT_EVALUATED" for value in receipt["labels"].values()):
                counts["evaluated"] += 1
            else:
                counts["not_evaluated"] += 1
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
