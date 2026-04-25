"""Webhook routes: GitHub, Linear, morning-intel, Telegram, routine-complete (RA-937, RA-1011)."""
import json
import logging
import os
import re
import urllib.request as _ur
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, field_validator

from ..auth import require_auth, require_rate_limit
from ..sessions import create_session
from ..supabase_log import mark_alert_acked
from ..webhook import (
    verify_github_signature,
    verify_linear_signature,
    parse_github_event,
    parse_linear_event,
    linear_issue_to_brief,
)
from .. import config
from .sessions import _find_active_session_for_repo

_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

log = logging.getLogger("pi-ceo.main")

router = APIRouter()


def _telegram_send(token: str, chat_id: int | str, text: str) -> None:
    """Fire-and-forget helper — sends a message via Telegram Bot API."""
    import urllib.request as _ur
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
    req = _ur.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with _ur.urlopen(req, timeout=8):
            pass
    except Exception as exc:
        log.warning("Telegram reply failed: %s", exc)


@router.post("/api/webhook", dependencies=[Depends(require_rate_limit)])
async def webhook(request: Request):
    raw_body = await request.body()
    gh_event = request.headers.get("x-github-event", "")
    gh_sig = request.headers.get("x-hub-signature-256", "")
    linear_sig = request.headers.get("linear-signature", "")

    if gh_event and gh_sig:
        # GitHub webhook
        if not config.WEBHOOK_SECRET:
            raise HTTPException(500, "Webhook secret not configured")
        if not verify_github_signature(raw_body, gh_sig, config.WEBHOOK_SECRET):
            raise HTTPException(401, "Invalid signature")
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            raise HTTPException(400, "Invalid JSON")
        # RA-847 — CI failure alerting (handled before parse_github_event which
        # only understands push/PR events and returns None for workflow_run).
        if gh_event == "workflow_run":
            await _handle_workflow_run(payload, request)
            return {"ok": True, "event": "workflow_run"}

        event = parse_github_event(gh_event, payload)
        if not event:
            return {"skipped": True, "reason": f"Unsupported event: {gh_event}"}
        repo_url = event["repo_url"]
        # RA-1182 — skip webhook-triggered sessions on Pi-CEO's own auto-
        # branches (pidev/auto-<sid>, pidev/analysis-*). Without this, every
        # push from a previous session's fix spawns a NEW session that
        # analyses the repo and pushes another auto-branch — recursive
        # self-modification that produced the 43-zombie-branch pile-up.
        ref = event.get("ref", "")
        if "pidev/" in ref:
            log.info("Skipping webhook session for own auto-branch: %s", ref)
            return {"skipped": True, "reason": f"Pi-CEO auto-branch: {ref}"}
        # RA-1182 — skip self-modification. Pi-Dev-Ops is the harness itself;
        # webhook-fired sessions against its own repo just commit random
        # "fixes" to scripts/* that were never requested. Portfolio repos
        # (carsi, dr-nrpg, restoreassist, etc.) still trigger normally.
        if "CleanExpo/Pi-Dev-Ops" in repo_url or "pi-dev-ops" in repo_url.lower():
            log.info("Skipping webhook session against Pi-CEO harness itself: %s", repo_url)
            return {"skipped": True, "reason": "Pi-CEO harness self-modification blocked"}
        existing_id = _find_active_session_for_repo(repo_url)
        if existing_id:
            log.info("Skipping duplicate webhook for %s — session %s already active", repo_url, existing_id)
            return {"skipped": True, "reason": f"session {existing_id} already active", "session_id": existing_id}
        brief = f"Triggered by GitHub {event['event']} on {event.get('ref', 'unknown')}. Analyze changes, run tests if present, commit fixes."
        try:
            session = await create_session(repo_url, brief, config.EVALUATOR_MODEL)
        except RuntimeError as e:
            raise HTTPException(429, str(e))
        return {"triggered": True, "session_id": session.id, "repo": repo_url, "event": event["event"]}

    elif linear_sig:
        # Linear webhook
        if not config.LINEAR_WEBHOOK_SECRET:
            raise HTTPException(500, "Linear webhook secret not configured")
        if not verify_linear_signature(raw_body, linear_sig, config.LINEAR_WEBHOOK_SECRET):
            raise HTTPException(401, "Invalid signature")
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            raise HTTPException(400, "Invalid JSON")
        event = parse_linear_event(payload)
        if not event:
            return {"skipped": True, "reason": "Not an issue-started event"}
        if not event.get("repo_url"):
            return {"skipped": True, "reason": "No repo URL found in issue (add repo:<url> label)"}
        repo_url = event["repo_url"]
        existing_id = _find_active_session_for_repo(repo_url)
        if existing_id:
            log.info("Skipping duplicate webhook for %s — session %s already active", repo_url, existing_id)
            return {"skipped": True, "reason": f"session {existing_id} already active", "session_id": existing_id}
        brief = linear_issue_to_brief(event)
        linear_issue_id = event.get("issue_id") or None
        try:
            session = await create_session(
                repo_url, brief, config.EVALUATOR_MODEL,
                linear_issue_id=linear_issue_id,
                autonomy_triggered=True,  # RA-888: webhook sessions are autonomous
            )
        except RuntimeError as e:
            raise HTTPException(429, str(e))
        return {
            "triggered": True,
            "session_id": session.id,
            "source": "linear",
            "event": event.get("event", "issue_started"),
            "title": event["title"],
            "linear_issue_id": linear_issue_id,
        }

    else:
        raise HTTPException(400, "Missing webhook signature header (x-hub-signature-256 or Linear-Signature)")


