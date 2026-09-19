"""Human-readable repair instructions and best-effort build alerts."""
import json
import logging
import urllib.request
from . import config
_log = logging.getLogger("pi-ceo.sessions")

def _send_scope_violation_alert(session, modified_files: list[str], max_files: int) -> None:
    """RA-676 — Fire-and-forget Telegram alert when scope contract is exceeded."""
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_ALERT_CHAT_ID
    if not token or not chat_id:
        return
    repo = (getattr(session, "repo_url", "") or "").rstrip("/").split("/")[-1] or "unknown"
    file_list = "\n".join(f"  • `{f}`" for f in modified_files[:15])
    tail = f"\n  _(+ {len(modified_files) - 15} more)_" if len(modified_files) > 15 else ""
    scope = getattr(session, "scope", None) or {}
    msg = (
        f"🚫 *Scope Contract Violated*\n\n"
        f"Session: `{session.id}`\n"
        f"Repo: `{repo}`\n"
        f"Declared max: *{max_files}* files\n"
        f"Actual: *{len(modified_files)}* files modified\n"
        f"Scope type: `{scope.get('type', 'unspecified')}`\n\n"
        f"Modified files:\n{file_list}{tail}\n\n"
        f"Build held — manual review required."
    )
    payload = json.dumps({
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode()
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8):
            pass
        _log.info("Scope violation alert sent: session=%s files=%d", session.id, len(modified_files))
    except Exception as exc:
        _log.warning("Scope violation Telegram alert failed (non-fatal): %s", exc)


def _build_repair_brief(
    spec: str,
    eval_text: str,
    classification: dict,
    threshold: float,
    weak_dims: list[str],
) -> str:
    """Build a targeted repair brief from the failure classification.

    Falls back to the legacy retry format when classification is empty.
    """
    if not classification:
        # Legacy format (existing behaviour preserved)
        return (
            spec + "\n\n--- RETRY INSTRUCTIONS ---\n"
            f"Previous attempt scored below threshold ({threshold}/10).\n"
            "Issues found:\n" + "\n".join(f"- {w}" for w in weak_dims) + "\n"
            "Fix these specific issues. Do not rewrite everything.\n--- END RETRY ---"
        )
    failure_type = classification.get("FAILURE_TYPE", "unknown")
    implicated = classification.get("IMPLICATED_FILES", [])
    scope = classification.get("REPAIR_SCOPE", "minimal")
    instructions = classification.get("REPAIR_INSTRUCTIONS", [])

    files_line = ", ".join(implicated) if implicated else "see evaluator output"
    instructions_text = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(instructions))

    return (
        f"REPAIR TASK — failure type: {failure_type}, scope: {scope}\n\n"
        f"Do NOT rewrite everything. Touch only the implicated files: {files_line}\n\n"
        f"Original task spec:\n{spec[:1500]}\n\n"
        f"Evaluator feedback:\n{eval_text[:1500]}\n\n"
        f"Specific repair instructions:\n{instructions_text or '  - Fix the issues described in the evaluator feedback above'}\n\n"
        "Verify your changes with a quick test run if tests exist.\n"
        "Do not modify files not in the implicated list."
    )


def _send_repair_exhausted_alert(session, score: float, eval_text: str) -> None:
    """RA-936 — Telegram alert when the repair loop exhausts all retries.

    Lets the operator know a session needs human review rather than silently
    being marked 'warned'. Never raises.
    """
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_ALERT_CHAT_ID
    if not token or not chat_id:
        return
    repo = getattr(session, "repo_url", "?").rstrip("/").split("/")[-1]
    issue_id = getattr(session, "linear_issue_id", None)
    ticket = f" | {issue_id}" if issue_id else ""
    # Pull first failing dimension from eval text for the alert
    failing_dim = ""
    for line in eval_text.splitlines():
        if any(d in line for d in ("COMPLETENESS:", "CORRECTNESS:", "CONCISENESS:", "FORMAT:")):
            if "/10" in line:
                try:
                    score_val = float(line.split("/10")[0].split()[-1])
                    if score_val < 7:
                        failing_dim = line.strip()[:80]
                        break
                except ValueError:
                    pass
    msg = (
        f"🔄 *Repair loop exhausted:* `{repo}`\n"
        f"Score: {score:.1f}/10 — needs human review{ticket}\n"
        f"{failing_dim}"
    )
    payload = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "Markdown",
                          "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        _log.debug("RA-936: _send_repair_exhausted_alert failed (non-fatal): %s", exc)
