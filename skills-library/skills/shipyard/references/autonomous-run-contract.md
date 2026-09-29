# Autonomous run contract

Every long-running or unattended run follows this contract: `shipyard`, `/loop`, background
builder agents, and `/goal` runs. It exists so a run keeps moving without asking about routine
choices, ends with a status nobody has to interpret, and leaves enough behind to resume.

Adapted from garrytan/gstack @ `b9706f36` (MIT). Sources: `autoplan/SKILL.md.tmpl` (decision
classes) and `scripts/resolvers/preamble/generate-completion-status.ts` (status and learnings).
Two gstack principles were deliberately NOT adopted. "Boil lakes" (fix everything in the blast
radius) conflicts with `CLAUDE.md` §3, surgical changes. "Merge over review cycles" conflicts with
the human-merge law. Our own rules replace them below.

## 0. The bar is a floor

Founder directive, 24/09/2026: AAA is the minimum, never the maximum.
- Every run names its bar before starting: a fetchable outside benchmark, per the claim
  grammar in `CLAUDE.md` §0 (`AAA-C(...)` or `AAA-S(...)`). "Good enough" with no named bar is
  not a bar.
- Reaching the bar does not end the run. If safe, in-scope improvement remains, the item is
  `DONE_WITH_CONCERNS` and the gap becomes a named follow-up. Silence is not acceptable.
- **Look 20 moves ahead.** Every plan and Board packet carries a move map: the next moves in
  order, the second-order effect of each, and what each unlocks toward the metric of record
  (paying customers, then MRR; `Unite-Group/NORTH-STAR.md`). A move that leads nowhere on that
  metric is marked as such.

## 1. Classify every decision before acting on it

| Class | Test | What the run does |
|---|---|---|
| **Mechanical** | One answer is clearly right, or an estate rule already decides it | Decide silently. Never ask. |
| **Taste** | Reasonable people could disagree: two viable approaches, borderline scope, or a reviewer with a valid different view | Decide on the recommendation, keep going, and list it at the final gate |
| **User challenge** | The run wants to change the founder's stated direction: add, drop, merge or split scope | Never auto-decide. Keep the original direction and list the proposal at the final gate |
| **Founder-only** | Merge, deploy, prod DB write, secrets, spend, a new vendor, deletion | Park that item (see `shipyard` Parking). Other items keep moving |

Mechanical examples: run the gates (always), run the reviewer (always), use the repo's declared
Node version (always), reduce the scope of a complete plan (never), add an unrequested feature
(never).

To decide Taste items, apply these in order:
1. **Reuse before building.** Something that already exists wins.
2. **Explicit over clever.** Pick the version a new reader understands in 30 seconds.
3. **Smallest change that fully does the task.** Nothing speculative, nothing adjacent.
4. **Pragmatic.** If two options fix the same thing, take the cleaner one and move on.

**The final gate is one message.** It lists every Taste and User-challenge item with the choice
made, the reason, and what was rejected. The founder answers once. Asking mid-run about a
Mechanical or Taste item is a contract breach.

## 2. End every item with one of four statuses

| Status | Meaning | Must include |
|---|---|---|
| `DONE` | Finished, with evidence | The command, exit code and commit SHA that prove it |
| `DONE_WITH_CONCERNS` | Finished, and something is worth a look | Each concern, as a ticket or a named follow-up |
| `BLOCKED` | Cannot proceed | The blocker, what was tried, who or what unblocks it |
| `NEEDS_CONTEXT` | Missing information only the founder has | The exact question, with a recommended default |

Format: `STATUS` · `REASON` · `ATTEMPTED` · `RECOMMENDATION`. A status without its evidence
is `BLOCKED`, not `DONE`.

**Three strikes.** After 3 failed attempts at the same step, stop that item with `BLOCKED` and
move to the next. The same applies after one attempt at an uncertain security-sensitive change.
Record a `guard.py hypothesis` before the third attempt, so the attempts differ. Never retry an
unchanged command.

## 3. Leave the run resumable

- Each stage writes its output to `~/.local/state/gs/projects/<repo>/`. The output is a design
  doc, a plan, a review report, or a test plan, named `<date>-<stage>-<item>.md`. The next stage
  reads from there, not from conversation memory.
- `resume-from-handoff` reads this folder when a run is picked up after a crash or `/clear`.

## 4. The learnings step always runs

Before the final gate, review the run for durable learnings: a project quirk, a command fix, a
pitfall, or anything that would save 5+ minutes next time. Save each one as a memory file. If
there are none, write "No durable learnings this run" in the report. An empty result is stated,
never skipped. gstack found that 43 of 44 learnings came only when this step was mandatory
(their issue #2402).
