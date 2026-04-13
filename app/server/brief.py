"""
brief.py — PITER intent classifier + ADW template router.

Classifies briefs into intent categories (feature/bug/chore/spike/hotfix)
using keyword matching, then routes to the corresponding Agent Developer
Workflow (ADW) template from skills/agent-workflow/SKILL.md.

The structured brief wraps the raw user brief with:
1. Intent classification and ADW workflow steps
2. Explicit phase instructions for Claude
3. Rules for commit messages and output format

RA-681: Three-tier complexity system.
  basic    — sparse spec (< ~80 words, trivial brief keywords)
  detailed — standard spec with lessons, skills, intent files  [default]
  advanced — full spec with extended quality gate + confidence requirement

Use classify_brief_complexity() to detect tier, or pass complexity_tier=
to build_structured_brief() to override.
"""
import os
import sys

# Ensure src/ is importable (skills.py lives in src/tao/)
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from .lessons import load_lessons  # noqa: E402

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
    # Check hotfix/bug first (highest priority), then chore/spike before feature.
    # Feature is the fallback — its broad keywords ("new", "build") would otherwise
    # swallow chore and spike briefs if checked first.
    for intent in ["hotfix", "bug", "chore", "spike", "feature"]:
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


def _get_skill_context(intent: str, max_chars: int = 4000) -> str:
    """Load relevant skills for the intent and return truncated context."""
    try:
        from src.tao.skills import skills_for_intent
        skills = skills_for_intent(intent)
        if not skills:
            return ""
        parts = []
        total = 0
        for s in skills:
            chunk = f"### Skill: {s['name']}\n{s['body'][:800]}\n"
            if total + len(chunk) > max_chars:
                break
            parts.append(chunk)
            total += len(chunk)
        if parts:
            return "--- RELEVANT SKILLS ---\n" + "\n".join(parts) + "--- END SKILLS ---\n\n"
    except Exception:
        pass
    return ""


# ── RA-678: Intent file types — loaded from <workspace>/.harness/intent/ ──────
_INTENT_FILES = [
    ("RESEARCH_INTENT.md",         "STRATEGIC INTENT"),
    ("ENGINEERING_CONSTRAINTS.md", "ENGINEERING CONSTRAINTS"),
    ("EVALUATION_CRITERIA.md",     "EVALUATION CRITERIA"),
]


def _load_intent_files(workspace: str, max_chars: int = 3000) -> str:
    """RA-678 — Load per-project intent files from <workspace>/.harness/intent/.

    Reads up to 3 intent files and returns a combined prompt section.
    Missing files are silently skipped.  Total length capped at max_chars.
    """
    if not workspace:
        return ""
    intent_dir = os.path.join(workspace, ".harness", "intent")
    sections: list[str] = []
    total = 0
    for filename, header in _INTENT_FILES:
        path = os.path.join(intent_dir, filename)
        if not os.path.isfile(path):
            continue
        try:
            content = open(path, encoding="utf-8").read().strip()
        except OSError:
            continue
        if not content:
            continue
        chunk = f"--- {header} ({filename}) ---\n{content}\n--- END {header} ---\n\n"
        if total + len(chunk) > max_chars:
            remaining = max_chars - total
            if remaining > 100:
                chunk = f"--- {header} ({filename}) ---\n{content[:remaining - 60]}\n...(truncated)\n--- END {header} ---\n\n"
            else:
                break
        sections.append(chunk)
        total += len(chunk)
    return "".join(sections)


def _get_lesson_context(intent: str, limit: int = 5, max_chars: int = 2000) -> str:
    """Load recent lessons relevant to the intent and format as prompt context."""
    lessons = load_lessons(category=intent, limit=limit)
    if not lessons:
        lessons = load_lessons(category=None, limit=3)
    if not lessons:
        return ""
    parts = []
    total = 0
    for entry in lessons:
        sev = entry.get("severity", "info").upper()
        text = entry.get("lesson", "")[:300]
        chunk = f"- [{sev}] {text}\n"
        if total + len(chunk) > max_chars:
            break
        parts.append(chunk)
        total += len(chunk)
    if parts:
        return "--- LESSONS LEARNED ---\n" + "".join(parts) + "--- END LESSONS ---\n\n"
    return ""


# ── RA-681: Brief complexity tiers ───────────────────────────────────────────

