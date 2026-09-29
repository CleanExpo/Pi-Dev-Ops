# REPORT-<YYYY-MM-DD>.md — template

Written to `_system/wiki-growth/`. The pilot edits the Approval column to `APPROVED`
before running apply mode.

```markdown
# Wiki Growth Report — <date>

## Run parameters
- Scope: <full vault | area | single note>
- Shortlist cap: 25 · Shortlisted: <n> · Batches: <n> × 5
- Dropped by cap (re-run to cover): <list or "none">
- Tiering: triage = Sonnet 5 via nexus; contested re-judgement = Opus 5; synthesis = Fable.
  Per-dispatch session-handoff omitted (read-only research).

## Inventory
| Target | Files | Shortlisted |
|---|---:|---:|
| Root specs | | |
| Sketches / Pitches / Grills / Personas | | |
| Wiki (marker-matched) | | |

## Disposition summary
| Disposition | Count |
|---|---:|

## Idea table
| # | Note | Idea (one line) | Disposition | Lane | Sceptic's why | High-stakes | Approval |
|--:|---|---|---|:--:|---|:--:|---|
| 1 | <path> | | | | | | PENDING |

## Contested rows (Opus re-judgement)
| # | First verdict | Opus verdict | Resolution |

## Conflicts and duplicates found across batches
- …

## Next safe action
Review the Idea table, set Approval to APPROVED on rows to act, then run
`/wiki-growth apply REPORT-<date>.md`.
```
