"""Score skill routing on the labelled corpus: today's intent table, lexical only, lexical + Jev.

usage: python -m evals.skill_routing.run --library <skills-library checkout> \
           [--corpus evals/skill_routing/corpus.jsonl] [--split heldout|tune|all] \
           [--jev --ledger <sqlite> --cap-usd 5] [--k 20] [--min-confidence 0.5] [--out report.json]

The Jev mode needs TYPESAFE_API_KEY in this process's environment. Without it the mode is
reported NOT RUN, never scored as zero. Every live call is reserved in a cost ledger first.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path
from urllib import request

from app.server.jev_transport import no_redirect_opener
from evals.skill_routing.generate_corpus import catalogue as inventory
from src.tao import skill_router as sr
from src.tao import skills as tao_skills

CALL_TOKENS = 48_000  # pack questions into one Jev call up to this estimate (model max 64k)
JEV_URL = "https://api.typesafe.ai/v1/systemone"


def usd(text: str) -> float:
    """A finite, non-negative dollar amount. NaN would make every cap comparison false."""
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a dollar amount: {text!r}") from None
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError(f"cap must be a finite amount >= 0, got {text!r}")
    return value


def load_skills(library: Path) -> dict[str, dict]:
    """Every skill in the inventory with its body, so loaded tokens can be counted."""
    skills = dict(tao_skills.load_all_skills())
    for name, item in inventory(library).items():
        if item["home"] == "library":
            meta, body = tao_skills._parse_frontmatter((library / "skills" / name / "SKILL.md").read_text("utf-8"))
            skills[name] = {"name": name, "description": item["description"], "body": body}
    return skills


def table_mode(case: dict, skills: dict[str, dict]) -> tuple[list[str], int]:
    """Today's path: keyword intent -> hand table -> brief.py's 800-char/4000-char injection."""
    from app.server.brief import classify_intent

    names = [n for n in tao_skills._INTENT_SKILLS.get(classify_intent(case["text"]), []) if n in skills]
    chars = 0
    for n in names:
        chars = min(chars + min(len(skills[n].get("body", "")), 800), 4000)
    return names, chars // sr.CHARS_PER_TOKEN


def jev_batch(batch: list[tuple[int, str, list[tuple[str, str]]]], key: str) -> dict:
    from scripts.mission_control_jev_shadow import MODEL, redact

    state, questions = {}, {}
    for i, text, options in batch:
        state[f"r{i}"] = redact(text)[:2000]
        criteria = {n: d[:sr.DESC_CHARS] or n for n, d in options} | {sr.NO_MATCH: "None of these skills fits the request."}
        questions[f"q{i}"] = {"type": "choice", "instructions": f"Which skill does `r{i}` need?", "criteria": criteria}
    body = json.dumps({"model": MODEL, "state": state, "questions": questions}).encode()
    req = request.Request(JEV_URL, data=body, method="POST",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    # No redirects: the request carries the Bearer key (skill-router review round 8).
    with no_redirect_opener().open(req, timeout=60) as resp:
        return {"questions": questions, "result": json.loads(resp.read())}


def score(rows: list[dict]) -> dict:
    pos = [r for r in rows if r["expected"] is not None]
    neg = [r for r in rows if r["expected"] is None]
    return {
        "cases": len(rows),
        "top1_accuracy": round(sum(r["expected"] in r["picked"][:1] for r in pos) / max(len(pos), 1), 4),
        "shortlist_recall": round(sum(r["expected"] in r.get("shortlist", []) for r in pos) / max(len(pos), 1), 4),
        "no_match_precision": round(sum(not r["picked"] for r in neg) / max(len(neg), 1), 4),
        "mean_skill_tokens": round(sum(r["tokens"] for r in rows) / max(len(rows), 1), 1),
    }


def lexical_rows(cases: list[dict], cat: list, skills: dict, args) -> list[dict]:
    rows = []
    for c in cases:
        d = sr.route(c["text"], catalogue=cat, skills=skills, jev=None, k=args.k)
        rows.append({**c, "picked": d.skills, "shortlist": d.shortlist, "tokens": d.tokens})
    return rows


def jev_rows(cases: list[dict], cat: list, skills: dict, args, key: str) -> tuple[list[dict], dict]:
    from scripts.mission_control_jev_shadow import RESERVED_INPUT_TOKENS_PER_CALL, finish_call, reserve_call

    by_name = {c.name: c for c in cat}
    rows, cost, latencies = [], {"input_tokens": 0, "calls": 0, "errors": 0}, []
    pending = [(i, c, sr.shortlist(c["text"], cat, args.k)) for i, c in enumerate(cases)]
    rows += [{**c, "picked": [], "shortlist": [], "tokens": 0} for _, c, s in pending if not s]
    pending = [p for p in pending if p[2]]
    for chunk, _estimate in packed(pending, by_name):
        # Reserve the most one answer can bill, not the packing estimate the answer may exceed.
        call_id = reserve_call(args.ledger, RESERVED_INPUT_TOKENS_PER_CALL, args.cap_usd)
        if call_id is None:
            raise SystemExit(f"cost cap ${args.cap_usd} reached after {cost['calls']} calls; nothing further sent")
        t0 = time.monotonic()
        try:
            out = jev_batch([(i, c["text"], [(n, by_name[n].description) for n, _ in s]) for i, c, s in chunk], key)
        except Exception as exc:
            finish_call(args.ledger, call_id, f"error:{type(exc).__name__}")
            cost["errors"] += 1
            rows += [{**c, "picked": ["<jev_error>"], "shortlist": [n for n, _ in s], "tokens": 0} for _, c, s in chunk]
            continue
        latencies.append(time.monotonic() - t0)
        used = int(out["result"].get("usage", {}).get("input_tokens", 0))
        finish_call(args.ledger, call_id, "answered", used)
        cost["input_tokens"] += used
        cost["calls"] += 1
        rows += chunk_rows(out, chunk, skills, args, cost)
    latencies.sort()
    cost["usd"] = round(cost["input_tokens"] * 0.042 / 1_000_000, 4)
    cost["p50_s"] = round(latencies[len(latencies) // 2], 2) if latencies else None
    cost["p95_s"] = round(latencies[int(len(latencies) * 0.95) - 1], 2) if latencies else None
    return rows, cost


def estimate_tokens(text: str, names: list[str], by_name: dict) -> int:
    chars = len(text) + sum(len(n) + len(by_name[n].description[:sr.DESC_CHARS]) + 8 for n in names)
    return chars // 4 + 60


def packed(pending: list, by_name: dict):
    """Yield (chunk, estimated_tokens): as many questions per Jev call as fit CALL_TOKENS."""
    chunk, total = [], 0
    for item in pending:
        cost = estimate_tokens(item[1]["text"], [n for n, _ in item[2]], by_name)
        if chunk and total + cost > CALL_TOKENS:
            yield chunk, total
            chunk, total = [], 0
        chunk.append(item)
        total += cost
    if chunk:
        yield chunk, total


def chunk_rows(out: dict, chunk: list, skills: dict, args, cost: dict) -> list[dict]:
    """Turn one batched Jev reply into rows, through the router's own decision rule."""
    from scripts.mission_control_jev_shadow import validate_answer

    rows = []
    for i, c, s in chunk:
        q = out["questions"][f"q{i}"]
        ans = validate_answer(f"q{i}", out["result"].get("answers", {}).get(f"q{i}"), q)
        d = sr.RouteDecision(shortlist=[n for n, _ in s])
        if ans is None:
            cost["errors"] += 1
            rows.append({**c, "picked": ["<malformed>"], "shortlist": d.shortlist, "tokens": 0})
            continue
        d = sr.apply_answer(d, ans["label"], ans["confidence"], skills, args.budget, args.min_confidence)
        rows.append({**c, "picked": d.skills, "shortlist": d.shortlist, "tokens": d.tokens,
                     "confidence": ans["confidence"]})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", type=Path, required=True)
    ap.add_argument("--corpus", type=Path, default=Path("evals/skill_routing/corpus.jsonl"))
    ap.add_argument("--split", default="heldout", choices=["heldout", "tune", "all"])
    ap.add_argument("--jev", action="store_true")
    ap.add_argument("--ledger", type=Path)
    ap.add_argument("--cap-usd", type=usd, default=5.0)
    ap.add_argument("--k", type=int, default=sr.SHORTLIST)
    ap.add_argument("--min-confidence", type=float, default=sr.MIN_CONFIDENCE)
    ap.add_argument("--budget", type=int, default=sr.DEFAULT_BUDGET)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--rows-out", type=Path, help="write every Jev row (with confidence) as JSONL")
    args = ap.parse_args()
    cases = [json.loads(line) for line in args.corpus.read_text("utf-8").splitlines() if line.strip()]
    cases = [c for c in cases if args.split == "all" or c["split"] == args.split][: args.limit or None]
    skills = load_skills(args.library)
    cat = sr.build_catalogue(skills)
    report = {"split": args.split, "k": args.k, "min_confidence": args.min_confidence, "skills": len(skills)}
    table = [{**c, "picked": (t := table_mode(c, skills))[0], "tokens": t[1]} for c in cases]
    report["table"] = score(table)
    report["lexical"] = score(lexical_rows(cases, cat, skills, args))
    key = os.environ.get("TYPESAFE_API_KEY")
    if args.jev and key and args.ledger:
        rows, cost = jev_rows(cases, cat, skills, args, key)
        report["jev"] = {**score(rows), **cost}
        if args.rows_out:
            args.rows_out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    else:
        report["jev"] = "NOT RUN: needs --jev, --ledger and TYPESAFE_API_KEY in the environment"
    text = json.dumps(report, indent=1)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
