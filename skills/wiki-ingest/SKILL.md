---
name: wiki-ingest
description: Write a research finding, Board session output, or Margot insight back into the Brain-1 wiki. Updates existing pages in place, creates new pages if warranted, appends to log.md, and re-uploads changed files to the Gemini corpus. Use after any research session, Board deliberation, or when the operator says "save this to the wiki".
owner_role: Curator
status: wave-5
---

# wiki-ingest

Compounding flywheel: every valuable synthesis writes back to the wiki so the next Margot session starts smarter.

## When to invoke

| Trigger | Source type |
|---|---|
| Margot turn with `research_called=True` | `"research"` |
| Board deliberation produces minutes | `"board"` |
| `[BOARD-TRIGGER]` sentinel fired in a Margot turn | `"board_trigger"` |
| Operator says "save this to the wiki" / "remember this" | `"manual"` |

Do NOT invoke on every Margot turn — only when new facts, decisions, or synthesis are worth preserving across sessions.

## Algorithm

1. Load `Wiki/index.md` — the page map.
2. **Identify targets.** LLM call: given the finding and the index, name ≤5 existing pages to update. If the finding doesn't fit any existing page, name one new page to create (slug + one-line description).
3. **Update each target page.** For each page: read current content → LLM merge call → write back. Rule: add, never delete. If a fact changes, update it and note the date. Preserve all existing cross-refs.
4. **Create new page (if needed).** Write the new page with correct frontmatter (`type: wiki`, `updated: YYYY-MM-DD`). Add it to `Wiki/index.md` under the correct heading.
5. **Log.** Append to `Wiki/log.md`: `YYYY-MM-DD | ingest | pages affected | one-line summary`.
6. **Corpus re-upload.** Re-upload each changed file to the Gemini File Search store via `swarm/wiki_ingest.py`. Failure is non-fatal — local wiki is the source of truth.

Cap: touch ≤10 pages per ingest. If finding is too broad, split into multiple ingests.

## Input schema

```json
{
  "finding": "...the text to ingest...",
  "source_type": "research" | "board" | "board_trigger" | "manual",
  "topic": "optional short label for log.md",
  "turn_id": "optional — links back to Margot turn or Board session"
}
```

## Output schema

```json
{
  "status": "ok" | "error",
  "pages_updated": ["founder.md", "ccw.md"],
  "pages_created": [],
  "log_entry": "2026-05-08 | ingest | ...",
  "corpus_synced": true,
  "error": null
}
```

## Content rules

- Every sentence carries information. No filler.
- Dates: always absolute (ISO-8601). Never "recently" or "last quarter".
- Numbers: always sourced. If unverified, mark `[unverified]`.
- Cross-refs: use `[[page-slug]]` when another wiki page is relevant. Add them — don't skip them.
- Contradictions: if the finding contradicts an existing wiki claim, overwrite the old claim and add a note: `<!-- updated YYYY-MM-DD: previously said X -->` inline.

## Python entry point

```python
from swarm.wiki_ingest import ingest

result = ingest(
    finding="...",
    source_type="research",
    topic="CCW churn risk Q2",
)
```

## Safety

- Read wiki dir from `config.BRAIN1_WIKI_DIR` — never hardcode paths.
- Corpus re-upload uses the same Gemini key as Margot — reads `~/.margot/gemini-api-key.txt` or `GEMINI_API_KEY` env. Failure logs WARN; never raises.
- Kill-switch: if `TAO_SWARM_ENABLED=0`, skip corpus re-upload but still write local files. Local wiki is always updated regardless of kill-switch.
- PII: if finding contains personal data (names + contact details), log a warning and skip corpus upload. Local write still proceeds.

## Verification

```python
from swarm.wiki_ingest import ingest
result = ingest(
    finding="CCW signed a 12-month SaaS contract at $2,400/year on 2026-05-08. Point-of-contact is Sarah Chen, ops@ccw.com.au.",
    source_type="manual",
    topic="CCW contract confirmed",
)
assert result["status"] == "ok"
assert "ccw.md" in result["pages_updated"]
assert "2026-05-08" in result["log_entry"]
```

## References

- Wiki schema layer: `~/2nd Brain/2nd Brain/CLAUDE.md`
- Config: `swarm/config.py` → `BRAIN1_WIKI_DIR`, `MARGOT_FILE_SEARCH_STORE`
- Corpus provisioning: `scripts/provision_wiki_corpus.py`
- Companion skills: `wiki-query` (Wave 5), `wiki-lint` (Wave 5)