# ── RA-847: CI failure alerting helpers ──────────────────────────────────────

_LINEAR_ENDPOINT = "https://api.linear.app/graphql"

# Per-repo routing: CI failure tickets go to the correct team + project.
# Default falls back to the Pi-Dev-Ops project (env-configured).
_REPO_LINEAR_ROUTING: dict[str, dict[str, str]] = {
    "CleanExpo/CARSI": {
        "teamId":    "91b3cd04-86eb-422d-81e2-9aa37db2f2f5",  # G-Pilot
        "projectId": "20538e04-ba27-467d-b632-1fb346063089",  # CARSI
    },
    "CleanExpo/Synthex": {
        "teamId":    "b887971b-6761-4260-a111-b94dbb628ebe",  # Synthex (SYN)
        "projectId": "3125c6e4-b729-48d4-a718-400a2b83ddc5",  # Synthex project
    },
    "CleanExpo/Pi-Dev-Ops": {
        "teamId":    "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673",  # RestoreAssist (RA)
        "projectId": "f45212be-3259-4bfb-89b1-54c122c939a7",  # Pi - Dev -Ops
    },
}



# RA-1008: Persist dedup set so restarts don't emit duplicate CI tickets.
# Stored as a JSON list of integers in DATA_DIR/dedup-run-ids.json.
_DEDUP_FILE = Path(config.DATA_DIR) / "dedup-run-ids.json"
_DEDUP_MAX = 500  # cap size; oldest half evicted when full


def _load_dedup_set() -> set[int]:
    try:
        return set(json.loads(_DEDUP_FILE.read_text()))
    except Exception:
        return set()


def _save_dedup_set(s: set[int]) -> None:
    try:
        tmp = _DEDUP_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(list(s)))
        os.replace(tmp, _DEDUP_FILE)
    except Exception:
        pass


_processed_run_ids: set[int] = _load_dedup_set()


