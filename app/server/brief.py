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
import glob as _glob
import json
import os
import sys

# Ensure src/ is importable (skills.py lives in src/tao/)
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from .lessons import load_lessons  # noqa: E402


# ── RA-1025: Grounded repo context scanner ────────────────────────────────────

def scan_repo_context(workspace_path: str) -> dict:
    """Scan a workspace directory and return repo-specific context for brief construction.

    Detects primary language, test framework, CI commands, and reads CLAUDE.md /
    README.md summaries.  Pure file reads — no external calls, target <500ms.
    Missing files are silently skipped.

    Returns a dict with keys:
        primary_language   str  — e.g. "python", "typescript", "javascript", "unknown"
        test_framework     str  — e.g. "pytest", "jest", "vitest", "unittest", "unknown"
        ci_commands        list[str]  — CI commands detected from .github/workflows/*.yml
        claude_md_summary  str  — first 800 chars of CLAUDE.md (or "")
        readme_summary     str  — first 400 chars of README.md (or "")
        has_claude_md      bool
    """
    result: dict = {
        "primary_language": "unknown",
        "test_framework": "unknown",
        "ci_commands": [],
        "claude_md_summary": "",
        "readme_summary": "",
        "has_claude_md": False,
    }

    if not workspace_path or not os.path.isdir(workspace_path):
        return result

    # ── Language detection via file-extension counts ──────────────────────────
    ext_counts: dict[str, int] = {"py": 0, "ts": 0, "js": 0}
    try:
        for root, dirs, files in os.walk(workspace_path):
            # Skip hidden dirs and common noise dirs
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".git", "dist", "build")]
            for fname in files:
                ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                if ext in ext_counts:
                    ext_counts[ext] += 1
    except OSError:
        pass

    if ext_counts:
        dominant_ext = max(ext_counts, key=lambda e: ext_counts[e])
        if ext_counts[dominant_ext] > 0:
            result["primary_language"] = {"py": "python", "ts": "typescript", "js": "javascript"}.get(dominant_ext, "unknown")

    # ── package.json — test script + devDependency framework ─────────────────
    pkg_path = os.path.join(workspace_path, "package.json")
    try:
        with open(pkg_path, encoding="utf-8") as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        dev_deps = {**pkg.get("devDependencies", {}), **pkg.get("dependencies", {})}
        # Check test script for framework hints
        test_script = scripts.get("test", "") + scripts.get("test:unit", "") + scripts.get("test:e2e", "")
        for fw in ("vitest", "jest", "mocha", "jasmine"):
            if fw in test_script.lower() or fw in dev_deps:
                result["test_framework"] = fw
                break
    except (OSError, json.JSONDecodeError, ValueError):
        pass

    # ── pyproject.toml / setup.cfg — Python test framework ───────────────────
    if result["test_framework"] == "unknown":
        for cfg_name in ("pyproject.toml", "setup.cfg"):
            cfg_path = os.path.join(workspace_path, cfg_name)
            try:
                content = open(cfg_path, encoding="utf-8").read().lower()
                if "pytest" in content:
                    result["test_framework"] = "pytest"
                    break
                if "unittest" in content:
                    result["test_framework"] = "unittest"
                    break
            except OSError:
                continue

    # Fall back: presence of pytest.ini or conftest.py
    if result["test_framework"] == "unknown":
        for indicator in ("pytest.ini", "conftest.py", "setup.cfg"):
            if os.path.isfile(os.path.join(workspace_path, indicator)):
                result["test_framework"] = "pytest"
                break

    # ── .github/workflows/*.yml — CI commands ────────────────────────────────
    workflows_dir = os.path.join(workspace_path, ".github", "workflows")
    _ci_keywords = ["pytest", "npm test", "jest", "vitest", "yarn test", "pnpm test", "npm run test", "make test"]
    try:
        yml_files = sorted(_glob.glob(os.path.join(workflows_dir, "*.yml")) + _glob.glob(os.path.join(workflows_dir, "*.yaml")))
        if yml_files:
            ci_text = open(yml_files[0], encoding="utf-8").read()
            result["ci_commands"] = [kw for kw in _ci_keywords if kw in ci_text.lower()]
    except OSError:
        pass

    # ── CLAUDE.md ────────────────────────────────────────────────────────────
    claude_md_path = os.path.join(workspace_path, "CLAUDE.md")
    try:
        text = open(claude_md_path, encoding="utf-8").read()
        result["claude_md_summary"] = text[:800]
        result["has_claude_md"] = True
    except OSError:
        pass

    # ── README.md ────────────────────────────────────────────────────────────
    for readme_name in ("README.md", "readme.md", "Readme.md"):
        readme_path = os.path.join(workspace_path, readme_name)
        try:
            text = open(readme_path, encoding="utf-8").read()
            result["readme_summary"] = text[:400]
            break
        except OSError:
            continue

    return result

