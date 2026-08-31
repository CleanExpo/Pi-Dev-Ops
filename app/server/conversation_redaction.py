"""conversation_redaction.py — the second redaction pass's pattern bank.

Extracted from `routes/conversations.py` at the 300-line ceiling. It is a real
seam: assembling the union of secret patterns, and reporting honestly when that
union could not be assembled, is a separate concern from the HTTP route that
applies it.

The names are re-exported by the route module, so
`monkeypatch.setattr(conversations, "_REDACTION_BANK_COMPLETE", False)` keeps
working and `_require_complete_bank` still reads its own module global. That
matters more than tidiness: moving a flag out from under the tests that
monkeypatch it is how a fail-closed guard quietly stops being tested.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from .scanner import _SECRET_PATTERNS as _SCANNER_SECRET_PATTERNS

log = logging.getLogger("pi-ceo.routes.conversations")


def _build_redaction_bank() -> tuple[list[tuple[re.Pattern[str], str]], bool]:
    """Compile the existing secret banks into (pattern, tag) pairs.

    Returns `(bank, complete)`. `complete` is False when the transcript-specific
    extension could not be loaded, and that flag is what closes the lane — see
    `_require_complete_bank`.

    Union, not a choice between them: `scanner._SECRET_PATTERNS` is the
    server-side bank (`scripts/secrets_check.py` documents itself as mirroring
    it), while `scripts/sync_claude_sessions.py` extends it with the shapes that
    bank misses but transcripts actually contain — Anthropic OAuth tokens,
    Google API keys, Slack tokens and GitHub PATs. Neither alone covers a
    conversation digest.

    The import stays best-effort so a refactor over there cannot 500 the route
    on startup, but a degraded bank must never be treated as a working one: the
    scanner half does not match the transcript-only shapes, so ingesting under
    it would persist exactly the tokens this endpoint exists to strip.
    """
    bank = [(re.compile(p), title) for p, title, _sev in _SCANNER_SECRET_PATTERNS]
    try:
        from scripts.sync_claude_sessions import _SECRET_PATTERNS as _extra  # noqa: PLC0415
        bank += [(re.compile(p), tag) for p, tag in _extra]
    except Exception:  # noqa: BLE001 — never let an import failure open the lane
        log.error(
            "conversation redaction: scripts.sync_claude_sessions bank unavailable — "
            "INGEST DISABLED, the scanner-only bank does not cover transcript token "
            "shapes", exc_info=True,
        )
        return bank, False
    return bank, True


_REDACTION_BANK, _REDACTION_BANK_COMPLETE = _build_redaction_bank()


def _redact(text: Optional[str]) -> Optional[str]:
    """Replace every known secret shape with a typed placeholder. Idempotent."""
    if not text:
        return text
    for rx, tag in _REDACTION_BANK:
        text = rx.sub(f"[REDACTED:{tag}]", text)
    return text
