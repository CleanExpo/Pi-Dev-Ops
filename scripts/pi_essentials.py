#!/usr/bin/env python3
"""
pi_essentials.py — Pi-CEO in 200 lines.

"If you understand this file, you understand Pi-CEO's algorithmic essence."

This is the minimal Ship Chain with zero external dependencies:
  parse_brief() → classify_intent() → build_spec() → generate() → evaluate() → ship()

No Linear, no Supabase, no Telegram, no Railway. Just the algorithm.
Run it: python scripts/pi_essentials.py "add a hello-world endpoint" /tmp/my-repo

RA-680 / Karpathy-7 reference implementation.
"""
import os
import re
import json
import time
import shutil
import tempfile
import subprocess
import sys

# ── 1. BRIEF PARSING ──────────────────────────────────────────────────────────
#
# Pi-CEO reads a plain-English brief and classifies it into one of 5 intent
# categories (PITER: Product, Implementation, Testing, Evaluation, Research).
# The intent drives which Agent Developer Workflow (ADW) template is selected.

_INTENT_KEYWORDS = {
    "hotfix": ["hotfix", "urgent", "critical fix", "production down", "p0"],
    "bug":    ["bug", "fix", "broken", "error", "crash", "regression"],
    "chore":  ["refactor", "rename", "upgrade", "lint", "cleanup", "migrate"],
    "spike":  ["research", "investigate", "explore", "prototype", "benchmark"],
    "feature":["add", "implement", "create", "build", "new", "feature"],
}

def classify_intent(brief: str) -> str:
    """Classify brief into hotfix | bug | chore | spike | feature."""
    lower = brief.lower()
    for intent in ["hotfix", "bug", "chore", "spike", "feature"]:
        if any(kw in lower for kw in _INTENT_KEYWORDS[intent]):
            return intent
    return "feature"


# ── 2. SPEC CONSTRUCTION ─────────────────────────────────────────────────────
#
# The classified intent selects an ADW workflow template. The template wraps
# the raw brief with step-by-step instructions + a quality gate that the agent
# must pass before committing.

_WORKFLOW_STEPS = {
    "feature": "1. DECOMPOSE → 2. BUILD → 3. TEST → 4. REVIEW → 5. COMMIT",
    "bug":     "1. REPRODUCE → 2. DIAGNOSE → 3. FIX → 4. VERIFY → 5. COMMIT",
    "chore":   "1. APPLY → 2. LINT → 3. TEST → 4. COMMIT",
    "spike":   "1. RESEARCH → 2. SUMMARISE → 3. RECOMMEND (write to .harness/spike.md)",
    "hotfix":  "PRIORITY: URGENT. 1. REPRODUCE → 2. FIX → 3. VERIFY → 4. COMMIT",
}

_QUALITY_GATE = """
BEFORE COMMITTING, self-score on 4 dimensions (must each score ≥8/10):
  COMPLETENESS — every requirement in the brief addressed
  CORRECTNESS  — no bugs, no security issues, tests pass
  CONCISENESS  — no dead code, no debug prints, no TODOs
  FORMAT       — matches existing naming/indentation conventions exactly
"""

def build_spec(brief: str, intent: str, repo_url: str = "") -> str:
    """Wrap raw brief in ADW workflow instructions + quality gate."""
    return (
        f"Project: {repo_url or '(local)'}\n"
        f"Intent: {intent.upper()}\n\n"
        f"Workflow:\n{_WORKFLOW_STEPS[intent]}\n\n"
        f"Brief:\n{brief}\n"
        f"{_QUALITY_GATE}\n"
        f"After all steps: git add -A && git commit -m '{intent}: <description>'"
    )


# ── 3. CODE GENERATION ───────────────────────────────────────────────────────
#
# The spec is sent to Claude via `claude -p` (the CLI, non-interactive mode).
# Claude reads the workspace, edits files, and commits the result.
# Pi-CEO's production path uses the Agent SDK; this demo uses the CLI directly.

def generate(spec: str, workspace: str, model: str = "sonnet", timeout: int = 300) -> bool:
    """Run Claude on the spec in the given workspace. Returns True on success."""
    if not shutil.which("claude"):
        print("  [SKIP] `claude` CLI not found — install Claude Code to run generation")
        return True  # demo mode: pretend it worked

    cmd = ["claude", "--dangerously-skip-permissions", "-p", spec,
           "--model", model, "--output-format", "stream-json", "--verbose"]
    try:
        proc = subprocess.run(
            cmd, cwd=workspace, capture_output=True, text=True, timeout=timeout
        )
        # Stream-JSON lines contain {"type":"text","text":"..."} events
        for line in proc.stdout.splitlines():
            try:
                evt = json.loads(line)
                if evt.get("type") == "text":
                    print(f"  {evt['text'][:120]}")
            except json.JSONDecodeError:
                pass
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"  [ERROR] Generation timed out after {timeout}s")
        return False


# ── 4. EVALUATION ─────────────────────────────────────────────────────────────
#
# After generation, a second Claude pass reviews the diff against the original
# brief. It scores on 4 dimensions and returns an OVERALL: <score>/10 line.
# Scores below the threshold trigger a retry (up to max_retries times).

