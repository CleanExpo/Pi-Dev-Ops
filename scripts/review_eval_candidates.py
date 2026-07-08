#!/usr/bin/env python3
"""Founder promotion CLI — eval candidates → evals/golden/feedback_loop.yaml.

RA-7014 slice 4 (spec: docs/specs/spec-cap5-slice4-online-eval.md).

Shows each pending captured candidate with a judge opinion (ADVISORY — the
binary judge is calibrated on intent_router, not threads) and an LLM-drafted
synthetic paraphrase. ONLY an explicit human accept writes to the golden file,
and what is written is the paraphrase — never the captured (redacted) text.

Usage:
    uv run python scripts/review_eval_candidates.py           # Supabase queue
    uv run python scripts/review_eval_candidates.py --local   # local JSONL fallback
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.server.agents.feedback_loop import (  # noqa: E402
    _NEGATIVE_KEYWORDS,
    _POSITIVE_KEYWORDS,
)

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "evals" / "golden" / "feedback_loop.yaml"
LOCAL_QUEUE = Path(".harness/eval-candidates/candidates.jsonl")
VALID_LABELS = ("positive", "negative", "neutral")


def keyword_tier(paraphrase: str, label: str) -> str:
    """'keyword' only when the frozen keyword classifier is decidable AND agrees
    with the founder label — otherwise 'llm', so a promotion can never land a
    case that immediately fails the blocking CI suite."""
    has_neg = any(kw in paraphrase for kw in _NEGATIVE_KEYWORDS)
    has_pos = any(kw in paraphrase for kw in _POSITIVE_KEYWORDS)
    verdict = "negative" if has_neg else ("positive" if has_pos else "neutral")
    return "keyword" if (has_neg or has_pos) and verdict == label else "llm"


def candidate_to_golden(candidate: dict[str, Any], paraphrase: str, label: str) -> dict[str, Any]:
    """Build the golden case dict. Uses ONLY the human-approved paraphrase —
    thread_redacted (client-derived) is deliberately not referenced."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return {
        "id": f"promoted-{candidate.get('pipeline_id', 'unknown')}-{stamp}",
        "tier": keyword_tier(paraphrase, label),
        "comments": [paraphrase],
        "state": candidate.get("state", ""),
        "days_since": int(candidate.get("days_since") or 0),
        "expected": label,
    }


_GOLDEN_HEADER = """\
# Prove-It golden suite — feedback_loop outcome classifier (RA-7014 slice 4).
#
# Grown ONLY via scripts/review_eval_candidates.py — every case is a
# HUMAN-ACCEPTED synthetic paraphrase; client-derived text never enters this
# file (grill NO-GO, Grills/08b-prove-it-gate-online-eval.md).
#
# tier: keyword → asserted deterministically against _detect_signal (CI-safe)
# tier: llm     → schema-validated only in keyless CI
"""


def append_golden_case(golden_path: Path, case: dict[str, Any]) -> None:
    doc = yaml.safe_load(golden_path.read_text()) if golden_path.exists() else {"cases": []}
    doc["cases"].append(case)
    golden_path.write_text(
        _GOLDEN_HEADER + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    )


def _claude_p(prompt: str, timeout: int = 60) -> str | None:
    """One-shot `claude -p` with ambient auth. None on any failure."""
    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", "sonnet", prompt],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,  # never let the child consume the CLI's stdin
        )
        out = proc.stdout.strip()
        return out if proc.returncode == 0 and out else None
    except Exception:  # noqa: BLE001 — drafting is best-effort
        return None


def judge_opinion(candidate: dict[str, Any]) -> str:
    predicted = candidate.get("predicted_category") or "?"
    answer = _claude_p(
        "You are a strict eval judge. Thread (already PII-redacted):\n"
        f"{candidate.get('thread_redacted', '')}\n\n"
        f"The classifier said the post-ship outcome is '{predicted}'. Reply with exactly "
        "one word — the correct category: positive, negative or neutral."
    )
    answer = (answer or "").strip().lower()
    if answer in VALID_LABELS:
        return f"judge suggests: {answer} (classifier said: {predicted})"
    return f"judge unavailable (classifier said: {predicted})"


def draft_paraphrase(candidate: dict[str, Any]) -> str | None:
    return _claude_p(
        "Rewrite this (already PII-redacted) Linear thread as a SYNTHETIC equivalent for a "
        "public test dataset: same outcome signals, same tone and shape, but invented "
        "company/product/people details with zero overlap with the original strings. "
        "Reply with the rewritten thread only.\n\n"
        f"{candidate.get('thread_redacted', '')}"
    )


def load_local_candidates(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [r for r in rows if r.get("status") == "pending"]


def _save_local_status(path: Path, captured_at: str, status: str) -> None:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for r in rows:
        if r.get("captured_at") == captured_at:
            r["status"] = status
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def review(local: bool, limit: int) -> int:
    if local:
        candidates = load_local_candidates(LOCAL_QUEUE)[:limit]
        mark = lambda c, s: _save_local_status(LOCAL_QUEUE, c["captured_at"], s)  # noqa: E731
    else:
        from app.server.supabase_log import (  # noqa: PLC0415
            select_eval_candidates,
            update_eval_candidate_status,
        )
        candidates = select_eval_candidates(limit=limit)
        mark = lambda c, s: update_eval_candidate_status(c["id"], s)  # noqa: E731

    if not candidates:
        src = "local JSONL" if local else "Supabase"
        print(f"queue empty ({src}) — capture flag is ON only if TAO_EVAL_SAMPLING=1 in prod")
        return 0

    print("NOTE: judge suggestions are ADVISORY (calibrated on intent_router, not threads)\n")
    promoted = rejected = skipped = 0
    for i, cand in enumerate(candidates, 1):
        print(f"── candidate {i}/{len(candidates)} · {cand.get('pipeline_id')} "
              f"· {cand.get('captured_at')} " + "─" * 20)
        print(cand.get("thread_redacted", "")[:2000])
        print(f"\n{judge_opinion(cand)}")
        draft = draft_paraphrase(cand)
        print(f"\ndrafted paraphrase:\n{draft}" if draft else "\nno draft — write your own")

        action = input("\n[a]ccept draft / [e]dit paraphrase / [r]eject / [s]kip / [q]uit: ").strip().lower()
        if action == "q":
            break
        if action == "s" or action not in {"a", "e", "r"}:
            skipped += 1
            continue
        if action == "r":
            mark(cand, "rejected")
            rejected += 1
            continue
        paraphrase = draft if action == "a" and draft else ""
        while not paraphrase.strip():
            paraphrase = input("synthetic paraphrase: ").strip()
        label = ""
        while label not in VALID_LABELS:
            label = input(f"label {VALID_LABELS}: ").strip().lower()
        case = candidate_to_golden(cand, paraphrase, label)
        append_golden_case(GOLDEN_PATH, case)
        mark(cand, "promoted")
        promoted += 1
        print(f"wrote {case['id']} (tier={case['tier']}) to {GOLDEN_PATH.name}:")
        print(yaml.safe_dump({"cases": [case]}, sort_keys=False))

    print(f"\ndone: promoted={promoted} rejected={rejected} skipped={skipped}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--local", action="store_true", help="read the local JSONL fallback queue")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()
    return review(args.local, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
