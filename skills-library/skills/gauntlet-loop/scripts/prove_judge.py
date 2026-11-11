#!/usr/bin/env python3
"""Blind, two-order pairwise judge: current vs challenger.

Every case is judged twice — once with the current output as A, once with it as B.
A verdict (overall or per criterion) counts only when both orders agree; otherwise
it is a tie. Outputs are never labelled old/new.

Input: JSONL, one case per line:
  {"id": "case-1",
   "task": "one sentence: the job the output must do",        # or pass --task
   "criteria": [{"key": "accuracy", "description": "..."}],   # or pass --criteria FILE.json
   "context": "the real input / source material",
   "current": "output of the current version",
   "challenger": "output of the challenger",
   "current_check": "optional AUTOMATED CHECK result for current",
   "challenger_check": "optional AUTOMATED CHECK result for challenger"}

Output: JSONL verdicts (one per case) for scripts/scoreboard.py.

Judge must be a different vendor from both contestants. Estate work is usually built by
Claude, so the default is a non-Anthropic model through OpenRouter:
  --provider openrouter (default; needs OPENROUTER_API_KEY; pip install openai)
  --provider openai     (needs OPENAI_API_KEY;   pip install openai)
  --provider anthropic  (needs ANTHROPIC_API_KEY; pip install anthropic) only when no contestant is Claude
  --provider mock       fixed verdicts for testing the pipeline; never evidence
Keys are read from the environment, then from ~/.hermes/.env (values are never printed).

Example:
  python prove_judge.py cases.jsonl --out verdicts.jsonl --model <openrouter-model-id>

Adapted from prove-it-better scripts/judge.py (MIT, Hamish Davison).
"""
import argparse, concurrent.futures as cf, json, os, sys
from pathlib import Path

OPENROUTER_URL = "https://openrouter.ai/api/v1"


def key(name):
    """An API key from the environment, else from ~/.hermes/.env (the estate's secret store)."""
    if os.environ.get(name):
        return os.environ[name]
    env = Path.home() / ".hermes" / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            k, _, v = line.partition("=")
            if k.strip().removeprefix("export ").strip() == name:
                return v.strip().strip('"').strip("'")
    sys.exit(f"{name} is not set (checked the environment and ~/.hermes/.env)")

SYSTEM = (
    "You are an impartial expert evaluator. You compare two outputs, A and B, produced for the same job "
    "from the same context. Judge only how well each does the job described, using the criteria given. "
    "Do not reward length or polish over substance. Facts in the context outrank claims in the outputs. "
    "If an AUTOMATED CHECK line is given for an output, trust it over your own impression. "
    "When the outputs are equally good on a criterion, say tie. List concrete defects for each output: "
    "specific, checkable problems, not general impressions."
)


def build_schema(keys):
    crit = {
        k: {
            "type": "object",
            "properties": {"winner": {"type": "string", "enum": ["A", "B", "tie"]}, "reason": {"type": "string"}},
            "required": ["winner", "reason"],
            "additionalProperties": False,
        }
        for k in keys
    }
    return {
        "type": "object",
        "properties": {
            "criteria": {"type": "object", "properties": crit, "required": list(keys), "additionalProperties": False},
            "overall": {"type": "string", "enum": ["A", "B", "tie"]},
            "overall_reason": {"type": "string"},
            "defects_A": {"type": "array", "items": {"type": "string"}},
            "defects_B": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["criteria", "overall", "overall_reason", "defects_A", "defects_B"],
        "additionalProperties": False,
    }


def prompt_for(case, a, b, a_check, b_check):
    crit = "\n".join(f"- {c['key']}: {c['description']}" for c in case["criteria"])
    def block(label, out, check):
        head = f"=== OUTPUT {label} ===\n"
        if check:
            head += f"AUTOMATED CHECK: {check}\n\n"
        return head + out
    return (
        f"JOB: {case['task']}\n\nCRITERIA:\n{crit}\n\n=== CONTEXT ===\n{case.get('context', '')}\n\n"
        f"{block('A', a, a_check)}\n\n{block('B', b, b_check)}\n\n"
        "Judge each criterion, give an overall verdict, and list defects for A and B."
    )


def call_judge(args, case, a, b, a_check, b_check):
    keys = [c["key"] for c in case["criteria"]]
    schema = build_schema(keys)
    user = prompt_for(case, a, b, a_check, b_check)
    if args.provider == "mock":  # pipeline test only: A wins every criterion
        return validate({"criteria": {k: {"winner": "A", "reason": "mock"} for k in keys}, "overall": "A",
                         "overall_reason": "mock", "defects_A": [], "defects_B": ["mock defect"]}, keys)
    if args.provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=key("ANTHROPIC_API_KEY"))
        r = client.messages.create(
            model=args.model,
            max_tokens=12000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in r.content if b.type == "text")
        if not text:
            raise RuntimeError(f"judge returned no verdict (stop_reason={r.stop_reason})")
        return validate(json.loads(text), keys)
    import openai
    if args.provider == "openrouter":
        client = openai.OpenAI(base_url=OPENROUTER_URL, api_key=key("OPENROUTER_API_KEY"))
    else:
        client = openai.OpenAI(api_key=key("OPENAI_API_KEY"))
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    try:
        r = client.chat.completions.create(
            model=args.model, messages=messages,
            response_format={"type": "json_schema", "json_schema": {"name": "verdict", "schema": schema, "strict": True}},
        )
    except openai.BadRequestError:
        # Some OpenRouter models do not support strict schemas; ask for the same shape as JSON.
        messages[0]["content"] += " Reply with one JSON object matching this schema: " + json.dumps(schema)
        r = client.chat.completions.create(model=args.model, messages=messages,
                                           response_format={"type": "json_object"})
    return validate(json.loads(r.choices[0].message.content), keys)


