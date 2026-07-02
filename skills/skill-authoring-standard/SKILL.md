---
name: skill-authoring-standard
description: Use when creating, editing, reviewing, or generating any skill — a SKILL.md, skill frontmatter, or a skill-foundation packet. Load BEFORE writing the skill so the four gates and frontmatter schema apply from the first line.
argument-hint: "<skill name/path to review, or the idea for a new skill>"
allowed-tools: Read, Grep, Glob, LS, Bash
---

# skill-authoring-standard — design every skill the same way

The Library-native standard for writing and reviewing skills. It makes a skill **predictable**
— the agent takes the same _process_ every run. Four gates: **Trigger → Structure → Steering →
Pruning**, plus the canonical frontmatter schema and the no-bloat `.md` rule.

**Prerequisite, not duplicated here:** `superpowers:writing-skills` owns TDD-for-skills
(RED→GREEN→REFACTOR) and Claude-search-optimisation. Invoke it for the *process of building*;
this skill is the *Library layer* on top — the frontmatter schema, archetypes, and the
`references/`-only design-element architecture it does not hold.

**Bold terms** are defined in [`GLOSSARY.md`](GLOSSARY.md); look them up there.

## When to invoke
Before creating a new skill, before editing an existing one, or to review a skill against the
standard. With a skill path → run the checklist and return findings + the corrected
frontmatter. With an idea → walk the four gates to design it.

## The four gates

### 1. Trigger — invocation and frontmatter
Pick the **Archetype**: **command-skill** (pilot fires it), **agent-role** (persona/gate on a
pinned model), or **plain-technique** (model reaches it). The archetype fixes the frontmatter —
read [`references/frontmatter-schema.md`](references/frontmatter-schema.md) and copy the
matching block. Default to user-invoked (`disable-model-invocation: true`, zero **context
load**); go model-invoked only when the agent or another skill must reach it autonomously, and
pay for it with a **WHEN-not-WHAT** **description**.
- **Completion criterion:** frontmatter matches the schema for the chosen archetype; no banned
  fields; description carries triggers (or one human line) only.

### 2. Structure — the information hierarchy
Place every element on the **information hierarchy**: in-skill step → in-skill reference →
external reference. Keep `SKILL.md` small; push branch-only or large (>~150-line) reference
into `references/` behind a worded **context pointer**. Each step ends on a checkable
**completion criterion**.
- **Completion criterion:** `SKILL.md` ≤ 200 lines; no branch-only reference inlined; every
  step has a checkable end condition.

### 3. Design elements — pulled efficiently, no cache/bloat
This is the structural discipline that keeps the catalog clean:
- External reference lives **only** in `references/`. Never a session-scoped symlink, a
  committed venv, a nested plugin repo, or a backup dir in the live skill folder.
- Name each external file for its contents; reach it by a **context pointer** whose wording
  states the load condition ("X are defined in [`FILE.md`](FILE.md); look them up there"). Fix
  pointer wording before inlining.
- **Single source of truth:** no template, definition, or trigger duplicated across files or
  steps (**duplication**).
- For design-heavy skills, defer element ownership to the four-layer boundary
  ([[feedback-design-md-boundary]]) — don't re-encode design/motion tokens.
- **Completion criterion:** every reference file is in `references/`, content-named,
  single-sourced, and pointer-reached.

### 4. Steering and Pruning
**Steering:** condense restated triads into a **leading word** (borrow a pretrained word before
coining). Where a step needs more **leg work**, split the skill — by sequence (hide
post-completion steps) or by invocation (a distinct leading word worth its context load).
**Pruning:** keep a **single source of truth**, run a relevance pass to clear **sediment**, then
run the **deletion test** sentence-by-sentence and cut every **no-op** (delete whole sentences,
be aggressive).
- **Completion criterion:** leading words recur in the reasoning trace; no sediment, no
  no-ops, no **premature-completion** bait survive a read-through.

## Reviewing a skill
Run [`references/review-checklist.md`](references/review-checklist.md) top to bottom — it is the
PASS/FAIL gate covering all four gates plus catalog placement. Return each FAIL with the
offending line and the fix.

## Catalog placement (operative 2-place rule)
The documented 3-place rule is aspirational — place #3 (`.claude-plugin/plugin.json`) and the
bucket `README.md`s do not exist. Operative reality: list the skill in
`~/.claude/skills/README.md`, and add one `index.md` row if it is an entry point. See
`~/.claude/skills/CLAUDE.md`.

---
Authoring complete when the **review-checklist** passes top to bottom and the skill is placed.
