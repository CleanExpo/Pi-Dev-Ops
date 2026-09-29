---
name: capture-intent
description: Stage 1 of Anthropic's AI-Native SDLC Playbook ("Capture as intent.md") and the required front door to gstack /plan-ceo-review. Turns a founder's raw thought — typed into Mission Control's Capture Intent box, pasted, or dictated here — into an accepted intent.md (problem, proposed outcome, affected users and systems, constraints, open questions), stages it where /plan-ceo-review reads its design doc, then runs the CEO review. Use when the user says "capture intent", "intent.md", "I have an idea", "brain dump", pastes an intent from Mission Control, or asks for /plan-ceo-review / a CEO review of a plan with no accepted intent yet.
---

# /capture-intent — the intent before the CEO review

**Source method.** Anthropic Academy, AI-Native SDLC Playbook, lesson "Capture as intent.md"
(`academy.claude.com/courses/ai-native-sdlc-playbook/capture-intent`), plus the vault
note `2nd Brain/Sources/Claude Code The Complete AI-Native SDLC Guide.md` (Stage 1, L71–83).
Five steps, in order, none skipped:

1. **Ideation** — the originator describes the problem in their own words.
2. **Refinement** — Claude asks the questions an analyst would ask until the idea is concrete.
3. **Structure** — Claude writes `intent.md` in the template below.
4. **Human review** — the originator corrects anything Claude misunderstood.
5. **Record** — the accepted intent is stored with author and timestamp; only then does
   the next stage (here: `/plan-ceo-review`) pick it up.

**Why this skill exists.** `gstack-plan-ceo-review` is pinned upstream code and must not be
edited. Its "Design doc check" already reads the newest
`~/.gstack/projects/<slug>/*-design-*.md` as "the problem, constraints and approach source
of truth". This skill puts the accepted intent exactly there, proves the CEO review's own
lookup finds it, then invokes the review. No upstream file changes.

## The template (exact headings — the stager refuses anything else)

```markdown
---
status: accepted
author: <originator email>
created: <ISO timestamp>
task: <Mission Control task id, or "cli">
---
# Intent: <one-line title>

## Problem
## Proposed outcome
## Affected users and systems
## Constraints
## Open questions
```

Every section must have content. "None known" is content; a blank section is not.
Plain prose only: code blocks (at any indent) and any line that STARTS with an HTML tag or
comment are refused. Mid-sentence text such as "notify <customer>" or "cost <AUD 500" and
<https://...> links are fine.
`Open questions` is where honest uncertainty goes — never invent answers to fill it.

## Step A — get the intent (first match wins)

1. **Pasted from Mission Control.** The founder uses the Capture Intent box at
   `/founder/command-centre` (idea → Clarify → Draft intent.md → edit → Accept), then
   presses **Copy intent.md** and pastes it here, or gives a file path. It is already
   through steps 1–4; check `status: accepted` and go to Step B.
2. **Raw thought, no intent yet.** Run steps 1–4 here:
   - Ask the founder to say it in their own words, if they have not already.
   - Ask analyst questions **one at a time** (grill-me style), each with your recommended
     answer, covering: who is hurt today and how often, what "fixed" looks like to them,
     who and what is touched, what must not change (money, compliance, brand, time),
     what is out of scope, and what we do not know yet. Stop when every template section
     can be filled without guessing — usually 4–7 questions.
   - Draft the intent.md with `status: draft`, show it, and ask the founder to correct it.
   - Only when they say it is right, set `status: accepted`, `author`, `created`.
   Write it to `$CLAUDE_JOB_DIR/tmp/intent.md` (or the scratchpad), never into a repo —
   several estate repos are PUBLIC and a raw founder idea must not be committed to one.
3. **Direct database pull** of the newest accepted Mission Control intent is deliberately
   not implemented yet. Add it only after reading `~/.claude/skills/library/connections.md`
   for the Unite-Group Supabase project and proving one read-only SELECT returns a row.

Never skip to the CEO review with a draft, a summary, or your own paraphrase. If the
founder will not accept an intent, stop there and say which section is unresolved.

## Step B — stage it for the CEO review

From the repo the review is about (the CEO review computes its slug and branch from the
current git checkout):

```bash
python3 ~/.claude/skills/capture-intent/scripts/stage_intent.py <intent.md> --repo .
```

- Exit 0 prints `STAGED: <path>` and `Design doc found: <path>` — the CEO review's own
  lookup, run verbatim from its SKILL.md, now resolves to this intent.
- Exit 1 prints `REFUSED: <reason>` and leaves nothing behind. Fix the named gap with the
  founder; do not hand-write the file into `~/.gstack` to get around it.
- "did not pick up the staged intent" means a newer `DESIGN.md` or `docs/designs/*.md` in
  the repo shadows it. Say so; do not delete the founder's or a teammate's design doc.
- "lookup snippet not found" means gstack's pinned version changed. Stop and re-check
  `tests/fixtures/ceo-lookup.md` against the new upstream before staging anything.

## Step C — run the CEO review

Invoke the `gstack-plan-ceo-review` skill. Tell the founder in one line which intent it
is reviewing (the title and the staged path). The review's design-doc check will print
`Design doc found:` with that path, so its "run /office-hours first?" offer will not fire.

## Tests

`python3 skills/capture-intent/tests/test_stage_intent.py` — 22 cases, stdlib only:
the accepted intent is the doc the lookup finds; draft, a second status line, missing
frontmatter, missing or empty author/created, missing section, sections placed only
inside the frontmatter, ANY code fence (16 variants: indent 0-3/tab, backtick/tilde,
closed or not) and any line opening with HTML, indented up to 3 spaces (fail-closed: review
rounds kept finding new ways to hide a heading, so nothing is stripped; mid-sentence
"<customer>" / "<AUD 500" prose is allowed), empty, invisible-only or marker-only sections
(".", "---", link-reference comments), missing title, a shadowing repo design doc, a HOME with a space (macOS bash 3.2's
lookup cannot see it — reported as that, not as shadowing; bash 5 can, and then it stages), and a drifted upstream
lookup are each refused with nothing left in `~/.gstack`; and the fixture lookup
matches the pinned upstream text when gstack is installed.