async def _handle_workflow_run(payload: dict, request: Request) -> None:
    """Create Linear ticket + Telegram alert when CI fails on main (RA-847)."""
    run = payload.get("workflow_run", {})

    # Only act on completed + failed runs on main branch
    if run.get("conclusion") != "failure":
        return
    if run.get("head_branch") != "main":
        return

    # Deduplicate: one ticket per (repo, sha) pair, not per workflow job.
    # GitHub fires one webhook per job; a single broken commit can trigger
    # 3+ deliveries (CI, Security Scanning, Deploy) all for the same SHA.
    repo = payload.get("repository", {}).get("full_name", "unknown/repo")
    sha_full = run.get("head_sha", "")
    dedup_key = hash((repo, sha_full))
    if dedup_key in _processed_run_ids:
        log.debug("RA-847 dedup: skipping duplicate workflow_run repo=%s sha=%s", repo, sha_full[:8])
        return
    _processed_run_ids.add(dedup_key)
    if len(_processed_run_ids) > _DEDUP_MAX:
        to_remove = list(_processed_run_ids)[:_DEDUP_MAX // 2]
        for k in to_remove:
            _processed_run_ids.discard(k)
    _save_dedup_set(_processed_run_ids)

    workflow_name = run.get("name", "CI")
    run_url = run.get("html_url", "")
    sha = sha_full[:8]
    commit_msg = run.get("head_commit", {}).get("message", "")[:80]

    title = f"[CI FAILURE] {repo} — {workflow_name} on main"
    description = (
        "## CI Failure — Auto-generated\n\n"
        f"**Repo:** {repo}\n"
        f"**Workflow:** {workflow_name}\n"
        "**Branch:** main\n"
        f"**Commit:** {sha} — {commit_msg}\n"
        f"**Run:** {run_url}\n\n"
        "Auto-created by Pi-CEO GitHub webhook handler (RA-847).\n"
    )

    linear_key = os.environ.get("LINEAR_API_KEY", "")
    if linear_key:
        routing = _REPO_LINEAR_ROUTING.get(repo, {
            "teamId":    config.LINEAR_TEAM_ID,
            "projectId": config.LINEAR_PROJECT_ID,
        })
        try:
            await _create_linear_ci_ticket(title, description, linear_key, routing)
        except Exception as exc:
            log.warning("RA-847: Linear ticket creation failed: %s", exc)

    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_chat = os.environ.get("TELEGRAM_ALERT_CHAT_ID", "")
    if telegram_token and telegram_chat:
        msg = (
            f"🔴 *CI FAILURE*\n"
            f"{repo} — {workflow_name}\n"
            f"`{sha}`: {commit_msg}\n"
            f"{run_url}"
        )
        _telegram_send(telegram_token, telegram_chat, msg)

    log.info(
        "RA-847 workflow_run processed: repo=%s workflow=%s sha=%s conclusion=failure",
        repo, workflow_name, sha,
    )


def _create_linear_ci_ticket_sync(
    title: str, description: str, api_key: str, routing: dict
) -> dict:
    """Create a High-priority Linear ticket routed to the correct team/project."""
    mutation = """
    mutation CreateIssue($input: IssueCreateInput!) {
        issueCreate(input: $input) {
            success
            issue { id identifier url title }
        }
    }
    """
    variables = {
        "input": {
            "teamId":    routing.get("teamId",    config.LINEAR_TEAM_ID),
            "projectId": routing.get("projectId", config.LINEAR_PROJECT_ID),
            "title": title,
            "description": description,
            "priority": 2,  # High
        }
    }
    payload = json.dumps({"query": mutation, "variables": variables}).encode()
    req = _ur.Request(
        _LINEAR_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": api_key,
        },
    )
    with _ur.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    if "errors" in data:
        raise RuntimeError(f"Linear GraphQL errors: {data['errors']}")
    result = data.get("data", {}).get("issueCreate", {})
    if not result.get("success"):
        raise RuntimeError(f"issueCreate returned success=false for title='{title}'")
    issue = result.get("issue", {})
    log.info("RA-847: Linear ticket created: %s %s", issue.get("identifier"), title)
    return issue


