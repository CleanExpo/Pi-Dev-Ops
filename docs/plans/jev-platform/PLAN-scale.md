# Jev Platform: Levels 9 and 10, a Gemini Flash agent, and a cheaper case writer — plan

Status: DRAFT rev 2 · 29/09/2026. It builds on PLAN.md rev 5 and PLAN-ask.md rev 4, both approved
100/100. Done contract v7 (`w_9a6c73db7577`, criteria C12–C16) is locked against this plan.
Rev 1 scored 72/100 (`judge-scale-r1.md`), and rev 2 answers every required change; see
"Rev 2 changes" at the end.

## Why

On 29/09 the founder asked to "dive deeper into Level 10 and 11 to move to scale", and to use
`google/gemini-3.8-flash` "to again assist and lower the costs". He then sent three screenshots
from IndyDevDan's lab. In each one the **agent model is `google/gemini-3.8-flash`**, and it calls
`ask_jev_files` / `pick_first_file`:

1. "Use ask_jev_files with the glob `src/**/*.ts` and one question: does this file contain a known
   bug, a TODO, or a comment admitting a shortcut. Tell me which files said yes and with what
   probability." Then run the same over `tests/**/*.ts`.
2. "Use ask_jev_files over `src/auth/session.ts`, `src/auth/jwt.ts` and `src/http/routes.ts` with two
   questions in one block: does the file touch authentication, and which layer is it
   (http_handler, domain_logic, data_access, other). Report a small table. Do not read the files."
3. "The proration test fails because of rounding. Use ask_jev_files recursively over the whole repo
   asking whether each file is relevant to fixing that bug, then pick_first_file among the ones
   that said yes, and open only that one file." Then fix it and run `npm test`.

**Facts checked this session, not recalled:**
- **There is no Level 11 in the source.** `disler/ten-levels-of-jev` is still at `777adaf` (GitHub
  API, 29/09) and has exactly ten level directories. This plan reads "Level 11" as Levels 9 and 10
  run at scale, with Gemini doing the cheap agent work.
- **The model exists and is pinned.** The Gemini API lists `models/gemini-3.8-flash` for the estate
  key (`~/.hermes/.env`, HTTP 200, 61 models). It is pinned by that id, never `gemini-flash-latest`.
- **Price** (ai.google.dev/gemini-api/docs/pricing, fetched 29/09):
  - Paid tier: US$0.75 per million input tokens and US$3.75 per million output tokens (thinking
    included) until 31/12/2026. Both **double on 01/01/2027**.
  - A free tier exists.
  - Jev costs US$0.042 per million input tokens (`client.py:17`), about 18× cheaper, so **Gemini never
    replaces a Jev judgment**.

## Where the cost actually is

| Seat | Today | After |
|---|---|---|
| Judgment on a file | Jev, US$0.042 per million tokens | unchanged |
| Agent deciding what to ask | Opus or Sonnet session | `gemini-3.8-flash` runner; file bytes never enter it unless it opens one approved file |
| Case writer (525 rules left) | `claude -p --model sonnet` on Max quota | opt-in `gemini-3.8-flash` writer, only after the control passes; Codex still labels blind |

## The boundary: unchanged from Level 8, applied to the whole outbound payload

**Nothing new may leave the machine.** The only content that can reach Jev or Gemini is:

- **(a)** files listed in `.jev-approved.json` at HEAD, with bytes matching the approved sha256. This
  is Level 8's `admit()`: a confined `O_NOFOLLOW` read, the deny-list, `sensitive()`, and a 32,000-byte
  cap.
- **(b)** the operator's prompt.
- **(c)** text derived only from (a), (b) and Jev's own answers.

Public visibility is not used as a reason to send anything.

1. **Globs expand over approved paths only.** Patterns match against the manifest's `files` keys,
   never the disk.
   - A glob cannot reach an unreviewed file, because it only ever sees the manifest list.
   - Level 9 prune rules (dependency, VCS and build dirs, binaries, lock files, empty files) still
     run and report each dropped path with its reason.
   - An approved path whose bytes have since changed is refused as today: "content differs from
     approved sha256".
2. **Bulk approval, still human-reviewed.**
   - `python -m jev_platform approve --glob G` prints manifest entries for every matching tracked
     file that passes `_DENY_NAMES` and `sensitive()`, and lists the refused ones with reasons.
   - As today, it never writes the manifest. A human reviews and commits it.