VERDICTS = ("A", "B", "tie")


def validate(v, keys):
    """Every reply, from every provider and fallback, must match the verdict schema exactly.
    A malformed reply fails the case (reported as an error), never counts as a verdict."""
    def bad(why):
        raise RuntimeError(f"judge reply does not match the verdict schema: {why}")
    if not isinstance(v, dict) or set(v) != {"criteria", "overall", "overall_reason", "defects_A", "defects_B"}:
        bad(f"top-level fields {sorted(v) if isinstance(v, dict) else type(v).__name__}")
    crit = v["criteria"]
    if not isinstance(crit, dict) or set(crit) != set(keys):
        bad(f"criteria keys {sorted(crit) if isinstance(crit, dict) else crit!r}, expected {sorted(keys)}")
    for k, c in crit.items():
        if not isinstance(c, dict) or set(c) != {"winner", "reason"} or c["winner"] not in VERDICTS \
                or not isinstance(c["reason"], str):
            bad(f"criterion {k!r}: {c!r}")
    if v["overall"] not in VERDICTS or not isinstance(v["overall_reason"], str):
        bad(f"overall {v['overall']!r}")
    for side in ("defects_A", "defects_B"):
        if not isinstance(v[side], list) or not all(isinstance(x, str) for x in v[side]):
            bad(f"{side} must be a list of strings")
    return v


def to_side(winner, current_is_a):
    if winner not in VERDICTS:
        raise RuntimeError(f"unknown verdict {winner!r}")
    if winner == "tie":
        return "tie"
    a_wins = winner == "A"
    return "current" if a_wins == current_is_a else "challenger"


def judge_case(args, case):
    if args.task and "task" not in case:
        case["task"] = args.task
    if args.criteria_list and "criteria" not in case:
        case["criteria"] = args.criteria_list
    cur, cha = case["current"], case["challenger"]
    cc, hc = case.get("current_check"), case.get("challenger_check")
    v1 = call_judge(args, case, cur, cha, cc, hc)   # current = A
    v2 = call_judge(args, case, cha, cur, hc, cc)   # current = B
    first, second = to_side(v1["overall"], True), to_side(v2["overall"], False)
    overall = first if first == second else "tie"
    crit = {}
    for c in case["criteria"]:
        k = c["key"]
        s1 = to_side(v1["criteria"][k]["winner"], True)
        s2 = to_side(v2["criteria"][k]["winner"], False)
        crit[k] = s1 if s1 == s2 else "tie"
    return {
        "id": case.get("id"),
        "overall": overall,
        "consistent": first == second,
        "criteria": crit,
        "challenger_defects": v1["defects_B"] + v2["defects_A"],
        "current_defects": v1["defects_A"] + v2["defects_B"],
        "reasons": [v1["overall_reason"], v2["overall_reason"]],
        "raw_orders": [first, second],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cases", help="JSONL file of cases")
    ap.add_argument("--out", required=True, help="JSONL file for verdicts")
    ap.add_argument("--provider", choices=["openrouter", "openai", "anthropic", "mock"], default="openrouter")
    ap.add_argument("--model", help="judge model id (required except for --provider mock)")
    ap.add_argument("--task", help="task sentence for cases that omit it")
    ap.add_argument("--criteria", help="JSON file with a criteria list for cases that omit it")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    if not args.model and args.provider != "mock":
        sys.exit(f"--model is required with --provider {args.provider}")
    args.criteria_list = json.load(open(args.criteria)) if args.criteria else None
    cases = [json.loads(l) for l in open(args.cases) if l.strip()]

    results = []
    with cf.ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(judge_case, args, c): c for c in cases}
        for f in cf.as_completed(futs):
            c = futs[f]
            try:
                r = f.result()
            except Exception as e:  # keep going; a failed case is reported, not dropped silently
                r = {"id": c.get("id"), "error": str(e)[:300]}
            results.append(r)
            print(f"{r.get('id')}: {r.get('overall', 'ERROR ' + r.get('error', ''))}", file=sys.stderr)
    with open(args.out, "w") as fh:
        for r in results:
            fh.write(json.dumps(r) + "\n")
    print(f"wrote {len(results)} verdicts to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
