# The house manner (Pocock manner) — the shape every specialised skill carries

Distilled from Matt Pocock's `mattpocock/skills` repo and locked as the Library's body
standard after `grill-me` (the in-house exemplar — read it alongside this file). The four
gates in `SKILL.md` decide *what goes in* a skill; this file decides *what shape it takes*.
Sources: vault `Wiki/skills-architecture-audit-2026-05-15.md` §1,
`Wiki/research-mattpocock-code-patterns-2026-05-15.md` §2.

## Repo-level rules (partly enforced by the catalog already)

1. **One skill, one job.** A skill does one thing with a sharp verb name. If a step needs
   its own trigger phrase, it is a second skill — split, don't grow. No skill ships with an
   `-orchestrator` companion; composition happens through shared vocabulary and files, not
   dispatch layers.
2. **In the catalog or it doesn't exist.** No `status: draft/proposed` frontmatter; a skill
   is listed (README.md + index.md row if entry-point) or it lives in a quarantine bucket.
3. **Small, adaptable, composable, model-agnostic.** The skill must survive being run by a
   different model. No behaviour that only works because the current model infers it.
4. **Shared language.** Reuse the term the catalog already uses ("gate", "grill", "sketch",
   "appetite") before coining one; on collision, check `~/.claude/skills/CLAUDE.md` §Domain
   vocabulary first.

## Body shape — the section recipe

A specialised skill's body IS these sections, in this order (omit one only when it is
genuinely empty for that skill, not to save lines):

1. **When to invoke** — concrete trigger situations, including the negative trigger
   ("you are about to X without Y — stop and run this first").
2. **Core procedure** — numbered steps, marked **DO NOT DEVIATE** when order is
   load-bearing. Each step is an action with a checkable end, not advice.
3. **Output format** — the exact artefact: destination path, frontmatter, template block.
   A skill whose output is "a good answer" has no gate; give the output a shape.
4. **Calibration** — numbers, not vibes: expected duration, question counts, size bounds,
   and what over/under those bounds means ("<5 questions → the sketch wasn't fat-marker
   enough; >50 → break it into sub-sketches").
5. **What this skill is NOT** — disambiguation against the sibling skills a router could
   confuse it with, each with the pointer to the right one ("Not a code review — that's
   `/code-review`").
6. **Hard rules** — numbered, each countering one *observed* failure mode, stated with its
   reality ("Never ask >1 question per turn. Bundling is the dominant failure mode."). No
   rule for a failure nobody has hit.
7. **Provenance** — when adapted from external material, link the exact sources (file-level
   URLs, chapters). Unsourced adaptations rot; sourced ones can be re-derived.

## Behavioural rules baked into the procedure (not appended as advice)

- **Explore before asking.** If the codebase/vault can answer a question, answer it there —
  never ask the user something `grep` could answer. (Load-bearing; Matt's rule.)
- **Always take a position.** Every question, option list, or review finding carries a
  recommendation with a one-sentence rationale; the user overrides, never fills a blank.
- **Terminal states, not open threads.** Every branch the skill opens resolves to an explicit
  state (e.g. DECIDED / RABBIT HOLE / NO-GO); "TBD" is converted, never accepted.
- **Respect the context budget.** Per-turn output bounded; no preamble ritual.

## What NOT to copy from the source repo

- His flat 3-folder taxonomy — our catalog + index.md is the (already-built) equivalent at
  10× the skill count.
- `plugin.json` as a third catalog place — doesn't exist here yet; the operative rule is
  2-place (see `~/.claude/skills/CLAUDE.md`).

Retrofit rule: existing skills are brought to this shape **when touched** (authored, edited,
or reviewed through this standard) — never as a big-bang rewrite of the live catalog.