# Keywords that signal a trivially simple brief
_BASIC_KEYWORDS: frozenset[str] = frozenset([
    "typo", "typos", "spelling", "rename", "comment", "comments",
    "whitespace", "indent", "indentation", "blank line", "newline",
    "small fix", "minor fix", "tiny fix", "quick fix",
    "version bump", "bump version", "update version",
    "add todo", "remove todo", "delete todo",
])

# Keywords that signal a complex brief requiring full context
_ADVANCED_KEYWORDS: frozenset[str] = frozenset([
    "architecture", "architect", "redesign", "rearchitect",
    "migration", "migrate", "database migration", "schema migration",
    "security", "authentication", "authorisation", "authorization",
    "oauth", "jwt", "encryption", "certificate",
    "performance", "optimisation", "optimization", "profiling",
    "integration", "integrate", "third-party", "external api",
    "multi-tenant", "multitenant", "sharding", "replication",
    "concurrent", "race condition", "deadlock", "async",
    "ci/cd", "pipeline", "deployment", "infrastructure",
    "refactor entire", "rewrite", "overhaul", "redesign",
    "multiple services", "microservice",
])

_BASIC_WORD_THRESHOLD = 30    # fewer words → candidate for basic tier
_ADVANCED_WORD_THRESHOLD = 100  # more words → candidate for advanced tier


def classify_brief_complexity(raw_brief: str) -> str:
    """RA-681 — Classify brief as 'basic', 'detailed', or 'advanced'.

    Decision logic (in priority order):
    1. Any advanced keyword → 'advanced'
    2. Any basic keyword AND word count < threshold → 'basic'
    3. Word count > advanced threshold → 'advanced'
    4. Otherwise → 'detailed'

    The result controls how much context is prepended to the generator spec:
      basic    — brief + ADW steps + minimal quality gate only (~500 tokens)
      detailed — adds lessons, skills, intent files              (~1 200 tokens)
      advanced — adds extended quality gate + confidence target  (~1 800 tokens)
    """
    lower = raw_brief.lower()
    word_count = len(raw_brief.split())

    # Advanced keywords override everything
    if any(kw in lower for kw in _ADVANCED_KEYWORDS):
        return "advanced"

    # Basic: clearly trivial keyword AND short
    if word_count < _BASIC_WORD_THRESHOLD and any(kw in lower for kw in _BASIC_KEYWORDS):
        return "basic"

    # Long brief → promote to advanced even without explicit keywords
    if word_count > _ADVANCED_WORD_THRESHOLD:
        return "advanced"

    return "detailed"


# ── Quality gates (one per tier) ──────────────────────────────────────────────

# Tier 1 — Basic: just the essential checklist, no scoring language
_QUALITY_GATE_BASIC = """\
--- QUALITY GATE ---
Before committing, confirm:
  ✓ The change matches the brief exactly — nothing more, nothing less
  ✓ No syntax errors, no debug prints, no leftover TODOs
  ✓ Commit message follows: <type>: <description>
--- END QUALITY GATE ---
"""

# Tier 2 — Detailed: current full gate (default)
_QUALITY_GATE = """\
--- QUALITY GATE (mandatory self-review before every commit) ---
You will be evaluated by a second AI pass on exactly these 4 dimensions.
Score yourself honestly. If any dimension falls below 8/10, fix it before committing.

COMPLETENESS (target ≥9/10)
  • Go back to the brief — list every explicit requirement.
  • Confirm each one is fully implemented, not partially addressed.
  • "I started it" is NOT done. Partial code = fail.

CORRECTNESS (target ≥9/10)
  • No bugs, no logic errors, no null/undefined references.
  • No security vulnerabilities (no hardcoded secrets, no unsanitised inputs).
  • If tests exist, run them. If they fail, fix before committing.

CONCISENESS (target ≥9/10)
  • Delete all dead code, debug prints, and TODO stubs.
  • No over-engineered abstractions for a single use-case.
  • Every line must serve a specific purpose from the brief.

FORMAT (target ≥9/10)
  • Match existing naming conventions exactly (camelCase/snake_case, file naming).
  • Match existing indentation, import order, and module structure.
  • Do NOT introduce new patterns that differ from what already exists in the project.

Only commit once all 4 dimensions pass your self-assessment at ≥8/10.
--- END QUALITY GATE ---
"""

