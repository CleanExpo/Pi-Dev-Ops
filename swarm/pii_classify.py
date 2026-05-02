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
from typing import Callable

from .pii_redactor import Hit  # type: ignore[import-not-found]

log = logging.getLogger("pi-ceo.pii_classify")


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


def _make_classifier_with_anthropic(model: str) -> Callable[[str], list[Hit]]:
    """Return a classifier closure backed by anthropic.Anthropic().messages.create."""
    try:
        from anthropic import Anthropic  # type: ignore[import-not-found]  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover — anthropic SDK guaranteed in prod
        log.warning("anthropic SDK unavailable; classifier degraded to no-op: %s", exc)
        return lambda _text: []

    client = Anthropic()

    def _classify(text: str) -> list[Hit]:
        if not text or len(text) < 8:
            return []
        prompt = _PROMPT.replace("{TEXT}", text)
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            # Concat all text blocks
            raw = "".join(
                getattr(block, "text", "")
                for block in (resp.content or [])
                if getattr(block, "type", None) == "text"
            ).strip()
            if not raw or raw == "[]":
                return []
            # Strip code-fence wrappers if model returned them
            if raw.startswith("```"):
                raw = raw.strip("`").lstrip("json").strip()
            spans = json.loads(raw)
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
                # Map classifier categories → Hit category labels (uppercase
                # convention used by the regex pass) + sensible replacement.
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
        except Exception as exc:
            log.warning("claude_classify call failed (returning empty): %s", exc)
            return []

    return _classify


def default_classifier() -> Callable[[str], list[Hit]]:
    """Return the default Claude-backed classifier.

    Honours `model_policy.select_model("monitor", ...)` per RA-1099 — uses Haiku
    by default for the cheap classification pass; can be overridden via the
    PII_CLASSIFY_MODEL env var.
    """
    model = os.environ.get("PII_CLASSIFY_MODEL", "claude-haiku-4-5-20251001")
    return _make_classifier_with_anthropic(model)


__all__ = ["default_classifier"]
