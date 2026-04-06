#!/usr/bin/env bash
# scripts/analyze.sh — Pi CEO CLI analysis runner
# Runs all 8 phases locally via Claude Code CLI and pushes .harness/ results to GitHub.
# Usage: ./scripts/analyze.sh <github-repo-url> [model=sonnet] [branch=pidev/analysis-YYYYMMDD]
set -euo pipefail

REPO_URL="${1:?Error: provide a GitHub repo URL.  Usage: ./scripts/analyze.sh https://github.com/owner/repo}"
MODEL="${2:-sonnet}"
DATE=$(date +%Y%m%d)
BRANCH="${3:-pidev/analysis-$DATE}"
REPO_NAME=$(basename "$REPO_URL" .git)
WORKSPACE=$(mktemp -d "/tmp/pi-ceo-XXXXXX")

echo ""
echo "  ██████╗ ██╗     ██████╗███████╗ ██████╗"
echo "  ██╔══██╗██║    ██╔════╝██╔════╝██╔═══██╗"
echo "  ██████╔╝██║    ██║     █████╗  ██║   ██║"
echo "  ██╔═══╝ ██║    ██║     ██╔══╝  ██║   ██║"
echo "  ██║     ██║    ╚██████╗███████╗╚██████╔╝"
echo "  ╚═╝     ╚═╝     ╚═════╝╚══════╝ ╚═════╝"
echo ""
echo "  Pi CEO — Autonomous Code Analysis"
echo "  Repo:   $REPO_URL"
echo "  Model:  $MODEL"
echo "  Branch: $BRANCH"
echo ""

cleanup() { rm -rf "$WORKSPACE"; }
trap cleanup EXIT

# ── Clone repo ────────────────────────────────────────────────────────────────
echo "[1/8] CLONE & INVENTORY"
git clone --depth 1 "$REPO_URL" "$WORKSPACE"
cd "$WORKSPACE"

# Create analysis branch
git checkout -b "$BRANCH"
mkdir -p .harness

# Record file inventory
find . -type f \
  ! -path './.git/*' \
  ! -path './node_modules/*' \
  ! -path './.next/*' \
  ! -path './dist/*' \
  > .harness/file-list.txt

TOTAL_FILES=$(wc -l < .harness/file-list.txt | tr -d ' ')
echo "  Files: $TOTAL_FILES"

# ── Helper: run a claude phase ─────────────────────────────────────────────────
run_phase() {
  local phase_num="$1"
  local phase_name="$2"
  local output_file="$3"
  local prompt="$4"

  echo ""
  echo "[$phase_num/8] $phase_name"
  echo "  Running claude --model $MODEL..."

  claude -p "$prompt" \
    --model "$MODEL" \
    --output-format text \
    > ".harness/$output_file" 2>&1

  echo "  Done → .harness/$output_file"
  git add -A
  git commit -m "audit: phase $phase_num — $phase_name" --quiet
}

