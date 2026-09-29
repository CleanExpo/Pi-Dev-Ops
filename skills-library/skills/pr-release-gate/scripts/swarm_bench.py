#!/usr/bin/env python3
"""swarm_bench.py — measure which OpenRouter models can actually do review work.

Runs every feasible model against a corpus of REAL defects with known ground truth
(swarm_bench_corpus.json) and scores whether the model names the actual mechanism.

Why a defect corpus and not a self-graded rubric: a model that says "looks fine"
scores identically to a broken one unless you plant defects it must catch. Same
plant-and-catch discipline the calibration gate uses on skills.

Scoring is deliberately mechanical and auditable — substring hits on mechanism-specific
terms, with the matched terms printed — so a ranking can be re-derived from the raw
answers rather than trusted.

Usage:
  swarm_bench.py --models-json /tmp/feasible.json [--max-cost 0.20] [--concurrency 10]
  swarm_bench.py --models "a/b,c/d"
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

URL = "https://openrouter.ai/api/v1/chat/completions"
CORPUS = pathlib.Path(__file__).with_name("swarm_bench_corpus.json")


def ask(model: str, case: dict, key: str, timeout: int) -> dict:
    prompt = (
        f"You are reviewing {case['language']} code for defects.\n\n"
        f"```{case['language']}\n{case['code']}\n```\n\n"
        f"{case['question']}\n\n"
        "Answer in at most 120 words. Name the precise mechanism, not a general concern."
    )
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 1200,
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        r = json.load(urllib.request.urlopen(req, timeout=timeout))
    except urllib.error.HTTPError as e:
        return {"ok": False, "err": f"HTTP{e.code}"}
    except Exception as e:
        return {"ok": False, "err": type(e).__name__}
    if "choices" not in r:
        return {"ok": False, "err": "no_choices"}
    m = r["choices"][0].get("message", {})
    txt = m.get("content") or m.get("reasoning") or ""
    u = r.get("usage", {})
    return {
        "ok": True,
        "text": txt,
        "in": u.get("prompt_tokens", 0),
        "out": u.get("completion_tokens", 0),
        "s": round(time.time() - t0, 1),
    }


def score(answer: str, case: dict) -> tuple[bool, list[str]]:
    """HIT when the answer names the mechanism, not merely the symptom.

    Rule: >=2 distinct mechanism terms, or >=1 term plus every must_mention token.
    Terms are returned so any ranking can be audited against the raw answer.
    """
    low = (answer or "").lower()
    hits = [t for t in case["kill_terms"] if t.lower() in low]
    musts = [t for t in case["must_mention"] if t.lower() in low]
    ok = len(hits) >= 2 or (len(hits) >= 1 and len(musts) == len(case["must_mention"]))
    return ok, hits


def run_model(model: str, cases: list[dict], key: str, timeout: int) -> dict:
    got, cost_in, cost_out, secs, detail, errs = 0, 0, 0, 0.0, [], []
    for case in cases:
        r = ask(model, case, key, timeout)
        if not r["ok"]:
            errs.append(f"{case['id']}:{r['err']}")
            detail.append((case["id"], False, []))
            continue
        ok, hits = score(r["text"], case)
        got += int(ok)
        cost_in += r["in"]
        cost_out += r["out"]
        secs += r["s"]
        detail.append((case["id"], ok, hits))
    return {
        "model": model,
        "score": got,
        "total": len(cases),
        "in": cost_in,
        "out": cost_out,
        "secs": round(secs, 1),
        "errors": errs,
        "detail": detail,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-json")
    ap.add_argument("--models")
    ap.add_argument("--max-cost", type=float, default=1e9)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--out", default="/tmp/swarm-bench-results.json")
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER_API_KEY not set", file=sys.stderr)
        return 2

    cases = json.loads(CORPUS.read_text())["cases"]
    if args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    else:
        entries = json.loads(pathlib.Path(args.models_json).read_text())
        models = [
            e["id"]
            for e in entries
            if 0 <= e.get("est_cost", 0) <= args.max_cost
        ]

    print(f"benchmarking {len(models)} models on {len(cases)} real defects "
          f"(concurrency={args.concurrency})")
    results = []
    with cf.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futs = {pool.submit(run_model, m, cases, key, args.timeout): m for m in models}
        for i, fut in enumerate(cf.as_completed(futs), 1):
            r = fut.result()
            results.append(r)
            flag = "!" if r["errors"] else " "
            print(f"[{i:3}/{len(models)}]{flag} {r['model'][:52]:54} "
                  f"{r['score']}/{r['total']}  {r['secs']}s")

    results.sort(key=lambda r: (-r["score"], r["secs"]))
    pathlib.Path(args.out).write_text(json.dumps(results, indent=2))

    print("\n=== PERFECT SCORERS (found every planted defect) ===")
    perfect = [r for r in results if r["score"] == r["total"]]
    for r in perfect:
        print(f"  {r['model']:56} {r['score']}/{r['total']}  {r['secs']:6}s")
    print(f"\nperfect={len(perfect)}  "
          f"partial={sum(1 for r in results if 0 < r['score'] < r['total'])}  "
          f"zero={sum(1 for r in results if r['score'] == 0)}")
    print(f"results: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
