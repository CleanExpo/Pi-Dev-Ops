"""
cron_watchdog_zte.py — ZTE Reality-Check watchdog (RA-608).

Every 30 minutes, fetches the Linear board state. If the pipeline is stalled
(In Progress = 0 AND Urgent/High Todo > 0) and has been so for >= 12 hours:
  1. A REALITY CHECK warning block is written into leverage-audit.md.
  2. A Telegram alert fires (if not already sent in the last 2h).

State is persisted in .harness/zte-reality-status.json to survive restarts.
"""
import time


async def _watchdog_zte_reality_check(log) -> None:
    """RA-608 — ZTE Reality-Check watchdog."""
    from . import config
    from pathlib import Path
    import json as _json

    _HARNESS = Path(__file__).parent.parent.parent / ".harness"
    _STATUS_FILE = _HARNESS / "zte-reality-status.json"
    _AUDIT_FILE = _HARNESS / "leverage-audit.md"
    _STALL_THRESHOLD_H = 12.0
    _ALERT_COOLDOWN_H = 2.0

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
                  nodes { priority state { type name } }
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

    now = time.time()
    is_stalled = len(in_progress) == 0 and len(urgent_todo) > 0

    # ── 3. Update stall_since tracking ────────────────────────────────────────
    if is_stalled:
        if stall_since is None:
            stall_since = now
            log.info(
                "ZTE reality check: stall detected — %d urgent/high todo, 0 in-progress",
                len(urgent_todo),
            )
    else:
        stall_since = None

    stall_h = (now - stall_since) / 3600 if stall_since else 0.0
    stall_qualifies = is_stalled and stall_h >= _STALL_THRESHOLD_H

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
                f"## ⚠️ REALITY CHECK — PIPELINE STALLED ({stall_h:.0f}h)\n\n"
                f"> **Auto-detected by ZTE watchdog — {time.strftime('%Y-%m-%dT%H:%M UTC', time.gmtime())}**\n>\n"
                f"> In Progress: **0**  |  Urgent/High Todo: **{len(urgent_todo)}**\n>\n"
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
            log.warning("ZTE reality check: STALL block written to leverage-audit.md (%dh stall)", stall_h)
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
        alert_due = (now - last_alerted) >= _ALERT_COOLDOWN_H * 3600

        if stall_qualifies and alert_due:
            tickets_list = "\n".join(
                f"  • priority={i['priority']} state={i['state']['name']}"
                for i in urgent_todo[:5]
            )
            text = (
                f"⚠️ *ZTE REALITY CHECK — Pipeline Stalled {stall_h:.0f}h*\n\n"
                f"In Progress: *0*  |  Urgent/High Todo: *{len(urgent_todo)}*\n\n"
                f"Top waiting items:\n{tickets_list or '  (none details available)'}\n\n"
                f"_The system is autonomous in theory only while work sits unprocessed._\n"
                f"Check: `TAO_AUTONOMY_ENABLED` env var and Railway logs."
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
                f"In Progress: *{len(in_progress)}*  |  Urgent/High Todo: *{len(urgent_todo)}*\n\n"
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
        "stalled":      is_stalled,
        "stall_since":  stall_since,
        "in_progress":  len(in_progress),
        "urgent_todo":  len(urgent_todo),
        "stall_h":      round(stall_h, 2),
        "last_alerted": last_alerted,
        "checked_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        tmp = str(_STATUS_FILE) + ".tmp"
        Path(tmp).write_text(_json.dumps(new_status, indent=2), encoding="utf-8")
        Path(tmp).replace(_STATUS_FILE)
    except Exception as exc:
        log.warning("ZTE reality check: could not write status file: %s", exc)