async def _create_linear_ci_ticket(
    title: str, description: str, api_key: str, routing: dict
) -> dict:
    """Async wrapper — runs the sync Linear call in the default executor."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _create_linear_ci_ticket_sync, title, description, api_key, routing
    )


# ── RA-845: Morning AI platform intelligence webhook ──────────────────────────

@router.post("/api/webhook/morning-intel", dependencies=[Depends(require_rate_limit)])
async def morning_intel_webhook(request: Request):
    """
    RA-845 — Receive daily AI platform intelligence from n8n (11:45 AM AEST).

    Payload:
      {
        "date": "2026-04-14",           # optional, defaults to today UTC
        "anthropic": "...",             # Anthropic updates summary
        "openai": "...",                # OpenAI updates summary
        "xai": "...",                   # xAI/Grok updates summary
        "flags": ["🔴 CRITICAL: ...", "🟢 ADOPT: ..."]
      }

    Writes to .harness/morning-intel/YYYY-MM-DD.json (atomic write).
    Board meeting build_board_system_prompt() reads it at run time.
    Protected by X-Pi-CEO-Secret header == TAO_WEBHOOK_SECRET.
    """
    import hmac as _hmac
    from datetime import datetime, timezone

    secret_header = request.headers.get("x-pi-ceo-secret", "")
    if config.WEBHOOK_SECRET:
        if not secret_header:
            raise HTTPException(401, "X-Pi-CEO-Secret header required")
        if not _hmac.compare_digest(secret_header, config.WEBHOOK_SECRET):
            raise HTTPException(401, "Invalid secret")

    raw_body = await request.body()
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")

    date_str = payload.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # RA-1007: Validate date_str before using as a filename to prevent path traversal.
    if not _DATE_RE.match(date_str):
        raise HTTPException(400, f"Invalid date format: {date_str!r}")

    intel_dir = Path(config.DATA_DIR).parent.parent / ".harness" / "morning-intel"
    intel_dir.mkdir(parents=True, exist_ok=True)

    intel_file = intel_dir / f"{date_str}.json"
    tmp = intel_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, intel_file)

    flags: list = payload.get("flags") or []
    critical_count = sum(1 for f in flags if "🔴" in str(f) or "CRITICAL" in str(f).upper())
    log.info(
        "Morning intel stored: date=%s flags=%d critical=%d path=%s",
        date_str, len(flags), critical_count, intel_file,
    )

    return {"ok": True, "date": date_str, "flags": len(flags), "critical": critical_count}


# ── RA-657: Telegram /ack_alert webhook ───────────────────────────────────────

@router.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    RA-657 — Receive Telegram bot updates.
    Handles /ack_alert <key> to silence the escalation watchdog.
    Secured via X-Telegram-Bot-Api-Secret-Token (set when registering webhook).
    """
    token = config.TELEGRAM_BOT_TOKEN
    expected_secret = config.TELEGRAM_WEBHOOK_SECRET
    # RA-1004: Require the secret to be configured. If it is absent the endpoint
    # would otherwise be open to anyone — mirror the pattern used for GitHub
    # webhook secret (lines 53-54).
    if not expected_secret:
        raise HTTPException(500, "Telegram webhook secret not configured")
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret != expected_secret:
        raise HTTPException(401, "Invalid Telegram webhook secret")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    message = data.get("message", {})
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")

    if text.startswith("/ack_alert"):
        parts = text.split(None, 1)
        alert_key = parts[1].strip() if len(parts) > 1 else ""
        if not alert_key:
            if token and chat_id:
                _telegram_send(token, chat_id, "⚠️ Usage: `/ack_alert <alert_key>`")
            return {"ok": True}
        try:
            mark_alert_acked(alert_key)
            log.info("Alert acked via Telegram: key=%s chat=%s", alert_key, chat_id)
        except Exception as exc:
            log.error("mark_alert_acked failed: %s", exc)
            if token and chat_id:
                _telegram_send(token, chat_id, f"❌ Failed to ack `{alert_key}`: {exc}")
            return {"ok": True}
        if token and chat_id:
            _telegram_send(token, chat_id, f"✅ Alert `{alert_key}` acknowledged — re-paging stopped.")

    return {"ok": True}


# ── RA-1011: Routine run outcome tracker ─────────────────────────────────────

_ROUTINE_RUNS_DIR_NAME = "routine-runs"

_VALID_TRIGGERS: frozenset[str] = frozenset({"api", "schedule", "github"})
_VALID_STATUSES: frozenset[str] = frozenset({"success", "failure", "timeout"})


class RoutineCompletePayload(BaseModel):
    routine_name: str
    repo: str
    trigger: str
    status: str
    duration_s: int | float
    run_url: str = ""
    summary: str = ""
    ts: str = ""

    @field_validator("trigger")
    @classmethod
    def _check_trigger(cls, v: str) -> str:
        if v not in _VALID_TRIGGERS:
            raise ValueError(f"trigger must be one of {sorted(_VALID_TRIGGERS)}")
        return v

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(_VALID_STATUSES)}")
        return v


