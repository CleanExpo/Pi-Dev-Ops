---
name: wiki-lint
description: Weekly health check for the Brain-1 wiki. Finds orphan pages, missing cross-refs, stale claims, and contradictions. Fixes orphans and cross-refs automatically; flags stale/contradictions for founder review. Run every Saturday or manually with "lint the wiki".
owner_role: Curator
status: wave-5
---

# wiki-lint

Keeps the compounding wiki honest. A wiki with stale facts or silent contradictions is worse than no wiki.

## When to invoke

- Weekly cron (Saturdays) via `swarm/orchestrator.py`
- Manually: operator says "lint the wiki" or "check the wiki"

## Four checks

| Check | Method | Auto-fix? |
|---|---|---|
| **Orphans** — pages in `Wiki/` not listed in `index.md` | Python (glob vs index parse) | Yes — adds to index under `## Orphaned` |
| **Missing cross-refs** — page mentions a wiki topic but uses plain text, not `[[link]]` | Python (slug matching) | Yes — wraps plain mentions in `[[...]]` |
| **Stale claims** — dates in page content older than decay threshold | Python (regex date extraction) | No — flagged in report |
| **Contradictions** — two pages assert different values for the same fact | LLM call (single pass over all pages) | No — flagged in report |

## Decay thresholds

| Topic class | Stale after |
|---|---|
| Market data, competitor positioning | 30 days |
| Pricing, financial metrics | 90 days |
| Regulatory, compliance | 365 days |
| General operational facts | 180 days |

The `updated:` frontmatter date is the staleness signal. A page not updated in >180 days is flagged regardless of content.

## Output schema

```json
{
  "orphans_fixed": ["new-page.md"],
  "cross_refs_fixed": [{"page": "ccw.md", "replaced": 2}],
  "stale_pages": [{"page": "ccw.md", "last_updated": "2025-11-01", "days_old": 188}],
  "contradictions": [{"pages": ["ccw.md", "businesses-overview.md"], "fact": "CCW contract value", "detail": "..."}],
  "log_entry": "2026-05-08 | lint | 0 orphans, 1 cross-ref, 0 stale, 0 contradictions",
  "clean": true
}
```

`clean: true` means no issues found or remaining after auto-fixes.

## Python entry point

```python
from swarm.wiki_lint import lint

report = lint()
print(report.log_entry)
```

## Safety

- Auto-fixes are conservative — orphan addition and cross-ref wrapping only. Never deletes content.
- Contradiction and stale flags go to the report only; founder decides what to do.
- Appends to `Wiki/log.md` after every run.

## Verification

```python
from swarm.wiki_lint import lint
report = lint()
assert report.log_entry.startswith("20")
assert isinstance(report.clean, bool)
```

## References

- Wiki schema: `~/2nd Brain/2nd Brain/CLAUDE.md`
- Config: `swarm/config.py` → `BRAIN1_WIKI_DIR`
- Companion skills: `wiki-ingest` (Wave 5), `wiki-query` (Wave 5)
