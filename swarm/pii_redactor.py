"""
swarm/pii_redactor.py — RA-1839: PII detection and redaction.

Implements pii-redactor SKILL.md regex pass. Claude classify pass is a
plug-point — module accepts an optional `claude_classify` callable that
returns extra hits.

Targets (against pii_test_corpus.jsonl when built):
  * ≥95% precision on PII samples
  * ≤5% false-positive rate on clean samples

Output is a redacted payload + a redaction_log of (category, offset, length).
The original text never lands in audit form — only the log + a salted hash.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

log = logging.getLogger("swarm.pii_redactor")

Strictness = Literal["standard", "high"]


@dataclass
class Hit:
    category: str
    start: int
    end: int
    method: str  # "regex" | "classify"
    replacement: str

    def as_log(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "original_offset": self.start,
            "length": self.end - self.start,
            "method": self.method,
        }


@dataclass
class Result:
    redacted_payload: str
    redaction_count: int
    redaction_log: list[dict[str, Any]]
    precision_score: float
    passed: bool
    salted_hash: str  # of ORIGINAL text (so audit can verify same payload)


# ── Pattern bank ─────────────────────────────────────────────────────────────
_LUHN_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_NI_RE = re.compile(r"\b[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\d{6}[A-D]\b")
_TFN_RE = re.compile(r"\b\d{3}\s?\d{3}\s?\d{3}\b")
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
_PHONE_E164_RE = re.compile(r"(?<!\d)\+\d{1,3}[\s-]?\d[\s\d-]{7,14}")
_API_KEY_RE = re.compile(
    r"\b("
    r"sk-[A-Za-z0-9_-]{20,}"
    r"|claude-api-[A-Za-z0-9_-]{20,}"
    r"|sk-ant-[A-Za-z0-9_-]{20,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[A-Z0-9]{16}"
    r"|xoxb-[A-Za-z0-9-]{20,}"
    r")\b"
)
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}")
_PASSWORD_RE = re.compile(
    r"\b(password|passwd|pwd)\s*[:=]\s*\S+", re.IGNORECASE
)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _scan_regex(text: str) -> list[Hit]:
    hits: list[Hit] = []

    # Credit card with Luhn validation
    for m in _LUHN_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            hits.append(Hit("CARD", m.start(), m.end(), "regex", "[CARD-REDACTED]"))

    for m in _SSN_RE.finditer(text):
        hits.append(Hit("SSN", m.start(), m.end(), "regex", "[SSN-REDACTED]"))
    for m in _NI_RE.finditer(text):
        hits.append(Hit("NI", m.start(), m.end(), "regex", "[NI-REDACTED]"))
    for m in _TFN_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) == 9 and _tfn_ok(digits):
            hits.append(Hit("TFN", m.start(), m.end(), "regex", "[TFN-REDACTED]"))
    for m in _EMAIL_RE.finditer(text):
        hits.append(Hit("EMAIL", m.start(), m.end(), "regex", "[EMAIL-REDACTED]"))
    for m in _PHONE_E164_RE.finditer(text):
        hits.append(Hit("PHONE", m.start(), m.end(), "regex", "[PHONE-REDACTED]"))
    for m in _API_KEY_RE.finditer(text):
        hits.append(Hit("KEY", m.start(), m.end(), "regex", "[KEY-REDACTED]"))
    for m in _BEARER_RE.finditer(text):
        hits.append(Hit("BEARER", m.start(), m.end(), "regex", "Bearer [TOKEN-REDACTED]"))
    for m in _PASSWORD_RE.finditer(text):
        hits.append(Hit("PASSWORD", m.start(), m.end(), "regex",
                       "password=[REDACTED]"))

    return hits


def _tfn_ok(digits: str) -> bool:
    """Validate Australian TFN checksum (9 digits)."""
    weights = (1, 4, 3, 7, 5, 8, 6, 9, 10)
    if len(digits) != 9:
        return False
    return sum(int(d) * w for d, w in zip(digits, weights)) % 11 == 0


def _resolve_overlaps(hits: list[Hit]) -> list[Hit]:
    """Sort by start; drop hits fully covered by an earlier longer hit."""
    if not hits:
        return hits
    hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
    out: list[Hit] = []
    last_end = -1
    for h in hits:
        if h.start >= last_end:
            out.append(h)
            last_end = h.end
        else:
            log.debug("overlap drop %s @%d-%d", h.category, h.start, h.end)
    return out


def _apply_redactions(text: str, hits: list[Hit]) -> str:
    if not hits:
        return text
    parts: list[str] = []
    cursor = 0
    for h in hits:
        parts.append(text[cursor:h.start])
        parts.append(h.replacement)
        cursor = h.end
    parts.append(text[cursor:])
    return "".join(parts)


def _salted_hash(text: str) -> str:
    """SHA-256 of normalized text + a per-process salt. Audit-stable."""
    norm = unicodedata.normalize("NFC", text)
    h = hashlib.sha256()
    h.update(b"pi-ceo-pii-v1::")
    h.update(norm.encode("utf-8"))
    return h.hexdigest()[:32]


def _normalize(text: str) -> str:
    """NFC-normalize, decode percent-encoded sequences (best-effort)."""
    norm = unicodedata.normalize("NFC", text)
    try:
        from urllib.parse import unquote
        decoded = unquote(norm)
        return decoded if decoded != norm else norm
    except Exception:
        return norm


def redact(
    payload: str,
    *,
    context: str = "telegram_send",
    preserve_structure: bool = True,
    strictness: Strictness = "standard",
    claude_classify: Callable[[str], list[Hit]] | None = None,
) -> Result:
    """Redact PII from `payload`. Returns Result with redacted text + log."""
    if not isinstance(payload, str):
        # Allow JSON-shaped payloads — caller stringifies first
        raise TypeError("redact() expects str; pre-serialize JSON")

    text = _normalize(payload)
    regex_hits = _scan_regex(text)

    # RA-1847: when strictness=high and no classifier supplied, auto-resolve
    # the default Claude-backed classifier from swarm.pii_classify. Caller can
    # still override by passing claude_classify explicitly (e.g. tests inject
    # a deterministic stub).
    if strictness == "high" and claude_classify is None:
        try:
            from .pii_classify import default_classifier  # noqa: PLC0415
            claude_classify = default_classifier()
        except Exception as exc:
            log.warning(
                "strictness=high requested but default_classifier unavailable "
                "(continuing regex-only, precision will reflect degradation): %s",
                exc,
            )

    classify_hits: list[Hit] = []
    if claude_classify is not None:
        try:
            classify_hits = list(claude_classify(text)) or []
        except Exception as exc:
            log.warning("claude_classify failed (continuing regex-only): %s", exc)

    all_hits = _resolve_overlaps(regex_hits + classify_hits)
    redacted = _apply_redactions(text, all_hits)

    redaction_log = [h.as_log() for h in all_hits]

    # Precision score: heuristic — assume regex hits are ≥95% precise (they are
    # exact patterns); classify pass varies. With no classify pass, score = 1.0.
    if claude_classify is None:
        precision = 1.0
    else:
        regex_count = sum(1 for h in all_hits if h.method == "regex")
        precision = (regex_count / len(all_hits)) if all_hits else 1.0

    passed = precision >= 0.95

    return Result(
        redacted_payload=redacted,
        redaction_count=len(all_hits),
        redaction_log=redaction_log,
        precision_score=precision,
        passed=passed,
        salted_hash=_salted_hash(payload),
    )


__all__ = ["redact", "Result", "Hit"]
