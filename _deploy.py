import os
import sys

# Cross-platform root: always the directory containing this script.
ROOT = os.path.dirname(os.path.abspath(__file__))

# ── Production guard ─────────────────────────────────────────────────────────
# _deploy.py is a one-time bootstrap skeleton writer.  If the harness already
# exists (i.e. this is a live Pi-Dev-Ops deployment) refuse to run — overwriting
# production harness files (spec.md, lessons.jsonl, config.yaml) would destroy
# operational state.
_GUARD_FILE = os.path.join(ROOT, ".harness", "spec.md")
if os.path.isfile(_GUARD_FILE):
    print(
        "ABORT: Pi-Dev-Ops harness already exists at:\n"
        f"  {_GUARD_FILE}\n\n"
        "_deploy.py is a first-run bootstrap script and must not be run on a\n"
        "live deployment — it would overwrite production harness state.\n\n"
        "To re-scaffold a clean environment, delete the .harness/ directory\n"
        "first and ensure you are not in your production working tree."
    )
    sys.exit(1)

os.chdir(ROOT)
n = 0


def w(p, c):
    global n
    f = os.path.join(ROOT, p)
    os.makedirs(os.path.dirname(f) or ".", exist_ok=True)
    open(f, "w", encoding="utf-8", newline="\n").write(c)
    n += 1
    print(f"  [{n}] {p}")

w("pyproject.toml", "[build-system]\nrequires = [\"hatchling\"]\nbuild-backend = \"hatchling.build\"\n\n[project]\nname = \"tao\"\nversion = \"1.0.0\"\ndescription = \"Tiered Agent Orchestrator\"\nrequires-python = \">=3.11\"\ndependencies = [\"httpx\", \"pyyaml\"]\n")

w(".harness/config.yaml", "project: pi-dev-ops\nharness_version: 1.0\nagents:\n  planner: {model: opus, temperature: 0.3}\n  generator: {model: sonnet, temperature: 0.2}\n  evaluator: {model: sonnet, temperature: 0.1}\nqa:\n  max_rounds: 3\n  auto_escalate: true\n")

w(".harness/spec.md", "# Pi Dev Ops - Product Spec\n\nTiered Agent Orchestrator (TAO) with 23 skills on Claude Max.\n\n## Tiers\n- Orchestrator: Opus 4.7 (1M ctx)\n- Specialist: Sonnet 4.6 (200K ctx)\n- Worker: Haiku 4.5 (200K ctx)\n")

w(".harness/handoff.md", "# Handoff\n\n## Project: Pi Dev Ops\n## Status: Initial deployment\n## Next: Run first build via web UI\n")

w("skills/tao-skills/SKILL.md", "---\nname: tao-skills\ndescription: Master index of all 23 TAO skills.\n---\n\n# TAO Skills Index\n\n23 skills across 5 layers.\n\n## Core\ntier-architect, tier-orchestrator, tier-worker, tier-evaluator, context-compressor, token-budgeter, auto-generator\n\n## Frameworks\npiter-framework, afk-agent, closed-loop-prompt, hooks-system, agent-workflow, agentic-review\n\n## Strategic\nzte-maturity, agent-expert, leverage-audit, agentic-loop, agentic-layer\n\n## Foundation\nbig-three, claude-max-runtime, pi-integration\n")

w("skills/big-three/SKILL.md", "---\nname: big-three\ndescription: The foundational framework - Model, Prompt, Context. Every decision maps to one of these.\n---\n\n# The Big Three\n\n## Model - The Intelligence Layer\nChoose the right model for each task. Opus for planning, Sonnet for implementation, Haiku for execution.\n\n## Prompt - The Instruction Layer\nSpec prompts with verification commands beat vague instructions every time.\n\n## Context - The Knowledge Layer\nMinimum viable context. Compress at boundaries. Recent matters more than old.\n\n## Debugging Order\n1. Is the MODEL capable? Test directly.\n2. Is the PROMPT specific? Read it as the agent.\n3. Is the CONTEXT sufficient? Check what the agent sees.\n")

w("skills/tier-architect/SKILL.md", "---\nname: tier-architect\ndescription: Design tier configurations - which models for which roles.\n---\n\n# Tier Architect\n\nDesign the tier hierarchy for your project.\n\n## Tier Config Format (YAML)\ntiers:\n  - name: orchestrator\n    model: opus\n    role: Plans and coordinates\n  - name: specialist\n    model: sonnet\n    parent: orchestrator\n    role: Complex implementation\n  - name: worker\n    model: haiku\n    parent: specialist\n    role: Discrete tasks\n")

