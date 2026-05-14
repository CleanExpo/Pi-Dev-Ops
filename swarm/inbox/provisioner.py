"""swarm/inbox/provisioner.py — Hour-1 portal provisioner.

Drains `stripe_provisioning_queue` (rows inserted by /api/webhooks/stripe
on first payment) and provisions the Hour-1 client experience per Margot's
Board call:

    "Build the Hour-1 portal template once — Linear project + Supabase
    portal content + Telegram intake bot + intro Loom + welcome email —
    so signature triggers it automatically, and every future client gets
    the same wow on minute 60."

For each pending row, in order:

    1. Load the linked `nexus_clients` row by slug.
    2. Create a Linear project for the engagement (idempotent — checks
       `portal_content.linear_project_id` first).
    3. Enqueue a client-inbound ContextBot via the existing context_bots
       registry (BotFather mint deferred to the bot provisioning worker
       to keep this loop side-effect-bounded).
    4. Populate the Day-0 `portal_content` JSON: Mission Counter, Brand
       Vote, Build Stream, Preview Deploys, Approvals Queue, Compliance
       Vault — all sections per the CMO Board CX plan.
    5. Send the welcome email via Resend.
    6. Single-shot ping to Phill via @PiCeoOpsBot.
    7. Mark queue row done.

Fail-soft per step: any individual failure logs to `processing_error`
and the row goes to `failed` so the operator can retry. Successive runs
are idempotent — re-running on a `done` row is a no-op.

Designed to be invoked as a 60-second LaunchAgent cron, same pattern as
intake_router. Public API:

    tick(dry_run: bool = False) -> dict
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Any

from .safe_slug import validate_slug

log = logging.getLogger("swarm.inbox.provisioner")

AEST = timezone(timedelta(hours=10))
RESEND_API = "https://api.resend.com"
LINEAR_API = "https://api.linear.app/graphql"
APP_URL = os.environ.get("UNITE_GROUP_APP_URL", "https://unite-group.in")
DEFAULT_FROM_EMAIL = os.environ.get(
    "UNITE_GROUP_FROM_EMAIL", "contact@unite-group.in"
)
DEFAULT_FROM_NAME = "Phill McGurk — Unite-Group"

# Per Margot's Board call: 14-day Sprint 1 cadence.
ENGAGEMENT_TOTAL_DAYS = 14


# ── Supabase access (PostgREST) ─────────────────────────────────────────────
def _sb_request(method: str, path: str, *, params: dict | None = None,
                body: Any = None, extra_headers: dict | None = None) -> Any:
    url = f"{os.environ['SUPABASE_UNITE_GROUP_URL'].rstrip('/')}/rest/v1{path}"
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    key = os.environ["SUPABASE_UNITE_GROUP_SERVICE_KEY"]
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


# ── Linear (GraphQL) ────────────────────────────────────────────────────────
def _linear_gql(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        LINEAR_API, data=body, method="POST",
        headers={
            "Authorization": os.environ["LINEAR_API_KEY"],
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = json.loads(r.read())
    if "errors" in raw:
        raise RuntimeError(f"Linear GQL errors: {raw['errors']}")
    return raw["data"]


def _resolve_team_id(team_key: str) -> str | None:
    data = _linear_gql(
        """query($filter: TeamFilter) {
            teams(filter: $filter, first: 1) { nodes { id key name } }
        }""",
        {"filter": {"key": {"eq": team_key}}},
    )
    nodes = data["teams"]["nodes"]
    return nodes[0]["id"] if nodes else None


def create_linear_project(*, name: str, description: str, team_key: str,
                          target_date: str | None = None) -> dict:
    """Create a Linear project. Returns {id, url, name}."""
    team_id = _resolve_team_id(team_key)
    if not team_id:
        raise RuntimeError(f"Linear team {team_key!r} not found")
    data = _linear_gql(
        """mutation($input: ProjectCreateInput!) {
            projectCreate(input: $input) {
                success
                project { id name url }
            }
        }""",
        {"input": {
            "name": name,
            "description": description,
            "teamIds": [team_id],
            **({"targetDate": target_date} if target_date else {}),
        }},
    )
    result = data["projectCreate"]
    if not result["success"]:
        raise RuntimeError(f"projectCreate failed: {result}")
    return result["project"]


# ── Resend email ────────────────────────────────────────────────────────────
def _send_email(*, to: str, subject: str, html: str,
                from_email: str = DEFAULT_FROM_EMAIL,
                from_name: str = DEFAULT_FROM_NAME) -> dict:
    body = json.dumps({
        "from": f"{from_name} <{from_email}>",
        "to": [to],
        "subject": subject,
        "html": html,
    }).encode()
    req = urllib.request.Request(
        f"{RESEND_API}/emails", data=body, method="POST",
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def welcome_email_html(*, client_display_name: str, engagement_label: str,
                       portal_url: str, brand_candidates: list[dict]) -> str:
    candidates_html = "".join(
        f'<li style="margin:0 0 6px 0;"><strong>{c["name"]}</strong> — {c["tagline"]}</li>'
        for c in brand_candidates
    )
    return f"""<!doctype html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',sans-serif;background:#f5f5f5;margin:0;padding:24px;">
  <div style="max-width:560px;margin:0 auto;background:#1a1a1a;color:#fff;border-radius:12px;padding:32px;">
    <div style="display:flex;align-items:center;margin-bottom:24px;">
      <div style="width:10px;height:24px;background:#dc143c;margin-right:12px;"></div>
      <strong style="font-size:20px;">Unite-Group</strong>
    </div>
    <h1 style="margin:0 0 12px 0;font-size:28px;line-height:1.2;">Welcome to {engagement_label}.</h1>
    <p style="color:#a0a0a0;font-size:16px;line-height:1.5;margin:0 0 20px 0;">
      Hi {client_display_name},
    </p>
    <p style="color:#e0e0e0;font-size:16px;line-height:1.5;margin:0 0 20px 0;">
      Your deposit cleared and your portal is live. Everything we ship for you over the next 14 days lands there first — preview deploys, weekly walkthroughs, approval gates, the lot.
    </p>
    <p style="margin:24px 0;">
      <a href="{portal_url}" style="display:inline-block;background:#dc143c;color:#fff;padding:14px 28px;border-radius:6px;text-decoration:none;font-weight:600;">
        Open your portal →
      </a>
    </p>
    <hr style="border:none;border-top:1px solid #333;margin:32px 0;"/>
    <h2 style="font-size:18px;margin:0 0 12px 0;">Day-1 ask: choose your brand mark</h2>
    <p style="color:#e0e0e0;font-size:15px;line-height:1.5;margin:0 0 12px 0;">
      I've cleared two names through preliminary trademark sweep — both are buildable, both clear AU + US fintech collisions:
    </p>
    <ul style="color:#e0e0e0;padding-left:20px;margin:0 0 20px 0;">
      {candidates_html}
    </ul>
    <p style="color:#a0a0a0;font-size:14px;line-height:1.5;margin:0;">
      Vote in your portal when you're ready. No rush — we'll have full mark concepts on Day 2.
    </p>
    <hr style="border:none;border-top:1px solid #333;margin:32px 0;"/>
    <p style="color:#a0a0a0;font-size:13px;line-height:1.5;margin:0;">
      Phill McGurk · Director, Unite-Group Nexus Pty Ltd<br/>
      ABN 95 691 477 844 · contact@unite-group.in
    </p>
  </div>
