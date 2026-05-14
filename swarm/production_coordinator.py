"""swarm/production_coordinator.py — master production line coordinator.

Scans the content_manifest.json for gaps across all 6 businesses and
dispatches the right skill via Claude Code for each. Priority order:
  1. RestoreAssist  2. CARSI  3. Synthex  4. CCW  5. DR  6. NRPG

Each gap becomes a Claude Code session running marketing-orchestrator or
remotion-orchestrator with a pre-filled brief. Output artefacts are
recorded back into the manifest under 'produced'.

Runs daily. Caps at MAX_JOBS_PER_RUN concurrent productions to control
Anthropic/Gemini cost.

Public API:
    run_daily(repo_root) -> ProductionResult
    should_run(state)    -> bool
"""
from __future__ import annotations

import json
import logging
import subprocess
import textwrap
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.production_coordinator")

STATE_KEY = "last_production_coordinator"
REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / ".harness" / "content_manifest.json"

# Priority order (user-confirmed 2026-05-08)
# Synthex elevated to #1 — it's the distribution channel, currently in active build
# RestoreAssist #2 — App Store pipeline critical
# CARSI #3 — compliance delivery needs positioning
PRIORITY_ORDER = ["synthex", "restoreassist", "carsi", "ccw", "disaster-recovery", "nrpg"]

# Max new production jobs per daily run (cost control)
MAX_JOBS_PER_RUN = 3

# Map content type → skill to invoke
SKILL_MAP: dict[str, str] = {
    # App builds → fix orchestrator handles these, not here
    "app_builds": None,

    # Marketing assets → marketing-orchestrator
    "positioning_statement":       "marketing-orchestrator",
    "landing_page_copy":           "marketing-orchestrator",
    "icp_research":                "marketing-orchestrator",
    "seo_keyword_strategy":        "marketing-orchestrator",
    "email_welcome_sequence":      "marketing-orchestrator",
    "email_sequence":              "marketing-orchestrator",
    "email_sequence_trial":        "marketing-orchestrator",
    "email_sequence_customers":    "marketing-orchestrator",
    "app_store_description":       "marketing-orchestrator",
    "case_study_written":          "marketing-orchestrator",
    "one_pager_pdf":               "marketing-orchestrator",
    "competitor_comparison_page":  "marketing-orchestrator",
    "google_ads_copy":             "marketing-orchestrator",
    "b2b_case_study":              "marketing-orchestrator",
    "compliance_use_case_content": "marketing-orchestrator",
    "movement_positioning":        "marketing-orchestrator",
    "practitioner_recruitment_copy": "marketing-orchestrator",
    "positioning_aeo_marketing_automation": "marketing-orchestrator",

    # Videos → remotion-orchestrator
    "product_demo_60s":            "remotion-orchestrator",
    "onboarding_walkthrough":      "remotion-orchestrator",
    "app_store_preview_30s":       "remotion-orchestrator",
    "how_to_create_inspection":    "remotion-orchestrator",
    "how_to_generate_report":      "remotion-orchestrator",
    "social_cut_15s_linkedin":     "remotion-orchestrator",
    "social_cut_15s_instagram":    "remotion-orchestrator",
    "social_cut_15s":              "remotion-orchestrator",
    "brand_awareness_30s":         "remotion-orchestrator",
    "case_study_video_90s":        "remotion-orchestrator",
    "case_study_video":            "remotion-orchestrator",
    "community_intro_60s":         "remotion-orchestrator",
    "what_is_nrpg_explainer":      "remotion-orchestrator",
    "member_testimonial_template": "remotion-orchestrator",
    "klark_brown_style_ep1":       "remotion-orchestrator",
    "klark_brown_style_ep2":       "remotion-orchestrator",
    "structure_systems_scale_explainer": "remotion-orchestrator",
    "independent_restorer_manifesto": "remotion-orchestrator",
    "platform_demo_60s":           "remotion-orchestrator",
    "practitioner_onboarding":     "remotion-orchestrator",
    "product_demo_for_prospects":  "remotion-orchestrator",
    "customer_onboarding_series":  "remotion-orchestrator",
    "how_to_place_order":          "remotion-orchestrator",
    "trade_account_signup_60s":    "remotion-orchestrator",
    "aeo_explainer_for_clients":   "remotion-orchestrator",
    "feature_ai_content_gen":      "remotion-orchestrator",
    "compliance_explainer":        "remotion-orchestrator",

    # Social → marketing-social-content
    "linkedin_launch_post":        "marketing-social-content",
    "linkedin_authority_series":   "marketing-social-content",
    "linkedin_b2b_series":         "marketing-social-content",
    "linkedin_movement_launch":    "marketing-social-content",
    "linkedin_b2b_case_study":     "marketing-social-content",
    "linkedin_thought_leadership": "marketing-social-content",
    "instagram_product_showcase":  "marketing-social-content",
    "practitioner_spotlight_series": "marketing-social-content",
    "aeo_education_series":        "marketing-social-content",
    "content_calendar_30day":      "marketing-orchestrator",
    "content_calendar_60day":      "marketing-orchestrator",
    "practitioner_story_series":   "marketing-social-content",

    # Podcast → NotebookLM + Remotion
    "nrpg_intro_episode":          "remotion-orchestrator",
    "independent_restorer_episode": "remotion-orchestrator",
    "ra_feature_showcase":         "remotion-orchestrator",
    "nrpg_founding_episode":       "remotion-orchestrator",
    "anz_vs_us_market_episode":    "remotion-orchestrator",
    "managed_repair_truth_episode": "remotion-orchestrator",
    "restopreneur_anz_episode":    "remotion-orchestrator",
    "dr_platform_launch_episode":  "remotion-orchestrator",
    "ai_marketing_automation_episode": "remotion-orchestrator",
}


