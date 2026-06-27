"""
skills.py — Skill loader and registry for the 31 TAO skills.

Parses YAML frontmatter (name, description) + markdown body from
each skills/*/SKILL.md file. Provides lookup by name and by intent
(maps PITER intents to relevant skill sets).
"""
from __future__ import annotations

import os
import re

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
        # RA-693: automation mode — "auto" (intent-routed) or "manual" (explicit-only)
        "automation": meta.get("automation", "auto"),
        # RA-693: backing Anthropic Cloud Skill reference, if any
        "anthropic_skill": meta.get("anthropic_skill", ""),
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
            # RA-693: include automation mode from frontmatter
            result[skill["name"]] = skill

    _SKILLS_CACHE = result
    return _SKILLS_CACHE


def get_skill(name: str) -> dict | None:
    """Lookup a skill by name."""
    return load_all_skills().get(name)


# ── Intent-to-skills mapping ─────────────────────────────────────────────────
_INTENT_SKILLS = {
    "feature": [
        "compound-development-loop",
        "tier-architect",
        "tier-worker",
        "tier-evaluator",
        "agent-workflow",
    ],
    "bug": ["tier-worker", "agentic-loop", "tier-evaluator"],
    "chore": ["tier-worker", "agent-workflow"],
    "spike": [
        "compound-development-loop",
        "ceo-mode",
        "context-compressor",
        "tier-orchestrator",
    ],
    "hotfix": ["tier-worker", "agentic-loop", "closed-loop-prompt"],
    "monitor": ["pi-seo-scanner", "pi-seo-health-monitor", "pi-seo-remediation", "maintenance-manager"],
    "spec":    ["compound-development-loop", "ship-chain", "define-spec"],
    "plan":    ["compound-development-loop", "ship-chain", "technical-plan"],
    "test":    ["ship-chain", "verify-test"],
    "ship":    ["ship-chain", "ship-release"],
    "review":  ["review-command", "launch-review", "agentic-review", "tier-evaluator", "leverage-audit"],
    # Pre-build challenge gate. "/judge" is read-only and explicit-invoke
    # (automation:manual in its frontmatter, so skills_manifest() classifies it
    # as manual even though it is intent-routed here). Distinct from "tao-judge"
    # (machine loop-termination scorer): judge decides whether to build.
    "judge":   ["judge"],
    # Durable end-of-session handoff. Companion to "judge". Read-only and
    # explicit-invoke (automation:manual), so skills_manifest() classifies it
    # as manual even though it is intent-routed here.
    "handoff": ["session-handoff"],
    # Read-side companion to "session-handoff": verify repo state against a
    # handoff, then resume the work. Explicit-invoke (automation:manual).
    "resume":  ["resume-from-handoff"],
    "video": [
        "remotion-orchestrator",
        "remotion-script",
        "remotion-production",
        "remotion-direction",
        "remotion-editing",
        "remotion-integrations",
        "remotion-professionalism",
    ],
    "remotion-video": [
        "remotion-orchestrator",
        "remotion-script",
        "remotion-production",
        "remotion-direction",
        "remotion-editing",
        "remotion-integrations",
        "remotion-professionalism",
    ],
    # Launch crew (wave-4): launch-readiness pre-flight. "ship-it" orchestrates
    # charter -> project-audit -> review -> enhance-debloat, then hands off to the
    # existing ship-chain / tao-loop / ship-release. These skills are
    # automation:manual, so skills_manifest() still classifies them as explicit-
    # invoke even though they are intent-routed here. "launch" is an alias.
    "northstar": ["northstar-shipit", "launch-charter", "ship-it", "launch-project-audit", "launch-review", "launch-enhance-debloat"],
    "ship-it": ["ship-it", "launch-charter", "launch-project-audit", "launch-review", "launch-enhance-debloat"],
    "launch":  ["ship-it", "launch-charter", "launch-project-audit", "launch-review", "launch-enhance-debloat"],
    # RA-693: content + design intents now route to local skill stubs that
    # reference the backing Anthropic Cloud Skills.
    "content": ["brand-ambassador"],
    "design":  ["design-system", "tier-architect"],
}


def skills_for_intent(intent: str) -> list[dict]:
    """Return skills relevant to a PITER intent.
    Returns list of skill dicts (only those that exist)."""
    all_skills = load_all_skills()
    names = _INTENT_SKILLS.get(intent, _INTENT_SKILLS["feature"])
    return [all_skills[n] for n in names if n in all_skills]


def skills_manifest() -> dict[str, list[dict]]:
    """RA-693 — Return skills grouped by automation mode.

    Returns:
        {
          "auto":   [list of intent-routed skills],
          "manual": [list of explicit-invoke-only skills],
        }

    "auto" skills are injected into generator prompts automatically when the
    brief intent matches.  "manual" skills must be referenced explicitly.
    """
    all_skills = load_all_skills()
    auto_names: set[str] = set()
    for names in _INTENT_SKILLS.values():
        auto_names.update(names)

    result: dict[str, list[dict]] = {"auto": [], "manual": []}
    for name, skill in sorted(all_skills.items()):
        # A skill is "auto" if it appears in any intent mapping AND its own
        # frontmatter does not explicitly declare it as manual.
        is_auto = name in auto_names and skill.get("automation", "auto") != "manual"
        bucket = "auto" if is_auto else "manual"
        result[bucket].append({
            "name": name,
            "description": skill.get("description", ""),
            "automation": skill.get("automation", "auto"),
            "anthropic_skill": skill.get("anthropic_skill", ""),
        })
    return result


def invalidate_cache() -> None:
    """Clear the skills cache (useful for testing or hot-reload)."""
    global _SKILLS_CACHE
    _SKILLS_CACHE = None
