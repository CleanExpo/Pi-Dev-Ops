"""
swarm/meta_curator.py — RA-1839: Skill self-authoring proposer.

Reads .harness/lessons.jsonl (weekly) and merged-PR diffs (daily),
clusters recurring patterns, proposes new SKILL.md drafts via the
existing skill-creator skill. Every proposal HITL-gated through
draft_review.

This module is the READER + CLUSTERER + PROPOSAL SHELL.
The "author the SKILL.md body" step delegates to claude_agent_sdk
when available (RA-1839 close-out 2026-05-02 — see
``_compose_skill_body_via_sdk``). When the SDK isn't reachable
the curator falls back to a deterministic stub body that the
operator can still 👍 to author manually.

Public API:
  scan_lessons(since_ts=None) -> list[Cluster]
  scan_pr_diffs(since_days=1) -> list[Cluster]
  propose_from_cluster(cluster) -> dict   # writes proposal to ledger + posts draft
  list_proposals(status=None) -> list[dict]

Cluster threshold: ≥3 evidence rows in the rolling window.
Rate limit: max 3 NEW proposals per 7-day window.

State:
  .harness/curator/proposals.jsonl     — append-only ledger
  .harness/curator/state.json          — last-seen offsets + cluster IDs
  .harness/curator/rejected.jsonl      — clusters the user 👎'd; archived 30d
  .harness/curator/expired.jsonl       — proposals that timed out
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.meta_curator")

REPO_ROOT = Path(__file__).resolve().parents[1]
LESSONS_FILE = REPO_ROOT / ".harness" / "lessons.jsonl"
CURATOR_DIR = REPO_ROOT / ".harness" / "curator"
PROPOSALS_FILE = CURATOR_DIR / "proposals.jsonl"
STATE_FILE = CURATOR_DIR / "state.json"
REJECTED_FILE = CURATOR_DIR / "rejected.jsonl"
EXPIRED_FILE = CURATOR_DIR / "expired.jsonl"
SKILLS_DIR = REPO_ROOT / "skills"

CLUSTER_MIN_EVIDENCE = 3
PROPOSAL_RATE_LIMIT_PER_WEEK = 3
LESSONS_LOOKBACK_DAYS = 30
PR_LOOKBACK_DAYS = 60
REJECT_COOLOFF_DAYS = 30


@dataclass
class Cluster:
    cluster_id: str          # stable hash of (key, source)
    source: str              # "lessons" | "prs"
    key: str                 # readable cluster key
    summary: str             # short human description
    evidence: list[dict[str, Any]] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _ensure_dir() -> None:
    CURATOR_DIR.mkdir(parents=True, exist_ok=True)


def _read_jsonl(p: Path) -> list[dict[str, Any]]:
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            log.debug("meta_curator: skipping malformed jsonl line in %s", p)
    return out


def _append_jsonl(p: Path, row: dict[str, Any]) -> None:
    _ensure_dir()
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"last_lessons_ts": None, "last_pr_check_ts": None,
                "proposals_this_week": 0, "week_start": None}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"last_lessons_ts": None, "last_pr_check_ts": None,
                "proposals_this_week": 0, "week_start": None}


def _save_state(state: dict[str, Any]) -> None:
    _ensure_dir()
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


def _cluster_id(source: str, key: str) -> str:
    h = hashlib.sha256(f"{source}::{key}".encode("utf-8")).hexdigest()
    return h[:16]


def _is_in_cooloff(cluster_id: str) -> bool:
    """True if a recent rejection blocks re-proposing this cluster for 30d."""
    cutoff = _now() - timedelta(days=REJECT_COOLOFF_DAYS)
    for row in _read_jsonl(REJECTED_FILE):
        if row.get("cluster_id") != cluster_id:
            continue
        try:
            ts = datetime.fromisoformat(row.get("ts", ""))
            if ts >= cutoff:
                return True
        except Exception:
            continue
    return False


def _existing_skill_names() -> set[str]:
    if not SKILLS_DIR.exists():
        return set()
    return {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}


def _rate_limit_ok(state: dict[str, Any]) -> bool:
    week_start = state.get("week_start")
    week_count = state.get("proposals_this_week", 0)
    now = _now()
    if week_start is None:
        return True
    try:
        ws = datetime.fromisoformat(week_start)
    except Exception:
        return True
    if (now - ws).days >= 7:
        return True
    return week_count < PROPOSAL_RATE_LIMIT_PER_WEEK


def _bump_rate(state: dict[str, Any]) -> None:
    now = _now()
    week_start = state.get("week_start")
    fresh = (week_start is None or
             (now - datetime.fromisoformat(week_start)).days >= 7)
    if fresh:
        state["week_start"] = now.isoformat()
        state["proposals_this_week"] = 1
    else:
        state["proposals_this_week"] = state.get("proposals_this_week", 0) + 1


# ── Cluster strategies ───────────────────────────────────────────────────────


def scan_lessons(since_ts: str | None = None) -> list[Cluster]:
    """Cluster .harness/lessons.jsonl by (category, repo) within lookback window."""
    rows = _read_jsonl(LESSONS_FILE)
    if not rows:
        return []
    cutoff = _now() - timedelta(days=LESSONS_LOOKBACK_DAYS)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        ts_raw = r.get("ts") or r.get("timestamp") or ""
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except Exception:
            continue
        if ts < cutoff:
            continue
        if since_ts:
            try:
                if ts <= datetime.fromisoformat(since_ts):
                    continue
            except Exception:
                pass
        category = (r.get("category") or r.get("type") or "uncategorised").strip()
        repo = (r.get("repo") or r.get("repository") or "unknown").strip()
        grouped[(category, repo)].append(r)

    clusters: list[Cluster] = []
    for (category, repo), evidence in grouped.items():
        if len(evidence) < CLUSTER_MIN_EVIDENCE:
            continue
        key = f"{category}:{repo}"
        clusters.append(Cluster(
            cluster_id=_cluster_id("lessons", key),
            source="lessons",
            key=key,
            summary=f"{len(evidence)} lessons in category={category} for repo={repo}",
            evidence=evidence,
        ))
    return clusters


def scan_pr_diffs(since_days: int = 1) -> list[Cluster]:
    """Cluster recently-merged PRs by recurring file path."""
    cmd = ["git", "log",
           f"--since={since_days} days ago",
           "--merges", "--pretty=format:%H|%s",
           "--name-only"]
    try:
        out = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True,
                             text=True, timeout=30)
    except Exception as exc:
        log.debug("git log failed (out of repo?): %s", exc)
        return []
    if out.returncode != 0:
        return []

    file_to_prs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    current_pr: dict[str, Any] | None = None
    for line in out.stdout.splitlines():
        line = line.rstrip()
        if "|" in line and len(line.split("|")[0]) == 40:
            sha, _, subject = line.partition("|")
            current_pr = {"sha": sha, "subject": subject}
            continue
        if not line or current_pr is None:
            continue
        file_to_prs[line].append(current_pr)

    clusters: list[Cluster] = []
    for fp, prs in file_to_prs.items():
        if len(prs) < CLUSTER_MIN_EVIDENCE:
            continue
        key = f"pr-recurrence:{fp}"
        clusters.append(Cluster(
            cluster_id=_cluster_id("prs", key),
            source="prs",
            key=key,
            summary=f"{len(prs)} merged PRs touching {fp} in last {since_days}d",
            evidence=[{"sha": p["sha"], "subject": p["subject"]} for p in prs],
        ))
    return clusters


# ── Proposal flow ────────────────────────────────────────────────────────────


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return s.strip("-")[:48] or "proposed-skill"


def _compose_skill_body_via_sdk(
    cluster: Cluster, proposed_name: str
) -> str | None:
    """Author a SKILL.md body via claude_agent_sdk. Returns None on any failure.

    Closes the RA-1839 L13 SDK plug-point. Brief sent to Claude is:
    cluster summary + first 5 evidence rows + the standard frontmatter
    schema. Per `Pi-Dev-Ops/CLAUDE.md` model-routing policy, the curator
    runs as role=`generator` (Sonnet by default; never Opus).

    Returns the full SKILL.md content (frontmatter + body) on success,
    None when the SDK isn't installed, the API key is unset, or the
    request times out. Caller falls back to ``_draft_skill_md_stub``.
    """
    try:
        import os
        if os.environ.get("TAO_SWARM_SKIP_SDK", "0") == "1":
            log.debug("curator: TAO_SWARM_SKIP_SDK=1 — using stub")
            return None
        if not (os.environ.get("ANTHROPIC_API_KEY", "").strip()
                or Path(os.path.expanduser("~/.claude")).exists()):
            log.debug("curator: no anthropic creds visible — using stub")
            return None
    except Exception:
        return None

    try:
        # Lazy import — keeps base swarm tests passing without the SDK installed.
        from claude_agent_sdk import (  # noqa: PLC0415
            ClaudeAgentOptions,
            ClaudeSDKClient,
        )
    except Exception as exc:
        log.debug("curator: claude_agent_sdk not importable (%s) — using stub", exc)
        return None

    evidence_preview = "\n".join(
        f"- {json.dumps(e, ensure_ascii=False)[:200]}"
        for e in cluster.evidence[:5]
    )
    prompt = (
        f"You are skill-creator inside Pi-CEO. Author a complete SKILL.md "
        f"for a new reusable skill named `{proposed_name}`. The skill is "
        f"proposed by the meta-curator from this cluster:\n\n"
        f"- source: {cluster.source}\n"
        f"- key: {cluster.key}\n"
        f"- summary: {cluster.summary}\n\n"
        f"Evidence sample:\n{evidence_preview}\n\n"
        f"Output requirements:\n"
        f"1. YAML frontmatter with fields: name, description, owner_role, "
        f"status. status MUST be `proposed` (operator approves before promote).\n"
        f"2. # Heading then 'Why this exists' / 'When to use' / "
        f"'When NOT to use' / 'Pipeline' / 'Verification' sections.\n"
        f"3. No prose preamble before the frontmatter — the response MUST "
        f"start with `---`.\n"
        f"4. Body should be runnable instructions, not theory.\n"
        f"5. Length 60-180 lines. No code blocks longer than 30 lines.\n"
        f"6. No emojis. No first-person business language (We/Our/I/Us/My).\n"
    )

    try:
        import asyncio
        async def _run() -> str | None:
            opts = ClaudeAgentOptions(
                model="claude-sonnet-4-6",
                permission_mode="bypassPermissions",
            )
            chunks: list[str] = []
            async with ClaudeSDKClient(opts) as client:
                await client.query(prompt)
                async for msg in client.receive_response():
                    content = getattr(msg, "content", None)
                    if isinstance(content, list):
                        for c in content:
                            txt = getattr(c, "text", None)
                            if txt:
                                chunks.append(txt)
                    elif isinstance(content, str):
                        chunks.append(content)
            return "".join(chunks).strip() or None

        # Run with a hard ceiling — never block the cron tick longer than 90s.
        body = asyncio.run(asyncio.wait_for(_run(), timeout=90))
    except Exception as exc:  # noqa: BLE001 — never raise from cron path
        log.warning("curator: SDK compose failed (%s) — using stub", exc)
        return None

    if not body or not body.startswith("---"):
        log.warning("curator: SDK returned non-frontmatter content — using stub")
        return None
    return body


def _draft_skill_md_stub(cluster: Cluster) -> tuple[str, str]:
    """Return (proposed_skill_name, SKILL.md content).

    Tries claude_agent_sdk first via ``_compose_skill_body_via_sdk``;
    falls back to a deterministic stub when SDK isn't available.
    """
    name = _slugify(f"curator-{cluster.key}")[:48]

    sdk_body = _compose_skill_body_via_sdk(cluster, name)
    if sdk_body:
        log.info("curator: SDK composed body for %s (%d chars)",
                 name, len(sdk_body))
        return name, sdk_body

    body = (
        f"---\n"
        f"name: {name}\n"
        f"description: PROPOSED — meta-curator suggests authoring this skill from {cluster.summary}\n"
        f"owner_role: (curator-proposed)\n"
        f"status: proposed\n"
        f"---\n\n"
        f"# {name}\n\n"
        f"**This is a curator stub.** The skill-creator skill should fill the body.\n\n"
        f"## Source cluster\n\n"
        f"- cluster_id: `{cluster.cluster_id}`\n"
        f"- source: `{cluster.source}`\n"
        f"- key: `{cluster.key}`\n"
        f"- evidence rows: {len(cluster.evidence)}\n\n"
        f"## Evidence sample\n\n"
        + "\n".join(f"- `{json.dumps(e, ensure_ascii=False)[:120]}`"
                    for e in cluster.evidence[:5])
        + "\n\n## Why this might warrant a skill\n\n"
        f"Three or more recurring rows in the same cluster suggests a pattern\n"
        f"that's worth promoting from one-off lessons to a reusable skill.\n"
    )
    return name, body


def propose_from_cluster(
    cluster: Cluster,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Persist a proposal record + post a draft to telegram-draft-for-review.

    Returns the proposal record with `status` set to:
      * "rejected_dedup"     — name collides with an existing skill
      * "rejected_cooloff"   — recent rejection still in 30d window
      * "rejected_rate"      — weekly proposal limit hit
      * "queued_dry_run"     — dry_run only, no draft posted
      * "pending"            — draft posted, awaiting reaction
    """
    state = _load_state()

    name, body = _draft_skill_md_stub(cluster)

    # Existing-skill collision check
    if name in _existing_skill_names():
        rec = {
            "ts": _now_iso(), "cluster_id": cluster.cluster_id,
            "status": "rejected_dedup",
            "proposed_skill_name": name,
            "reason": "skill name already exists",
        }
        _append_jsonl(PROPOSALS_FILE, rec)
        return rec

    # Cool-off window
    if _is_in_cooloff(cluster.cluster_id):
        rec = {
            "ts": _now_iso(), "cluster_id": cluster.cluster_id,
            "status": "rejected_cooloff",
            "proposed_skill_name": name,
            "reason": "recently rejected; 30d cooloff active",
        }
        _append_jsonl(PROPOSALS_FILE, rec)
        return rec

    # Rate limit
    if not _rate_limit_ok(state):
        rec = {
            "ts": _now_iso(), "cluster_id": cluster.cluster_id,
            "status": "rejected_rate",
            "proposed_skill_name": name,
            "reason": f"weekly limit ({PROPOSAL_RATE_LIMIT_PER_WEEK}) reached",
        }
        _append_jsonl(PROPOSALS_FILE, rec)
        return rec

    proposal_id = uuid.uuid4().hex[:12]
    rec = {
        "ts": _now_iso(), "proposal_id": proposal_id,
        "cluster_id": cluster.cluster_id,
        "trigger_source": cluster.source,
        "cluster_summary": cluster.summary,
        "evidence_count": len(cluster.evidence),
        "proposed_skill_name": name,
        "proposed_skill_path": f"skills/{name}/SKILL.md",
        "proposed_skill_content": body,
        "status": "queued_dry_run" if dry_run else "pending",
        "created_at": _now_iso(),
    }

    if dry_run:
        _append_jsonl(PROPOSALS_FILE, rec)
        return rec

    # Post the draft to review chat (HITL gate)
    try:
        from . import draft_review
        draft_payload = (
            f"📥 Skill proposal — `{name}`\n\n"
            f"Source: {cluster.source} cluster `{cluster.key}`\n"
            f"Evidence: {len(cluster.evidence)} rows in window\n\n"
            f"Proposed brief (skill-creator will expand on 👍):\n"
            f"{body[:600]}\n"
            f"\nReact 👍 to author the SKILL.md, ❌ to reject (30d cooloff)."
        )
        review_chat = (__import__("os").environ.get("REVIEW_CHAT_ID")
                      or "smoke-curator")
        draft = draft_review.post_draft(
            draft_text=draft_payload,
            destination_chat_id=str(review_chat),
            drafted_by_role="Curator",
            originating_intent_id=proposal_id,
        )
        rec["draft_id"] = draft.get("draft_id")
    except Exception as exc:
        log.warning("curator: draft post failed: %s", exc)
        rec["status"] = "draft_post_failed"
        rec["error"] = repr(exc)

    _append_jsonl(PROPOSALS_FILE, rec)
    _bump_rate(state)
    _save_state(state)

    try:
        from . import audit_emit
        audit_emit.row("curator_proposal", "Curator",
                       cluster_id=cluster.cluster_id,
                       proposed_skill_name=name,
                       evidence_count=len(cluster.evidence))
    except Exception:
        pass

    return rec


