"""swarm/research/gemini_research.py — RA-1986: Gemini grounded research engine.

Citation-grounded research backend for Margot, PM bots, and board
deliberations. Calls Google's Gemini API with the `google_search` tool
enabled so every claim returns with a real source URL — the foundation
for ATIA's E.E.A.T moat.

Design notes
------------
* **Model swap is a single env-var change.** `MARGOT_RESEARCH_MODEL`
  controls the default; when Phill's DeepMind tier lands with Gemini 3.x
  he flips the env var, no code change required.
* **Three depth modes.** `quick` forces flash (latency-optimised).
  `standard` uses the env default. `deep` keeps the env default but
  bumps `maxOutputTokens` from 4096 to 8192.
* **Citations are mandatory.** When `citations_required=True` and the
  first response has zero grounding chunks, we re-prompt once asking
  for explicit citations. Still zero → `GroundingFailedError`.
* **Australian English.** The system prompt mandates AUD, DD/MM/YYYY,
  AEST/AEDT, and prioritises AS/NZS + IICRC + Master Builders +
  state-regulator sources over blog spam.
* **HTTP transport is `httpx`** — already in pyproject deps; no new
  dependency added.

Public API
----------
    @dataclass Citation: url, title, snippet
    @dataclass GroundedResearchResult: topic, text, citations, model,
                                      grounding_used, elapsed_s, raw_response
    async grounded_research(topic, *, depth, citations_required,
                            max_tokens, model) -> GroundedResearchResult
    format_citation(c, style) -> str
    format_citations_block(citations, style, heading) -> str
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger("swarm.research.gemini_research")

# ── Configuration ────────────────────────────────────────────────────────────

# Default model — overridden by env. When DeepMind enterprise tier lands
# with Gemini 3.x, set MARGOT_RESEARCH_MODEL=gemini-3-pro (or similar).
DEFAULT_MODEL = "gemini-2.5-pro"
QUICK_MODEL = "gemini-2.5-flash"  # latency-optimised; overrides env when depth="quick"

# generationConfig defaults
DEFAULT_MAX_TOKENS = 4096
DEEP_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.2

# Network + retry policy
HTTP_TIMEOUT_S = 30.0
RATE_LIMIT_MAX_RETRIES = 3
UPSTREAM_MAX_RETRIES = 2
# Exponential backoff base seconds; actual sleep is base * (2 ** attempt).
RATE_LIMIT_BACKOFF_BASE_S = 1.0
UPSTREAM_BACKOFF_S = (5.0, 15.0)

# API endpoint — v1beta is where the google_search tool currently lives.
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


# ── System prompt ────────────────────────────────────────────────────────────

# Australian-English aware, citation-strict. Optimised for ATIA's six
# verticals: Restoration, Carpet Cleaning, IEP, Plumbing, HVAC,
# Pressure Washing.
SYSTEM_PROMPT = """You are a Senior Research Analyst for Phill McGurk's autonomous swarm.
You are researching a topic to support strategic decisions for the
Australian Trade Industry Association (ATIA), a body covering Restoration,
Carpet Cleaning, Indoor Environmental Professional, Plumbing, HVAC, and
Pressure Washing verticals across Australia + New Zealand.

Rules:
1. Use Australian English. AUD. DD/MM/YYYY. AEST/AEDT.
2. Every claim must be backed by a citation from a credible source —
   prefer AS/NZS standards, IICRC, Master Builders, government regulators,
   peer-reviewed journals, or industry publications. Avoid blog spam.
3. If the topic touches restoration or moisture, prioritise IICRC and
   AS/NZS sources. If touching trade certification, prioritise state
   regulator + Master Builders + HIA sources.
4. State explicitly when a claim is uncertain or contested.
5. Output structure:
   - 1-paragraph executive summary (the answer)
   - 2-5 bullet points of supporting facts (each citation-tagged)
   - 1-paragraph implications / what this means for the swarm's next action
   - Sources list at the end
