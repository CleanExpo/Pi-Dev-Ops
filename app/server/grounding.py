"""app/server/grounding.py — source-grounding primitive.

Stops generation-on-generation degradation: every derived artifact carries a
source anchor (back-pointer + content hash + TTL); reground() re-fetches the
primary source before the next generation, verifying hash + TTL and detecting
lineage cycles (the self-feeding-loop alarm). require_grounding() is the
enforced gate.

Pure functions; resolvers are injectable for tests. Spec:
docs/superpowers/specs/2026-06-21-grounding-primitive-design.md
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

FRESH = "FRESH"
DRIFTED = "DRIFTED"
STALE = "STALE"
MISSING = "MISSING"
CYCLE = "CYCLE"

DEFAULT_TTL_HOURS = 168

Resolver = Callable[[str], tuple[str, str]]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEME_RE = re.compile(r"^([a-z][a-z0-9+.\-]*)://")


class GroundingError(Exception):
    """Raised by require_grounding when an artifact is not FRESH."""


@dataclass
class GroundResult:
    status: str
    primary_text: str | None = None
    primary_uri: str | None = None
    chain: list[str] = field(default_factory=list)
    detail: str = ""


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _scheme(uri: str) -> str:
    m = _SCHEME_RE.match(uri or "")
    if not m:
        return "file"
    return "file" if m.group(1) == "file" else m.group(1)


def default_resolvers(repo_root: Path) -> dict[str, Resolver]:
    def file_res(uri: str) -> tuple[str, str]:
        rel = uri[len("file://"):] if uri.startswith("file://") else uri
        target = (repo_root / rel).resolve()
        if not target.is_relative_to(repo_root.resolve()):
            raise ValueError(f"path escapes repo root: {uri!r}")
        data = target.read_bytes()
        return data.decode("utf-8", errors="replace"), _sha256_hex(data)

    return {"file": file_res}


def _resolve(uri: str, resolvers: dict[str, Resolver]) -> tuple[str, str]:
    res = resolvers.get(_scheme(uri))
    if res is None:
        raise KeyError(f"no resolver for scheme of {uri!r}")
    return res(uri)


def record(
    *,
    primary_source: str,
    derived_from: str | list[str],
    parent_text: str,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    confidence: float | None = None,
    parent_chain: list[str] | None = None,
) -> dict:
    """Build a source-anchor dict for a derived artifact.

    parent_text is the immediate parent's current content, hashed for drift
    detection. parent_chain is the parent's own lineage; the returned chain
    appends this hop's immediate parent so reground() can detect cycles. The
    caller persists the returned dict (frontmatter for markdown, fenced block
    for ticket/JSONL bodies).
    """
    first_parent = derived_from if isinstance(derived_from, str) else derived_from[0]
    anchor: dict = {
        "primary_source": primary_source,
        "derived_from": derived_from,
        "source_sha256": _sha256_hex(parent_text.encode("utf-8")),
        "derived_at": _utcnow().isoformat(),
        "ttl_hours": ttl_hours,
        "chain": list(parent_chain or []) + [first_parent],
    }
    if confidence is not None:
        anchor["confidence"] = confidence
    return anchor


_ANCHOR_RE = re.compile(r"<!--\s*ground:anchor\s*(\{.*?\})\s*-->", re.DOTALL)
_SOURCE_LINK_RE = re.compile(r"Source:\s*\[[^\]]*\]\(([^)]+)\)")


def anchor_to_block(anchor: dict) -> str:
    """Serialize an anchor as an HTML comment (invisible in rendered Markdown)."""
    return f"<!-- ground:anchor {json.dumps(anchor, separators=(',', ':'))} -->"


def anchor_from_text(text: str) -> dict | None:
    """Extract an anchor from a body. Structured block wins; else prose-link
    fallback; else None."""
    m = _ANCHOR_RE.search(text or "")
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            log.warning("grounding: malformed anchor block ignored")
    link = _SOURCE_LINK_RE.search(text or "")
    if link:
        path = link.group(1).strip()
        return {"primary_source": path, "derived_from": path, "source_sha256": "", "chain": []}
    return None


def reground(
    artifact_uri: str,
    anchor: dict,
    *,
    resolvers: dict[str, Resolver] | None = None,
    repo_root: Path | None = None,
) -> GroundResult:
    """Re-fetch the primary source for a derived artifact and classify it.

    Returns a GroundResult whose status is one of FRESH/DRIFTED/STALE/
    MISSING/CYCLE (precedence in that order of severity).
    """
    repo_root = repo_root or _REPO_ROOT
    resolvers = resolvers or default_resolvers(repo_root)
    primary = anchor.get("primary_source") or ""
    derived_from = anchor.get("derived_from") or primary
    parents = [derived_from] if isinstance(derived_from, str) else list(derived_from)
    chain = list(anchor.get("chain") or [])

    # 1. CYCLE — artifact sourced from itself, or a repeated hop in its lineage.
    if artifact_uri in ([primary] + parents + chain) or len(set(chain)) != len(chain):
        return GroundResult(CYCLE, None, primary, chain, f"lineage revisits {artifact_uri!r}")

    # 2. MISSING — primary cannot be resolved.
    try:
        primary_text, _ = _resolve(primary, resolvers)
    except Exception as exc:  # noqa: BLE001 — any resolver failure means unreachable
        return GroundResult(MISSING, None, primary, chain, f"cannot resolve {primary!r}: {exc}")

    # 3. DRIFTED — immediate parent changed since derive (skip if no recorded sha).
    recorded = anchor.get("source_sha256") or ""
    if recorded:
        try:
            _, current = _resolve(parents[0], resolvers)
        except Exception as exc:  # noqa: BLE001
            return GroundResult(MISSING, primary_text, primary, chain,
                                f"cannot resolve parent {parents[0]!r}: {exc}")
        if current != recorded:
            return GroundResult(DRIFTED, primary_text, primary, chain,
                                f"parent {parents[0]!r} changed since derive")

    # 4. STALE — past TTL.
    if _is_stale(anchor):
        return GroundResult(STALE, primary_text, primary, chain, "past ttl")

    # 5. FRESH.
    return GroundResult(FRESH, primary_text, primary, chain, "ok")


def _is_stale(anchor: dict) -> bool:
    ttl = int(anchor.get("ttl_hours") or DEFAULT_TTL_HOURS)
    derived_at = anchor.get("derived_at")
    if not derived_at or ttl <= 0:
        return False
    try:
        ts = datetime.fromisoformat(derived_at)
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (_utcnow() - ts).total_seconds() / 3600 > ttl


def require_grounding(
    artifact_uri: str,
    anchor: dict,
    *,
    resolvers: dict[str, Resolver] | None = None,
    repo_root: Path | None = None,
    allow_ungrounded: bool = False,
) -> GroundResult:
    """Gate a generation step. Returns a FRESH GroundResult or raises
    GroundingError. allow_ungrounded downgrades the failure to a logged
    warning and returns the (non-FRESH) result."""
    result = reground(artifact_uri, anchor, resolvers=resolvers, repo_root=repo_root)
    if result.status == FRESH:
        return result
    if allow_ungrounded:
        log.warning("grounding: proceeding ungrounded for %s — %s: %s",
                    artifact_uri, result.status, result.detail)
        return result
    raise GroundingError(f"{artifact_uri}: {result.status} — {result.detail}")