# Tier 3 — Advanced: raises bar, adds confidence and risk sections
_QUALITY_GATE_ADVANCED = """\
--- QUALITY GATE: ADVANCED (mandatory self-review before every commit) ---
You will be evaluated on 4 dimensions (target ≥9/10 each) AND a confidence score.
A score below 9/10 on any dimension OR confidence below 80 % triggers a retry.

COMPLETENESS (target ≥9/10)
  • Re-read the full brief — enumerate every explicit and implicit requirement.
  • Complex briefs often have unstated invariants (existing API contracts,
    backward compatibility, permissions). Identify and honour them.

CORRECTNESS (target ≥9/10)
  • No bugs, no logic errors, no null/undefined dereferences.
  • Security: no hardcoded secrets, all external inputs sanitised, no IDOR.
  • Run the full test suite. All tests must pass before committing.
  • If tests do not exist, write the critical path tests first.

CONCISENESS (target ≥9/10)
  • Zero dead code, zero debug prints, zero TODO stubs.
  • Prefer editing existing abstractions over creating new ones.
  • No speculative generality — only what the brief requires.

FORMAT (target ≥9/10)
  • Naming, indentation, import order: match the existing codebase exactly.
  • Architectural patterns: no new patterns unless the brief explicitly requires them.
  • Commit message: conventional commit with scope (e.g. feat(auth): ...).

CONFIDENCE (target ≥80 %)
  • State your confidence in each dimension.
  • If confidence < 80 %, ask a clarifying question or flag the risk in the
    commit message before shipping.

RISK REGISTER (required for advanced briefs)
  • List up to 3 risks this change introduces.
  • For each: describe mitigation taken or explicitly left as a known trade-off.

Only commit once ALL dimensions pass ≥9/10 and confidence ≥80 %.
--- END QUALITY GATE: ADVANCED ---
"""

_QUALITY_GATES = {
    "basic":    _QUALITY_GATE_BASIC,
    "detailed": _QUALITY_GATE,
    "advanced": _QUALITY_GATE_ADVANCED,
}


def build_structured_brief(
    raw_brief: str,
    intent: str,
    repo_url: str = "",
    workspace: str = "",
    complexity_tier: str = "",
) -> str:
    """Compose a structured spec string for claude -p from a raw brief + intent.

    Returns the full spec string incorporating ADW workflow steps, relevant
    skill context, quality gate criteria, and rules.

    RA-678: when workspace is provided, intent files from
    <workspace>/.harness/intent/ are injected between lesson context and the
    user brief, giving PMs and the CEO declarative steering without touching
    Python.  Missing files are silently skipped.

    RA-681: complexity_tier controls spec verbosity:
      'basic'    — minimal spec (brief + workflow + simple gate)
      'detailed' — standard spec with skills, lessons, intent files  [default]
      'advanced' — full spec with extended quality gate and risk register
    If complexity_tier is empty, it is auto-detected from the brief text.
    """
    if not complexity_tier:
        complexity_tier = classify_brief_complexity(raw_brief)

    template = get_adw_template(intent)
    gate = _QUALITY_GATES.get(complexity_tier, _QUALITY_GATE)

    # Context layers — only included for detailed/advanced tiers
    skill_context = ""
    lesson_context = ""
    intent_context = ""
    if complexity_tier in ("detailed", "advanced"):
        skill_context = _get_skill_context(intent)
        lesson_context = _get_lesson_context(intent)
        intent_context = _load_intent_files(workspace)  # RA-678

    # Tier label in the header so the evaluator knows what was sent
    tier_label = f" [{complexity_tier.upper()} BRIEF]"

    spec = (
        f"You are Pi CEO orchestrator on Claude Max.{tier_label}\n"
        f"Project: {repo_url}\n"
        f"Intent: {intent.upper()} — {template['name']}\n\n"
        f"{template['instructions']}\n\n"
        f"{skill_context}"
        f"{lesson_context}"
        f"{intent_context}"
        f"--- USER BRIEF ---\n{raw_brief}\n--- END BRIEF ---\n\n"
        f"{gate}\n"
        f"RULES:\n"
        f"- Follow the workflow steps above in order\n"
        f"- Show your thinking at each step\n"
        f"- Pass the Quality Gate self-review BEFORE every commit\n"
        f"- After changes: git add -A && git commit -m '<type>: <description>'\n"
        f"- Use conventional commits: feat:, fix:, chore:, docs:\n"
        f"- At the end write a summary of what you did and what to do next"
    )
    return spec
