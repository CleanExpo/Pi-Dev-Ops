"""Single reviewer pass — invoked as a subprocess by 03_quality_gate.py.

Reads the candidate draft on stdin, runs `claude --print --model haiku-4-5`
against a specialist reviewer prompt (QA Lead / Brand Guardian / Contrarian),
emits a one-line JSON verdict.

Per [[feedback-model-routing-max-first]] — Max-plan Haiku via `claude --print`
is $0 marginal. Per PoLL paper (Cohere 2024, arXiv 2404.18796) panel of
smaller models outperforms single large judge at 7x less cost. Per
finding Q1.5 (TPR>96%, TNR<25%) minority-veto aggregation across
specialised roles is the documented mitigation.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

REVIEWER_PROMPTS = {
    "qa-lead": """You are the QA Lead reviewer for Unite-Group. Per the wiki page
QA Lead, you hold every deliverable against a pass/fail rubric. Review the
candidate draft below. Apply this rubric:

1. Factual accuracy — every claim verifiable, no hallucination, no fabricated citation
2. Acceptance match — does this answer the question the user actually asked
3. No incomplete sections, no TODO markers, no placeholder text
4. No code that wouldn't run (if any code present)
5. No claims about state that contradict observable session reality

You are biased toward catching FAILURES (not toward approving). When uncertain,
return NO with the specific reason. The literature shows LLM judges have
TPR>96% but TNR<25% — your job is to fight that bias and catch the FAIL.

Reply with ONLY a JSON object on a single line:
{"reviewer":"qa-lead","verdict":"PASS"|"NO","confidence":"high"|"medium"|"low","reason":"<10-30 words>"}""",

    "brand-guardian": """You are the Brand Guardian reviewer for Unite-Group. Per
[[feedback-design-preferences]] Rule 6 (Nexus UI scope) + per-brand BrandConfig
(unite #E55A2B + #1E293B; CCW #D62828 + #003049; RA #1C2E47; DR #0B2545; NRPG
#059669; CARSI #2563EB; Synthex #FF6B35; John-Coutis #1A1A1A). Per
[[feedback-make-calls-not-questions]] and [[feedback-tight-code]].

Review the candidate draft below. Apply this rubric:
1. Founder voice — direct, no waffle, no trailing "want me to" questions
2. No options-without-recommendation
3. No unsolicited summary tables when one sentence would do
4. No AI-slop language (uplifting, exciting, leverage, robust, seamless, leverage)
5. Brand tokens correctly scoped (Nexus UI vs per-brand video — don't conflate)

You are biased toward catching FAILURES. TNR<25% literature applies — return NO
when uncertain.

Reply with ONLY a JSON object on a single line:
{"reviewer":"brand-guardian","verdict":"PASS"|"NO","confidence":"high"|"medium"|"low","reason":"<10-30 words>"}""",

    "contrarian": """You are the Contrarian reviewer for Unite-Group Pi-CEO Board.
Your job is adversarial stress-test, not approval. Per finding Q5 (When AIs Judge
AIs, arXiv 2508.02994) adversarial-pair pattern is literature-validated for
catching quality regressions.

Review the candidate draft below. Find the strongest reason it's WRONG:
1. Hidden unverified assumption that everyone else would accept silently
2. Claim that sounds confident but has no citation, no measurement, no source
3. Sequencing or dependency the draft glossed over
4. False dichotomy or missed alternative
5. Pattern that worked last time but won't work this time

Return NO unless you cannot find ANY meaningful weakness. Be willing to be
wrong; being too lenient is worse than being too harsh per TNR<25% problem.

Reply with ONLY a JSON object on a single line:
{"reviewer":"contrarian","verdict":"PASS"|"NO","confidence":"high"|"medium"|"low","reason":"<10-30 words>"}""",
}


def review(role: str, draft: str, timeout_s: int = 60) -> dict:
    """Run a single reviewer pass via `claude --print --model haiku-4-5`.

    Returns dict matching the verdict schema. On any subprocess error,
    returns a default-safe NO with low confidence (favours blocking)."""
    if role not in REVIEWER_PROMPTS:
        return {"reviewer": role, "verdict": "NO", "confidence": "low",
                "reason": f"unknown role {role}", "_error": "unknown-role"}

    prompt = REVIEWER_PROMPTS[role] + "\n\n--- CANDIDATE DRAFT ---\n\n" + draft[:30000] + "\n\n--- END DRAFT ---"
    try:
        result = subprocess.run(
            ["claude", "--print", "--model", "claude-haiku-4-5-20251001"],
            input=prompt, capture_output=True, text=True,
            timeout=timeout_s,
            env={**os.environ, "CLAUDE_CODE_DISABLE_TELEMETRY": "1"},
        )
    except subprocess.TimeoutExpired:
        return {"reviewer": role, "verdict": "NO", "confidence": "low",
                "reason": f"reviewer timeout after {timeout_s}s", "_error": "timeout"}
    except (OSError, subprocess.SubprocessError) as e:
        return {"reviewer": role, "verdict": "NO", "confidence": "low",
                "reason": f"reviewer subprocess error: {type(e).__name__}", "_error": str(e)[:200]}

    out = (result.stdout or "").strip()
    # Find the JSON line — model may add prose before/after
    import re
    m = re.search(r"\{[^{}\n]*\"reviewer\"[^{}\n]*\}", out)
    if not m:
        return {"reviewer": role, "verdict": "NO", "confidence": "low",
                "reason": "reviewer returned non-JSON output",
                "_error": "non-json", "_raw": out[:400]}
    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"reviewer": role, "verdict": "NO", "confidence": "low",
                "reason": "reviewer JSON parse failed",
                "_error": "json-parse", "_raw": m.group(0)[:400]}

    if parsed.get("verdict") not in ("PASS", "NO"):
        return {"reviewer": role, "verdict": "NO", "confidence": "low",
                "reason": "reviewer returned invalid verdict",
                "_error": "invalid-verdict", "_raw": json.dumps(parsed)[:400]}
    return parsed


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True, choices=list(REVIEWER_PROMPTS.keys()))
    ap.add_argument("--timeout", type=int, default=60)
    ns = ap.parse_args(argv[1:])
    draft = sys.stdin.read()
    if not draft.strip():
        sys.stdout.write(json.dumps({"reviewer": ns.role, "verdict": "PASS",
                                     "confidence": "low",
                                     "reason": "empty draft — skipped"}))
        return 0
    started = time.time()
    verdict = review(ns.role, draft, timeout_s=ns.timeout)
    verdict["_elapsed_s"] = round(time.time() - started, 1)
    sys.stdout.write(json.dumps(verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