6. NEVER fabricate citations. If you can't find a source, say so.
"""


# ── Exceptions ───────────────────────────────────────────────────────────────


class GeminiResearchError(Exception):
    """Base for all gemini_research errors."""

    def __init__(self, message: str, *, topic: str = "", model: str = "") -> None:
        ctx = f" [topic={topic!r} model={model!r}]" if (topic or model) else ""
        super().__init__(f"{message}{ctx}")
        self.topic = topic
        self.model = model


class AuthError(GeminiResearchError):
    """GEMINI_API_KEY missing or rejected (HTTP 401/403)."""


class RateLimitError(GeminiResearchError):
    """HTTP 429 after all retries exhausted."""


class UpstreamError(GeminiResearchError):
    """HTTP 5xx after all retries exhausted."""


class TimeoutError(GeminiResearchError):  # noqa: A001 — shadowing builtin is intentional; namespaced via module
    """Network timeout (> HTTP_TIMEOUT_S)."""


class EmptyResponseError(GeminiResearchError):
    """API returned 200 but candidates / content was empty."""


class GroundingFailedError(GeminiResearchError):
    """citations_required=True but model produced zero grounding chunks after retry."""

    def __init__(self, message: str, *, topic: str = "", model: str = "",
                 partial: "GroundedResearchResult | None" = None) -> None:
        super().__init__(message, topic=topic, model=model)
        self.partial = partial


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class Citation:
    """A single grounded citation parsed from Gemini's groundingMetadata."""

    url: str
    title: str
    snippet: str = ""  # relevant excerpt from the surrounding text


@dataclass
class GroundedResearchResult:
    """Full result of a grounded_research call."""

    topic: str
    text: str  # synthesised answer
    citations: list[Citation]
    model: str  # which model actually produced this
    grounding_used: bool  # did google_search grounding actually fire?
    elapsed_s: float
    raw_response: dict[str, Any] = field(default_factory=dict)


# ── Public formatting helpers ────────────────────────────────────────────────

# Gemini's grounding response packs the publisher domain (and sometimes the
# article headline) into Citation.title, while Citation.url is the Vertex AI
# redirect (`vertexaisearch.cloud.google.com/grounding-api-redirect/…`).
# Rendering `url` raw in briefings + Telegram alerts gives unreadable redirect
# soup; these helpers project the title into a human-readable label so a
# reader sees the publisher at a glance.

# Telegram MarkdownV2 reserved chars that must be backslash-escaped when they
# appear inside link text or body text. See Telegram Bot API docs.
_TELEGRAM_MD2_SPECIAL = r"_*[]()~`>#+-=|{}.!"

# Separators that may sit between "publisher.tld" and "headline" inside a
# citation title (e.g. "carsi.com.au - Mould Remediation Pathway"). Order
# matters — longer/em-dash variants first so they win over plain hyphen.
_TITLE_SEPARATORS = (" — ", " – ", " - ", " | ")


def _split_publisher_headline(title: str) -> tuple[str, str]:
    """Split a citation title into (publisher, headline).

    Returns ("", "") if the title is empty. If no separator is present,
    returns the full title as the publisher and an empty headline (so the
    caller still gets a usable label).
    """
    title = (title or "").strip()
    if not title:
        return "", ""
    for sep in _TITLE_SEPARATORS:
        if sep in title:
            publisher, _, headline = title.partition(sep)
            return publisher.strip(), headline.strip()
    return title, ""


def _telegram_escape(text: str) -> str:
    """Escape Telegram MarkdownV2 special characters in a plain-text run."""
    return "".join(("\\" + ch) if ch in _TELEGRAM_MD2_SPECIAL else ch for ch in (text or ""))


def format_citation(c: "Citation", style: str = "markdown") -> str:
    """Render a single Citation in a human-readable form.

    Styles
    ------
    "markdown"  — ``[publisher — headline](url)`` (or ``[title](url)`` when no
                  separator is present in the title).
    "plain"     — ``publisher — headline (url)`` with no markdown.
    "compact"   — ``[publisher](url)`` (publisher only — for tight UIs).
    "telegram"  — Telegram MarkdownV2-safe link with reserved chars escaped.

    The ``title`` field carries the publisher domain plus (optionally) the
    article headline separated by " - ", " — ", " – " or " | ". The ``url``
    is typically the Vertex AI redirect URL — we do not resolve it here.
    """
    publisher, headline = _split_publisher_headline(c.title)
    url = (c.url or "").strip()

    # Build the human label (no URL part yet).
    if publisher and headline:
        label = f"{publisher} — {headline}"
        compact_label = publisher
    elif publisher:
        label = publisher
        compact_label = publisher
    else:
        label = url or "(no source)"
        compact_label = label

    if style == "markdown":
        return f"[{label}]({url})" if url else label
    if style == "plain":
        return f"{label} ({url})" if url else label
    if style == "compact":
        return f"[{compact_label}]({url})" if url else compact_label
    if style == "telegram":
        # MarkdownV2: link text needs special chars escaped; URL must have
        # ')' and '\' escaped inside the parens.
        safe_label = _telegram_escape(label)
        safe_url = url.replace("\\", "\\\\").replace(")", "\\)") if url else ""
        return f"[{safe_label}]({safe_url})" if safe_url else safe_label
    raise ValueError(
        f"format_citation: unknown style {style!r}; "
        f"expected one of 'markdown'|'plain'|'compact'|'telegram'",
    )