def list_proposals(status: str | None = None) -> list[dict[str, Any]]:
    rows = _read_jsonl(PROPOSALS_FILE)
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return rows


def _latest_proposal_state(proposal_id: str) -> tuple[int, dict[str, Any] | None]:
    """Return (line_index, latest_record) for the most recent proposal row.

    Each accept/reject/expire appends a NEW row with the same proposal_id and
    an updated `status` — we read the most recent one to determine current
    state. The returned `line_index` is unused today but kept for future
    `_rewrite_jsonl` semantics if we ever switch to in-place edits.
    """
    rows = _read_jsonl(PROPOSALS_FILE)
    latest = None
    latest_idx = -1
    for i, row in enumerate(rows):
        if row.get("proposal_id") == proposal_id:
            latest = row
            latest_idx = i
    return latest_idx, latest


def accept_proposal(proposal_id: str) -> dict[str, Any]:
    """Materialise a curator proposal — write SKILL.md + flip ledger to accepted.

    RA-1848. Idempotent: if already accepted, returns the existing record
    without re-writing the file.
    """
    _, current = _latest_proposal_state(proposal_id)
    if current is None:
        raise KeyError(f"proposal_id {proposal_id} not found in {PROPOSALS_FILE}")
    if current.get("status") == "accepted":
        return current

    name = current["proposed_skill_name"]
    body = current.get("proposed_skill_content") or ""
    skill_dir = SKILLS_DIR / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(body, encoding="utf-8")

    accepted = {
        "ts": _now_iso(),
        "proposal_id": proposal_id,
        "cluster_id": current.get("cluster_id"),
        "proposed_skill_name": name,
        "proposed_skill_path": f"skills/{name}/SKILL.md",
        "status": "accepted",
        "accepted_at": _now_iso(),
        "skill_path_written": str(skill_path.relative_to(REPO_ROOT)),
    }
    _append_jsonl(PROPOSALS_FILE, accepted)

    try:
        from . import audit_emit  # noqa: PLC0415
        audit_emit.row(
            "curator_accepted", "Curator",
            proposal_id=proposal_id,
            cluster_id=current.get("cluster_id"),
            skill_path=accepted["skill_path_written"],
        )
    except Exception:
        pass

    return accepted