w("skills/tier-orchestrator/SKILL.md", "---\nname: tier-orchestrator\ndescription: The orchestrator plans, decomposes briefs, and delegates to lower tiers.\n---\n\n# Tier Orchestrator\n\nThe orchestrator is the top tier. It receives the brief, decomposes it into features, creates sprint contracts, and delegates to specialists and workers.\n\n## Delegation Patterns\n- Fan-out: Independent tasks run in parallel\n- Serial: Each depends on the previous\n- Hierarchical: Specialists decompose further before workers execute\n")

w("skills/tier-worker/SKILL.md", "---\nname: tier-worker\ndescription: Workers execute discrete, well-scoped tasks quickly.\n---\n\n# Tier Worker\n\nWorkers receive specific instructions and execute them exactly. They do not make architectural decisions.\n\n## When to Escalate\n- Task references files not in context\n- Multiple valid interpretations\n- Scope too large (>3 files)\n")

w("skills/tier-evaluator/SKILL.md", "---\nname: tier-evaluator\ndescription: QA agent that grades output against acceptance criteria.\n---\n\n# Tier Evaluator\n\nThe evaluator is SKEPTICAL by default. It runs tests, checks criteria, and reports PASS or FAIL.\n\n## Grading\n- Completeness (threshold 7/10)\n- Correctness (threshold 7/10)\n- Conciseness (threshold 5/10)\n- Format compliance (threshold 8/10)\n")

w("skills/context-compressor/SKILL.md", "---\nname: context-compressor\ndescription: Compress context at tier boundaries to save tokens.\n---\n\n# Context Compressor\n\n## Strategies\n1. Truncate - Keep first/last N chars (free)\n2. Extract - Pull keyword-relevant sections (free)\n3. Summarize - AI summary via Haiku (cheap)\n")

w("skills/token-budgeter/SKILL.md", "---\nname: token-budgeter\ndescription: Track and enforce token budgets per tier.\n---\n\n# Token Budgeter\n\n## Model Costs (April 2026)\n- Opus 4.7: / per M tokens\n- Sonnet 4.6: / per M tokens\n- Haiku 4.5: .80/ per M tokens\n\nOn Claude Max:  for everything.\n")

w("skills/auto-generator/SKILL.md", "---\nname: auto-generator\ndescription: Generate tier configs from project briefs automatically.\n---\n\n# Auto Generator\n\nGiven a brief, recommends the optimal tier configuration.\n\n## Presets\n- 2-tier-codereview: Sonnet reviewer + Haiku workers\n- 3-tier-webapp: Opus orchestrator + Sonnet specialist + Haiku workers\n- 4-tier-research: Full hierarchy with research tier\n")

w("skills/piter-framework/SKILL.md", "---\nname: piter-framework\ndescription: 5-pillar AFK agent setup - Prompt, Intent, Trigger, Environment, Review.\n---\n\n# PITER Framework\n\n## P - Prompt\nSpec prompts with verification commands, not chat messages.\n\n## I - Intent\nClassify: bug, feature, chore, spike, hotfix. Each routes differently.\n\n## T - Trigger\nCLI -> webhook -> cron -> CI. Progress from manual to automatic.\n\n## E - Environment\nIsolated workspace. Disposable. API keys via env vars.\n\n## R - Review\nSelf-review (closed loop) -> CI review -> Human review (PR only).\n")

w("skills/afk-agent/SKILL.md", "---\nname: afk-agent\ndescription: Run agents unattended with stop guards and notifications.\n---\n\n# AFK Agent\n\n## The AFK Contract\n1. Bounded runtime (max N minutes)\n2. Bounded cost (max N tokens)\n3. No silent failure\n4. No premature exit (stop guards)\n5. Notification on completion\n\n## Stop Guards\nIntercept exit attempts. Verify completion criteria before allowing stop.\n")

w("skills/closed-loop-prompt/SKILL.md", "---\nname: closed-loop-prompt\ndescription: Self-correcting prompts with embedded verification.\n---\n\n# Closed-Loop Prompting\n\nEmbed verification INTO the prompt:\n1. Build X\n2. Run Y to check\n3. If Y fails, fix and retry\n4. Max 3 attempts\n\n## Patterns\n- Test-Fix Loop: implement -> test -> fix -> retest\n- Build-Verify-Iterate: build -> verify output -> fix discrepancy\n- Multi-Step Cascade: phase 1 verify -> phase 2 verify -> integration verify\n")

