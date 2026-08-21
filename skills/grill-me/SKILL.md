---
name: grill-me
description: Run a relentless one-question-at-a-time interview on a sketch or plan until every branch of the decision tree resolves into either a decision, a rabbit hole, or an explicit no-go. Use when the user wants to stress-test a fat-marker sketch before any code is written, or asks to be "grilled", "interviewed", or to "stress-test" a plan. Adapted from Matt Pocock's /grill-me (mattpocock/skills) and combined with Shape Up's appetite + fidelity discipline.
---

# /grill-me — Nexus shaping interviewer

## When to invoke

- User just produced (or asked you to produce) a fat-marker sketch in the active Obsidian vault's `Sketches/`.
- User says "grill me", "interview me", "stress-test this plan", "find the rabbit holes".
- You are about to write code AND there is no corresponding grill transcript in the active vault's sibling `Grills/`. Stop and grill first.

**Routing rule (Pocock, 2026-07):** if the work targets an EXISTING codebase with established
domain language, route to `grill-with-docs` instead — same interview, plus the ubiquitous-language
glossary and ADR context. grill-me is for greenfield/no-codebase shaping. See
[[pocock-beyond-grill-me-for-coding-2026-07-14-ingest]].

**Fidelity gate (before Q1):** confirm the target is grillable — a fat-marker sketch with real
unknowns. If the scope is already specifiable, skip the grill and go straight to spec/pitch; if
it's vague vibes, sketch first. If the scope spans multiple components, pre-decompose and grill
one component per session.

## Core procedure (DO NOT DEVIATE)

1. **Read the sketch.** Locate the relevant file in the real vault's `Sketches/` directory; do not assume the repository contains a `2nd-brain/` folder. If none exists, refuse to grill and produce a sketch first. The sketch is the input — you cannot grill an idea that hasn't been sketched.
2. **Identify the decision tree.** Every place in the sketch that says "TBD", every connection line without a defined protocol, every affordance without a defined trigger, every rabbit hole — these are the leaves to resolve.
3. **Walk the tree dependency-first.** A decision that gates other decisions is asked first. Never ask a leaf question before its parent is resolved.
4. **Ask one question at a time.** Never bundle. Never list 5 things and ask the user to address them. One question per turn.
5. **Recommend an answer.** Every question carries your best recommendation with a one-sentence rationale. The user can take the recommendation by saying "default" or override with their own answer.
6. **Convert ambiguity into one of three terminal states** for each branch:
   - **DECIDED** — the user gave an answer (or accepted your recommendation).
   - **RABBIT HOLE** — known unknown the user explicitly defers ("decide later"). Goes into the sketch's `RABBIT HOLES:` section.
   - **NO-GO** — explicit scope exclusion ("not doing that"). Goes into the sketch's `NO-GOS:` section.
7. **If a question can be answered by exploring the codebase, explore the codebase instead.** Don't ask the user something `grep` could answer. (This rule is Matt's, and it's load-bearing.)
8. **Stop when the tree is fully resolved.** Every leaf is DECIDED, RABBIT HOLE, or NO-GO. Then write the transcript.

## Governed session boundary — run it through the controller

When `senior-harness` is available, run the grill through its controller so the sketch is
digest-bound and the confirmation is verbatim. The controller's receipt grants **no**
implementation authority; delivery is a separate governed phase.

- Controller: `skills/senior-harness/scripts/grill_session.py`
- Contract: `skills/senior-harness/references/grill-contract.md`

Every command takes `--state <session.json>`. `S` below is that path.

**Preflight — the refusals `start` can raise. Each returns `status: invalid`:**

1. `--objective` must be non-empty.
2. `--sketch` must name a **real, existing file** *and* sit under a `Sketches/` root.
3. `--transcript` must be a `.md` file under the **sibling `Grills/` root** — that is
   `<parent-of-Sketches>/Grills/`, not any directory named `Grills`. Any Markdown filename below
   that root is accepted; `NN-<slug>.md` is our convention, not a controller rule.
4. `--state` must live below `$SENIOR_HARNESS_STATE_DIR` when that is set, otherwise below
   `~/.local/state/senior-harness/`, **and must end in `.json`** (use `grills/<slug>.json`). The
   controller keeps session state external to the checkout.
5. `start` **refuses to replace an existing state file** — choose a fresh path, or remove the old
   one deliberately.
6. `--decision-tree` must be a JSON **object** wrapping the leaves, not a bare array, and the
   tree must be non-empty and acyclic:

```json
{"decision_tree": [
  {"leaf_id": "store", "kind": "human-decision", "question": "Which store?",
   "recommendation": "Postgres", "rationale": "already operated here", "depends_on": []},
  {"leaf_id": "schema", "kind": "evidence-fact", "question": "Does a sessions table exist?",
   "depends_on": ["store"]}
]}
```

Leaf rules: `kind` is `human-decision` or `evidence-fact`. A `human-decision` leaf **requires**
`recommendation` and `rationale` (hard rule 4, mechanised). An `evidence-fact` leaf **must not**
carry either — those are answered from sources, not opinion. `depends_on` holds leaf ids and
drives the dependency-first ordering in step 3.

| Step | Command |
| --- | --- |
| Open the session | `start --state S --objective "<goal>" --sketch <sketch.md> --decision-tree <tree.json> --transcript <out.md>` |
| Inspect current leaf | `show --state S` |
| Check integrity | `validate --state S` |
| Answer from repo evidence | `evidence --state S --answer "<finding>" --sources <evidence.json>` |
| Record a human answer | `answer --state S --answer "<verbatim>" --resolution DECIDED\|RABBIT_HOLE\|NO_GO` |
| Lock shared understanding | `confirm --state S --phrase "I confirm this is our shared understanding."` |
| Write buffered outputs | `materialize --state S` |

