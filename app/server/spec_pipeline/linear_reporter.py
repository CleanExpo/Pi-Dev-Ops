"""linear_reporter.py — write the machine spec pipeline's progress back to Linear.

`run_pipeline` used to put the issue id in a PR body string and nowhere else, so a
blocked pipeline was invisible on the board that triggered it. This closes that
loop by reusing `autonomy.comment_on_issue`, the same write path ordinary
autonomy sessions already use.

Observability must never block the pipeline (CLAUDE.md § Observability), so
`report()` is fire-and-forget: it catches everything, including a missing Linear
key, a missing issue id, and a dead API. It has no return value to check because
there is no failure a caller should act on.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("pi-ceo.spec_pipeline.linear_reporter")

_ENV_FLAG = "SPEC_PIPELINE_LINEAR_REPORT"
_MAX_SUMMARY_CHARS = 4000


def reporting_enabled() -> bool:
    """On unless `SPEC_PIPELINE_LINEAR_REPORT` is explicitly falsy."""
    return (os.environ.get(_ENV_FLAG) or "1").strip().lower() not in ("0", "false", "no", "off")


def _linear_api_key() -> str:
    return (os.environ.get("LINEAR_API_KEY") or "").strip()


def _body(stage: str, summary: str) -> str:
    text = (summary or "").strip() or "(no detail)"
    if len(text) > _MAX_SUMMARY_CHARS:
        text = text[:_MAX_SUMMARY_CHARS] + "\n\n_(truncated)_"
    return f"**Machine spec pipeline — {stage}**\n\n{text}"


def _post(issue_id: str, stage: str, summary: str) -> bool:
    """Do the write. Separated so `report()` stays a pure never-raise wrapper."""
    if not reporting_enabled():
        log.debug("linear_reporter: %s disabled — skipping %r", _ENV_FLAG, stage)
        return False
    if not issue_id:
        log.debug("linear_reporter: no issue_id — skipping %r", stage)
        return False
    api_key = _linear_api_key()
    if not api_key:
        log.debug("linear_reporter: LINEAR_API_KEY unset — skipping %r", stage)
        return False

    # Imported here, not at module scope: `autonomy` imports the spec pipeline,
    # so a top-level import would close a cycle through this package's __init__.
    from app.server import autonomy

    autonomy.comment_on_issue(api_key, issue_id, _body(stage, summary))
    log.info("linear_reporter: commented on %s (stage=%s)", issue_id, stage)
    return True


def report(issue_id: str | None, stage: str, summary: str) -> None:
    """Fire-and-forget Linear comment for one pipeline stage. Never raises.

    A missing `issue_id`, a missing `LINEAR_API_KEY`, or a disabled
    `SPEC_PIPELINE_LINEAR_REPORT` is a silent no-op, not an error.
    """
    try:
        _post((issue_id or "").strip(), stage, summary)
    except Exception as exc:  # noqa: BLE001 — observability must not block the pipeline
        log.warning("linear_reporter: comment failed for %s (stage=%s): %s", issue_id, stage, exc)
