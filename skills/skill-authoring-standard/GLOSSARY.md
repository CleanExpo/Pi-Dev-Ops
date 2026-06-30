# GLOSSARY — skill-authoring vocabulary

The domain model for the [`skill-authoring-standard`](SKILL.md) leading words. **Bold terms**
in any definition are themselves headings here. Each entry ends with `_Avoid_:` — the loose
synonyms that dilute it. Adapted from Matt Pocock's `writing-great-skills/GLOSSARY.md`.

## Predictability
The degree to which a skill makes the agent take the same _process_ every run — not produce
the same output. The root virtue every lever below serves; token cost and maintainability
are symptoms of it, not rivals.
_Avoid_: consistency, reliability, robustness, output-determinism

## Archetype
The shape a skill takes, which fixes its frontmatter: **command-skill** (user-invoked tool
the pilot fires deliberately), **agent-role** (a persona/gate the model or user invokes,
pinned to a model tier), or **plain-technique** (model-invoked know-how). Pick the archetype
before writing frontmatter; the schema follows from it. See
[`references/frontmatter-schema.md`](references/frontmatter-schema.md).
_Avoid_: type, kind, category, flavour

## Context load
The cost a **model-invoked** skill imposes on the agent's context window — its **description**,
always loaded, spending tokens and attention on every request. The brake on adding more
model-invoked skills. User-invoked skills pay zero context load.
_Avoid_: overhead, footprint, weight

## Cognitive load
The cost a **user-invoked** skill imposes on the pilot — one more thing to remember exists
and to know when to fire. Traded against context load; neither is free.
_Avoid_: mental burden, friction, effort

## Description
The frontmatter line that does a skill's invocation work. Model-invoked: write **WHEN-not-WHAT**
trigger phrasing ("Use when the user…"). User-invoked (`disable-model-invocation: true`):
a human-facing one-line summary, triggers stripped. Every word is **context load**, so it
earns harder pruning than the body.
_Avoid_: summary, blurb, title

## WHEN-not-WHAT
The rule that a **description** states the conditions that should trigger the skill, never a
summary of what it does or its model tier. "Use when the user asks to draft a SOW" — not
"Drafts a milestone SOW. Model: sonnet." Baking the workflow in makes the agent follow the
description instead of reading the skill.
_Avoid_: trigger-rule, when-clause

## Information hierarchy
The three rungs every piece of a skill sits on: **in-skill step** → **in-skill reference** →
**external reference**. Push material down as far as it will go so the top stays legible.
_Avoid_: layering, structure, organisation

## Context pointer
The worded link from `SKILL.md` to an **external reference** ("X are defined in [`FILE.md`](FILE.md);
look them up there"). Its _wording_, not its target, decides how reliably the agent reaches
the material — a must-have behind a weak pointer is a variance bug; fix the wording before
inlining.
_Avoid_: link, reference, import, include

## Progressive disclosure
Moving reference down the **information hierarchy** — out of `SKILL.md` into a co-located
`.md` reached by a **context pointer**, loaded only when the pointer fires. Protects the
hierarchy's legibility first; token saving is the second benefit.
_Avoid_: lazy-loading, chunking, paging

## Single source of truth
Each meaning — a template, definition, or rule — lives in exactly one authoritative file, so
changing the behaviour is a one-place edit. The cure for **duplication**.
_Avoid_: canonical-copy, master, primary

## Leading word
A word that anchors a region of behaviour in the fewest tokens by recruiting priors the model
already holds (*vertical slice*, *relentless*, *tight*). Put it in the skill; watch it
reappear in the reasoning trace. Borrow a pretrained word before coining one — a made-up word
recruits no priors.
_Avoid_: keyword, term, motif, phrase

## Leg work
The effort an agent invests in the step it is on. Agents under-invest when they can see the
final goal. Increase it by splitting a skill so the agent sees one step at a time.
_Avoid_: effort, work, diligence

## Completion criterion
The checkable, and where it matters exhaustive, condition that ends a step ("every modified
model accounted for", not "produce a change list"). A vague criterion invites **premature
completion**.
_Avoid_: done-condition, exit, definition-of-done

## Deletion test
The procedure for finding a **no-op**: delete a sentence and ask whether the agent would still
behave the same. If yes, it was a no-op — delete the whole sentence, don't trim words. Be
aggressive.
_Avoid_: review, audit, pass

## No-op _(failure mode)_
A line the model already obeys by default, so you pay load to say nothing. Model-relative, not
reader-relative: "write a detailed commit message" when the agent already does. A weak
**leading word** is a no-op; the fix is a stronger word, not more prose.
_Avoid_: filler, fluff, redundancy

## Sediment _(failure mode)_
Material that accumulates in a shared skill because no one feels brave enough to delete it —
often stale or relevant to only one **branch**. Fix by structure: move it to the branch that
needs it, or kill it. Includes filesystem sediment: backup dirs, committed venvs, nested repos
left in the live catalog.
_Avoid_: cruft, legacy, debris

## Duplication _(failure mode)_
The same reference or trigger stated in more than one place. Violates **single source of
truth**; costs tokens and drifts out of sync. A description with two triggers that rename one
**branch** is duplication.
_Avoid_: repetition, copy, redundancy

## Sprawl _(failure mode)_
A `SKILL.md` grown past what it needs — usually a symptom of **sediment**, **duplication**, or
un-disclosed reference. The 200-line soft cap is the tripwire.
_Avoid_: bloat, size, length

## Premature completion _(failure mode)_
The agent declaring a step done before doing the **leg work**, because it sees the goal ahead.
Cured by a sharp **completion criterion** or by splitting the skill to hide post-completion
steps.
_Avoid_: rushing, shortcutting, skipping