`--sources` takes **one JSON object file**, not a list of paths. Every item needs a non-empty
`source_id` and a `source_digest` of exactly `sha256:` plus 64 lower-case hex characters:

```json
{"evidence": [
  {"source_id": "app/server/sessions.py", "source_digest": "sha256:<64-lowercase-hex>"}
]}
```

An `evidence` response is accepted **only while the session is in `awaiting-evidence`**.

What the controller enforces so you do not have to:

1. The sketch path and its digest are recorded at `start` and written into the receipt. **The CLI
   does not re-hash the sketch on later transitions** — editing it mid-session is not detected, so
   treat sketch stability as your discipline, not a guarantee the controller provides.
2. `evidence` is the mechanised form of hard rule 7 below: repository facts are answered from
   named, digest-bound sources, never asked of the founder.
3. Resolutions are exactly `DECIDED`, `RABBIT_HOLE`, `NO_GO`. Nothing else is accepted.
4. The transcript and any glossary/ADR updates stay **buffered** until `confirm` succeeds with
   the phrase verbatim (`I confirm this is our shared understanding.`). A near-miss does not confirm.
5. `materialize` is the only command that writes the **transcript** — `start`, `evidence`,
   `answer` and `confirm` each persist control state under the external state root. `materialize`
   refuses before confirmation, refuses if the content digest differs from the confirmed receipt,
   and creates the transcript exclusively, so it will not overwrite an existing target.

## Output format

Two different things share this name — do not confuse them.

**What `materialize` emits** (the receipt-bound transcript, generated by the controller). It is
written to the explicit `--transcript` target under the sibling `Grills/` root, and its shape is
fixed:

```markdown
---
type: grill
session_id: <digest>
sketch: <absolute resolved path>
sketch_sha256: sha256:<64-hex>
status: resolved
---

# Grill transcript

**Objective:** <objective>

## Q1: <question>
**My recommendation:** <rec>        # human-decision leaves only
**Rationale:** <rationale>          # human-decision leaves only
**Evidence sources:** <source ids>  # evidence-fact leaves only
**Answer (verbatim):** <answer>
**Resolution:** DECIDED | RABBIT_HOLE | NO_GO

## Domain updates
...
```

Note what it does **not** carry: no `component`, no `created`, no in-progress status, no
final-state buckets, no appetite, and no pitch next-step. `status` is always `resolved` — the
transcript only exists after confirmation.

**The hand-authored convention below** is our own upstream sketch/vault format, used when running
a grill without the controller. It is a template for humans, not the controller's output contract:

```markdown
---
type: grill
component: <slug matching the sketch>
sketch: ../Sketches/NN-<slug>.md
status: in-progress | resolved
created: YYYY-MM-DD
---

# Grill transcript — <component>

## Q1: <one-line question>
**My recommendation:** <one sentence + rationale>
**Phill's answer:** <verbatim>
**Resolution:** DECIDED | RABBIT HOLE | NO-GO

## Q2: ...

---

## Final state

**Decided:**
- ...

**Rabbit holes (to be revisited):**
- ...

**No-gos (explicitly excluded):**
- ...

**Appetite (Shape Up time budget):** 1d | 3d | 1w | 2w | 6w

**Next step:** promote to `Pitches/NN-<slug>.md`
```

## Pacing

- Sessions typically run 30-60 minutes / 15-50 questions (per Matt Pocock).
- A grill that resolves in <5 questions means the sketch wasn't fat-marker enough — go back and re-sketch with more abstraction.
- A grill that's stuck >50 questions means the sketch is too big — break it into sub-sketches.

## What grill-me is NOT

- **Not a code review.** That's `/code-review`.
- **Not a PRD writer.** The PRD/pitch is downstream — only after the grill resolves.
- **Not a brainstorm.** Brainstorm produces options; grill picks between them.
- **Not optional.** If you're tempted to skip the grill because you "know what to build," that's exactly when you most need it.

## Hard rules

1. **Never ask >1 question per turn.** Bundling is the dominant failure mode.
2. **Never accept "TBD" without a follow-up.** If the user says "TBD," ask "should this be a RABBIT HOLE (defer) or a NO-GO (exclude)?"
3. **Never write code during a grill.** Code is downstream. The grill's only output is the transcript markdown.
4. **Always recommend an answer.** "I don't know" is not a valid recommendation. Take a position, then let the user override.
5. **Respect context budget.** The user has a token ceiling. Long-winded preambles burn it. Each Q+A should fit in <300 tokens of agent output.
6. **Stay out of the dumb zone.** Run grills on a frontier model and keep the session under ~120k tokens of context; past that, question quality degrades. Never `/clear` (or abandon the session) before the transcript is written — the grill's value lives in the transcript, not the chat.
7. **Prototype what can't be answered in words.** If a question only resolves by seeing something, pause the grill, produce a throwaway prototype, and boomerang back with the answer.

## Provenance

Adapted from:
- [mattpocock/skills /grill-me SKILL.md](https://github.com/mattpocock/skills/blob/main/skills/productivity/grill-me/SKILL.md)
- 2026-07-14 corrections from Pocock's "9 Things People Get Wrong With My /grill-* skills" and "I stopped using /grill-me for coding" — vault pages [[pocock-grill-skills-9-mistakes-2026-07-14-ingest]], [[pocock-beyond-grill-me-for-coding-2026-07-14-ingest]]
- [Shape Up — Chapter 4: Find the Elements](https://basecamp.com/shapeup/1.3-chapter-04) (fat marker sketch + breadboarding)
- [Shape Up — Chapter 3: Set Boundaries](https://basecamp.com/shapeup/1.2-chapter-03) (appetite + fidelity discipline)