def format_citations_block(
    citations: "list[Citation]",
    style: str = "markdown",
    heading: str | None = "Sources",
) -> str:
    """Format a numbered citation block. Returns ``""`` when ``citations`` is empty.

    The heading is rendered as bold markdown when ``style='markdown'``, as a
    Telegram-safe bold run when ``style='telegram'``, and as a plain underlined
    line for ``style='plain'`` / ``style='compact'``. Pass ``heading=None`` to
    suppress the heading entirely.
    """
    if not citations:
        return ""
    lines: list[str] = []
    if heading:
        if style == "markdown":
            lines.append(f"**{heading}**")
        elif style == "telegram":
            lines.append(f"*{_telegram_escape(heading)}*")
        else:  # plain / compact
            lines.append(heading)
    for i, c in enumerate(citations, 1):
        lines.append(f"{i}. {format_citation(c, style)}")
    return "\n".join(lines)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _resolve_model(*, depth: str, override: str | None) -> str:
    """Resolve which model name to use.

    Order of precedence:
      1. depth='quick' -> QUICK_MODEL (forced for latency)
      2. explicit `model` parameter
      3. MARGOT_RESEARCH_MODEL env var
      4. DEFAULT_MODEL constant
    """
    if depth == "quick":
        return QUICK_MODEL
    if override:
        return override
    return os.environ.get("MARGOT_RESEARCH_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _resolve_max_tokens(*, depth: str, max_tokens: int) -> int:
    """`deep` depth bumps max_tokens to 8192 (unless caller passed something larger)."""
    if depth == "deep":
        return max(max_tokens, DEEP_MAX_TOKENS)
    return max_tokens


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise AuthError(
            "GEMINI_API_KEY not set — add it to ~/.hermes/.env or the process env",
        )
    return key


def _build_request_body(
    *, topic: str, max_tokens: int, extra_user_instruction: str = "",
) -> dict[str, Any]:
    """Build the POST body for generateContent with google_search tool."""
    user_text = topic if not extra_user_instruction else f"{topic}\n\n{extra_user_instruction}"
    return {
        # systemInstruction is the supported field name on v1beta for the
        # persona/rules prompt. It applies for every turn in the conversation.
        "systemInstruction": {
            "role": "system",
            "parts": [{"text": SYSTEM_PROMPT}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_text}],
            },
        ],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "temperature": DEFAULT_TEMPERATURE,
            "maxOutputTokens": max_tokens,
        },
    }


def _extract_text(raw: dict[str, Any]) -> str:
    """Pull the synthesised answer text out of the Gemini response."""
    candidates = raw.get("candidates") or []
    if not candidates:
        return ""
    content = (candidates[0] or {}).get("content") or {}
    parts = content.get("parts") or []
    chunks: list[str] = []
    for p in parts:
        if isinstance(p, dict):
            t = p.get("text")
            if isinstance(t, str) and t:
                chunks.append(t)
    return "\n".join(chunks).strip()


