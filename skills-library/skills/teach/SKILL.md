---
name: teach
description: Teaches the user a topic over many sessions in a dedicated teaching workspace of cited HTML lessons, quizzes, learning records and spaced review. Use when the user runs /teach, says "teach me" or asks to learn a topic over weeks, or /spm routes a request to its Learn lane. Not for a single explanation inside the current task.
argument-hint: "What would you like to learn about?"
effort: high
---

# teach: a standing course on one topic

The user wants to learn something over several sessions. This is stateful: the course lives
as files in a teaching workspace, so "next lesson" in a fresh session carries on from them.
This is the estate's version of Matt Pocock's `teach`, with his documented failure modes fixed
(see [PROVENANCE.md](PROVENANCE.md)). Reached through `/spm` (Learn lane) or `/teach` directly.

## When to invoke

- The learning is the project: a language, framework, codebase, standard, certification or trade skill, over weeks.
- `/handoff` from a grilling sent the user here to learn a term before carrying on.
- Negative trigger: one explanation inside the current task is not a course. Answer it in place.

## Teaching workspace

One mission per workspace. Use a dedicated folder or repo, never the working project. Workspace
paths resolve from the directory `/teach` ran in; the format links below resolve from this skill.

| Path | Holds | Format |
|---|---|---|
| `MISSION.md` | Why the user is learning this. Every lesson traces back to it. | [mission-format.md](references/mission-format.md) |
| `RESOURCES.md` | Vetted sources: Knowledge and Wisdom (communities), plus Gaps. | [resources-format.md](references/resources-format.md) |
| `GLOSSARY.md` | Canonical terms, added only once the user can use them. | [glossary-format.md](references/glossary-format.md) |
| `learning-records/0001-*.md` | ADR-style evidence of what the user can now do. | [learning-record-format.md](references/learning-record-format.md) |
| `lessons/0001-*.html` | One short, self-contained lesson each. The main unit of teaching. | Core procedure step 5 |
| `reference/*.html` | Cheat sheets, algorithms, glossaries. What the user returns to. | Print-friendly |
| `assets/` | Shared components. Seed it from [lesson.css](assets/lesson.css) and [quiz.js](assets/quiz.js). | Reuse first |
| `NOTES.md` | The user's stated teaching preferences. | Free form |
| `REVIEW.md` | The spaced-review queue. | Core procedure step 7 |

## Core procedure (DO NOT DEVIATE from the order)

1. **Read state.** Read every workspace file that exists, plus the nearest project `CLAUDE.md`
   for overlays (CARSI: Australian English and its IICRC rules, see Hard rules). Done when you
   can say which step below this session starts at.
2. **Mission.** If `MISSION.md` is missing or vague, interview the user one question at a time
   (the `grilling` manner, with a recommended answer each time) until the Why and Success lines
   are concrete. Confirm before writing it. Done when `MISSION.md` exists and the user agreed.
3. **Starting point (session one, or after a mission change).** Before any lesson, run a short
   diagnostic: 3 to 6 questions that probe what the user already knows and where it stops,
   including terms they would meet in lesson one. Write each finding as a learning record
   (prior knowledge, with the depth claimed). Done when lesson one can be pitched without guessing.
   This closes upstream issue #725 (no assessment step, undefined jargon).
4. **Resources before lessons.** Until `RESOURCES.md` covers the mission, search for high-trust
   primary sources and record them. Never teach from parametric knowledge. Done when every
   claim the next lesson makes has a source in `RESOURCES.md`.
5. **One lesson.** Pick the next skill inside the user's zone of proximal development (mission
   plus learning records, never re-teaching a demonstrated skill). Read `./assets/` and build
   from it. Write `lessons/NNNN-slug.html` linking `../assets/lesson.css` and `../assets/quiz.js`
   (lessons sit one folder below `assets/`), containing in order:
   the one tangible win, the minimum knowledge for it (cited inline), an interactive feedback
   loop (a `.quiz` block, or real-world steps with a self-check), one recommended
   primary source, a "check this lesson" block, and a reminder to ask follow-up questions.
   Open it for the user (`open <file>`). Done when the file exists and passes step 6.
6. **Gate the prose.** Run `unslop` over the lesson text: no AI tells, sentence-case headings,
   no decorative emoji, no em-dash chains. Then re-check that every claim still carries its
   link. A lesson with no citations is the model teaching from memory: rewrite it.
7. **Record and schedule.** When the user shows understanding, write a learning record and
   promote any term they can now use into `GLOSSARY.md`. Add the lesson's key items to
   `REVIEW.md` with due dates at 1, 3, 7 and 21 days. Done when the record and queue are written.

**Every later session:** run step 1, then serve any `REVIEW.md` items that are due as mixed
retrieval practice (interleaved, no notes, answer first then reveal) before new material. When
three consecutive reviews pass without help, say so and offer real practice or a community
instead of another lesson. That closes the "never knows when to stop" gap.

## Modes

- Effort stays high: upstream reports show medium effort produces thin lessons.
- Coding topics: for hands-on drills inside a real repo, suggest `/output-style Learning`. It
  leaves `TODO(human)` spots in real code and waits, which is a tighter feedback loop than a quiz.
  Switch back afterwards. Output styles reach the main thread and forks only.
- Long source reading or resource hunting: run it in a forked subagent so the main context
  holds only the cited summary.

## Output format

Each session ends with: the lesson path (or review result), the learning records written, what
is due in `REVIEW.md` next, and one line on what the next lesson will be. Nothing else.

## Calibration

- A lesson takes one sitting, roughly 10 to 20 minutes, and gives exactly one new ability.
  Over 20 minutes means it holds two lessons: split it.
- Quiz answers are the same number of words. The component shuffles their order at render
  time; author the correct answer first with `data-correct="0"`.
- Each lesson cites at least one source per factual claim and recommends one primary source.
- More than two lessons in a row with no learning record means the level is wrong: re-run step 3.

## What this skill is NOT

- Not a one-off explanation: answer in place.
- Not a re-pitch of the last message: that is `wait-what`.
- Not sharpening thinking you already have: that is `grill-me` / `grilling`.
- Not a cited research document: that is `nexus-research`.
- Not CARSI student course production: that is `carsi-course-production`. `teach` can teach
  the founder or staff; it does not publish student courses.

## Hard rules

1. Never write a lesson before `MISSION.md` exists. Upstream's most common failure was abstract lessons.
2. Never write a lesson before the starting-point diagnostic. Assumed knowledge and undefined jargon were the most common complaint.
3. Never state a fact without a link to a source in `RESOURCES.md`. A 2x2 Rubik's cube lesson shipped made-up moves this way.
4. Never hard-code the correct answer's position. Instruction-only fixes failed 33 of 33 times; use the component.
5. Never record coverage as learning. A learning record needs evidence.
6. Respect project overlays. In CARSI workspaces: Australian English and metric units; IICRC
   standards are cited by name and section only, and their text is never pasted, summarised
   from, or fed into any AI tool; no lesson implies CARSI delivers IICRC certification.
7. Respect a stated preference not to join communities; record it in `RESOURCES.md`.

## Provenance

Adapted from `mattpocock/skills` `skills/productivity/teach` at a pinned commit, MIT licence
([LICENSE](LICENSE)). What changed and why: [PROVENANCE.md](PROVENANCE.md).
