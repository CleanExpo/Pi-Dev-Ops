---
name: wiki-growth
description: Senior-review-board audit of the 2nd Brain vault — challenge shortlisted ideas, assign dispositions, route survivors to storm/spm/skill-authoring. Writes only inside its _system/wiki-growth/ sandbox.
argument-hint: "<scan [area or note path] | apply REPORT-YYYY-MM-DD.md>"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, LS, Bash, Agent, Write
---

# wiki-growth — challenge the vault, route the survivors

A thin router, not an engine. It walks the vault, runs each shortlisted idea through the
review-board rubric, and dispatches survivors to the skills that already own the downstream
work: `storm` (source-backed strengthening), `spm` (idea → spec), `skill-authoring-standard`
(idea → skill), `marketing-orchestrator` (idea → marketing asset), all via the `nexus`
wrapper for sub-tier dispatch. Never re-encode those skills' logic — invoke them.

**Boundary vs `wiki-ingest`:** ingest pulls new session learnings *in*; wiki-growth
audits, challenges, and grows what is *already there*. No overlap.

## Vault ground truth

Vault root: `~/2nd Brain/2nd Brain/`. Idea-bearing scan targets, in priority order:

1. Root-level spec/blueprint `*.md` (≈40 files — `AGENTIC_*`, `NEXUS_*`, `*_SPEC.md`, …)
2. `Sketches/`, `Pitches/`, `Grills/`, `Personas/`
3. `Wiki/` (≈455 notes) — only pages Grep-matching idea markers
   (`TODO|PROPOSAL|IDEA|Plan:|Next step|should we|could build`)

**Excluded:** `Sources/` (evidence, not ideas), `Templates/`, `outputs/`, `process/`,
`sprint/`, dot-dirs, `log.md`, `index.md` files.

## Hard write-gate (both modes)

The ONLY writable path is the sandbox `~/2nd Brain/2nd Brain/_system/wiki-growth/`
(create on first run). Never edit, move, or delete a live vault page in v1 — apply mode
stages drafts in the sandbox; promotion out of it is a manual act by the pilot.

## Mode: scan (default)

`/wiki-growth` or `/wiki-growth scan [area or note path]` — read-only except the report.

1. **Inventory** — Glob the scan targets; collect path, title, first heading, mtime. No
   full-file reads. — *Done when: an inventory count per target exists for the report.*
2. **Shortlist** — cap at **25 ideas per run** (an argument narrows to one area or note).
   Priority: root specs and Sketches/Pitches first, then marker-matching Wiki pages,
   newest-modified first. State in the report exactly what the cap dropped — no silent
   truncation. — *Done when: shortlist ≤25 with the drop-list recorded.*
3. **Batch triage** — split the shortlist into batches of 5. One parallel subagent per
   batch, each dispatch wrapped per the `nexus` skill (tier ladder below). Each subagent
   reads only its 5 notes, answers the review rubric per idea (rubric and the 11
   disposition labels are defined in [`references/review-rubric.md`](references/review-rubric.md);
   the subagent prompt must inline the rubric questions), and returns structured rows:
   `{note path, one-line idea, rubric verdicts, disposition, evidence/why, high-stakes flag}`.
   The lane column is derived at synthesis from the routing table, never by the subagent.
   — *Done when: every shortlisted idea has a returned row.*
4. **Synthesise** (this session, not a subagent) — merge batches, dedupe ideas that are the
   same proposal in different notes (mark the extras `Merge`), flag conflicts between
   batches rather than silently resolving, and escalate any *contested or high-stakes* row
   (spend, prod change, new build) to a single Opus 4.8 re-judgement via `nexus`.
   — *Done when: no duplicate rows and every contested row carries a second verdict.*
5. **Report** — fill [`references/report-template.md`](references/report-template.md) and
   write it to `_system/wiki-growth/REPORT-<YYYY-MM-DD>.md`. End the turn with the
   disposition counts and: `Scan complete. Next safe action: review the report, mark rows
   APPROVED, then run /wiki-growth apply REPORT-<date>.md.`

## Mode: apply

`/wiki-growth apply REPORT-<date>.md` — acts ONLY on rows the pilot marked `APPROVED`.

1. Read the named report from the sandbox; collect approved rows. Zero approved rows →
   say so and stop. — *Done when: the approved set is listed back before any action.*
2. Route each approved row by its lane — the disposition→lane→skill map is in
   [`references/routing-table.md`](references/routing-table.md); look it up there. All
   outputs land in `_system/wiki-growth/drafts/<note-slug>/`, nothing else.
3. Lane C (promote) never authorises a build: its output is a spec/skill/asset **draft**,
   and any implementation still requires a separate `/judge` real-100/100 pass plus
   explicit user approval, per the judge hard line.
4. Close with a manifest of drafts written and the promotion instruction (pilot moves
   approved drafts out of the sandbox by hand). — *Done when: every approved row maps to
   a draft file or a stated skip reason.*

## Tier ladder (caller-side, per nexus step 4)

- **Haiku 4.5** — none in v1 (inventory is Glob/Grep, cheaper than any dispatch).
- **Sonnet 5** — default for batch-triage subagents (clear rubric, known pattern).
- **Opus 4.8** — single-idea re-judgement of contested/high-stakes rows.
- **Fable (this session)** — synthesis, dedupe, conflict calls, the report itself.

Triage dispatches are pure read-only research: per the nexus skill's own step 7, the
per-dispatch `session-handoff` is omitted — state that omission once in the report.