def _extract_citations(raw: dict[str, Any]) -> list[Citation]:
    """Parse groundingMetadata.groundingChunks into Citation list.

    Gemini's grounding response shape (v1beta with google_search tool):

        candidates[0].groundingMetadata.groundingChunks = [
            {"web": {"uri": "...", "title": "..."}},
            ...
        ]
        candidates[0].groundingMetadata.groundingSupports = [
            {"segment": {"text": "..."}, "groundingChunkIndices": [0, 2]},
            ...
        ]

    We use groundingChunks for the citation list (url + title) and
    groundingSupports for the snippet excerpt where available.
    """
    candidates = raw.get("candidates") or []
    if not candidates:
        return []
    meta = (candidates[0] or {}).get("groundingMetadata") or {}
    chunks = meta.get("groundingChunks") or []
    supports = meta.get("groundingSupports") or []

    # Build chunk_index -> snippet map from groundingSupports.
    snippet_for: dict[int, str] = {}
    for sup in supports:
        if not isinstance(sup, dict):
            continue
        seg = sup.get("segment") or {}
        text = seg.get("text") if isinstance(seg, dict) else None
        if not isinstance(text, str) or not text:
            continue
        for idx in sup.get("groundingChunkIndices") or []:
            if isinstance(idx, int) and idx not in snippet_for:
                snippet_for[idx] = text

    citations: list[Citation] = []
    for i, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            continue
        web = chunk.get("web") or {}
        uri = (web.get("uri") or "").strip()
        title = (web.get("title") or "").strip()
        if not uri:
            continue
        citations.append(Citation(
            url=uri,
            title=title or uri,
            snippet=snippet_for.get(i, "")[:400],
        ))
    return citations


# ── HTTP transport ───────────────────────────────────────────────────────────


async def _post_generate_content(
    *,
    model: str,
    body: dict[str, Any],
    api_key: str,
    topic: str,
) -> dict[str, Any]:
    """POST to Gemini generateContent with retry policy.

    Retry policy:
      * 429 -> exponential backoff (1s, 2s, 4s), retry up to 3 times
      * 5xx -> 5s then 15s, retry up to 2 times
      * 401/403 -> raise AuthError immediately
      * Timeout -> raise TimeoutError
      * Other 4xx -> raise UpstreamError (treated as non-retryable client error)
    """
    url = f"{GEMINI_API_BASE}/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}

    rl_attempt = 0
    up_attempt = 0

    while True:
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
                resp = await client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"Gemini request timed out after {HTTP_TIMEOUT_S}s: {exc}",
                topic=topic, model=model,
            ) from exc
        except httpx.RequestError as exc:
            # Connection / DNS / TLS — treat as timeout-class failure.
            raise TimeoutError(
                f"Gemini request failed: {exc}",
                topic=topic, model=model,
            ) from exc

        status = resp.status_code

        if status == 200:
            try:
                return resp.json()
            except ValueError as exc:
                raise EmptyResponseError(
                    f"Gemini returned 200 but body was not valid JSON: {exc}",
                    topic=topic, model=model,
                ) from exc

        if status in (401, 403):
            raise AuthError(
                f"Gemini auth rejected (HTTP {status}): "
                f"check GEMINI_API_KEY in ~/.hermes/.env",
                topic=topic, model=model,
            )

        if status == 429:
            if rl_attempt >= RATE_LIMIT_MAX_RETRIES:
                raise RateLimitError(
                    f"Gemini rate-limited (HTTP 429) after "
                    f"{RATE_LIMIT_MAX_RETRIES} retries",
                    topic=topic, model=model,
                )
            backoff = RATE_LIMIT_BACKOFF_BASE_S * (2 ** rl_attempt)
            log.warning(
                "[gemini-research] rate-limited; backing off %.1fs (attempt %d/%d) "
                "topic=%r model=%s",
                backoff, rl_attempt + 1, RATE_LIMIT_MAX_RETRIES, topic, model,
            )
            await asyncio.sleep(backoff)
            rl_attempt += 1
            continue

        if 500 <= status < 600:
            if up_attempt >= UPSTREAM_MAX_RETRIES:
                raise UpstreamError(
                    f"Gemini upstream error (HTTP {status}) after "
                    f"{UPSTREAM_MAX_RETRIES} retries",
                    topic=topic, model=model,
                )
            backoff = UPSTREAM_BACKOFF_S[min(up_attempt, len(UPSTREAM_BACKOFF_S) - 1)]
            log.warning(
                "[gemini-research] upstream %d; backing off %.1fs (attempt %d/%d) "
                "topic=%r model=%s",
                status, backoff, up_attempt + 1, UPSTREAM_MAX_RETRIES, topic, model,
            )
            await asyncio.sleep(backoff)
            up_attempt += 1
            continue

        # Other 4xx (400, 404, etc.) — surface upstream with body.
        body_snippet = (resp.text or "")[:500]
        raise UpstreamError(
            f"Gemini returned HTTP {status}: {body_snippet}",
            topic=topic, model=model,
        )


# ── Public API ───────────────────────────────────────────────────────────────