# ── Phase 2: Architecture ──────────────────────────────────────────────────────
run_phase 2 "ARCHITECTURE" "phase2-architecture.json" \
"You are a senior architect. Analyse this codebase and output ONLY valid JSON:
{\"techStack\":[\"<tech>\"],\"pattern\":\"<monolith|microservices|serverless|MVC>\",\"entryPoints\":[\"<path>\"],\"keyDependencies\":[\"<package>\"],\"architectureNotes\":\"<2-3 sentences>\"}
Read: $(ls package.json requirements.txt pyproject.toml 2>/dev/null | head -3 | tr '\n' ' ')"

# ── Phase 3: Code Quality ─────────────────────────────────────────────────────
run_phase 3 "CODE QUALITY" "phase3-quality.json" \
"You are a code reviewer applying agentic-review (6 dimensions: Architecture, Naming, Error handling, DRY, Complexity, Conventions).
Output ONLY valid JSON: {\"scores\":{\"completeness\":<1-10>,\"correctness\":<1-10>,\"codeQuality\":<1-10>,\"documentation\":<1-10>},\"issues\":[{\"severity\":\"high|medium|low\",\"file\":\"<path>\",\"description\":\"<issue>\"}],\"securityConcerns\":[\"<concern>\"]}
Analyse the full codebase in this directory."

# ── Phase 4: Context ──────────────────────────────────────────────────────────
run_phase 4 "CONTEXT" "phase4-context.json" \
"Apply context-compressor and big-three (Model/Prompt/Context) skills.
Read all README files and config files. Output ONLY valid JSON:
{\"projectPurpose\":\"<1-2 sentences>\",\"targetUsers\":[\"<type>\"],\"businessLogic\":\"<key rules>\",\"currentState\":\"<production-ready|alpha|prototype|WIP>\",\"keyInsights\":[\"<insight>\"]}"

# ── Phase 5: Gap Analysis ─────────────────────────────────────────────────────
run_phase 5 "GAP ANALYSIS" "phase5-gaps.json" \
"Apply leverage-audit (12 leverage points) and zte-maturity (levels 1-3) skills.
Score each leverage point 1-5. Sum = ZTE score (12-20: Manual, 21-35: Assisted, 36-48: Autonomous, 49-60: ZTE).
Output ONLY valid JSON: {\"zteLevel\":<1|2|3>,\"zteScore\":<12-60>,\"leveragePoints\":[{\"id\":1,\"name\":\"Spec Quality\",\"score\":<1-5>},{\"id\":2,\"name\":\"Context Precision\",\"score\":<1-5>},{\"id\":3,\"name\":\"Model Selection\",\"score\":<1-5>},{\"id\":4,\"name\":\"Tool Availability\",\"score\":<1-5>},{\"id\":5,\"name\":\"Feedback Loops\",\"score\":<1-5>},{\"id\":6,\"name\":\"Error Recovery\",\"score\":<1-5>},{\"id\":7,\"name\":\"Session Continuity\",\"score\":<1-5>},{\"id\":8,\"name\":\"Quality Gating\",\"score\":<1-5>},{\"id\":9,\"name\":\"Cost Efficiency\",\"score\":<1-5>},{\"id\":10,\"name\":\"Trigger Automation\",\"score\":<1-5>},{\"id\":11,\"name\":\"Knowledge Retention\",\"score\":<1-5>},{\"id\":12,\"name\":\"Workflow Standardization\",\"score\":<1-5>}],\"productionGaps\":[\"<gap>\"],\"loadRisks\":[\"<risk>\"]}"

# ── Phase 6: Enhancement Plan ─────────────────────────────────────────────────
run_phase 6 "ENHANCEMENT PLAN" "phase6-sprints.json" \
"Apply piter-framework and agent-workflow skills. Create a prioritised sprint plan.
Output ONLY valid JSON: {\"sprints\":[{\"id\":1,\"name\":\"<name>\",\"duration\":\"<Xd>\",\"items\":[{\"title\":\"<task>\",\"size\":\"S|M|L\",\"priority\":\"P1|P2|P3\"}]}]}"

# ── Phase 7: Executive Summary ────────────────────────────────────────────────
run_phase 7 "EXECUTIVE SUMMARY" "phase7-exec.json" \
"Apply ceo-mode skill. Write a CEO-level one-page summary. Be direct, no fluff.
Output ONLY valid JSON: {\"headline\":\"<one sentence>\",\"currentState\":\"<paragraph>\",\"strengths\":[\"<s>\"],\"weaknesses\":[\"<w>\"],\"risks\":[\"<r>\"],\"opportunities\":[\"<o>\"],\"nextActions\":[{\"action\":\"<what>\",\"why\":\"<why>\",\"effort\":\"S|M|L\"}]}"

# ── Build harness files from phase outputs ────────────────────────────────────
echo ""
echo "[8/8] GENERATING HARNESS FILES"

# Build spec.md
python3 - << 'PYEOF'
import json, os, pathlib
h = pathlib.Path(".harness")

def load(f):
    try: return json.loads((h / f).read_text())
    except: return {}

arch  = load("phase2-architecture.json")
qual  = load("phase3-quality.json")
ctx   = load("phase4-context.json")
gaps  = load("phase5-gaps.json")
plan  = load("phase6-sprints.json")
ex    = load("phase7-exec.json")

repo = os.path.basename(os.getcwd())
date = __import__("datetime").date.today().isoformat()

spec = f"""# Pi CEO Analysis — {repo}
Date: {date}

## Project
{ctx.get("projectPurpose", "")}

## Tech Stack
{", ".join(arch.get("techStack", []))}

## Quality Scores
| Completeness | Correctness | Code Quality | Docs |
|---|---|---|---|
| {qual.get("scores",{}).get("completeness","?")} | {qual.get("scores",{}).get("correctness","?")} | {qual.get("scores",{}).get("codeQuality","?")} | {qual.get("scores",{}).get("documentation","?")} |

## ZTE Maturity: Level {gaps.get("zteLevel","?")} ({gaps.get("zteScore","?")}/60)

## Sprint Plan
{"".join(f"### Sprint {s['id']}: {s['name']} ({s['duration']})" + chr(10) + chr(10).join(f"- [{i['size']}] {i['title']}" for i in s.get("items",[])) + chr(10) + chr(10) for s in plan.get("sprints",[]))}
"""
(h / "spec.md").write_text(spec)

summary = f"""# Executive Summary — {repo}
{ex.get("currentState","")}

## Strengths
{"".join(f"- {s}"+chr(10) for s in ex.get("strengths",[]))}

## Weaknesses
{"".join(f"- {w}"+chr(10) for w in ex.get("weaknesses",[]))}

## Next Actions
{"".join(f"{i+1}. {a['action']}"+chr(10) for i,a in enumerate(ex.get("nextActions",[])))}
"""
(h / "executive-summary.md").write_text(summary)

features = [
    {"id": f"F{s['id']*100+j:03d}", "title": i["title"], "sprint": s["id"],
     "size": i["size"], "priority": i["priority"], "status": "planned"}
    for s in plan.get("sprints",[])
    for j,i in enumerate(s.get("items",[]))
]
(h / "feature_list.json").write_text(json.dumps(features, indent=2))
print(f"  spec.md + executive-summary.md + feature_list.json written")
PYEOF

git add -A
git commit -m "audit: Pi CEO full analysis — $REPO_NAME" --quiet

# ── Push ──────────────────────────────────────────────────────────────────────
echo "  Pushing branch $BRANCH to origin..."
git push origin "$BRANCH"

echo ""
echo "  ✓ Analysis complete"
echo "  Branch: $BRANCH"
echo "  Open a PR at: $REPO_URL/compare/$BRANCH"
echo ""