@dataclass
class ProductionJob:
    business_id: str
    content_type: str       # marketing | videos | social | podcast
    asset_id: str
    skill: str
    brief: str
    status: str = "dispatched"
    output_path: str = ""
    linear_ticket_id: str = ""
    created_at: str = ""


@dataclass
class ProductionResult:
    jobs_dispatched: list[ProductionJob] = field(default_factory=list)
    jobs_skipped: int = 0
    error: str | None = None


def should_run(state: dict) -> bool:
    last = state.get(STATE_KEY)
    if not last:
        return True
    try:
        return date.fromisoformat(last[:10]) < date.today()
    except (ValueError, TypeError):
        return True


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _save_manifest(manifest: dict) -> None:
    manifest["_updated"] = date.today().isoformat()
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _wiki_context(business_id: str) -> str:
    """Load relevant wiki pages for a business to enrich the brief."""
    wiki = Path.home() / "2nd Brain" / "2nd Brain" / "Wiki"
    pages = []
    for name in [f"{business_id}.md", "founder.md", "voice-klark-brown.md"]:
        p = wiki / name
        if p.exists():
            pages.append(p.read_text(encoding="utf-8")[:800])
    return "\n\n".join(pages)


def _build_brief(business_id: str, asset_id: str,
                 content_type: str, manifest_biz: dict) -> str:
    """Build a production brief for the marketing/remotion orchestrator."""
    brand_slug = manifest_biz.get("brand_slug", business_id)
    voice = manifest_biz.get("voice", "professional")
    wiki_ctx = _wiki_context(business_id)

    asset_label = asset_id.replace("_", " ").title()

    channel_map = {
        "videos": "video",
        "social": "social",
        "marketing": "web",
        "podcast": "video",
    }
    surface = channel_map.get(content_type, "web")

    return textwrap.dedent(f"""
        Use the {SKILL_MAP.get(asset_id, 'marketing-orchestrator')} skill.

        Brand: {brand_slug}
        Asset: {asset_label}
        Surface: {surface}
        Voice: {voice}

        Business context:
        {wiki_ctx[:600]}

        Brief:
        Produce a {asset_label} for {business_id}. This is one asset in a full agency
        production run. Be complete and production-ready. Do not ask clarifying questions —
        use the brand config and wiki context above to fill any gaps.

        Priority: URGENT — {business_id} is in the top-priority production queue.
        Output the finished artefact or, for video, the complete storyboard + composition
        ready for the render pipeline.
    """).strip()


