"""jev_triage.py — advisory Jev triage over Mission Control browser-run snapshots (WP-10).

Reads journey snapshots (JSONL), redacts them, asks TypeSafe Jev the J1–J4 questions in
docs/plans/mission-control/jev-decision-contracts.md, and writes ADVISORY labels (JSONL).
A label never changes a pass/fail or a grade; it only orders the triage queue.

Request/response shape is TypeSafe's documented one (docs.typesafe.ai quick start,
fetched 2026-09-28): POST /v1/systemone {state, model, questions:{id:{type,
instructions, criteria}}} -> {model, answers:{id:{...}}, usage:{input_tokens}}.

Safety rails, all enforced before any byte leaves the machine:
  * secrets and PII are redacted (swarm.tmux_validator + swarm.pii_redactor);
  * state is truncated to MAX_STATE_TOKENS (Jev allows 32k for state + longest question);
  * a per-UTC-day ledger records spend, and stops calls only if a cap is set
    (JEV_DAILY_CAP_USD or --daily-cap; uncapped by founder decision 2026-09-28);
  * --dry-run (the default) prints request bodies and sends nothing.

Usage:
    python scripts/jev_triage.py --snapshots run.jsonl --out labels.jsonl [--live]
Snapshot line: {"run_id","sha","surface","contract":"J1|J2|J3|J4","page_text",
                "network":[{"method","path","status"}], "assertion"?, "label"?}
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from swarm.pii_redactor import redact as _redact_pii  # noqa: E402
from swarm.tmux_validator import redact_secrets as _redact_secrets  # noqa: E402

log = logging.getLogger("jev_triage")

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
PRICE_PER_MTOK_INPUT = 0.042  # docs.typesafe.ai/models, 2026-09-28; output tokens are free
# Founder decision 2026-09-28: no daily cap on Jev while the system is used heavily.
# Spend is still recorded per day; set JEV_DAILY_CAP_USD to reinstate a cap.
DAILY_CAP_USD: float | None = None
MAX_STATE_TOKENS = 24_000

Transport = Callable[[dict, str], dict]

QUESTIONS: dict[str, dict] = {
    "J1": {"type": "choice",
           "instructions": "Given this page's visible text and its network calls, which best "
                           "describes what a signed-in user sees?",
           "criteria": {"REAL_DATA": "Content loaded from the live backend is shown",
                        "EXPLICIT_EMPTY_STATE": "The page says plainly there is nothing to show",
                        "ERROR_SHOWN": "An error or failure message is shown",
                        "STUCK_LOADING": "Only loading indicators or placeholders are shown",
                        "AUTH_WALL": "A sign-in prompt or access refusal is shown",
                        "NO_MATCH": "None of these describe the page"}},
    "J2": {"type": "choice",
           "instructions": "Given this failing check's assertion message, page text and network "
                           "calls, what is the most likely cause of the failure?",
           "criteria": {"PRODUCT_BUG": "The application behaves incorrectly",
                        "TEST_BUG": "The check itself is wrong or looks for the wrong thing",
                        "ENVIRONMENT": "Deployment, credentials or network were unavailable",
                        "TIMING": "The check ran before the page finished updating",
                        "NO_MATCH": "None of these explain the failure"}},
    "J3": {"type": "noul",
           "instructions": "The control's label accurately describes the effect of the network "
                           "calls it made, and it caused no other effect."},
    "J4": {"type": "score",
           "instructions": "How well do the listed assertions cover this page's visible features?",
           "criteria": ["Almost nothing on the page is checked", "A few features are checked",
                        "About half the features are checked", "Most features are checked",
                        "Every visible feature is checked"]},
}


def estimate_tokens(text: str) -> int:
    """Upper-leaning estimate (≈4 chars/token) used only for pre-call budgeting."""
    return math.ceil(len(text) / 4)


def redact_state(text: str) -> str:
    """Secrets first (keys, tokens), then PII (emails, phones) — before any egress."""
    no_secrets, _ = _redact_secrets(text)
    return _redact_pii(no_secrets).redacted_payload


def build_state(snap: dict) -> str:
    """Page text + call list (+ assertion/label for J2/J3), redacted and truncated."""
    calls = "\n".join(f"{c.get('method')} {c.get('path')} -> {c.get('status')}"
                      for c in snap.get("network", []))
    parts = [f"PAGE TEXT:\n{snap.get('page_text', '')}", f"NETWORK CALLS:\n{calls}"]
    for key in ("assertion", "label"):
        if snap.get(key):
            parts.append(f"{key.upper()}:\n{snap[key]}")
    state = redact_state("\n\n".join(parts))
    limit = MAX_STATE_TOKENS * 4
    return state if len(state) <= limit else state[:limit] + "\n[TRUNCATED]"


def build_body(snap: dict) -> dict:
    contract = snap["contract"]
    return {"state": build_state(snap), "model": MODEL,
            "questions": {contract.lower(): QUESTIONS[contract]}}


class Ledger:
    """Per-UTC-day spend, persisted so separate runs on one day share the cap."""

    def __init__(self, path: Path, today: str, cap: float | None = DAILY_CAP_USD) -> None:
        self.path, self.today, self.cap = path, today, cap
        data = json.loads(path.read_text()) if path.exists() else {}
        self.spent = float(data.get(today, 0.0))

    def allows(self, tokens: int) -> bool:
        if self.cap is None:
            return True
        return self.spent + tokens * PRICE_PER_MTOK_INPUT / 1e6 <= self.cap

    def record(self, tokens: int) -> None:
        self.spent += tokens * PRICE_PER_MTOK_INPUT / 1e6
        data = json.loads(self.path.read_text()) if self.path.exists() else {}
        data[self.today] = round(self.spent, 6)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        os.replace(tmp, self.path)


def http_transport(body: dict, api_key: str) -> dict:
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {api_key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as res:  # noqa: S310 — fixed https endpoint
        return json.loads(res.read())


def label_row(snap: dict, answer: dict | None, model: str | None, status: str) -> dict:
    return {"run_id": snap.get("run_id"), "sha": snap.get("sha"), "surface": snap.get("surface"),
            "contract": snap["contract"], "mode": "ADVISORY", "status": status,
            "model": model, "answer": answer}


def evaluate(snap: dict, ledger: Ledger, transport: Transport, api_key: str) -> dict:
    """One snapshot -> one advisory label. Never raises on vendor failure."""
    body = build_body(snap)
    tokens = estimate_tokens(body["state"] + json.dumps(body["questions"]))
    if not ledger.allows(tokens):
        return label_row(snap, None, None, "BUDGET_STOP")
    try:
        res = transport(body, api_key)
    except Exception as exc:  # noqa: BLE001 — advisory: a vendor failure is NOT_EVALUATED
        log.warning("jev call failed for %s: %s", snap.get("surface"), exc)
        return label_row(snap, None, None, "NOT_EVALUATED")
    ledger.record(int((res.get("usage") or {}).get("input_tokens") or tokens))
    answer = (res.get("answers") or {}).get(snap["contract"].lower())
    return label_row(snap, answer, res.get("model"), "OK" if answer else "NOT_EVALUATED")


def run(snaps: list[dict], out: Path, ledger: Ledger, transport: Transport | None,
        api_key: str) -> int:
    """Dry run when transport is None: prints bodies, sends nothing. Returns rows written."""
    rows = []
    for snap in snaps:
        if transport is None:
            print(json.dumps(build_body(snap)))
            continue
        rows.append(evaluate(snap, ledger, transport, api_key))
    if rows:
        out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--snapshots", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("jev-labels.jsonl"))
    p.add_argument("--ledger", type=Path, default=Path(".harness/jev-spend.json"))
    p.add_argument("--live", action="store_true", help="send requests (default: dry run)")
    p.add_argument("--daily-cap", type=float, default=None,
                   help="USD/day stop; default JEV_DAILY_CAP_USD env, else no cap")
    a = p.parse_args(argv)
    snaps = [json.loads(line) for line in a.snapshots.read_text().splitlines() if line.strip()]
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if a.live and not key:
        print("TYPESAFE_API_KEY is not set; refusing a live run.", file=sys.stderr)
        return 2
    a.ledger.parent.mkdir(parents=True, exist_ok=True)
    env_cap = os.environ.get("JEV_DAILY_CAP_USD", "").strip()
    cap = a.daily_cap if a.daily_cap is not None else (float(env_cap) if env_cap else DAILY_CAP_USD)
    ledger = Ledger(a.ledger, datetime.now(UTC).date().isoformat(), cap)
    n = run(snaps, a.out, ledger, http_transport if a.live else None, key)
    cap_txt = "no cap" if cap is None else f"cap ${cap:.2f}"
    print(f"wrote {n} advisory labels; spent today ${ledger.spent:.4f} ({cap_txt})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