w("skills/hooks-system/SKILL.md", "---\nname: hooks-system\ndescription: Lifecycle hooks for agent observability and safety.\n---\n\n# Hooks System\n\n## 6 Hook Types\n1. PreToolUse - Block dangerous commands\n2. PostToolUse - Log every action\n3. Stop - Enforce completion criteria\n4. SubagentStop - Track parallel completion\n5. PreCompact - Backup context before compaction\n6. SessionStart - Load handoff from previous session\n")

w("skills/agent-workflow/SKILL.md", "---\nname: agent-workflow\ndescription: ADWs - reusable workflow templates from trigger to deploy.\n---\n\n# Agent Developer Workflows\n\n## Pre-built ADWs\n1. Feature Build: decompose -> build -> test -> review -> PR\n2. Bug Fix: reproduce -> diagnose -> fix -> verify -> commit\n3. Chore: apply -> lint -> test -> auto-merge\n4. Code Review: read diff -> analyze -> report\n5. Research Spike: research -> summarize -> recommend\n")

w("skills/agentic-review/SKILL.md", "---\nname: agentic-review\ndescription: Review agent output for quality, not just correctness.\n---\n\n# Agentic Review\n\nTesting checks: does it work?\nReviewing checks: is it good?\n\n## 6 Review Dimensions\n1. Architecture - Structure sensible?\n2. Naming - Names communicate intent?\n3. Error handling - Failures graceful?\n4. Duplication - Logic DRY?\n5. Complexity - Simple as possible?\n6. Conventions - Matches project patterns?\n")

w("skills/zte-maturity/SKILL.md", "---\nname: zte-maturity\ndescription: Zero Touch Engineering maturity model.\n---\n\n# ZTE Maturity\n\n## Level 1: In the Loop\nYou type every prompt. You review every output. 2-5x advantage.\n\n## Level 2: Out of the Loop\nYou write the spec. Agent executes AFK. You review the PR. 10-50x advantage.\n\n## Level 3: Zero Touch Engineering\nSystem detects work, writes specs, executes, tests, reviews, deploys. 100x+ advantage.\n")

w("skills/agent-expert/SKILL.md", "---\nname: agent-expert\ndescription: Act-Learn-Reuse cycle for agent improvement over time.\n---\n\n# Agent Experts\n\n## The Cycle\n1. ACT - Execute the task\n2. LEARN - Extract lessons (patterns, pitfalls, context, tools, conventions)\n3. REUSE - Inject relevant lessons into next task\n\nStore lessons in .harness/lessons.jsonl. Inject top 5 most relevant per task.\n")

w("skills/leverage-audit/SKILL.md", "---\nname: leverage-audit\ndescription: 12 Leverage Points diagnostic for agent autonomy.\n---\n\n# 12 Leverage Points\n\nScore each 1-5. Bottom 3 = highest ROI improvements.\n\n1. Spec Quality\n2. Context Precision\n3. Model Selection\n4. Tool Availability\n5. Feedback Loops\n6. Error Recovery\n7. Session Continuity\n8. Quality Gating\n9. Cost Efficiency\n10. Trigger Automation\n11. Knowledge Retention\n12. Workflow Standardization\n\n12-20: Manual | 21-35: Assisted | 36-48: Autonomous | 49-60: ZTE\n")

w("skills/agentic-loop/SKILL.md", "---\nname: agentic-loop\ndescription: Infinite self-correcting iteration until completion criteria met.\n---\n\n# Agentic Loop\n\nTwo-prompt system: task prompt + stop guard.\nAgent works -> tries to stop -> guard checks criteria -> not met -> continues.\n\n## Safety Rails\n- max_iterations: 20\n- max_tokens: 200000\n- max_runtime_minutes: 60\n- Detect oscillation (fix A breaks B) after 3 iterations\n")

w("skills/agentic-layer/SKILL.md", "---\nname: agentic-layer\ndescription: Design products with agent-native architecture.\n---\n\n# The Agentic Layer\n\nEvery product needs two interfaces:\n- Human Layer: HTML/CSS/JS, visual, interactive\n- Agentic Layer: JSON I/O, structured, deterministic\n\n## Design Principles\n1. Structured over visual (JSON not HTML)\n2. Actions as named operations\n3. State as machine-readable document\n4. Feedback as structured result\n5. Self-describing API (capabilities endpoint)\n")

