"""
brief.py — PITER intent classifier + ADW template router.

Classifies briefs into intent categories (feature/bug/chore/spike/hotfix)
using keyword matching, then routes to the corresponding Agent Developer
Workflow (ADW) template from skills/agent-workflow/SKILL.md.

The structured brief wraps the raw user brief with:
1. Intent classification and ADW workflow steps
2. Explicit phase instructions for Claude
3. Rules for commit messages and output format
"""
import re

# ── PITER Intent Classification ───────────────────────────────────────────────
_INTENT_KEYWORDS = {
    "hotfix": ["hotfix", "urgent fix", "critical fix", "production down", "p0", "emergency"],
    "bug": ["bug", "fix", "broken", "error", "crash", "failing", "doesn't work", "not working", "issue", "defect", "regression"],
    "feature": ["add", "implement", "create", "build", "new", "feature", "enhance", "integrate", "support"],
    "chore": ["chore", "cleanup", "refactor", "rename", "update deps", "upgrade", "lint", "format", "migrate", "move"],
    "spike": ["research", "investigate", "explore", "spike", "prototype", "evaluate", "compare", "benchmark", "analyze"],
}


def classify_intent(brief: str) -> str:
    """Classify a brief's intent using keyword matching.
    Returns one of: feature, bug, chore, spike, hotfix.
    Checks hotfix first (highest priority), then bug, feature, chore, spike.
    Default: feature."""
    lower = brief.lower()
    for intent in ["hotfix", "bug", "feature", "chore", "spike"]:
        for kw in _INTENT_KEYWORDS[intent]:
            if kw in lower:
                return intent
    return "feature"


# ── ADW Templates (from skills/agent-workflow/SKILL.md) ──────────────────────
_ADW_TEMPLATES = {
    "feature": {
        "name": "Feature Build",
        "steps": ["decompose", "build", "test", "review", "PR"],
        "instructions": (
            "WORKFLOW: Feature Build\n"
            "1. DECOMPOSE: Break the feature into discrete sub-tasks\n"
            "2. BUILD: Implement each sub-task with clean, tested code\n"
            "3. TEST: Run existing tests, add new tests for the feature\n"
            "4. REVIEW: Self-review for correctness, security, style\n"
            "5. PR: Stage changes with a clear commit message"
        ),
    },
    "bug": {
        "name": "Bug Fix",
        "steps": ["reproduce", "diagnose", "fix", "verify", "commit"],
        "instructions": (
            "WORKFLOW: Bug Fix\n"
            "1. REPRODUCE: Identify the exact failure condition\n"
            "2. DIAGNOSE: Trace root cause — read logs, check recent changes\n"
            "3. FIX: Apply minimal, targeted fix\n"
            "4. VERIFY: Confirm the fix resolves the issue without regressions\n"
            "5. COMMIT: Stage with conventional commit (fix: ...)"
        ),
    },
    "chore": {
        "name": "Chore",
        "steps": ["apply", "lint", "test", "auto-merge"],
        "instructions": (
            "WORKFLOW: Chore\n"
            "1. APPLY: Make the maintenance change (refactor, rename, upgrade)\n"
            "2. LINT: Run linters and formatters\n"
            "3. TEST: Verify nothing broke\n"
            "4. COMMIT: Stage with conventional commit (chore: ...)"
        ),
    },
    "spike": {
        "name": "Research Spike",
        "steps": ["research", "summarize", "recommend"],
        "instructions": (
            "WORKFLOW: Research Spike\n"
            "1. RESEARCH: Read relevant code, docs, and prior art\n"
            "2. SUMMARIZE: Document findings clearly\n"
            "3. RECOMMEND: Propose an approach with trade-offs\n"
            "Write findings to .harness/spike-<topic>.md"
        ),
    },
    "hotfix": {
        "name": "Hotfix (URGENT)",
        "steps": ["reproduce", "diagnose", "fix", "verify", "commit"],
        "instructions": (
            "WORKFLOW: Hotfix (URGENT)\n"
            "PRIORITY: This is a production-impacting issue. Move fast.\n"
            "1. REPRODUCE: Identify the failure immediately\n"
            "2. DIAGNOSE: Find root cause — check recent deploys first\n"
            "3. FIX: Apply minimal fix, no scope creep\n"
            "4. VERIFY: Confirm fix, check for side effects\n"
            "5. COMMIT: Stage with conventional commit (fix: ...)"
        ),
    },
}


def get_adw_template(intent: str) -> dict:
    """Return the ADW template for a given intent."""
    return _ADW_TEMPLATES.get(intent, _ADW_TEMPLATES["feature"])


def build_structured_brief(raw_brief: str, intent: str, repo_url: str = "") -> str:
    """Compose a structured spec string for claude -p from a raw brief + intent.

    Returns the full spec string incorporating ADW workflow steps and rules.
    """
    template = get_adw_template(intent)

    spec = (
        f"You are Pi CEO orchestrator on Claude Max.\n"
        f"Project: {repo_url}\n"
        f"Intent: {intent.upper()} — {template['name']}\n\n"
        f"{template['instructions']}\n\n"
        f"--- USER BRIEF ---\n{raw_brief}\n--- END BRIEF ---\n\n"
        f"RULES:\n"
        f"- Follow the workflow steps above in order\n"
        f"- Show your thinking at each step\n"
        f"- After changes: git add -A && git commit -m '<type>: <description>'\n"
        f"- Use conventional commits: feat:, fix:, chore:, docs:\n"
        f"- At the end write a summary of what you did and what to do next"
    )
    return spec
