# Improvement Proposal: Persistence

**Generated:** 2026-04-10  
**Source:** lessons.jsonl — 2 entries (1 warnings)  
**Proposed action:** Add a CLAUDE.md section  
**Target:** CLAUDE.md section: `## Persistence Guidelines`

## Recurring Lessons (2 occurrences)

- ⚠️ **[architecture-review]** _sessions is an in-memory dict — any server restart loses all running sessions. Always persist status to disk atomically after every state change.
- ℹ️ **[architecture-review]** Use write-to-.tmp-then-os.replace() for JSON file writes. os.replace() is atomic on NTFS and POSIX — a crash mid-write leaves the old file intact, not a corrupt half-written one.

## Proposed Content

Add the following section to CLAUDE.md:

```markdown
## Persistence Guidelines

- _sessions is an in-memory dict — any server restart loses all running sessions. Always persist status to disk atomically after every state change.
- Use write-to-.tmp-then-os.replace() for JSON file writes. os.replace() is atomic on NTFS and POSIX — a crash mid-write leaves the old file intact, not a corrupt half-written one.
```

## Review Required

This proposal was auto-generated. A human must review and apply it.
Close this Linear ticket when applied or explicitly rejected.