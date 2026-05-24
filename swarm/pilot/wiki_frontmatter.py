"""Master pillar enum loader — reads [[master-plan-2b-by-2028-v3]] YAML frontmatter.

Per ADR 001 — wiki is source-of-truth for the pillar enum. 24h TTL + manual
invalidation hook for wiki-sync. PillarCanonicaliser calls load_master_pillars()
in __init__; long-lived processes call invalidate_cache() + re-instantiate on
wiki-sync events.

Cache invalidation contract: TTL 24h; call invalidate_cache() from wiki-sync
handler when master-plan-2b-by-2028-v3 changes. PillarCanonicaliser materialises
master set in __init__, so long-lived processes need invalidate_cache() PLUS
re-instantiation. Cadence-cron (Phase 5-6) instantiates per cycle, so 24h TTL
is sufficient there.
"""
import time
from pathlib import Path

import yaml

DEFAULT_PATH = (
    Path.home() / "2nd Brain" / "2nd Brain" / "Wiki" / "master-plan-2b-by-2028-v3.md"
)
TTL_SECONDS = 24 * 60 * 60
_cache: dict[str, tuple[float, list[str]]] = {}


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        raise RuntimeError("missing frontmatter — wiki page must start with '---'")
    end = text.find("\n---", 3)
    if end < 0:
        raise RuntimeError("unterminated frontmatter")
    return yaml.safe_load(text[3:end]) or {}


def load_master_pillars(path: Path | None = None) -> list[str]:
    p = Path(path) if path else DEFAULT_PATH
    key = str(p)
    now = time.time()
    cached = _cache.get(key)
    if cached and (now - cached[0]) < TTL_SECONDS:
        return list(cached[1])
    fm = _parse_frontmatter(p.read_text())
    pillars = fm.get("pillars")
    if not pillars or not isinstance(pillars, list):
        raise RuntimeError(f"missing or empty 'pillars' list in frontmatter at {p}")
    pillars = [str(x).strip() for x in pillars]
    _cache[key] = (now, pillars)
    return list(pillars)


def invalidate_cache() -> None:
    _cache.clear()