def reject_proposal(proposal_id: str, *, reason: str | None = None) -> dict[str, Any]:
    """Reject a curator proposal — append to rejected.jsonl + flip ledger.

    RA-1848. The 30d cooloff window in `_is_in_cooloff()` reads
    `rejected.jsonl`, so this is what activates the cooloff.
    """
    _, current = _latest_proposal_state(proposal_id)
    if current is None:
        raise KeyError(f"proposal_id {proposal_id} not found")
    if current.get("status") == "rejected":
        return current

    rejected = {
        "ts": _now_iso(),
        "proposal_id": proposal_id,
        "cluster_id": current.get("cluster_id"),
        "proposed_skill_name": current.get("proposed_skill_name"),
        "status": "rejected",
        "rejected_at": _now_iso(),
        "reason": reason or "operator reaction ❌",
    }
    _append_jsonl(PROPOSALS_FILE, rejected)
    # rejected.jsonl is the file `_is_in_cooloff()` reads
    _append_jsonl(REJECTED_FILE, {
        "ts": _now_iso(),
        "cluster_id": current.get("cluster_id"),
        "proposal_id": proposal_id,
        "reason": rejected["reason"],
    })

    try:
        from . import audit_emit  # noqa: PLC0415
        audit_emit.row(
            "curator_rejected", "Curator",
            proposal_id=proposal_id,
            cluster_id=current.get("cluster_id"),
            reason=rejected["reason"],
        )
    except Exception:
        pass

    return rejected