3. **Operator prompt admission.**
   - The runner's `--prompt` goes through `sensitive()` and a 4,000-character cap before the first
     Gemini request. A refused prompt means exit 2 with zero requests.
   - The operator is accountable for the prompt text, as they are today for what they type into
     any model.
4. **Why agent-written text is allowed, and how it is enforced.**
   - The agent's context holds only (a), (b) and Jev's typed answers.
   - Every tool result returned to Gemini is built by code from those sources. Refusals carry the
     path and reason only, never bytes.
   - So agent-written questions, criteria, options and Level 10 `state` are derived from trusted
     inputs.
   - Defence in depth: **every outbound payload** passes `sensitive()` as one serialised string
     before it is sent. That covers each Jev body (state, questions, criteria, options, pick-first
     candidate lists) and each Gemini request (contents plus tool results).
   - A hit refuses that request. The refusal is recorded, and the agent is told
     `refused: sensitive content in request`.
5. **Question shape.**
   - At most 8 questions per call, each at most 1,000 characters.
   - `noul` needs non-empty `true` and `false` criteria.
   - `choice` needs 2–250 options, and `other` is added when the agent leaves none out.
   - Every question must mention `content`, `state` or `files`.

## Level 9: `ask_jev_files` and `pick_first_file` (`jev_platform/scout.py`)

- **`scout_files(repo, patterns, questions, post, budget)`:**
  - expands `patterns` over the manifest, then prunes
  - enforces the **255-file cap before any request**; the rest are listed as
    `over the 255 file cap; narrow the pattern`
  - makes one Jev call per file, **sequentially**; concurrency is deferred
  - output per file: path, sha256, then answers or `unavailable`; plus the `skipped` list
- **Budget.** It reuses the atomic `client.Budget`, whose `reserve()` holds a lock (`client.py:52-59`).
  - Each attempt reserves US$0.002688, so 255 files need US$0.685.
  - The scout's `--max-usd` default is **US$0.75**, which is 279 attempts.
  - Files left unsent when the cap is hit are listed as `budget exhausted`.
- **`pick_first(question, candidates, post, budget, floor=0.3)`:**
  - Candidates are deduplicated, capped at **250**, and keyed `f001…f250`. Keys are never the path
    text, so a file named `none` or `other` cannot collide.
  - The state carries `{question, files: {key: path}}`. The choice is `f001…fN` plus `none`, and
    `other` is added automatically, so there are at most 252 options, under Jev's 255.
  - **Results are distinct:**
    - `picked`: path, confidence, probabilities
    - `none`: Jev chose `none` or `other`, or confidence was under the floor, with the numbers
      shown
    - `unavailable`: transport failure, malformed, a missing answer, or a key outside the sent set.
      No numbers are given.
    - Empty candidates give `none`, with zero requests.

## Level 10: `ask_jev` (same module)

`ask_jev(repo, state, paths, questions)` makes **one** Jev call covering:
- the agent's `state`: text, at most 8,000 characters
- up to 20 approved `paths`, each admitted as in (a)
- the agent's questions

Size is checked on the **serialised request**, not on tokens. When the aggregate goes over
`client.MAX_REQUEST_BYTES` (64,000), the call is refused before sending, with the per-part byte
sizes. Twenty files that are each valid can still be refused this way.

**No `command` field.** The video runs the agent's command through its Level 6 bash gate. We have
no Level 6 gate: that is RA-7841, a founder decision. Its own `ask-jev.ts:31` also passes the key
to the child's environment. So Level 10 ships without command execution, and the command half is
filed under RA-7841.

## The Gemini agent runner (`jev_platform/agent.py`, `python -m jev_platform agent`)

A Python loop over Gemini `generateContent` with function calling.
- **Model and key.** The model is pinned to `gemini-3.8-flash`.
  - A missing `GEMINI_API_KEY` prints `BLOCKED` plus the route, then exits 2.
  - The key goes in the `x-goog-api-key` header. It is never logged, and it is not in any
    subprocess environment, because there are no subprocesses.
- **Tools:**
  - `ask_jev_files`, `pick_first_file` and `ask_jev`, as above
  - `read_file(path)`, the only way file bytes reach Gemini; it goes through (a)
- **No tools for:** write, edit, shell, approve or the network. The screenshots' "fix it and run
  npm test" step is out of scope.
