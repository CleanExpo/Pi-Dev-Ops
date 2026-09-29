---
name: gauntlet-pair
description: Emits a matched pair of gauntlet-loop prompts - one for the Claude Desktop app, one for the Claude CLI - so both grind separate projects at once without colliding, each looping until the board holds 100% AAA+. Dispatched by gauntlet-loop when the user wants two surfaces working in parallel. Triggers on "both desktop and cli", "run a pair", "two projects at once", "use the desktop app too".
---

# Gauntlet Pair

Two surfaces. Two projects. One exit condition: **100% AAA+**.

You are not doing the work. You are writing the two prompts that make Claude Desktop and
Claude CLI each grind their own project until the board holds.

Read `../gauntlet-loop/SKILL.md` first. Everything there about **the bar** still applies and is
still the whole trick. This skill only adds: how two surfaces share a machine, and what
"100% AAA+" means in a way a critic cannot inflate.

## The north star: 100% AAA+

The parent skill warns that scores out of 10 drift upward every round, and that a named exit
after N rounds is a failure. So AAA+ is **not a rating a critic assigns**. It is a property of
the board, derived from binary comparisons that cannot be inflated.

Per piece:

| Rung | Meaning |
|---|---|
| — | Not built yet |
| **A** | Built, blind comparison run, the bar won |
| **AA** | Ours won the blind comparison once |
| **AAA** | Ours won again, judged by a critic with **fresh context** that never saw the earlier rounds |
| **AAA+** | At AAA, and a fresh critic asked only "name the single biggest remaining gap" names nothing that is both **in this piece's scope** and **material to the bar** |

**100%** means every piece sits at AAA+ **at the same time**. Not the average. Not most of them.

### The two qualifiers on AAA+ are load-bearing

Without them AAA+ is unreachable. A harsh critic asked for the biggest remaining gap on any real
codebase always names one — that is the job it was given. An exit condition a competent critic can
never satisfy is not a high bar, it is a loop that cannot terminate, and the run dies of stall
instead of finishing.

So a named gap blocks AAA+ only when both hold:

- **In scope.** It belongs to this piece. A gap in a neighbouring file is real work, and it goes on
  the board as its own piece — it does not hold this one down.
- **Material to the bar.** The bar would beat us on it. A gap the reference artifact also has is an
  observation about the category, not a deficit against the bar.

Anything failing either test is **recorded and spawned, never suppressed**. The board grows; the
piece finishes. A critic that names nothing at all is a soft critic and its verdict is discarded.

Why this cannot drift:

- No number is ever assigned. Every judgement stays binary — A or B, which is better.
- The rung comes from **repetition under fresh context**, not from a critic feeling generous.
  A critic that has watched the builder struggle starts scoring effort. A fresh one cannot.
- "Nothing actionable" is falsifiable. If the critic names a gap, the piece is not AAA+ and
  the gap is the next task. The critic proves the rung by failing to break it.
- Coverage, not average. One weak piece cannot be hidden behind strong ones — which is exactly
  what a score out of 10 does.

A piece can **regress**. If a later change drops any piece below AAA+, the board is no longer
100% and the loop resumes.

### Stalling is an exit, and it must be taken

The run ends three ways: the board holds at 100%, the user stops it, or **a full sweep moves no
piece's rung**. That third one is mandatory, not optional. A sweep that changes nothing means the
loop cannot reach its exit from where it is standing, and grinding further only burns the session.

On a stall: stop, release the claim, and hand to `goal-circuit-breaker` to classify the residual.
Report what is actually blocking. Do not re-emit the same board in different words — a restated
blocker reads as progress and is not.

Claims carry a 12-hour staleness marker for this reason. A `[STALE]` claim on `claim.mjs status`
means a previous run died mid-grind; read its board section before reclaiming, then reclaim with
`--force`. Leaving stale claims in place is how a project ends up looking busy while nothing runs.

## Flow

1. **Two projects, never one.** If the user names one project, say so and ask for the second —
   a pair on one project is the thing this skill exists to prevent.
2. **A bar per project.** Apply the parent skill's three tests to each: named, fetchable,
   comparable. Two projects need two bars; a shared bar means one of them is wrong.
3. **Claim both.** Run the claim command for each. A refusal means that project is already
   being ground — pick another.
4. **Emit the pair.** Two prompts, surface-shaped. Never one prompt pasted twice.
5. **Release on exit.** Both prompts end by releasing their claim.

## What differs between the surfaces

