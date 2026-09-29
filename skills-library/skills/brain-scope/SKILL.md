---
name: brain-scope
description: Scope a task by pulling the latest note from the user's Obsidian "2nd brain" vault, gather related context from the vault, run a client-friendly multiple-choice dialog with recommendations, and produce a plan/spec (no production code). Use when the user says "scope this", "brain-scope", "plan from my 2nd brain", "shape this note", or references a vault note that needs turning into a plan.
---

# Brain Scope

Turn a note from the user's Obsidian **2nd brain** vault into a scoped, client-ready plan/spec.

This skill **plans only — it never writes production code.** Its output is a spec document, plus
inline summary. Run it, hand the plan to the user, stop.

- **Vault (absolute, always):** `/Users/phillmcgurk/2nd-brain/`
- **Output (relative to the active project):** `docs/specs/YYYY-MM-DD-<slug>.md`

> The vault is an Obsidian-compatible markdown + git repo. Folders: `Sources/ Sketches/ Grills/
> Pitches/ Decisions/ Personas/ Outcomes/ Research/ Plans/ Wiki/ Ideas/`. Notes use YAML frontmatter
> (`type/status/tags/...`) and `NN-slug.md` naming (date-prefixed for `Sources/` and `Outcomes/`).

**Never read these — they are auto-generated / machine-written noise:** `.git/`,
`.agentic_nexus/`, `Backups/`, and `Outcomes/` logs. Exclude them from every search below.

Do **not** modify the vault's git repo, and do **not** modify any other git repo except to write the
single output spec file into the active project.

---

## Stage 1 — Select the task note

If the user passed an argument (a note name or path), resolve it to a file under the vault and use it
as "the task." Skip the menu.

Otherwise, list the ~5 most-recently-modified `.md` notes (excluding the noisy areas) and ask the
user which one is the task:

```bash
find /Users/phillmcgurk/2nd-brain -name '*.md' \
  -not -path '*/.git/*' -not -path '*/.agentic_nexus/*' \
  -not -path '*/Backups/*' -not -path '*/Outcomes/*' \
  -type f -exec stat -f '%m %N' {} \; | sort -rn | head -5
```

Present the results as a multiple-choice prompt (use **AskUserQuestion**), each option labelled with
the note's folder + filename and its modified time. Default-highlight the most recent as
"(Recommended)". The chosen note is **the task note** for the rest of this skill.

## Stage 2 — Gather context (VAULT ONLY)

Read the task note in full. Then build a context bundle **from the vault only** — never the open
web, never the active project's code. Pull related notes via three signals:

1. **Wikilinks** — follow every `[[wikilink]]` in the task note one hop out; resolve each to its file.
2. **Shared tags** — read the task note's `tags:` frontmatter; find other notes that share any tag.
3. **Keyword / title matches** — take the task note's title words and key nouns, and grep across the
   high-signal folders: `Wiki/ Research/ Decisions/ Pitches/ Sources/`.

Use `Grep`/`Glob` scoped to the vault and the same exclusions as Stage 1. Read the matched notes
(or the relevant sections). Then produce a **deduped, ranked context bundle**: drop duplicates, rank
by relevance to the task note (wikilink hits and ratified `Decisions/`/`Pitches/` rank highest), and
keep a short note of why each item is included. This bundle is the evidence base for Stages 3–4.

## Stage 3 — Client-friendly dialog (ONE round)

Run **exactly one** multiple-choice round using **AskUserQuestion**. Frame questions in plain,
client-friendly language (no jargon). Cover, in this single round:

- **Scope** — how much of the task to take on (thin slice vs. full build).
- **Approach** — the main implementation/strategy fork.
- **Any decisive fork** — the one open question that most changes the plan (often a `rabbit_hole`
  surfaced in the note or its grill).

Each option must be **tailored to this specific note** (use what you read in Stages 1–2 — don't ask
generic questions), and the option you'd advise must be clearly marked **"(Recommended)"** with a
one-line reason. Goal: get to the **best result first time**, so the recommendations should reflect
the ratified `Decisions/` and `Pitches/` context you gathered.

## Stage 4 — Produce the plan/spec

Resolve the **active project root** at runtime:

```bash
git rev-parse --show-toplevel 2>/dev/null || pwd
```

Write the spec to `<project-root>/docs/specs/YYYY-MM-DD-<slug>.md` (create `docs/specs/` if needed;
`<slug>` = the task note's slug; `YYYY-MM-DD` = today). Then **also print the plan inline** in your
reply.

The spec must contain:

- **Title + source** — task note's title and its absolute vault path.
- **Context** — the ranked bundle from Stage 2 (link each item by relative vault path).
- **Decisions** — the user's Stage-3 answers, with the recommended option noted.
- **Scope** — what's in, and an explicit **Out of scope / No-gos** list.
- **Plan** — ordered steps / thinnest end-to-end slice first. Reference vault notes by relative path
  so a future agent can re-load context.
- **Open questions / rabbit holes** — anything still unresolved. Don't fake-answer; write the
  question.

Remember: **no production code.** This file is a plan. End by telling the user the path written and
the headline of the plan.

---

## Guardrails

- Vault path is **always** the absolute `/Users/phillmcgurk/2nd-brain/`; the output path is **always**
  relative to the active project (resolved via `git rev-parse --show-toplevel`, fall back to cwd).
- Read only `.md` files; exclude `.git/`, `.agentic_nexus/`, `Backups/`, `Outcomes/` everywhere.
- One dialog round only — don't drip-feed questions.
- Plan, don't build. The only file you write is the spec.