- **Prepaid budget, reserved before every attempt** (`GeminiBudget`, the same pattern as
  `client.Budget`):
  1. Before sending, a local upper bound on input tokens is taken as the byte length of the
     serialised request. No tokenizer produces more tokens than bytes for UTF-8 text.
  2. Output is bounded with `maxOutputTokens=2048`, and thinking with `thinkingBudget=1024`
     (counted inside output pricing).
  3. The reservation is `bytes × in_rate + 2048 × out_rate`. It is taken under a lock, and the call
     is refused if the reservation would pass the cap.
  4. Reported `usageMetadata` settles the spend down. **Missing usage, a timeout or a 5xx keeps the
     full reservation.**
  5. Retries (429/503 only, at most 2, each within the cap) reserve again.
- **Caps:**
  - The default run cap is **US$0.10**, and the case writer shares the same class with its own cap.
  - Turn cap: 12.
  - Jev keeps its own `client.Budget`.
- **Price table in code**, with an expiry date:
  - `{"gemini-3.8-flash": {"in": 0.75e-6, "out": 3.75e-6, "valid_until": "2026-12-31"}}`
  - After that date the runner prints `BLOCKED: price table expired` and sends nothing.
  - A human updates the table in a reviewed commit.
- **Failure contract:**
  - A Gemini outage, a safety block, an empty candidate, a malformed function call, or the cap
    being reached ends the run as `incomplete`, with the reason.
  - Jev results that were `unavailable` are passed to the agent as `unavailable`.
- **Report.** The run report is **rendered by code from the tool ledger**: every Jev answer or
  `unavailable`, every `read_file`, and the costs. Gemini's closing prose is shown underneath, labelled
  `agent summary (unverified)`. It never replaces or fills in the ledger.
- **Ledger:** agent model, turns, Jev calls, questions, `files_read`, Gemini tokens reserved and
  reported, Jev US$, Gemini US$, the price table used, and the outcome (`complete` or
  `incomplete: reason`).

## Gemini case writer (`evals/jev_constitution/generate.py --writer gemini`)

- **Same contract as `claude_write()`, opt-in.** Codex labels blind, and a case is admitted **only
  when the writer's label and Codex's label agree** (unchanged). Claude stays the default. Writer
  calls use `GeminiBudget` with a per-run cap (default US$1.00).
- **Frozen control, run before any bulk use,** on `core-44` (already calibrated):
  - **Sampling.** Each writer gets the same schedule, fixed in `gemini-writer-control.json` before
    it runs:
    - 5 hard classes (arithmetic, dates, indirection, irrelevant context, adversarial)
    - 10 requested cases per class, 5 labelled violation and 5 compliant
    - the same seeds and domains
  - **Denominators reported per writer:** requested, returned, malformed, Codex unavailable,
    disagreed and agreed. Nothing is silently dropped.
  - **Independent anchors.** The arithmetic and date classes are generated in a structured form:
    - arithmetic: `numerator`, `denominator`, `claimed_pct`
    - dates: `start`, `end`, `claimed_days`
    - Code computes the true label from those fields. Each writer's label accuracy against code
      truth is reported. This is the one check that doesn't rest on model agreement.
  - **Verdict rule.** `use` requires every one of these:
    - Gemini's agreement is **at least 0.85 absolute**.
    - Gemini's agreement is at least Claude's minus 0.05.
    - Every class has at least 7 of its 10 cases admitted.
    - Gemini's anchor accuracy is **at least 0.95** and not below Claude's.

    Otherwise the verdict is `do-not-use`, with the failing clause named.
  - The file states that **model agreement is proxy evidence, not correctness**.
- **A deliberately failing control** is a test: a fake writer that flips half its labels and gets
  the anchor sums wrong must produce `do-not-use`.

## Tests (offline; fake Jev `post` and fake Gemini transport)

- **Boundary**
  - A glob never yields an unapproved path, even when that file exists on disk.
  - An approved path with changed bytes is refused.
  - A secret planted in the operator prompt → exit 2, zero requests.
  - A secret planted in agent-written `state` or in a choice option → that request is refused and
    not sent.
  - A secret inside a tool result is impossible by construction. The test proves a refusal result
    carries no bytes.
  - `approve --glob` never writes the manifest and lists refused files.
- **Level 9**
  - `cap_255`: 300 approved files → 255 requests, and 45 skipped with the cap reason.
  - Prune reasons are reported.
  - A budget of US$0.01 leaves the rest listed as `budget exhausted`.