_EVAL_PROMPT = """You are a senior code reviewer. Score the diff below against the original brief.

ORIGINAL BRIEF:
{brief}

GIT DIFF (last commit):
{diff}

Score on 4 dimensions (1-10) and give a final overall score:
COMPLETENESS: <n>/10 — <reason>
CORRECTNESS:  <n>/10 — <reason>
CONCISENESS:  <n>/10 — <reason>
FORMAT:       <n>/10 — <reason>
OVERALL: <average>/10 — PASS or FAIL (threshold: {threshold}/10)
CONFIDENCE: <0-100>% — <how certain are you?>
"""

def evaluate(workspace: str, brief: str, threshold: float = 8.0) -> tuple[float, str]:
    """Run the evaluator. Returns (score, eval_text). Score=0 on failure."""
    # Get the diff from the last commit
    result = subprocess.run(
        ["git", "diff", "HEAD~1"], cwd=workspace,
        capture_output=True, text=True, timeout=15
    )
    diff = result.stdout[:6000] if result.stdout else "(no diff)"

    if not shutil.which("claude"):
        print("  [SKIP] Evaluator: `claude` CLI not found — demo score = 8.5/10")
        return 8.5, "OVERALL: 8.5/10 — PASS"

    prompt = _EVAL_PROMPT.format(brief=brief, diff=diff, threshold=threshold)
    cmd = ["claude", "--dangerously-skip-permissions", "-p", prompt,
           "--model", "sonnet", "--output-format", "text"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        text = proc.stdout
        # Parse OVERALL: <score>/10
        for line in text.splitlines():
            if line.upper().startswith("OVERALL:"):
                try:
                    score = float(re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", line).group(1))
                    return score, text
                except (AttributeError, ValueError):
                    pass
    except subprocess.TimeoutExpired:
        print("  [ERROR] Evaluator timed out")
    return 0.0, ""


# ── 5. SHIP DECISION ─────────────────────────────────────────────────────────
#
# The evaluator score determines the outcome:
#   score >= threshold         → PASS  (auto-ship)
#   score <  threshold, retries remain → RETRY the generator
#   score <  threshold, no retries    → WARN (ship anyway, log lesson)

def decide(score: float, threshold: float, attempt: int, max_retries: int) -> str:
    """Returns 'pass', 'retry', or 'warn'."""
    if score >= threshold:
        return "pass"
    if attempt < max_retries:
        return "retry"
    return "warn"


# ── 6. THE SHIP CHAIN (main loop) ────────────────────────────────────────────
#
# Everything above is wired together here. This is the algorithm:
#
#   brief → classify → spec → generate → evaluate → decide → ship
#                                   ↑_____retry_____↓

def run_ship_chain(
    brief: str,
    workspace: str,
    repo_url: str = "",
    model: str = "sonnet",
    threshold: float = 8.0,
    max_retries: int = 2,
) -> dict:
    """Run the full Ship Chain. Returns {score, status, attempts, duration_s}."""
    t0 = time.monotonic()
    intent = classify_intent(brief)
    spec   = build_spec(brief, intent, repo_url)

    print(f"\n🚀 Ship Chain — intent={intent.upper()} model={model} threshold={threshold}/10")
    print(f"   Brief: {brief[:80]}")

    score, status = 0.0, "error"
    for attempt in range(max_retries + 1):
        print(f"\n[BUILD] Attempt {attempt + 1}/{max_retries + 1}")
        if not generate(spec, workspace, model=model):
            print("  [ERROR] Generation failed")
            break

        print("\n[EVAL]  Scoring...")
        score, eval_text = evaluate(workspace, brief, threshold)
        print(f"  Score: {score:.1f}/10 (threshold: {threshold}/10)")

        outcome = decide(score, threshold, attempt, max_retries)
        if outcome == "pass":
            status = "passed"
            print(f"\n✅ PASS — {score:.1f}/10 — build shipped")
            break
        elif outcome == "retry":
            print(f"  ↺ Below threshold — retrying (attempt {attempt + 2})")
            # Inject the evaluator feedback into the retry spec
            spec = spec + f"\n\n--- RETRY {attempt + 1}: previous score {score:.1f}/10 ---\n{eval_text[-500:]}"
        else:  # warn
            status = "warned"
            print(f"\n⚠️  WARN — {score:.1f}/10 — shipped with warning")
            break

    duration = time.monotonic() - t0
    return {"score": score, "status": status, "attempts": attempt + 1, "duration_s": round(duration, 1)}


# ── DEMO ─────────────────────────────────────────────────────────────────────

def _make_demo_workspace() -> str:
    """Create a minimal git repo for the demo."""
    d = tempfile.mkdtemp(prefix="pi-essentials-demo-")
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.email", "demo@pi-ceo.io"], cwd=d)
    subprocess.run(["git", "config", "user.name", "Pi-CEO Demo"], cwd=d)
    readme = os.path.join(d, "README.md")
    open(readme, "w").write("# Demo repo\n")
    subprocess.run(["git", "add", "."], cwd=d, check=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=d, check=True)
    return d


if __name__ == "__main__":
    brief     = sys.argv[1] if len(sys.argv) > 1 else "add a hello-world function to main.py"
    workspace = sys.argv[2] if len(sys.argv) > 2 else None

    if workspace is None:
        workspace = _make_demo_workspace()
        print(f"Demo workspace: {workspace}")
        cleanup = True
    else:
        cleanup = False

    result = run_ship_chain(brief, workspace)
    print(f"\nResult: {result}")

    if cleanup:
        shutil.rmtree(workspace, ignore_errors=True)
