---
name: jev
description: Ask TypeSafe Jev typed yes/no, pick-one or pick-a-file questions about reviewed files without reading them into an expensive model's context (Levels 8–10), or run the Gemini 3.8 Flash scout agent over them. Use for "is this file relevant", "which layer is this", "which file do I open first", triage before reading. Never for sums, dates, counts, gating an action, or UI. Answers are advisory and never clear an action.
---

# jev — cheap typed questions about reviewed files

Jev (TypeSafe `jev-latest`) answers bounded questions with a probability, for about
US$0.042 per million input tokens. The code lives in `jev_platform/`. The specs are
`docs/plans/jev-platform/PLAN-ask.md` (Level 8) and `PLAN-scale.md` (Levels 9–10 and the
Gemini agent), both approved 100/100 by Codex.

## When to use it

- You want to *learn* something about a file, not edit or quote it: "does this touch auth",
  "which layer is this", "does it contain a TODO or an admitted shortcut".
- Scouting: ask the same question of many files, then open only the one that matters.
- Triage: bundle the task and a few files, and ask where the fault most likely lies.

## When NOT to use it

- **Sums, percentages, dates and counts.** Jev takes stated numbers at face value (RA-7842).
  Compute them in code.
- **Gating or clearing an action.** Every answer is labelled `advisory, not authorization`.
  Nothing may branch to allow on it.
- **Anything you need to edit or quote.** Read the file instead.
- Long-running control, UIs, or open-ended writing.

## The boundary: nothing unreviewed leaves the machine

Only content listed in `.jev-approved.json` **committed at HEAD** can be sent. It has three lists:

- `files`: path → sha256. A changed file is refused until it is re-approved.
- `questions`: reviewed templates. Each declares the `state` it reads: `["content"]`,
  `["task", "content"]` or `["task", "files"]`. Each tool accepts only matching templates and
  refuses the rest before sending.
- `prompts`: reviewed operator prompts, referred to by id. The Gemini agent takes a prompt id,
  never free text.

Deny-listed paths (`.env*`, keys, `.ssh/`, `.vercel/` and others) and anything `sensitive()`
matches (keys, JWTs, IICRC or Standards Australia text) are refused, even when approved.

**Approving is a reviewed commit.** These commands print entries and never write the manifest:

```bash
.venv/bin/python -m jev_platform approve <path>                      # one file
.venv/bin/python -m jev_platform approve --glob 'src/**/*.ts'        # many; lists refusals too
.venv/bin/python -m jev_platform approve --prompt-file p.txt --id my-prompt
```

Read what you approve, paste it into `.jev-approved.json`, and commit.

## The tools

Every command takes `--repo <absolute path>`, because `vercel env run` changes the working
directory. Replace `<cmd>` below with one of these:

| Level | Command | What it does |
|---|---|---|
| 8 | `ask --file F --q T` | One or more templates about one file |
| 9 | `scout --glob G --q T [--prompt P]` | The same templates over every approved file matching the glob. At most 255 files; pruned files are listed with reasons |
| 9 | `pick-first --prompt P --q T --file F ...` | One pick across up to 250 candidate paths. Returns `picked`, `none` or `unavailable` |
| 10 | `ask-jev --prompt P --file F ... --q T` | One call bundling the task and up to 20 files. Refused over 64,000 bytes |
| — | `agent --prompt P` | The Gemini 3.8 Flash agent chooses the above tools itself; read-only |

**Keys are injected at run time and never stored.** Run from the Vercel-linked dashboard:

```bash
cd ~/Pi-Dev-Ops/dashboard && PYTHONPATH=<worktree> vercel env run -e production --non-interactive -- \
  <worktree>/.venv/bin/python -m jev_platform <cmd> --repo <worktree>
```

With no `TYPESAFE_API_KEY` (and, for `agent`, no `GEMINI_API_KEY`), the command prints
`BLOCKED` to stderr and exits 2.

## What each answer means

- A number is Jev's probability. `unavailable: <reason>` means **no signal**: an outage, a
  malformed reply or a budget stop. It is never a "no".
- `refused: <reason>` means nothing was sent.
- **The agent's report is written by code from its ledger.** Gemini's closing prose is shown
  underneath, labelled `agent summary (unverified)`.
- The agent can *propose* a new question (`propose_template`). The proposal is recorded in the
  report and never sent. A human approves it by committing it to `questions`.

## Cost and caps

- **Jev** reserves US$0.002688 per attempt and settles down to its reported usage, about
  US$0.0003 per file.
  - `ask` defaults to US$0.14.
  - `pick-first` and `ask-jev` make one call and default to US$0.01, which is 3 attempts.
  - `scout` defaults to US$0.75, enough for 255 files. The agent's Jev budget is also US$0.75.
- **Gemini** runs on a chain of five Flash models (`gemini.CHAIN`, dearest first: 3.8 Flash at
  US$0.75 / US$3.75 per million input / output tokens). The price table in `gemini.py` expires on
  31/12/2026 and must be updated; the 3.8/3.7/3.6 prices double on 01/01/2027.
  - A 404, 429 or 503 that outlasts the retries moves to the next priced model. The first model that
    answers is locked for the whole run; until then only one call at a time may send.
  - Each call is reserved beforehand at its own model's price: Google's `countTokens` for a single
    turn, the model's input-token limit for a multi-turn agent body, plus a 2,048-token output cap.
  - The run cap is US$2.50 (`RUN_CAP_USD`) and the turn cap is 12.

## What it is not

- It is **not a guard.** Levels 6 and 7 (hooks acting on answers) are RA-7841: log-only first,
  then allowed only to raise the bar, never to clear an action.
- It is **not a truth source for the Constitution.** Per-rule calibration lives in
  `jev_platform/calibration/`. `provisional` is the ceiling state, because labels come from two
  models agreeing, not from human review.
