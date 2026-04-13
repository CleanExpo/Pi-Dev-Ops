"""
auto_generator.py — RA-691: Generate .harness/config.yaml from repo URL + brief.

Analyses a project's repo URL and brief description to infer complexity tier,
then produces a complete config.yaml that is ready to write into the project.

Complexity tiers (maps to skill presets in skills/auto-generator/SKILL.md):
  standard  — sonnet planner, sonnet generator, sonnet evaluator (2-tier-codereview)
  complex   — opus planner,   sonnet generator, opus evaluator   (3-tier-webapp)
  critical  — opus planner,   opus generator,   opus evaluator   (4-tier-research)

Usage:
    from .auto_generator import generate_project_config, config_to_yaml
    cfg  = generate_project_config(repo_url="https://github.com/org/repo", brief="...")
    yaml = config_to_yaml(cfg)
"""
from __future__ import annotations

import datetime
import logging

log = logging.getLogger("pi-ceo.auto_generator")

# ── Complexity keyword tables ─────────────────────────────────────────────────

_CRITICAL_KEYWORDS = frozenset({
    "medical", "health", "hipaa", "financial", "banking", "payment",
    "billing", "stripe", "gdpr", "pci", "auth", "authentication",
    "credential", "encryption", "wallet", "compliance", "insurance",
})

_COMPLEX_KEYWORDS = frozenset({
    "ai", "ml", "machine-learning", "machine_learning", "machine learning",
    "data", "analytics", "research", "pipeline", "transform", "etl",
    "distributed", "microservice", "orchestrat", "inference", "embedding",
    "vector", "llm", "nlp", "recommendation", "forecast",
})

# ── Tier config templates ─────────────────────────────────────────────────────

_TIER_CONFIGS: dict[str, dict] = {
    "standard": {
        "agents": {
            "planner":   {"model": "sonnet", "temperature": 0.3},
            "generator": {"model": "sonnet", "temperature": 0.2, "sdk": True},
            "evaluator": {"model": "sonnet", "temperature": 0.1, "sdk": True, "parallel": True},
        },
        "qa": {"max_rounds": 2, "auto_escalate": False},
        "preset": "2-tier-codereview",
    },
    "complex": {
        "agents": {
            "planner":   {"model": "opus",   "temperature": 0.3},
            "generator": {"model": "sonnet", "temperature": 0.2, "sdk": True},
            "evaluator": {"model": "opus",   "temperature": 0.1, "sdk": True, "parallel": True},
        },
        "qa": {"max_rounds": 3, "auto_escalate": True},
        "preset": "3-tier-webapp",
    },
    "critical": {
        "agents": {
            "planner":   {"model": "opus", "temperature": 0.2},
            "generator": {"model": "opus", "temperature": 0.1, "sdk": True},
            "evaluator": {"model": "opus", "temperature": 0.1, "sdk": True, "parallel": True},
        },
        "qa": {"max_rounds": 4, "auto_escalate": True},
        "preset": "4-tier-research",
    },
}

_SDK_BLOCK = {
    "enabled_by_flag": "TAO_USE_AGENT_SDK",
    "fallback_removed": True,
    "reference_impl": "app/server/agents/board_meeting.py",
    "version_policy": ".harness/agents/sdk-version-policy.md",
}


# ── Public API ────────────────────────────────────────────────────────────────

def classify_project_complexity(repo_url: str, brief: str = "") -> str:
    """Infer complexity tier from repo URL and brief text.

    Returns 'critical', 'complex', or 'standard'.
    Critical takes precedence over complex.
    """
    text = (repo_url + " " + brief).lower()

    for kw in _CRITICAL_KEYWORDS:
        if kw in text:
            log.info("auto_generator: critical tier matched keyword=%r repo=%s", kw, repo_url)
            return "critical"
    for kw in _COMPLEX_KEYWORDS:
        if kw in text:
            log.info("auto_generator: complex tier matched keyword=%r repo=%s", kw, repo_url)
            return "complex"
    return "standard"


def generate_project_config(
    repo_url: str,
    brief: str = "",
    existing_config: str | None = None,
) -> dict:
    """Generate a complete harness config dict for a project.

    When existing_config is provided, the returned dict only contains the
    fields that differ from the existing config — allowing targeted upgrades
    rather than wholesale replacement.  Currently returns the full config in
    all cases; diff logic is reserved for a future iteration.

    Returns a dict suitable for serialisation with config_to_yaml().
    """
    tier = classify_project_complexity(repo_url, brief)
    project_slug = (
        repo_url.rstrip("/").split("/")[-1].lower().replace(".git", "")
        if repo_url else "unknown"
    )
    tier_cfg = _TIER_CONFIGS[tier]
    cfg: dict = {
        "project": project_slug,
        "harness_version": "1.2",
        "auto_generated": True,
        "auto_generated_at": datetime.date.today().isoformat(),
        "complexity_tier": tier,
        "preset": tier_cfg["preset"],
        "agents": tier_cfg["agents"],
        "qa": tier_cfg["qa"],
        "sdk": _SDK_BLOCK,
    }
    log.info(
        "auto_generator: config generated project=%s tier=%s preset=%s",
        project_slug, tier, tier_cfg["preset"],
    )
    return cfg


def config_to_yaml(cfg: dict) -> str:
    """Serialise a config dict to a YAML string with a header comment.

    Uses PyYAML (pyyaml>=6, in requirements.txt).
    """
    import yaml  # noqa: PLC0415  — PyYAML is in requirements.txt
    header = (
        f"# Auto-generated by Pi-CEO auto_generator (RA-691)\n"
        f"# Project: {cfg.get('project', '?')}  "
        f"Tier: {cfg.get('complexity_tier', '?')}  "
        f"Preset: {cfg.get('preset', '?')}\n"
        f"# Generated: {cfg.get('auto_generated_at', '?')}\n"
        f"# Edit this file to override auto-detected settings.\n\n"
    )
    return header + yaml.dump(cfg, default_flow_style=False, sort_keys=False)
