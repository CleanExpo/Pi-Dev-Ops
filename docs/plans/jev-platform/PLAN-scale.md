# Jev Platform: Levels 9 and 10, a Gemini Flash agent, and a cheaper case writer — plan

Status: DRAFT rev 1 · 29/09/2026 · builds on PLAN.md rev 5 and PLAN-ask.md rev 4 (both approved
100/100). Done contract v7 (`w_9a6c73db7577`, criteria C12–C16) is locked against this plan.

## Why

The founder asked on 29/09 to "dive deeper into Level 10 and 11 to move to scale" and to use
`google/gemini-3.8-flash` "to again assist and lower the costs". He then sent three screenshots
from IndyDevDan's lab. In each one the **agent model is `google/gemini-3.8-flash`**, and the agent
calls `ask_jev_files` / `pick_first_file`:

1. "Use ask_jev_files with the glob `src/**/*.ts` and one question: does this file contain a known
   bug, a TODO, or a comment admitting a shortcut. Tell me which files said yes and with what
   probability." Then: the same over `tests/**/*.ts`.
2. "Use ask_jev_files over `src/auth/session.ts`, `src/auth/jwt.ts` and `src/http/routes.ts` with two
   questions in one block: does the file touch authentication, and which layer is it
   (http_handler, domain_logic, data_access, other). Report a small table. Do not read the files."
3. "The proration test fails because of rounding. Use ask_jev_files recursively over the whole repo
   asking whether each file is relevant to fixing that bug, then pick_first_file among the ones
   that said yes, and open only that one file." Then: fix it and run `npm test`.

**Facts checked this session, not recalled:**
- `disler/ten-levels-of-jev` is still at `777adaf` (GitHub API, 29/09) and has exactly ten level
  directories. **There is no Level 11 in the source.** This plan's reading: "Level 11" = running
  Levels 9 and 10 at scale, with Gemini carrying the cheap agent work. Stated, not asked.
- `models/gemini-3.8-flash` is listed by the Gemini API with the estate key (`~/.hermes/.env`,
  HTTP 200, 61 models). It is the newest numbered Flash. We pin that id, never
  `gemini-flash-latest` (the same alias lesson as `jev-latest`).
- Price (ai.google.dev/gemini-api/docs/pricing, fetched 29/09): paid tier US$0.75 per million input
  tokens and US$3.75 per million output tokens (thinking included) until 31/12/2026, **doubling on
  01/01/2027**. A free tier exists. Jev is US$0.042 per million input tokens (`client.py:17`), about
  18× cheaper than Flash, so **Gemini never replaces a Jev judgment**. It replaces the expensive
  seat: the agent, and the case writer.

## Where the cost actually is

| Seat | Today | After | Why it is cheaper |
|---|---|---|---|
| Judgment on a file | Jev, US$0.042/M | unchanged | already the cheapest |
| Agent that decides what to ask | Opus/Sonnet session | `gemini-3.8-flash` runner | Flash input is a fraction of a frontier model's, and file bytes never enter it |
| Case writer (525 rules left) | `claude -p --model sonnet` on Max quota | `gemini-3.8-flash` writer, Codex still labels blind | frees about one day of Max quota; metered cost is measured, not estimated |

## What to build

### A. Scout boundary (new, needed by Levels 9 and 10)

Level 8 sends only approved bytes and reviewed templates. The screenshots need agent-written
questions over whole globs of unapproved files. The judge's round-1 P1 on PLAN-ask (a harmless
`notes.md` can hold copied standards text or a credential) still holds for arbitrary files, so the
scout does **not** widen what can leave the machine. It sends only what is already public:

1. **Public origin, checked at run time.** `gh repo view <origin> --json visibility` must return
   `PUBLIC`. Anything else, including a failed check, is `BLOCKED: scout needs a public origin` and
   exit 2. Private repos keep the Level 8 manifest route and nothing else.
2. **Bytes come from `origin/main`, not the disk.** Files are listed with
   `git ls-tree -r origin/main -- <prefix>` and read with `git cat-file blob <sha>`. No filesystem
   open, so no symlink or TOCTOU race. Symlink entries (mode `120000`) and submodules (`160000`) are
   dropped. Uncommitted and unpushed content cannot be sent because it is not in that tree.