w("skills/claude-max-runtime/SKILL.md", "---\nname: claude-max-runtime\ndescription: Execute TAO natively within Claude Max subscription.\n---\n\n# Claude Max Runtime\n\n## Tier Mapping\n- Orchestrator: Main Claude Code session (Opus 4.7, 1M ctx)\n- Specialist: Subagent (Sonnet 4.6)\n- Worker: Subagent (Haiku 4.5)\n- Evaluator: Subagent (Sonnet 4.6, read-only)\n\nZero API cost. Everything included in Max subscription.\n")

w("skills/pi-integration/SKILL.md", "---\nname: pi-integration\ndescription: Bridge TAO to pi-mono runtime for multi-provider support.\n---\n\n# Pi Integration\n\nFor multi-provider setups (Anthropic + OpenAI + Ollama).\nUse claude-max-runtime instead if you are on Max plan.\n\npi-mono provides: unified LLM API, session trees, hooks, packages.\n")

w("skills/ceo-mode/SKILL.md", "---\nname: ceo-mode\ndescription: Executive decision-making mode for strategic choices.\n---\n\n# CEO Mode\n\nWhen facing strategic decisions, activate CEO mode.\nWeigh options, consider tradeoffs, make a call, document the rationale.\n")

# Engine stubs
w("src/tao/__init__.py", "")
w("src/tao/schemas/__init__.py", "")
w("src/tao/agents/__init__.py", "")
w("src/tao/budget/__init__.py", "")
w("src/tao/tiers/__init__.py", "")

w("src/tao/schemas/artifacts.py", "from dataclasses import dataclass, field\nfrom typing import Optional, Any\nimport uuid, time\n\n@dataclass\nclass TaskSpec:\n    description: str\n    tier: str\n    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])\n    context: str = ''\n    parent_task_id: Optional[str] = None\n    expected_output: str = ''\n    max_tokens: int = 4096\n\n@dataclass\nclass TaskResult:\n    task_id: str\n    tier: str\n    content: str\n    success: bool = True\n    tokens_used: int = 0\n    model: str = ''\n    duration_seconds: float = 0.0\n\n@dataclass\nclass Escalation:\n    task_id: str\n    from_tier: str\n    reason: str\n    context_needed: str = ''\n    partial_result: Optional[str] = None\n")

w("src/tao/tiers/config.py", "import yaml\nfrom dataclasses import dataclass, field\nfrom typing import Optional\n\nMODEL_MAP = {'opus':'claude-opus-4-7','sonnet':'claude-sonnet-4-6','haiku':'claude-haiku-4-5-20251001'}\n\n@dataclass\nclass TierConfig:\n    name: str\n    model: str\n    role: str = ''\n    parent: Optional[str] = None\n    max_concurrency: int = 1\n    token_budget_pct: int = 0\n    fallback_model: Optional[str] = None\n\ndef load_config(path):\n    with open(path) as f:\n        raw = yaml.safe_load(f)\n    tiers = []\n    for t in raw.get('tiers', []):\n        tiers.append(TierConfig(**{k:v for k,v in t.items() if k in TierConfig.__dataclass_fields__}))\n    return {'total_token_budget': raw.get('total_token_budget', 100000), 'tiers': tiers}\n")

w("src/tao/budget/tracker.py", "from dataclasses import dataclass, field\nimport time\n\n@dataclass\nclass BudgetTracker:\n    total_budget: int = 100000\n    used: int = 0\n    per_tier: dict = field(default_factory=dict)\n    \n    def record(self, tier, tokens):\n        self.used += tokens\n        self.per_tier.setdefault(tier, 0)\n        self.per_tier[tier] += tokens\n    \n    def remaining(self): return self.total_budget - self.used\n    def pct_used(self): return (self.used / self.total_budget * 100) if self.total_budget else 0\n")

w("src/tao/templates/3-tier-webapp.yaml", "total_token_budget: 500000\n\ntiers:\n  - name: orchestrator\n    model: opus\n    role: Plans and coordinates the build\n    max_concurrency: 1\n    token_budget_pct: 20\n\n  - name: specialist\n    model: sonnet\n    role: Complex feature implementation\n    parent: orchestrator\n    max_concurrency: 2\n    token_budget_pct: 30\n\n  - name: worker\n    model: haiku\n    role: Discrete execution tasks\n    parent: specialist\n    max_concurrency: 5\n    token_budget_pct: 50\n")

print(f"\nDone! {n} files created.")
print("Now run: git add -A && git commit -m 'feat: full system' && git push origin main")