@router.post("/api/webhook/routine-complete", dependencies=[Depends(require_rate_limit)])
async def routine_complete_webhook(request: Request):
    """
    RA-1011 — Receive Claude Code Routine completion events.

    Protected by X-Pi-CEO-Secret header == TAO_WEBHOOK_SECRET.
    Writes one JSONL entry per run to .harness/routine-runs/YYYY-MM-DD.jsonl.
    Creates a Linear ticket when status == 'failure'.
    """
    import hmac as _hmac
    from datetime import datetime, timezone

    secret_header = request.headers.get("x-pi-ceo-secret", "")
    if config.WEBHOOK_SECRET:
        if not secret_header:
            raise HTTPException(401, "X-Pi-CEO-Secret header required")
        if not _hmac.compare_digest(secret_header, config.WEBHOOK_SECRET):
            raise HTTPException(401, "Invalid secret")

    raw_body = await request.body()
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")

    try:
        payload = RoutineCompletePayload(**body)
    except Exception as exc:
        raise HTTPException(422, str(exc))

    now_utc = datetime.now(timezone.utc)
    ts = payload.ts or now_utc.isoformat()
    date_str = now_utc.strftime("%Y-%m-%d")

    runs_dir = Path(config.DATA_DIR).parent.parent / ".harness" / _ROUTINE_RUNS_DIR_NAME
    runs_dir.mkdir(parents=True, exist_ok=True)

    entry = {
        "routine_name": payload.routine_name,
        "repo":         payload.repo,
        "trigger":      payload.trigger,
        "status":       payload.status,
        "duration_s":   payload.duration_s,
        "run_url":      payload.run_url,
        "summary":      payload.summary,
        "ts":           ts,
    }
    run_file = runs_dir / f"{date_str}.jsonl"
    tmp = run_file.with_suffix(".tmp")
    # Atomic append: read existing + new entry → write to tmp → replace.
    existing = run_file.read_text() if run_file.exists() else ""
    tmp.write_text(existing + json.dumps(entry) + "\n")
    os.replace(tmp, run_file)

    log.info(
        "RA-1011 routine run logged: routine=%s repo=%s status=%s duration=%ss",
        payload.routine_name, payload.repo, payload.status, payload.duration_s,
    )

    if payload.status == "failure":
        linear_key = os.environ.get("LINEAR_API_KEY", "")
        if linear_key:
            routing = _REPO_LINEAR_ROUTING.get(payload.repo, {
                "teamId":    config.LINEAR_TEAM_ID,
                "projectId": config.LINEAR_PROJECT_ID,
            })
            title = f"[ROUTINE FAILURE] {payload.routine_name} — {payload.repo}"
            description = (
                "## Routine Failure — Auto-generated\n\n"
                f"**Routine:** {payload.routine_name}\n"
                f"**Repo:** {payload.repo}\n"
                f"**Trigger:** {payload.trigger}\n"
                f"**Duration:** {payload.duration_s}s\n"
                f"**Run URL:** {payload.run_url}\n"
                f"**Timestamp:** {ts}\n\n"
                f"**Summary:**\n{payload.summary or '_No summary provided._'}\n\n"
                "Auto-created by Pi-CEO routine-complete webhook (RA-1011).\n"
            )
            try:
                await _create_linear_ci_ticket(title, description, linear_key, routing)
            except Exception as exc:
                log.warning("RA-1011: Linear ticket creation failed: %s", exc)

    return {"ok": True, "logged": True}


# ── RA-826: Google Workspace Intel endpoints ─────────────────────────────────

_WORKSPACE_INTEL_DIR_NAME = "workspace-intel"


class _WorkspaceIntelItem(BaseModel):
    title: str
    link: str
    pub_date: str = ""
    summary: str = ""
    keywords_matched: list[str] = []
    categories: list[str] = []
    guid: str = ""


class _WorkspaceIntelBatch(BaseModel):
    items: list[_WorkspaceIntelItem]
    batch_date: str = ""
    count: int = 0
    source: str = "n8n:workspace-rss-monitor"