3. **The Level 8 filters still apply on top:** `_DENY_NAMES` on the path, `sensitive()` on the path,
   the bytes and every question, and a 32,000-byte file cap.
4. **Prune, as in `level09/prune.ts`**, each drop with its reason: `node_modules`, `.git`, `dist`,
   `build`, `coverage`, `.sessions`, `.pi`; binaries and lock files by extension; empty files; over
   the size cap. **255-file cap, enforced before any request**; the rest are listed as
   `over the 255 file cap; narrow the pattern`.
5. **Agent-written questions** (the screenshots need them): at most 8, each at most 1,000 characters,
   `noul` needing both `true` and `false` criteria, `choice` needing 2–254 options, with `other`
   added when the agent leaves none out. Every question must mention `content`. The question text
   goes through `sensitive()`.

### B. Level 9: `ask_jev_files` and `pick_first_file` (`jev_platform/scout.py`)

- `scout_files(repo, patterns, recursive, questions, post, budget, prefix="")`: glob, directory
  or file patterns → expand over the `origin/main` tree → prune → one Jev call per file, at most 4 in
  flight, sharing the existing atomic `Budget`. Output per file: path, blob sha, answers or
  `unavailable`, plus the `skipped` list with reasons.
- **Budget.** Level 8 runs one request at a time. Here, up to 4 workers share the one `Budget`,
  whose `reserve()` is already atomic under a lock (`client.py:52-59`).
  - Each attempt reserves US$0.002688, so 255 files need US$0.685 reserved.
  - The scout's `--max-usd` default is **US$0.75**: 279 attempts, covering 255 files plus 24 retries.
  - Reported usage settles the real spend down to about US$0.0003 per file.
  - A run that hits the cap lists the unsent files as `budget exhausted`.
- `pick_first(question, candidates, post, budget, floor=0.3)`: one `choice` keyed by the candidate
  paths themselves, plus `none`. The state is `{question, files}`, with paths only and no bytes. Any
  pick that is not a candidate path, or that falls under the floor, gives `path: null`.
- Response validation reuses `ask.validate_answers`. Everything is labelled advisory; nothing exits
  non-zero because of an answer.
- CLI: `python -m jev_platform scout --repo R [--prefix P] --glob G ... [--recursive] --questions-json F`
  and `python -m jev_platform pick-first ...`.

### C. Level 10: `ask_jev` (in the same module)

