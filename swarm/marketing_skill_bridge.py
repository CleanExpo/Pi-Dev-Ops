"""marketing_skill_bridge.py — UNI-2236 skill↔cron bridge.

Runs marketing content generation on a schedule (or after production_coordinator
dispatches), scores with eeat/geo gates, and writes rows to Supabase
`social_posts` for publisher crons to drain.

Public API:
    run_scheduled_bridge() -> BridgeResult
    ingest_production_output(job) -> str | None
    ingest_markdown_file(path, *, business_key, channel) -> str | None
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .marketing_content_generator import generate_social_post, load_icp_context

log = logging.getLogger("swarm.marketing_skill_bridge")

REPO_ROOT = Path(__file__).resolve().parents[1]
SOCIAL_DIR = REPO_ROOT / "marketing-studio" / ".marketing" / "social"
ARTEFACTS_DIR = REPO_ROOT / ".harness" / "artefacts"
STATE_PATH = REPO_ROOT / ".harness" / "marketing-bridge-state.json"

AUTHORITY_BRANDS = ("synthex", "restoreassist", "carsi")


def _founder_id() -> str | None:
    """Unite-Hub social-publisher filters on FOUNDER_USER_ID — must match."""
    import os  # noqa: PLC0415

    raw = (os.environ.get("TAO_FOUNDER_USER_ID") or os.environ.get("FOUNDER_USER_ID") or "").strip()
    if raw:
        return raw
    try:
        from app.server.supabase_log import _select  # noqa: PLC0415

        rows = _select("settings", "select=value&key=eq.founder_user_id&limit=1")
        if rows and rows[0].get("value"):
            return str(rows[0]["value"]).strip() or None
    except Exception as exc:  # noqa: BLE001
        log.debug("marketing_bridge: settings founder_user_id lookup failed: %s", exc)
    return None


@dataclass
class BridgeResult:
    rows_written: int = 0
    rows_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    post_ids: list[str] = field(default_factory=list)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"ingested_files": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"ingested_files": {}}


def _save_state(state: dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(STATE_PATH)
    except OSError as exc:
        log.warning("marketing_bridge: state save failed: %s", exc)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, parts[2].strip()


def _insert_social_post(row: dict[str, Any]) -> str | None:
    if not row.get("founder_id"):
        log.warning("marketing_bridge: skipping insert — founder_id not configured")
        return None
    post_id = str(row.get("id") or uuid.uuid4())
    row["id"] = post_id
    try:
        from app.server.supabase_log import _insert  # noqa: PLC0415

        if _insert("social_posts", row):
            return post_id
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing_bridge: supabase insert failed: %s", exc)
    return None


def _row_from_post(post: Any, *, scheduled_hours: int = 24) -> dict[str, Any]:
    founder_id = _founder_id()
    if not founder_id:
        log.warning("marketing_bridge: TAO_FOUNDER_USER_ID / FOUNDER_USER_ID unset — row will not drain")
    scheduled_at = (_utc_now() + timedelta(hours=scheduled_hours)).isoformat()
    status = "scheduled" if post.scores.verdict != "fail" else "draft"
    post_id = str(uuid.uuid4())
    return {
        "id": post_id,
        "founder_id": founder_id,
        "business_key": post.business_key,
        "title": post.title,
        "content": post.content,
        "platforms": post.platforms,
        "status": status,
        "scheduled_at": scheduled_at,
        "metadata": {
            **post.metadata,
            "hashtags": post.hashtags,
            "quality_verdict": post.scores.verdict,
            "bridge": "marketing_skill_bridge",
        },
        "eeat_score": post.scores.eeat,
        "geo_score": post.scores.geo,
    }


def ingest_markdown_file(
    path: Path,
    *,
    business_key: str,
    channel: str = "linkedin",
) -> str | None:
    """Parse a skill output file and write one social_posts row."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("marketing_bridge: cannot read %s: %s", path, exc)
        return None

    meta, body = _parse_frontmatter(raw)
    topic = meta.get("topic") or meta.get("title") or path.stem
    channel = meta.get("channel") or channel
    brand = meta.get("brand") or business_key

    post = generate_social_post(
        business_key=brand,
        topic=topic,
        body=body,
        channel=channel,
        icp=load_icp_context(brand),
    )
    row = _row_from_post(post)
    row_id = _insert_social_post(row)
    if row_id:
        log.info("marketing_bridge: wrote social_posts row for %s (%s)", path.name, brand)
    return row_id


