"""Pure build-method routing for Pi-Dev-Ops founder commands.

This module is intentionally side-effect free: no server imports, no config loading,
no logging setup, no model calls, and no filesystem mutation. It is safe for CLIs,
tests, and workflow gates that need deterministic routing before any build starts.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

INTENT_KEYWORDS: dict[str, list[str]] = {
    "ship-it": ["ship it", "launch crew", "launch readiness", "ready to launch", "is this ready"],
    "repo-intake": [
        "github.com/",
        "gitlab.com/",
        "bitbucket.org/",
        ".git",
        "look at this repo",
        "use this repo",
        "can we use this",
        "bring this in",
    ],
    "hotfix": ["hotfix", "urgent fix", "critical fix", "production down", "p0", "emergency"],
    "bug": ["bug", "fix", "broken", "error", "crash", "failing", "doesn't work", "not working", "issue", "defect", "regression"],
    "video": [
        "explainer",
        "promo video",
        "promo reel",
        "marketing video",
        "training video",
        "release video",
        "feature video",
        "social cut",
        "social ad",
        "video ad",
        "remotion",
        "render video",
        "branded video",
        "intro video",
        "outro video",
        "60s video",
        "30s video",
        "15s video",
        "linkedin video",
        "youtube video",
        "instagram reel",
        "tiktok",
    ],
    "feature": ["add", "implement", "create", "build", "new", "feature", "enhance", "integrate", "support"],
    "chore": ["chore", "cleanup", "refactor", "rename", "update deps", "upgrade", "lint", "format", "migrate", "move"],
    "spike": ["research", "investigate", "explore", "spike", "prototype", "evaluate", "compare", "benchmark", "analyze"],
}

REPO_URL_MARKERS = ("github.com/", "gitlab.com/", "bitbucket.org/")

ADW_TEMPLATES: dict[str, dict[str, Any]] = {
    "repo-intake": {
        "name": "External Repo Intake",
        "steps": ["clone-readonly", "map-stack", "classify-fit", "recommend", "next-lane"],
        "instructions": (
            "WORKFLOW: External Repo Intake / Build Method Selection\n"
            "1. CLONE-READONLY: Shallow clone the external repo into a temp/sandbox directory\n"
            "2. MAP-STACK: Read README, manifests, CI, Dockerfiles, docs, AGENTS/CLAUDE files\n"
            "3. CLASSIFY-FIT: Mark reference-only, tool-adoption, fork-and-adapt, vendor-risk, or not-fit\n"
            "4. RECOMMEND: Explain whether it enhances Pi-Dev-Ops and why\n"
            "5. NEXT-LANE: Select spike/feature/chore/security lane with verification commands; do not code yet"
        ),
    },
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


def classify_intent(brief: str) -> str:
    """Classify a brief's safest first build lane.

    Returns one of: feature, bug, chore, spike, hotfix, video, ship-it,
    repo-intake. Bare repo URLs route to repo-intake so external projects are
    scanned before any build lane starts. Default: feature.
    """
    lower = brief.lower()
    if any(kw in lower for kw in INTENT_KEYWORDS["ship-it"]):
        return "ship-it"

    has_repo_url = any(marker in lower for marker in REPO_URL_MARKERS) or lower.strip().endswith(".git")
    if has_repo_url:
        return "repo-intake"

    for intent in ["hotfix", "bug", "video", "chore", "spike", "feature", "repo-intake"]:
        for kw in INTENT_KEYWORDS[intent]:
            if kw in lower:
                return intent
    return "feature"


def get_adw_template(intent: str) -> dict[str, Any]:
    """Return a defensive copy of the ADW template for a given intent."""
    return deepcopy(ADW_TEMPLATES.get(intent, ADW_TEMPLATES["feature"]))