# ── PITER Intent Classification ───────────────────────────────────────────────
_INTENT_KEYWORDS = {
    "hotfix": ["hotfix", "urgent fix", "critical fix", "production down", "p0", "emergency"],
    "bug": ["bug", "fix", "broken", "error", "crash", "failing", "doesn't work", "not working", "issue", "defect", "regression"],
    "video": [
        "explainer", "promo video", "promo reel", "marketing video", "training video",
        "release video", "feature video", "social cut", "social ad", "video ad",
        "remotion", "render video", "branded video", "intro video", "outro video",
        "60s video", "30s video", "15s video", "linkedin video", "youtube video",
        "instagram reel", "tiktok",
    ],
    "feature": ["add", "implement", "create", "build", "new", "feature", "enhance", "integrate", "support"],
    "chore": ["chore", "cleanup", "refactor", "rename", "update deps", "upgrade", "lint", "format", "migrate", "move"],
    "spike": ["research", "investigate", "explore", "spike", "prototype", "evaluate", "compare", "benchmark", "analyze"],
}


def classify_intent(brief: str) -> str:
    """Classify a brief's intent using keyword matching.
    Returns one of: feature, bug, chore, spike, hotfix, video.
    Checks hotfix first (highest priority), then bug, video, chore, spike, feature.
    Default: feature.

    `video` sits between bug and chore so that explicit video keywords
    (explainer, promo, social cut, remotion, etc.) route to the
    remotion-orchestrator skill ahead of the broad "feature" fallback. Video
    keywords are intentionally narrow — bare "video" is not enough; the brief
    must name a video format or platform."""
    lower = brief.lower()
    # Order matters: hotfix/bug guard production work; video must beat the
    # generic "feature" keywords ("create", "build", "new") which otherwise
    # swallow every video brief.
    for intent in ["hotfix", "bug", "video", "chore", "spike", "feature"]:
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
    "video": {
        "name": "Branded Video Render",
        "steps": ["orchestrate", "research", "storyboard", "build", "render"],
        "instructions": (
            "WORKFLOW: Branded Video Render\n"
            "Use the remotion-orchestrator skill as the entry point. It will\n"
            "read the brief, classify (brand, composition, channel, duration),\n"
            "and dispatch sub-skills in waves via the existing P3-B fan-out.\n"
            "1. ORCHESTRATE: remotion-orchestrator emits wave plan JSON\n"
            "2. RESEARCH: remotion-brand-research + remotion-marketing-strategist (wave 1)\n"
            "3. STORYBOARD: remotion-screen-storyteller + colour-family + motion-language (wave 2)\n"
            "4. BUILD: remotion-brand-codify + remotion-designer + remotion-composition-builder (wave 3-4)\n"
            "5. RENDER: remotion-render-pipeline runs `npx tsx render/render.ts`,\n"
            "   synthesises ElevenLabs voiceover, validates MP4, ships to\n"
            "   Telegram via app.server.telegram_video.send_telegram_video,\n"
            "   uploads to Supabase, opens Linear ticket per .harness/projects.json."
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


# Karpathy constraints — always-on engineering guardrails. ~150 tokens,
# trivial vs. the rest of the context, so no gating needed.
# Source of truth: CLAUDE.md lines 184-246.
KARPATHY_CONSTRAINTS = """\
ENGINEERING CONSTRAINTS (Karpathy, always on):
- Minimum code. No speculative abstractions, no features beyond the request.
- Surgical diffs. Every changed line must trace to the stated goal.
- State assumptions upfront. If unclear, ASK before coding.
- Define success criteria before implementing; verify with tests.
- Match existing code style. Do not refactor adjacent unbroken code.
"""


def build_structured_brief(
    raw_brief: str,
    intent: str,
    repo_url: str = "",
    workspace: str = "",
    complexity_tier: str = "",
    repo_context: dict | None = None,
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

    # RA-1025 — Repo context section injected before the user brief
    repo_context_section = ""
    if repo_context:
        lang = repo_context.get("primary_language", "unknown")
        fw = repo_context.get("test_framework", "unknown")
        ci = ", ".join(repo_context.get("ci_commands", [])) or "none detected"
        conventions = (repo_context.get("claude_md_summary", "") or "")[:400]
        repo_context_section = (
            "## Repo Context (auto-detected)\n"
            f"- Primary language: {lang}\n"
            f"- Test framework: {fw}\n"
            f"- CI commands: {ci}\n"
            f"- Conventions: {conventions}\n\n"
            "Use this context to choose the correct test framework, commit style, and file "
            "conventions. Do not introduce new frameworks or tools not already present.\n\n"
        )

    # Tier label in the header so the evaluator knows what was sent
    tier_label = f" [{complexity_tier.upper()} BRIEF]"

    spec = (
        f"You are Pi CEO orchestrator on Claude Max.{tier_label}\n"
        f"Project: {repo_url}\n"
        f"Intent: {intent.upper()} — {template['name']}\n\n"
        f"{template['instructions']}\n\n"
        f"{repo_context_section}"
        f"{skill_context}"
        f"{lesson_context}"
        f"{intent_context}"
        f"--- USER BRIEF ---\n{raw_brief}\n--- END BRIEF ---\n\n"
        f"{gate}\n"
        f"{KARPATHY_CONSTRAINTS}\n"
        f"RULES:\n"
        f"- Follow the workflow steps above in order\n"
        f"- Show your thinking at each step\n"
        f"- Pass the Quality Gate self-review BEFORE every commit\n"
        f"- After changes: git add -A && git commit -m '<type>: <description>'\n"
        f"- Use conventional commits: feat:, fix:, chore:, docs:\n"
        f"- At the end write a summary of what you did and what to do next"
    )
    return spec