`ask_jev(repo, state, paths, questions)`: the agent's own `state` (free text, which goes through
`sensitive()`), plus up to 20 `paths` read through boundary A, plus agent-written questions, all
**in one call** (about 60k tokens at most, the client's existing 64,000-byte request cap).

**No `command` field.** The video runs the agent's command "through the Level 6 bash gate". We have
no Level 6 gate; that is RA-7841, a founder decision. Running agent-supplied shell with the Jev key
in its environment is the defect already found at `ask-jev.ts:31`. So Level 10 ships without
command execution, and the command half is filed under RA-7841.

### D. The Gemini agent runner (`jev_platform/agent.py`, CLI `python -m jev_platform agent`)

A plain Python loop over the Gemini `generateContent` REST API with function calling.
- Model pinned to `gemini-3.8-flash`. The key comes from `GEMINI_API_KEY`. If it is missing, print
  `BLOCKED` and the `vercel env run` route, then exit 2. The key is sent as the `x-goog-api-key`
  header (connections.md: `Bearer` returns 401) and is never logged.
- **Tools:** `ask_jev_files`, `pick_first_file` and `ask_jev` (B and C), plus `read_file(path)`.
  `read_file` is the only way file bytes reach Gemini, and it goes through the same boundary A.
  There is **no write, edit or shell tool**. The screenshots' "then fix it and run npm test" step
  is out of scope, and the runner prints what it would change.
- **Caps:** at most 12 turns, a US$0.05 Gemini cap computed from the observed `usageMetadata`, and
  the existing Jev `Budget`. The first cap reached stops the run with the reason.
- **Ledger:** each run records the agent model, turns, Jev calls, questions, `files_read`, Gemini
  input and output tokens as reported, Jev US$, Gemini US$ at the rate above (with the rate's date),
  and the final text.
- **Advisory only.** The runner holds no merge, push, write or approve power. It cannot touch
  `.jev-approved.json`.

### E. Gemini case writer (`evals/jev_constitution/generate.py --writer gemini`)

- `gemini_write()` has the same contract as `claude_write()`: scenarios plus a proposed label and
  class. Codex still labels blind, so "two different models agreeing" survives. Claude stays the
  default writer, and `--writer gemini` is opt-in.
- **Control before any bulk run.** Generate at least 50 cases for `core-44` (already calibrated) with
  each writer. Record in `docs/plans/jev-platform/gemini-writer-control.json` the proposed count,
  Codex agreement, class spread and observed tokens for each writer. **Verdict rule:** Gemini may
  be used for bulk writing only when its agreement is at least the Claude writer's minus 5 points
  and every one of the 5 hard classes (arithmetic, dates, indirection, irrelevant context,
  adversarial) appears. Otherwise the verdict is `do-not-use` and the saving is recorded as not
  real.

## Tests (offline, fake `post` and fake Gemini transport)

- **Boundary A**
  - A private or unknown origin → `BLOCKED`, exit 2, zero requests.
  - A file that is only in the working tree (not on `origin/main`) is not sent.
  - A symlink blob is dropped.
  - A `.env` blob on `origin/main` is refused.
  - A file containing `standards australia` is refused.
  - A question containing a key pattern is refused.
- **Level 9**
  - 300 eligible files → 255 requests, and 45 skipped with the cap reason (`cap_255`).
  - `node_modules` and `.lock` files are pruned.
  - A pick outside the candidates, `none`, or a pick under the floor → `null` (`pick_first_only_real_path`).
  - Multiple questions in one block → one request per file.
  - A missing answer → `unavailable`.
- **Level 10**
  - `state`, paths and questions → exactly one request.
  - 21 paths → refused.
  - A `command` argument is rejected by the schema.
- **Agent runner**
  - No key → `BLOCKED`, exit 2.
  - A scripted fake Gemini that calls `ask_jev_files` then answers → ledger `jev_calls=1`, `files_read=0`.
  - `read_file` on a denied path → refused, with no bytes in the next Gemini request.
  - The turn cap stops the run.
  - The US$ cap stops the run.
  - The key never appears in the ledger or stdout.
- **Case writer**
  - A fake Gemini reply is parsed into the same case shape.
  - Malformed JSON → the batch is dropped, not written.
- **Mutation:** each new guard gets a mutant in `tests/mutation/jev_platform_mutants.py`, and all
  must be killed (C11).

## Live evidence (after the offline gates are green)

- **`level9-live.json`** runs the three screenshot prompts, verbatim, with the Gemini runner against
  the video's own sandbox, `disler/ten-levels-of-jev@777adaf`, prefix `apps/ten-levels/sandbox`. It is
  a public origin and the same files the screenshots name.
- **Pass condition (C15):**
  - Each run makes at least one Jev call.
  - Prompts 1 and 2 read zero files into the agent.
  - Prompt 3 opens exactly one file.
  - The file prompt 3 picks is recorded. The video's answer was `src/domain/billing.ts`, and a
    different pick is reported as a disagreement, not hidden.
- **`gemini-writer-control.json`** is described in E above (C16).

## Out of scope, and why

- **Command execution in `ask_jev`:** RA-7841 (founder).
- **Any hook or gate that acts on an answer:** the shadow-only decision stays in force.
- **Writing, editing or running tests from the Gemini runner.**
- **Bulk generation for the remaining 525 rules:** it follows the E control result, not this plan.
- **The estate `jev` SKILL.md:** already planned in PLAN-ask §5. It gains Level 9 and 10 usage once
  this ships.

## Risks

- **The free tier may let Google use prompts to improve its products.** The boundary sends only
  public, pushed bytes and synthetic scenarios, so nothing private is exposed. Whether the key's
  project is billed is **UNVERIFIED**; the first live ledger records which price applied.
- **Gemini's price doubles on 01/01/2027.** The ledger stores the rate and its date, so later runs
  recompute the cost rather than trust it.
- **Agents do what agents do** (the video's own note). C15 records what the agent actually did,
  not what it was told to do.
