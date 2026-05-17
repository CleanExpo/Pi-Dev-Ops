"""Default Claude-backed PII classifier — RA-1847.

Provides ``default_classifier()`` returning a ``Callable[[str], list[Hit]]`` that
the pii_redactor can plug in when strictness=high is requested. Classifies the
payload via Claude into 6 buckets:

  - name             (proper-noun person name in privacy-sensitive context)
  - attendee_list    (a roster of people in a meeting/email)
  - location         (street, suburb, town not already covered by postcode regex)
  - org_internal     (Unite-Group internal-only project / codename)
  - unknown          (model uncertain; do NOT redact)
  - clean            (model confident it's not PII)

Categories ``name`` / ``attendee_list`` / ``location`` / ``org_internal`` are
returned as Hits. ``unknown`` and ``clean`` are not.

Loaded lazily so callers that never need high-strictness don't pay for the
import; falls through to a no-op (returning empty) if the Anthropic SDK or
ANTHROPIC_API_KEY isn't available — degraded mode noted in caller logs.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Callable

from .pii_redactor import Hit  # type: ignore[import-not-found]

log = logging.getLogger("pi-ceo.pii_classify")

# Cost-strategy per `[[feedback-model-routing-max-first]]`:
#   Tier 0 (NEW): `claude --print` — $0 marginal under the Max plan.
#   Tier 1: Anthropic API direct (Haiku) — was the only path; now fallback.
#   Tier 2: degraded no-op (returns []).
#
# Same JSON-output prompt for both tiers, so the response parser is shared.
# Subprocess overhead of `claude --print` (~3-5s) is acceptable here — this
# classifier is only invoked by pii_redactor when strictness=high, which is
# off the hot path.
CLAUDE_CLI = os.environ.get("CLAUDE_CLI", "claude")
CLAUDE_PRINT_TIMEOUT = int(os.environ.get("CLAUDE_PRINT_TIMEOUT", "60"))


_PROMPT = """Classify each PII span in TEXT below. Return ONE JSON array on a single line.
Each element MUST be of shape:
  {"start": <int>, "end": <int>, "category": "<one of: name, attendee_list, location, org_internal>", "value": "<exact substring>"}

