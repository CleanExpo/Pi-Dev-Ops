"""
skills.py — Skill loader and registry for the 31 TAO skills.

Parses YAML frontmatter (name, description) + markdown body from
each skills/*/SKILL.md file. Provides lookup by name and by intent
(maps PITER intents to relevant skill sets).
"""
import os, re

_SKILLS_CACHE: dict | None = None

# ── YAML frontmatter parser ──────────────────────────────────────────────────
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML-ish frontmatter from SKILL.md content.
    Returns (metadata dict, body string)."""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}, content
    meta_block, body = m.group(1), m.group(2)
    meta = {}
    for line in meta_block.split("\n"):
        line = line.strip()
        if ":" in line:
            key, val = line.split(":", 1)
            meta[key.strip()] = val.strip()
    return meta, body.strip()


# ── Skill loading ─────────────────────────────────────────────────────────────
def load_skill(skill_dir: str) -> dict | None:
    """Load a single SKILL.md from a directory. Returns dict or None."""
    skill_path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(skill_path):
        return None
    with open(skill_path, "r", encoding="utf-8") as f:
        content = f.read()
    meta, body = _parse_frontmatter(content)
    return {
        "name": meta.get("name", os.path.basename(skill_dir)),
        "description": meta.get("description", ""),
        "body": body,
        "path": skill_path,
    }


def load_all_skills(skills_root: str = "") -> dict[str, dict]:
    """Scan all subdirectories of skills_root for SKILL.md files.
    Returns { skill_name: { name, description, body, path } }.
    Results are cached after first load."""
    global _SKILLS_CACHE
    if _SKILLS_CACHE is not None:
        return _SKILLS_CACHE

    if not skills_root:
        # Default: skills/ relative to project root (2 dirs up from src/tao/)
        skills_root = os.path.join(os.path.dirname(__file__), "..", "..", "skills")
    skills_root = os.path.abspath(skills_root)

    if not os.path.isdir(skills_root):
        _SKILLS_CACHE = {}
        return _SKILLS_CACHE

    result = {}
    for entry in sorted(os.listdir(skills_root)):
        full = os.path.join(skills_root, entry)
        if not os.path.isdir(full):
            continue
        skill = load_skill(full)
        if skill:
            result[skill["name"]] = skill

    _SKILLS_CACHE = result
    return _SKILLS_CACHE


def get_skill(name: str) -> dict | None:
    """Lookup a skill by name."""
    return load_all_skills().get(name)


# ── Intent-to-skills mapping ─────────────────────────────────────────────────
_INTENT_SKILLS = {
    "feature": ["tier-architect", "tier-worker", "tier-evaluator", "agent-workflow"],
    "bug": ["tier-worker", "agentic-loop", "tier-evaluator"],
    "chore": ["tier-worker", "agent-workflow"],
    "spike": ["ceo-mode", "context-compressor", "tier-orchestrator"],
    "hotfix": ["tier-worker", "agentic-loop", "closed-loop-prompt"],
    "monitor": ["pi-seo-scanner", "pi-seo-health-monitor", "pi-seo-remediation", "maintenance-manager"],
    "spec":    ["ship-chain", "define-spec"],
    "plan":    ["ship-chain", "technical-plan"],
    "test":    ["ship-chain", "verify-test"],
    "ship":    ["ship-chain", "ship-release"],
}


def skills_for_intent(intent: str) -> list[dict]:
    """Return skills relevant to a PITER intent.
    Returns list of skill dicts (only those that exist)."""
    all_skills = load_all_skills()
    names = _INTENT_SKILLS.get(intent, _INTENT_SKILLS["feature"])
    return [all_skills[n] for n in names if n in all_skills]


def invalidate_cache() -> None:
    """Clear the skills cache (useful for testing or hot-reload)."""
    global _SKILLS_CACHE
    _SKILLS_CACHE = None