Desktop is not a weaker CLI. It has its own isolation, and the prompt should lean on it.

| | Claude Desktop | Claude CLI |
|---|---|---|
| Isolation | Its **native leased worktree** — `<repo>/.claude/worktrees/<slug>` on `claude/<slug>` off `main`, tracked in `git-worktrees.json`. Let it do this; do not hand-roll one. | State it explicitly: its own worktree, or the main checkout |
| Loop mechanism | No `/loop`. Plain: "keep going until the board is 100% AAA+" | `/loop` and `ultracode` |
| Fan-out | Subagents in-app | Subagents plus `ultracode` |
| Claim | `claim.mjs claim <project> desktop` | `claim.mjs claim <project> cli` |

## Shared surfaces neither loop may touch

They do not fight over repo files — Desktop isolates by worktree. They collide everywhere else.
Both prompts carry these four rules:

- **`~/.claude/skills/`** — read freely, never edit mid-run. Three machines already commit here.
  A wanted skill change goes on the board as a proposal, not into the tree.
- **`~/.claude/projects/*/memory/`** — same. `MEMORY.md` is a shared index and last write wins.
- **Merge and deploy gates** — neither loop merges to main or approves a production deploy.
  Those are human gates and stay human gates, however good the board looks.
- **The other surface's project** — never read into it, never "just fix" something there.

## The claim

```bash
node ~/.claude/skills/gauntlet-pair/claim.mjs claim   <project> <desktop|cli>
node ~/.claude/skills/gauntlet-pair/claim.mjs release <project> <desktop|cli>
node ~/.claude/skills/gauntlet-pair/claim.mjs status
```

Advisory by design — it refuses and explains rather than locking. A hard lock that wedges is
worse than a claim you can see and override with `--force`. Exit 3 means the other surface
holds it. Concurrent claims are settled by an atomic mutex: exactly one wins.

## The board

Both loops append to `~/.claude/gauntlet/board.md`, every entry prefixed with its surface and
project. One file, so the user watches two grinds in one place instead of alt-tabbing. Each
entry: the piece, its rung, and the gap the critic just named.

## Prompt template

Adapt the wording every time. Fill the brackets, keep it short, keep the closing lines.
Around 150 to 200 words each — a little longer than a solo gauntlet, because the claim and the
rung ladder have to survive being pasted into a session with no other context.

```
Work in [PROJECT] only. First run:
node ~/.claude/skills/gauntlet-pair/claim.mjs claim [PROJECT] [SURFACE]
If that refuses, stop and tell me.

Build [GOAL].

The bar is [BAR]. Get the real thing first and compare against it directly, not against a
description of it.

Break this into the smallest pieces that can be judged on their own. For each piece, fan out a
builder and a separate critic with fresh context. The critic inspects the actual output, puts it
next to the bar blind with the labels stripped, and says which is better.

Grade every piece: A means the bar still wins. AA means ours won once. AAA means ours won again
under a critic that never saw the earlier rounds. AAA+ means a fresh critic asked for the single
biggest remaining gap has nothing actionable to name.

Do not stop until every piece is AAA+ at the same time. Not the average - every piece. If one
regresses, the board is not done and you keep going.

Never assign a score out of 10. Every judgement is binary, A or B.

Do not edit ~/.claude/skills or the memory directory. Do not merge to main or approve a
production deploy - those are human gates.

Append progress to ~/.claude/gauntlet/board.md, prefixed [SURFACE] [PROJECT].

When the board holds, release the claim.
[LOOP LINE]
```

`[LOOP LINE]` is `/loop on each piece until every piece is AAA+. Fan out subagents and
ultracode.` for the CLI, and `Keep looping on each piece until every piece is AAA+. Run the
builders and critics as parallel subagents.` for Desktop.

## What breaks a pair

Everything in the parent skill's list, plus:

- **One project, two surfaces.** They stomp each other's branches and both open PRs for the
  same scope. The claim exists for this; do not skip it because "it is only a quick one".
- **A shared bar.** Two projects graded against one reference means one project is being judged
  against something it was never trying to be.
- **A loop that edits skills mid-run.** It changes the behaviour of the other loop underneath
  it, and neither result is attributable afterwards.
- **Averaging to 100%.** "Nine of ten pieces at AAA+" is not 100%. It is nine pieces done and
  one unfinished, and the tenth is the one that will be seen.
- **A critic that has been watching.** By round four it is grading effort, not output. Fresh
  context per judgement or the ladder means nothing.