@router.post("/api/webhook/workspace-intel-refresh", dependencies=[Depends(require_rate_limit)])
async def workspace_intel_refresh(request: Request):
    """
    RA-826 — Receive filtered Google Workspace update batch from n8n RSS monitor.

    Payload (application/json):
      {
        "batch_date": "2026-04-18",
        "count": 2,
        "items": [
          {
            "title":            "New Gemini feature in Docs",
            "link":             "https://workspaceupdates.googleblog.com/...",
            "pub_date":         "2026-04-18T10:00:00Z",
            "summary":          "...",
            "keywords_matched": ["gemini", "agent"],
            "categories":       ["Google Docs", "Gemini"],
            "guid":             "tag:blogger.com,1999:blog-xxx.post-yyy"
          }
        ],
        "source": "n8n:workspace-rss-monitor"
      }

    Stores one JSONL entry per batch to .harness/workspace-intel/YYYY-MM-DD.jsonl (atomic).
    Protected by X-Pi-CEO-Secret header == TAO_WEBHOOK_SECRET.
    """
    import hmac as _hmac
    from datetime import datetime, timezone

    secret_header = request.headers.get("x-pi-ceo-secret", "")
    if config.WEBHOOK_SECRET:
        if not secret_header:
            raise HTTPException(401, "X-Pi-CEO-Secret header required")
        if not _hmac.compare_digest(secret_header, config.WEBHOOK_SECRET):
            raise HTTPException(401, "Invalid secret")

    raw_body = await request.body()
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")

    try:
        batch = _WorkspaceIntelBatch(**body)
    except Exception as exc:
        raise HTTPException(422, str(exc))

    if not batch.items:
        return {"ok": True, "stored": False, "reason": "empty_items"}

    now_utc = datetime.now(timezone.utc)
    date_str = batch.batch_date or now_utc.strftime("%Y-%m-%d")

    if not _DATE_RE.match(date_str):
        raise HTTPException(400, f"Invalid batch_date format: {date_str!r}")

    intel_dir = Path(config.DATA_DIR).parent.parent / ".harness" / _WORKSPACE_INTEL_DIR_NAME
    intel_dir.mkdir(parents=True, exist_ok=True)

    entry = {
        "batch_date": date_str,
        "count":      len(batch.items),
        "items":      [item.model_dump() for item in batch.items],
        "source":     batch.source,
        "ts":         now_utc.isoformat(),
    }
    run_file = intel_dir / f"{date_str}.jsonl"
    existing = run_file.read_text(encoding="utf-8") if run_file.exists() else ""
    tmp = run_file.with_suffix(".tmp")
    tmp.write_text(existing + json.dumps(entry) + "\n", encoding="utf-8")
    os.replace(tmp, run_file)

    log.info(
        "RA-826 workspace intel stored: date=%s count=%d source=%s",
        date_str, len(batch.items), batch.source,
    )
    return {"ok": True, "stored": True, "batch_date": date_str, "count": len(batch.items)}


@router.get("/api/workspace-intel", dependencies=[Depends(require_rate_limit)])
async def get_workspace_intel(
    request: Request,
    limit: int = Query(default=30, ge=1, le=100),
):
    """
    RA-826 — Return recent workspace intel batches for the weekly brief workflow.

    Protected by X-Pi-CEO-Secret header (same token used by n8n webhooks).
    Returns up to `limit` most-recent batches sorted newest-first.
    """
    import hmac as _hmac

    secret_header = request.headers.get("x-pi-ceo-secret", "")
    if config.WEBHOOK_SECRET:
        if not secret_header:
            raise HTTPException(401, "X-Pi-CEO-Secret header required")
        if not _hmac.compare_digest(secret_header, config.WEBHOOK_SECRET):
            raise HTTPException(401, "Invalid secret")

    intel_dir = Path(config.DATA_DIR).parent.parent / ".harness" / _WORKSPACE_INTEL_DIR_NAME
    entries: list[dict] = []

    if intel_dir.exists():
        for jsonl_file in sorted(intel_dir.glob("*.jsonl"), reverse=True):
            try:
                for line in jsonl_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        log.warning("RA-826: Skipping malformed JSONL line in %s", jsonl_file)
            except OSError as exc:
                log.warning("RA-826: Could not read %s: %s", jsonl_file, exc)

    entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
    total = len(entries)
    return {
        "entries": entries[:limit],
        "total":   total,
        "since":   "7 days",
        "limit":   limit,
    }


@router.get("/api/routines")
async def get_routine_runs(
    limit: int = Query(default=50, ge=1, le=500),
    _auth: bool = Depends(require_auth),
):
    """
    RA-1011 — Return recent routine run history.

    Reads all .harness/routine-runs/*.jsonl files, merges and sorts by timestamp
    descending, returns the top `limit` entries.
    """
    runs_dir = Path(config.DATA_DIR).parent.parent / ".harness" / _ROUTINE_RUNS_DIR_NAME
    runs: list[dict] = []

    if runs_dir.exists():
        for jsonl_file in sorted(runs_dir.glob("*.jsonl")):
            try:
                for line in jsonl_file.read_text().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        runs.append(json.loads(line))
                    except json.JSONDecodeError:
                        log.warning("RA-1011: Skipping malformed JSONL line in %s", jsonl_file)
            except OSError as exc:
                log.warning("RA-1011: Could not read %s: %s", jsonl_file, exc)

    runs.sort(key=lambda r: r.get("ts", ""), reverse=True)
    total = len(runs)
    return {"runs": runs[:limit], "total": total}