def expire_proposal(proposal_id: str) -> dict[str, Any]:
    """Expire a curator proposal — append to expired.jsonl + flip ledger.

    RA-1848. Called for proposals whose draft hit `expired` status without a
    reaction within the draft_review.expire_overdue() window.
    """
    _, current = _latest_proposal_state(proposal_id)
    if current is None:
        raise KeyError(f"proposal_id {proposal_id} not found")
    if current.get("status") == "expired":
        return current

    expired = {
        "ts": _now_iso(),
        "proposal_id": proposal_id,
        "cluster_id": current.get("cluster_id"),
        "proposed_skill_name": current.get("proposed_skill_name"),
        "status": "expired",
        "expired_at": _now_iso(),
    }
    _append_jsonl(PROPOSALS_FILE, expired)
    _append_jsonl(EXPIRED_FILE, expired)

    try:
        from . import audit_emit  # noqa: PLC0415
        audit_emit.row(
            "curator_expired", "Curator",
            proposal_id=proposal_id,
            cluster_id=current.get("cluster_id"),
        )
    except Exception:
        pass

    return expired


def reconcile_proposals() -> dict[str, Any]:
    """Sweep pending curator proposals against current draft_review state.

    RA-1848. Polled from the orchestrator main loop. For each proposal still
    in `pending` status:
      * draft_review status `sent`     → accept_proposal() + write SKILL.md
      * draft_review status `revise`   → reject_proposal() + populate cooloff
      * draft_review status `expired`  → expire_proposal()

    Returns a summary dict suitable for daily-brief inclusion.
    """
    from . import draft_review  # noqa: PLC0415

    snap = draft_review._load_snapshot()  # type: ignore[attr-defined]
    rows = _read_jsonl(PROPOSALS_FILE)

    # Walk forward; keep the latest status per proposal_id.
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        pid = row.get("proposal_id")
        if pid:
            latest[pid] = row

    accepted: list[str] = []
    rejected: list[str] = []
    expired: list[str] = []
    skipped: list[str] = []

    for pid, prop in latest.items():
        if prop.get("status") != "pending":
            continue
        draft_id = prop.get("draft_id")
        if not draft_id:
            skipped.append(pid)
            continue
        draft = snap.get(draft_id)
        if not draft:
            skipped.append(pid)
            continue
        ds = draft.get("status")
        if ds == "sent":
            try:
                accept_proposal(pid)
                accepted.append(pid)
            except Exception as exc:  # pragma: no cover — safety net
                log.warning("accept_proposal failed for %s: %s", pid, exc)
        elif ds == "revise":
            try:
                reject_proposal(pid, reason="operator reacted ❌ on draft")
                rejected.append(pid)
            except Exception as exc:
                log.warning("reject_proposal failed for %s: %s", pid, exc)
        elif ds == "expired":
            try:
                expire_proposal(pid)
                expired.append(pid)
            except Exception as exc:
                log.warning("expire_proposal failed for %s: %s", pid, exc)
        else:
            # still pending / deferred — leave alone
            continue

    return {
        "ts": _now_iso(),
        "accepted": accepted,
        "rejected": rejected,
        "expired": expired,
        "skipped": skipped,
    }


def run_now(dry_run: bool = False) -> dict[str, Any]:
    """Trigger one full curator cycle. Used by /curator:run-now Telegram cmd."""
    lessons_clusters = scan_lessons()
    pr_clusters = scan_pr_diffs(since_days=1)
    all_clusters = lessons_clusters + pr_clusters

    results: list[dict[str, Any]] = []
    for c in all_clusters:
        results.append(propose_from_cluster(c, dry_run=dry_run))

    return {
        "ts": _now_iso(),
        "lessons_clusters": len(lessons_clusters),
        "pr_clusters": len(pr_clusters),
        "results": results,
    }


__all__ = [
    "Cluster", "scan_lessons", "scan_pr_diffs",
    "propose_from_cluster", "list_proposals", "run_now",
    # RA-1848 acceptance handler
    "accept_proposal", "reject_proposal", "expire_proposal",
    "reconcile_proposals",
]