def _dispatch_via_claude(job: ProductionJob) -> bool:
    """Fire a non-interactive Claude Code session with the skill brief."""
    try:
        result = subprocess.run(
            ["claude", "--print", job.brief],
            capture_output=True, text=True, timeout=300,
            cwd=str(REPO_ROOT),
        )
        if result.returncode == 0:
            # Save output to artefacts directory
            out_dir = REPO_ROOT / ".harness" / "artefacts" / job.business_id
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"{job.asset_id}-{date.today().isoformat()}.md"
            out_file.write_text(result.stdout, encoding="utf-8")
            job.output_path = str(out_file)
            log.info("production: %s/%s → %s", job.business_id, job.asset_id, out_file.name)
            return True
        log.warning("production: claude exited %d for %s/%s",
                    result.returncode, job.business_id, job.asset_id)
    except subprocess.TimeoutExpired:
        log.warning("production: timeout on %s/%s", job.business_id, job.asset_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("production: dispatch failed for %s/%s (%s)",
                    job.business_id, job.asset_id, exc)
    return False


def _file_linear_ticket(job: ProductionJob) -> str:
    """File the production-job Linear ticket. Dedupe-gated.

    The (business_id, asset_id) pair determines uniqueness — if the same
    production job is dispatched again within 14 days (typically because
    the manifest hasn't recorded `produced` yet), the second call returns
    the empty string and writes nothing to Linear.
    """
    try:
        from .margot_tools import propose_idea  # noqa: PLC0415
        from ._dedupe import content_hash, already_filed, record_filed  # noqa: PLC0415
        title = f"[Production] {job.business_id} — {job.asset_id.replace('_', ' ')}"
        body = (
            f"**Business:** {job.business_id}\n"
            f"**Asset:** {job.asset_id}\n"
            f"**Skill:** {job.skill}\n"
            f"**Status:** {job.status}\n"
            + (f"**Output:** {job.output_path}\n" if job.output_path else "")
            + f"\n---\n*Production Coordinator — {date.today().isoformat()}*"
        )
        h = content_hash(title, body)
        existing = already_filed("prod_coord", h)
        if existing is not None:
            log.info(
                "[dedupe:prod_coord] skipped existing hash=%s linear=%s",
                h, existing,
            )
            return ""
        r = propose_idea(
            title=title,
            description=body,
            priority=1 if job.business_id in ("restoreassist", "carsi") else 2,
            project="Pi - Dev -Ops",
        )
        if r.get("status") == "created":
            new_id = r.get("identifier", "")
            record_filed("prod_coord", h, new_id)
            log.info(
                "[dedupe:prod_coord] filed new hash=%s linear=%s", h, new_id,
            )
            return new_id
        return ""
    except Exception as exc:  # noqa: BLE001
        log.debug("production: linear ticket failed (%s)", exc)
        return ""


def run_daily(repo_root: Path | None = None) -> ProductionResult:
    """Scan manifest for gaps and dispatch production jobs in priority order."""
    result = ProductionResult()
    manifest = _load_manifest()
    businesses = manifest.get("businesses", {})
    dispatched = 0

    for biz_id in PRIORITY_ORDER:
        if dispatched >= MAX_JOBS_PER_RUN:
            break

        biz = businesses.get(biz_id, {})
        produced = set(biz.get("produced", {}).keys())
        in_progress = set(biz.get("in_progress", {}).keys())

        for content_type, assets in biz.get("needed", {}).items():
            if content_type == "app_builds":
                continue  # handled by fix_orchestrator

            for asset_id in assets:
                if dispatched >= MAX_JOBS_PER_RUN:
                    break
                if asset_id in produced or asset_id in in_progress:
                    result.jobs_skipped += 1
                    continue

                skill = SKILL_MAP.get(asset_id)
                if not skill:
                    continue

                brief = _build_brief(biz_id, asset_id, content_type, biz)
                job = ProductionJob(
                    business_id=biz_id,
                    content_type=content_type,
                    asset_id=asset_id,
                    skill=skill,
                    brief=brief,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )

                # Mark in-progress immediately
                biz.setdefault("in_progress", {})[asset_id] = {
                    "started": date.today().isoformat(),
                    "skill": skill,
                }
                _save_manifest(manifest)

                # Dispatch
                success = _dispatch_via_claude(job)
                job.status = "done" if success else "failed"

                if success:
                    biz["in_progress"].pop(asset_id, None)
                    biz.setdefault("produced", {})[asset_id] = {
                        "date": date.today().isoformat(),
                        "output_path": job.output_path,
                    }
                    _save_manifest(manifest)

                job.linear_ticket_id = _file_linear_ticket(job)
                result.jobs_dispatched.append(job)
                dispatched += 1

    return result


__all__ = ["run_daily", "should_run", "ProductionJob", "ProductionResult"]