Rules:
- ONLY return spans you are >= 0.95 confident are PII.
- Skip spans already obvious to a regex (emails, phone numbers, postcodes) — those are handled separately.
- For names: only person names where the surrounding context is privacy-sensitive (e.g. "Met with John Smith about budget"); skip generic mentions ("John Smith Inc." brand names, public figures in public-context references).
- For attendee_list: comma-separated rosters in a meeting/email payload, e.g. "Attendees: Alice Lee, Bob Singh, Carol Tran".
- For location: street addresses, suburb/town names not already postcode-covered.
- For org_internal: Unite-Group internal codenames (e.g. project tags that aren't already public).
- Skip everything you're not sure about. Empty array `[]` is a valid response.

TEXT:
\"\"\"
{TEXT}
\"\"\""""


def _parse_spans(raw: str, text: str) -> list[Hit]:
    """Parse the model's JSON-array response into validated Hit objects.

    Shared between the claude --print tier-0 path and the Anthropic API
    tier-1 path so both surfaces enforce the same span validation
    (offset/value match + category whitelist).
    """
    if not raw or raw == "[]":
        return []
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    try:
        spans = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("classifier JSON parse failed: %s (raw=%r)", exc, raw[:100])
        return []
    hits: list[Hit] = []
    for span in spans:
        if not isinstance(span, dict):
            continue
        start = int(span.get("start", -1))
        end = int(span.get("end", -1))
        category = str(span.get("category", "unknown"))
        value = str(span.get("value", ""))
        if start < 0 or end <= start or category not in {
            "name", "attendee_list", "location", "org_internal",
        }:
            continue
        # Validate the span actually matches text at offsets — guards against
        # model hallucinating offsets that don't line up.
        if text[start:end] != value:
            log.debug("classifier span mismatch (skipping): %r != %r", text[start:end], value)
            continue
        cat_map = {
            "name": ("NAME", "[NAME-REDACTED]"),
            "attendee_list": ("ATTENDEES", "[ATTENDEES-REDACTED]"),
            "location": ("LOCATION", "[LOCATION-REDACTED]"),
            "org_internal": ("ORG_INTERNAL", "[ORG-REDACTED]"),
        }
        hit_cat, replacement = cat_map[category]
        hits.append(Hit(
            category=hit_cat,
            start=start,
            end=end,
            method="classify",
            replacement=replacement,
        ))
    return hits


class _ClassifyError(RuntimeError):
    """Wraps a single-tier failure so the cascade can fall through cleanly."""


def _classify_via_claude_print(text: str) -> list[Hit]:
    """Tier 0 — `claude --print` ($0 marginal under Max). Raises on failure."""
    prompt = _PROMPT.replace("{TEXT}", text)
    try:
        result = subprocess.run(
            [CLAUDE_CLI, "--print", prompt],
            capture_output=True, text=True, timeout=CLAUDE_PRINT_TIMEOUT, check=False,
        )
    except FileNotFoundError as exc:
        raise _ClassifyError(f"claude CLI not found at {CLAUDE_CLI}") from exc
    except subprocess.TimeoutExpired as exc:
        raise _ClassifyError(f"claude --print timed out after {CLAUDE_PRINT_TIMEOUT}s") from exc
    if result.returncode != 0:
        raise _ClassifyError(f"claude --print exit {result.returncode}: {result.stderr[:200]}")
    return _parse_spans(result.stdout.strip(), text)


def _make_classifier_with_anthropic(model: str) -> Callable[[str], list[Hit]]:
    """Tier 1 — anthropic.Anthropic().messages.create (the original path)."""
    try:
        from anthropic import Anthropic  # type: ignore[import-not-found]  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover — anthropic SDK guaranteed in prod
        log.warning("anthropic SDK unavailable; tier-1 disabled: %s", exc)
        return lambda _text: []

    client = Anthropic()

    def _classify(text: str) -> list[Hit]:
        prompt = _PROMPT.replace("{TEXT}", text)
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = "".join(
                getattr(block, "text", "")
                for block in (resp.content or [])
                if getattr(block, "type", None) == "text"
            ).strip()
            return _parse_spans(raw, text)
        except Exception as exc:
            log.warning("anthropic_classify call failed (returning empty): %s", exc)
            return []

    return _classify


def default_classifier() -> Callable[[str], list[Hit]]:
    """Return the cascade-backed classifier.

    Cascade per `[[feedback-model-routing-max-first]]`:
      0. `claude --print`           — $0 marginal under Max plan
      1. Anthropic API (Haiku)      — paid fallback; was the only tier before
      2. no-op []                   — degraded mode when both tiers unavailable

    Set DISABLE_CLAUDE_PRINT_CLASSIFIER=1 to skip tier 0 (e.g. when the Max
    plan is rate-limited or you're benchmarking the Anthropic-API path).
    """
    model = os.environ.get("PII_CLASSIFY_MODEL", "claude-haiku-4-5-20251001")
    anthropic_classifier = _make_classifier_with_anthropic(model)
    skip_tier_0 = os.environ.get("DISABLE_CLAUDE_PRINT_CLASSIFIER", "0") == "1"

    def _cascade(text: str) -> list[Hit]:
        if not text or len(text) < 8:
            return []
        if not skip_tier_0:
            try:
                hits = _classify_via_claude_print(text)
                log.debug("pii_classify tier=0 (claude --print) → %d hit(s)", len(hits))
                return hits
            except _ClassifyError as exc:
                log.info("pii_classify tier-0 unavailable, falling back: %s", exc)
        hits = anthropic_classifier(text)
        log.debug("pii_classify tier=1 (anthropic api) → %d hit(s)", len(hits))
        return hits

    return _cascade


__all__ = ["default_classifier"]