def ingest_production_output(job: Any) -> str | None:
    """Hook for production_coordinator after a successful skill dispatch."""
    if not job.output_path:
        return None
    path = Path(job.output_path)
    if not path.is_file():
        return None
    channel = "linkedin" if job.content_type == "social" else "linkedin"
    return ingest_markdown_file(path, business_key=job.business_id, channel=channel)


def _discover_skill_outputs() -> list[tuple[Path, str, str]]:
    """Scan marketing-studio + production artefacts for un-ingested markdown."""
    found: list[tuple[Path, str, str]] = []
    if SOCIAL_DIR.is_dir():
        for path in sorted(SOCIAL_DIR.rglob("*.md")):
            parts = path.relative_to(SOCIAL_DIR).parts
            brand = parts[0] if parts else "synthex"
            channel = "linkedin"
            m = re.match(r"([a-z]+)-\d+\.md$", path.name)
            if m:
                channel = m.group(1)
            found.append((path, brand, channel))
    if ARTEFACTS_DIR.is_dir():
        for path in sorted(ARTEFACTS_DIR.glob("*/*.md")):
            biz = path.parent.name
            if "linkedin" in path.stem or path.parent.name in AUTHORITY_BRANDS:
                found.append((path, biz, "linkedin"))
    return found


def run_scheduled_bridge(*, max_rows: int = 5) -> BridgeResult:
    """Scheduled entry: authority brands first, then offers."""
    result = BridgeResult()
    state = _load_state()
    ingested: dict[str, str] = state.setdefault("ingested_files", {})

    candidates = _discover_skill_outputs()
    candidates.sort(key=lambda t: (0 if t[1] in AUTHORITY_BRANDS else 1, t[0].name))

    if not candidates:
        topic = "Autonomous marketing bridge — authority post"
        body = (
            "## What changed\n\n"
            "Pi CEO now pipes marketing-skill output into the social publisher queue "
            "with E-E-A-T and GEO scoring before scheduling.\n\n"
            "## Why it matters\n\n"
            "Publisher crons can drain `social_posts` without a human seeding each row.\n\n"
            "## Question\n\n"
            "Which portfolio brand should lead the next authority series?"
        )
        for brand in AUTHORITY_BRANDS[:max_rows]:
            post = generate_social_post(
                business_key=brand,
                topic=topic,
                body=body,
                channel="linkedin",
            )
            row = _row_from_post(post)
            row_id = _insert_social_post(row)
            if row_id:
                result.rows_written += 1
                result.post_ids.append(row_id)
            else:
                result.errors.append(f"insert failed for generated {brand}")
        state["last_run"] = _utc_now().isoformat()
        _save_state(state)
        return result

    for path, brand, channel in candidates:
        if result.rows_written >= max_rows:
            break
        key = str(path.resolve())
        if ingested.get(key):
            result.rows_skipped += 1
            continue
        row_id = ingest_markdown_file(path, business_key=brand, channel=channel)
        if row_id:
            ingested[key] = _utc_now().isoformat()
            result.rows_written += 1
            result.post_ids.append(row_id)
        else:
            result.errors.append(f"insert failed: {path}")

    state["last_run"] = _utc_now().isoformat()
    _save_state(state)
    return result


__all__ = [
    "BridgeResult",
    "ingest_markdown_file",
    "ingest_production_output",
    "run_scheduled_bridge",
]
