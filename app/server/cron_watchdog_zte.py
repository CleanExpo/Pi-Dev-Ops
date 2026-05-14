"""
cron_watchdog_zte.py — ZTE Reality-Check watchdog (RA-608).

Every 30 minutes, fetches the Linear board state. If the pipeline is stalled
(In Progress = 0 AND aged Urgent/High Todo > 0) and has been so for >= 12 hours:
  1. A REALITY CHECK warning block is written into leverage-audit.md.
  2. A Telegram alert fires on an escalating cadence (see ``_alert_cooldown_for_age``).

State is persisted in .harness/zte-reality-status.json to survive restarts.

Age-aware behaviour (per Phill's "no repeating alerts" rule):
  * Only tickets older than ``_MIN_TICKET_AGE_H`` count toward the stall — freshly
    filed tickets do not trip the watchdog.
  * The alert reports the *oldest waiting ticket's age*, not the time since the
    watchdog first noticed the stall.
"""
import os
import time
from datetime import datetime, timedelta, timezone


_MIN_TICKET_AGE_H = float(os.getenv("ZTE_MIN_TICKET_AGE_H", "24.0"))
_STALL_THRESHOLD_H = float(os.getenv("ZTE_STALL_THRESHOLD_H", "12.0"))


def _filter_aged(tickets, min_age_hours: float = _MIN_TICKET_AGE_H) -> list:
    """Return only tickets older than ``min_age_hours`` from ``createdAt``.

    Unknown-age tickets are kept defensively so that an API shape change does not
    silently suppress real stalls.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
    aged = []
    for t in tickets:
        # Ticket dict has 'createdAt' as ISO string (Linear API shape)
        created_at_iso = t.get('createdAt') or t.get('created_at')
        if not created_at_iso:
            aged.append(t)  # unknown age — keep (defensive)
            continue
        try:
            created_at = datetime.fromisoformat(created_at_iso.replace('Z', '+00:00'))
            if created_at <= cutoff:
                aged.append(t)
        except Exception:
            aged.append(t)
    return aged


def _oldest_age_hours(tickets) -> float:
    """Hours since the oldest ticket's ``createdAt``. Empty list returns 0.0."""
    if not tickets:
        return 0.0
    now = datetime.now(timezone.utc)
    ages = []
    for t in tickets:
        created_at_iso = t.get('createdAt') or t.get('created_at')
        if not created_at_iso:
            continue
        try:
            created_at = datetime.fromisoformat(created_at_iso.replace('Z', '+00:00'))
            ages.append((now - created_at).total_seconds() / 3600.0)
        except Exception:
            pass
    return max(ages) if ages else 0.0


def _alert_cooldown_for_age(oldest_h: float) -> float:
    """Escalating cadence — sleeps longer the older the stall (it's not getting fresher)."""
    if oldest_h < 48:
        return 6.0      # first 2 days: every 6h
    if oldest_h < 168:
        return 24.0     # 2-7 days: daily
    return 72.0          # 1 week+: every 3 days (alert fatigue mitigation)