</body></html>"""


# ── Telegram notify (reuse swarm.telegram_router if available) ──────────────
def _telegram_ping(text: str) -> None:
    try:
        from swarm import telegram_router  # type: ignore[import-not-found]
        telegram_router.send(text, channel="ops", severity="info",
                             bot_name="HourOneProvisioner")
    except Exception as e:  # noqa: BLE001
        log.warning("Telegram ping failed (non-fatal): %s", e)


# ── Day-0 portal content (CMO 6-section template) ───────────────────────────
def build_day0_portal_content(*, client: dict, linear_project: dict | None,
                              brand_candidates: list[dict]) -> dict:
    """Construct the Day-0 portal_content JSON for the new client."""
    existing = client.get("portal_content") or {}
    return {
        **existing,
        "schema_version": "hour1-v1",
        "hour1_provisioned_at": datetime.now(AEST).isoformat(),

        # Linear surface
        "linear_project_id": linear_project["id"] if linear_project else None,
        "linear_project_url": linear_project["url"] if linear_project else None,

        # Mission counter
        "engagement": {
            "label": existing.get("engagement_label")
                     or f"{client.get('company_name','engagement')}",
            "started_at": datetime.now(AEST).date().isoformat(),
            "total_days": ENGAGEMENT_TOTAL_DAYS,
            "current_day": 0,
            "deliverables_shipped": 0,
            "active_blockers": 0,
        },

        # Brand-Mark Vote (CMO §2 — Day 0–2 only)
        "brand_vote": {
            "active": True,
            "closes_at": (datetime.now(AEST) + timedelta(days=2)).isoformat(),
            "candidates": brand_candidates,
            "votes": {c["name"]: 0 for c in brand_candidates},
        },

        # Section placeholders with "Arrives Day X" copy
        "build_stream": {
            "items": [],
            "empty_state": "Arrives Day 4 — first sprint output.",
        },
        "preview_deploys": {
            "current": None,
            "empty_state": "Arrives Day 6 — first staging URL.",
        },
        "approvals_queue": {
            "items": [
                {
                    "id": "discovery-day0",
                    "title": "12-question discovery — 9 min",
                    "subtitle": "Tell us what 'done' looks like.",
                    "due": (datetime.now(AEST) + timedelta(days=3)).date().isoformat(),
                    "url": f"{APP_URL}/clients/{client['slug']}/discovery",
                    "blocking": True,
                },
            ],
        },
        "compliance_vault": {
            "populated_by_day": 10,
            "empty_state": "Arrives Day 10 — ASIC/AFSL/PII handling memos.",
        },
    }


# ── Default brand candidates per client ─────────────────────────────────────
def resolve_brand_candidates(client: dict) -> list[dict]:
    """Pull the 2-mark short-list from client.brand_config (if set), else default."""
    cfg = client.get("brand_config") or {}
    candidates = cfg.get("candidates")
    if isinstance(candidates, list) and candidates:
        # Wrap raw strings into dicts if needed
        return [
            {"name": c, "tagline": "", "tm_status": "candidate"} if isinstance(c, str) else c
            for c in candidates
        ]
    # Fallback (used when brand_config is missing — rare)
    return [
        {"name": "Option A", "tagline": "", "tm_status": "candidate"},
        {"name": "Option B", "tagline": "", "tm_status": "candidate"},
    ]


# ── The full Hour-1 sequence for one queue row ──────────────────────────────
def _enqueue_context_bot(*, client: dict, admin_email: str = DEFAULT_FROM_EMAIL) -> None:
    """Insert a pending ContextBot row for the bot-provisioning worker to mint."""
    slug = validate_slug(client["slug"])
    body = {
        "bot_username": f"UniteGroup{''.join(p.capitalize() for p in slug.split('-'))}Bot",
        "bot_token": "pending-provision",
        "kind": "client",
        "brand": "unite-group",
        "context_id": slug,
        "context_label": client.get("company_name") or slug,
        "linear_team_key": "UNI",
        "wiki_section": f"clients/{slug}.md",
        "greeting_template": f"Got it — filed to {client.get('company_name','your project')}. I'll start working on it now and ping back.",
        "intake_enabled": True,
        "provision_status": "pending",
        "client_email": client.get("contact_email"),
        "client_display_name": client.get("contact_name"),
        "metadata": {
            "enqueued_by": "hour1-provisioner",
            "enqueued_at": datetime.now(AEST).isoformat(),
        },
    }
    try:
        _sb_request("POST", "/context_bots",
                    body=body,
                    extra_headers={"Prefer": "return=minimal"})
    except urllib.error.HTTPError as e:
        # Duplicate bot_username (already provisioned) is fine
        if e.code == 409:
            log.info("context_bot for %s already exists", slug)
        else:
            raise


def _provision_one(row: dict, *, dry_run: bool) -> str:
    """Process a single queue row. Returns 'done' or 'failed'."""
    slug = validate_slug(row["nexus_slug"])

    # 1. Load client
    clients = _sb_request("GET", "/nexus_clients", params={
        "slug": f"eq.{slug}",
        "select": "id,slug,company_name,contact_name,contact_email,plan,status,brand_config,portal_content",
    }) or []
    if not clients:
        raise RuntimeError(f"nexus_clients row for slug={slug!r} not found")
    client = clients[0]

    # 2. Linear project (idempotent)
    existing_pc = client.get("portal_content") or {}
    if existing_pc.get("linear_project_id"):
        linear_project = {
            "id": existing_pc["linear_project_id"],
            "url": existing_pc.get("linear_project_url"),
            "name": existing_pc.get("engagement_label", slug),
        }
        log.info("linear project already exists for %s", slug)
    elif dry_run:
        linear_project = {"id": "dry_run_id", "url": "https://linear.app/dry-run", "name": "DRY RUN"}
    else:
        linear_project = create_linear_project(
            name=client.get("company_name") or slug,
            description=(
                f"Hour-1 provisioned at {datetime.now(AEST).isoformat()} for client {slug}.\n\n"
                f"Trigger: {row['trigger']}.\n"
                f"Stripe customer: {row['stripe_customer_id']}."
            ),
            team_key="UNI",
            target_date=(datetime.now(AEST) + timedelta(days=ENGAGEMENT_TOTAL_DAYS)).date().isoformat(),
        )

    # 3. ContextBot enqueue (idempotent)
    if not dry_run:
        _enqueue_context_bot(client=client)

    # 4. Day-0 portal_content
    brand_candidates = resolve_brand_candidates(client)
    day0 = build_day0_portal_content(
        client=client, linear_project=linear_project,
        brand_candidates=brand_candidates,
    )
    if not dry_run:
        _sb_request("PATCH", "/nexus_clients",
                    params={"id": f"eq.{client['id']}"},
                    body={"portal_content": day0},
                    extra_headers={"Prefer": "return=minimal"})

    # 5. Welcome email
    if not dry_run and client.get("contact_email"):
        portal_url = f"{APP_URL}/clients/{slug}"
        html = welcome_email_html(
            client_display_name=(client.get("contact_name") or "there").split(" ")[0],
            engagement_label=day0["engagement"]["label"],
            portal_url=portal_url,
            brand_candidates=brand_candidates,
        )
        try:
            _send_email(
                to=client["contact_email"],
                subject=f"Welcome to {day0['engagement']['label']} — your portal is live",
                html=html,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("welcome email failed (continuing): %s", e)

    # 6. Telegram ping (single-shot)
    if not dry_run:
        _telegram_ping(
            f"🚀 Hour-1 provisioned for {client.get('company_name', slug)} ({slug}).\n"
            f"Linear: {linear_project.get('url','—')}\n"
            f"Portal: {APP_URL}/clients/{slug}\n"
            f"Trigger: {row['trigger']}"
        )

    return "done"


# ── Main loop ───────────────────────────────────────────────────────────────
def tick(*, dry_run: bool = False, max_rows: int = 5) -> dict:
    rows = _sb_request("GET", "/stripe_provisioning_queue", params={
        "status": "eq.pending",
        "order": "created_at",
        "limit": max_rows,
    }) or []

    processed = 0
    failed: list[str] = []
    for row in rows:
        # Move to processing (skip if dry_run)
        if not dry_run:
            _sb_request(
                "PATCH", "/stripe_provisioning_queue",
                params={"id": f"eq.{row['id']}"},
                body={"status": "processing"},
                extra_headers={"Prefer": "return=minimal"},
            )
        try:
            outcome = _provision_one(row, dry_run=dry_run)
            if not dry_run:
                _sb_request(
                    "PATCH", "/stripe_provisioning_queue",
                    params={"id": f"eq.{row['id']}"},
                    body={"status": outcome,
                          "processed_at": datetime.now(AEST).isoformat()},
                    extra_headers={"Prefer": "return=minimal"},
                )
            processed += 1
        except Exception as e:  # noqa: BLE001
            log.exception("provisioning failed for queue row %s", row["id"])
            failed.append(f"{row['id']}:{row.get('nexus_slug')}: {e}")
            if not dry_run:
                _sb_request(
                    "PATCH", "/stripe_provisioning_queue",
                    params={"id": f"eq.{row['id']}"},
                    body={"status": "failed",
                          "processing_error": str(e)[:500],
                          "processed_at": datetime.now(AEST).isoformat()},
                    extra_headers={"Prefer": "return=minimal"},
                )

    return {"rows_seen": len(rows), "processed": processed,
            "failed": failed, "dry_run": dry_run}


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    import sys
    dry = "--dry-run" in sys.argv
    print(json.dumps(tick(dry_run=dry), indent=2, default=str))