- **pick_first**
  - `pick_first_only_real_path`: a key outside the sent set → `unavailable`.
  - `none` or `other`, or confidence under the floor → `none`, with numbers.
  - A malformed reply → `unavailable`, with no numbers.
  - Duplicates are removed.
  - A file literally named `none` is keyed `f00N` and can be picked.
  - More than 250 candidates are capped.
  - Empty candidates → `none`, with zero requests.
- **Level 10**
  - One call per `ask_jev`.
  - 21 paths → refused.
  - An aggregate over 64,000 bytes → refused with per-part sizes.
  - A `command` argument is rejected by the tool schema.
- **Agent runner**
  - No key → `BLOCKED`, exit 2.
  - An expired price table → `BLOCKED`, zero requests.
  - A reservation over the cap → no request.
  - Missing `usageMetadata` keeps the full reservation.
  - A scripted fake Gemini calling `ask_jev_files` → `jev_calls=1`, `files_read=0`.
  - `read_file` on an unapproved path → refusal with no bytes.
  - The turn cap → `incomplete`.
  - A Gemini 500 → `incomplete`, with the ledger intact.
  - The key string never appears in the ledger, stdout or stderr.
- **Writer**
  - A fake reply is parsed into the case shape.
  - Malformed JSON → counted as malformed, not written.
  - The deliberately failing control → `do-not-use`.
  - Anchor maths is computed by code.
- **Mutation:** each new guard gets a mutant in `tests/mutation/jev_platform_mutants.py`, and all
  must be killed (C11). The guards are:
  - glob-over-manifest
  - outbound `sensitive()`
  - the reservation-before-send
  - usage retention
  - the price expiry
  - the pick key check
  - the 255 cap
  - the 64,000 aggregate
  - the verdict clauses

## Live evidence (after the offline gates are green)

- **`level9-live.json`**
  - **Target:** the video's own sandbox (`disler/ten-levels-of-jev@777adaf`,
    `apps/ten-levels/sandbox`), copied into a scratch git repo.
  - **Approval:** its `.jev-approved.json` is produced by `approve --glob` and reviewed. Every
    approved file is read by the reviewer before commit.
  - **Prompts:** the three screenshot prompts, verbatim.
  - **Pass condition (C15):**
    - Each run makes at least one Jev call.
    - Prompts 1 and 2 open zero files.
    - Prompt 3 opens exactly one file.
    - The pick is recorded against the video's `src/domain/billing.ts`; a different pick is
      reported as a disagreement.
- **`gemini-writer-control.json`**, as above (C16).

## Out of scope

- Command execution (RA-7841).
- Any hook or gate acting on an answer; shadow-only stays in force.
- Writes and edits from the runner.
- Bulk generation for the remaining 525 rules, which follows the control verdict.
- Concurrency.
- The estate `jev` SKILL.md, which is already planned in PLAN-ask §5 and gains Level 9/10 usage
  after this ships.

## Risks

- **Free-tier training.** On the free tier, Google may use prompts to improve its products. Only
  approved bytes and synthetic scenarios are sent. Whether the key's project is billed is
  **UNVERIFIED**, and the ledger records the price table used.
- **Agents do what agents do.** C15 records what the agent did, not what it was told.
- **Bulk approval can become rubber-stamping.** It is still a human-committed diff of paths and
  hashes. It lowers the chore without removing the review.

## Rev 2 changes (answers to judge-scale-r1)

1. **Public-origin boundary removed.** The manifest stays the only disclosure boundary. Globs run
   over approved paths, and bulk approval is human-committed. Provenance of `origin/main` is no
   longer relied on.
2. **Outbound payload admission.** It covers the operator prompt, agent state, questions, criteria,
   options, pick lists and tool results, for both providers.
3. **Prepaid Gemini reservation before every attempt.** Output and thinking are bounded,
   reservations are retained on uncertain failure, the price table expires, and the writer shares
   the budget type.
4. **Failure contracts.** `picked` / `none` / `unavailable` are separate for `pick_first`. Runs
   are `incomplete`. The report is code-rendered and prose is labelled unverified.
5. **Writer control.** It now has a frozen schedule, an absolute floor, full denominators, per-case
   agreement admission, code-computed anchors, a proxy-evidence statement and a deliberately failing
   control.
6. **Picker limits.** 250 candidates with `f` keys, plus `none` and `other`, is at most 252. It
   handles empty lists, duplicates and collisions.
7. **Level 10 size.** Checked on serialised bytes, not a token claim; the aggregate is refused with
   part sizes.
8. **Concurrency deferred.**