async def _watchdog_zte_reality_check(log) -> None:
    """RA-608 — ZTE Reality-Check watchdog."""
    from . import config
    from pathlib import Path
    import json as _json

    _HARNESS = Path(__file__).parent.parent.parent / ".harness"
    _STATUS_FILE = _HARNESS / "zte-reality-status.json"
    _AUDIT_FILE = _HARNESS / "leverage-audit.md"

    # ── 1. Load persisted state ───────────────────────────────────────────────
    status: dict = {}
    if _STATUS_FILE.exists():
        try:
            status = _json.loads(_STATUS_FILE.read_text())
        except Exception:
            pass

    stall_since: float | None = status.get("stall_since")
    last_alerted: float = status.get("last_alerted", 0.0)
    was_stalled: bool = status.get("stalled", False)

    # ── 2. Query Linear board ────────────────────────────────────────────────
    if not config.LINEAR_API_KEY:
        return

    _LINEAR_ENDPOINT = "https://api.linear.app/graphql"
    _PROJECT_ID = "f45212be-3259-4bfb-89b1-54c122c939a7"

    def _gql(query: str, variables: dict) -> dict:
        import urllib.request as _ureq
        payload = _json.dumps({"query": query, "variables": variables}).encode()
        req = _ureq.Request(
            _LINEAR_ENDPOINT, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": config.LINEAR_API_KEY},
        )
        with _ureq.urlopen(req, timeout=10) as resp:
            return _json.loads(resp.read()).get("data", {})

    try:
        data = _gql(
            """
            query BoardState($projectId: String!) {
              project(id: $projectId) {
                issues(first: 100) {
                  nodes { identifier createdAt priority state { type name } }
                }
              }
            }
            """,
            {"projectId": _PROJECT_ID},
        )
        issues = (data.get("project") or {}).get("issues", {}).get("nodes", [])
    except Exception as exc:
        log.warning("ZTE reality check: Linear fetch failed: %s", exc)
        return

    in_progress = [i for i in issues if i.get("state", {}).get("type") == "started"]
    urgent_todo = [
        i for i in issues
        if i.get("state", {}).get("type") in ("unstarted", "backlog")
        and i.get("priority", 4) <= 2  # 1=Urgent, 2=High
    ]

    # Only count tickets that have aged past _MIN_TICKET_AGE_H — freshly filed
    # tickets shouldn't trip the stall alarm.
    aged_urgent_todo = _filter_aged(urgent_todo, _MIN_TICKET_AGE_H)

    now = time.time()
    is_stalled = len(in_progress) == 0 and len(aged_urgent_todo) > 0

    # ── 3. Update stall_since tracking ────────────────────────────────────────
    if is_stalled:
        if stall_since is None:
            stall_since = now
            log.info(
                "ZTE reality check: stall detected — %d aged urgent/high todo, 0 in-progress",
                len(aged_urgent_todo),
            )
    else:
        stall_since = None

    stall_h = (now - stall_since) / 3600 if stall_since else 0.0
    stall_qualifies = is_stalled and stall_h >= _STALL_THRESHOLD_H
    oldest_h = _oldest_age_hours(aged_urgent_todo)

    # ── 4. Update leverage-audit.md ───────────────────────────────────────────
    _STALL_MARKER_START = "<!-- ZTE-REALITY-CHECK-START -->"
    _STALL_MARKER_END   = "<!-- ZTE-REALITY-CHECK-END -->"

    if _AUDIT_FILE.exists():
        audit_text = _AUDIT_FILE.read_text(encoding="utf-8")
        import re as _re
        audit_text = _re.sub(
            rf"{_re.escape(_STALL_MARKER_START)}.*?{_re.escape(_STALL_MARKER_END)}\n?",
            "",
            audit_text,
            flags=_re.DOTALL,
        )
        if stall_qualifies:
            stall_block = (
                f"{_STALL_MARKER_START}\n"
                f"## ⚠️ REALITY CHECK — PIPELINE STALLED (oldest {oldest_h:.0f}h)\n\n"
                f"> **Auto-detected by ZTE watchdog — {time.strftime('%Y-%m-%dT%H:%M UTC', time.gmtime())}**\n>\n"
                f"> In Progress: **0**  |  Urgent/High Todo (≥{int(_MIN_TICKET_AGE_H)}h old): **{len(aged_urgent_todo)}**\n>\n"
                f"> While scores above reflect *capability*, the pipeline is currently **not processing work**.\n"
                f"> A stall of >=12h is a ZTE failure condition — the system is autonomous in theory only.\n"
                f"> Resolve: assign an In Progress issue or check autonomy poller (`TAO_AUTONOMY_ENABLED`).\n"
                f"{_STALL_MARKER_END}\n\n"
            )
            audit_text = _re.sub(
                r"(# Pi Dev Ops — Leverage Audit\n)",
                r"\1" + stall_block,
                audit_text,
                count=1,
            )
            log.warning("ZTE reality check: STALL block written to leverage-audit.md (oldest %dh)", oldest_h)
        else:
            log.info("ZTE reality check: pipeline healthy — no stall block")
        try:
            tmp = str(_AUDIT_FILE) + ".tmp"
            Path(tmp).write_text(audit_text, encoding="utf-8")
            Path(tmp).replace(_AUDIT_FILE)
        except Exception as exc:
            log.warning("ZTE reality check: could not write leverage-audit.md: %s", exc)

    # ── 5. Telegram alert ─────────────────────────────────────────────────────
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_ALERT_CHAT_ID
    if token and chat_id:
        cooldown_s = _alert_cooldown_for_age(oldest_h) * 3600
        alert_due = (now - last_alerted) >= cooldown_s

        if stall_qualifies and alert_due:
            top_items_lines = "\n".join(
                f"  • {i.get('identifier','?')} priority={i['priority']} state={i['state']['name']}"
                for i in aged_urgent_todo[:5]
            ) or "  (no details available)"
            text = (
                f"⚠️ *ZTE REALITY CHECK — Pipeline Stalled*\n\n"
                f"Oldest urgent/high ticket waiting: *{oldest_h:.0f}h*\n"
                f"In Progress: 0  |  Urgent/High Todo (≥{int(_MIN_TICKET_AGE_H)}h old): {len(aged_urgent_todo)}\n\n"
                f"Top waiting items:\n"
                f"{top_items_lines}\n\n"
                f"The system is autonomous in theory only while work sits unprocessed.\n"
                f"Check: TAO_AUTONOMY_ENABLED env var and Railway logs."
            )
            import urllib.request as _ureq2
            payload = _json.dumps(
                {"chat_id": chat_id, "text": text, "parse_mode": "Markdown",
                 "disable_web_page_preview": True}
            ).encode()
            req = _ureq2.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=payload, method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                with _ureq2.urlopen(req, timeout=10):
                    pass
                log.warning("ZTE reality check: stall Telegram alert sent")
                last_alerted = now
            except Exception as exc:
                log.warning("ZTE reality check: Telegram alert failed: %s", exc)

        elif was_stalled and not is_stalled and alert_due:
            text = (
                "✅ *ZTE REALITY CHECK — Pipeline Healthy*\n\n"
                f"In Progress: *{len(in_progress)}*  |  Urgent/High Todo (aged): *{len(aged_urgent_todo)}*\n\n"
                "_Stall cleared. Autonomous pipeline is processing work again._"
            )
            import urllib.request as _ureq3
            payload = _json.dumps(
                {"chat_id": chat_id, "text": text, "parse_mode": "Markdown",
                 "disable_web_page_preview": True}
            ).encode()
            req = _ureq3.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=payload, method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                with _ureq3.urlopen(req, timeout=10):
                    pass
                log.info("ZTE reality check: stall cleared — Telegram alert sent")
                last_alerted = now
            except Exception as exc:
                log.warning("ZTE reality check: Telegram clear alert failed: %s", exc)

    # ── 6. Persist state ──────────────────────────────────────────────────────
    new_status = {
        "stalled":          is_stalled,
        "stall_since":      stall_since,
        "in_progress":      len(in_progress),
        "urgent_todo":      len(urgent_todo),
        "aged_urgent_todo": len(aged_urgent_todo),
        "oldest_h":         round(oldest_h, 2),
        "stall_h":          round(stall_h, 2),
        "last_alerted":     last_alerted,
        "checked_at":       time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        tmp = str(_STATUS_FILE) + ".tmp"
        Path(tmp).write_text(_json.dumps(new_status, indent=2), encoding="utf-8")
        Path(tmp).replace(_STATUS_FILE)
    except Exception as exc:
        log.warning("ZTE reality check: could not write status file: %s", exc)