async def grounded_research(
    topic: str,
    *,
    depth: str = "standard",
    citations_required: bool = True,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    model: str | None = None,
) -> GroundedResearchResult:
    """Run grounded research via Gemini + google_search.

    Parameters
    ----------
    topic : str
        The question or research brief. Passed directly as the user turn.
    depth : str
        One of "quick" | "standard" | "deep".
        * "quick"    -> always uses QUICK_MODEL (gemini-2.5-flash)
        * "standard" -> uses env MARGOT_RESEARCH_MODEL (or DEFAULT_MODEL)
        * "deep"     -> uses env default + bumps max_tokens to 8192
    citations_required : bool
        When True (default), if the first response has zero grounding
        chunks we re-prompt once. Still zero -> GroundingFailedError.
        When False, returns whatever the model produced with
        grounding_used=False and an empty citations list.
    max_tokens : int
        generationConfig.maxOutputTokens. Default 4096; overridden upward
        by depth="deep".
    model : str | None
        Override the env-resolved model. Mostly for tests + experiments.

    Returns
    -------
    GroundedResearchResult

    Raises
    ------
    AuthError, RateLimitError, UpstreamError, TimeoutError,
    EmptyResponseError, GroundingFailedError
    """
    if depth not in ("quick", "standard", "deep"):
        raise ValueError(f"depth must be 'quick'|'standard'|'deep', got {depth!r}")

    resolved_model = _resolve_model(depth=depth, override=model)
    resolved_max = _resolve_max_tokens(depth=depth, max_tokens=max_tokens)
    api_key = _api_key()

    started = time.monotonic()
    retry_count = 0

    body = _build_request_body(topic=topic, max_tokens=resolved_max)
    raw = await _post_generate_content(
        model=resolved_model, body=body, api_key=api_key, topic=topic,
    )

    text = _extract_text(raw)
    citations = _extract_citations(raw)
    grounding_used = bool(citations)

    if not text and not citations:
        raise EmptyResponseError(
            "Gemini returned no text and no grounding chunks",
            topic=topic, model=resolved_model,
        )

    # Citation-required retry — one shot only.
    if citations_required and not grounding_used:
        retry_count = 1
        log.info(
            "[gemini-research] zero citations on first pass; re-prompting "
            "topic=%r model=%s",
            topic, resolved_model,
        )
        retry_body = _build_request_body(
            topic=topic,
            max_tokens=resolved_max,
            extra_user_instruction=(
                "Your answer above must include citations from web search. "
                "Re-answer with explicit citation markers [1], [2] and a "
                "sources list."
            ),
        )
        raw_retry = await _post_generate_content(
            model=resolved_model, body=retry_body, api_key=api_key, topic=topic,
        )
        text_retry = _extract_text(raw_retry)
        citations_retry = _extract_citations(raw_retry)
        if citations_retry:
            text = text_retry or text
            citations = citations_retry
            grounding_used = True
            raw = raw_retry
        else:
            elapsed = time.monotonic() - started
            partial = GroundedResearchResult(
                topic=topic,
                text=text_retry or text,
                citations=[],
                model=resolved_model,
                grounding_used=False,
                elapsed_s=elapsed,
                raw_response=raw_retry,
            )
            log.warning(
                "[gemini-research] grounding_failed topic=%r model=%s "
                "elapsed_s=%.2f retry_count=%d",
                topic, resolved_model, elapsed, retry_count,
            )
            raise GroundingFailedError(
                "citations_required=True but Gemini produced zero grounding "
                "chunks even after explicit re-prompt",
                topic=topic, model=resolved_model, partial=partial,
            )

    elapsed = time.monotonic() - started
    log.info(
        "[gemini-research] ok topic=%r depth=%s model=%s elapsed_s=%.2f "
        "citation_count=%d grounding_used=%s retry_count=%d",
        topic, depth, resolved_model, elapsed,
        len(citations), grounding_used, retry_count,
    )

    return GroundedResearchResult(
        topic=topic,
        text=text,
        citations=citations,
        model=resolved_model,
        grounding_used=grounding_used,
        elapsed_s=elapsed,
        raw_response=raw,
    )


__all__ = [
    "AuthError",
    "Citation",
    "EmptyResponseError",
    "GroundedResearchResult",
    "GroundingFailedError",
    "RateLimitError",
    "TimeoutError",
    "UpstreamError",
    "format_citation",
    "format_citations_block",
    "grounded_research",
]
