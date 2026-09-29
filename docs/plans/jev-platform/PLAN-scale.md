# Jev Platform: Levels 9 and 10, a Gemini Flash agent, and a cheaper case writer — plan

Status: DRAFT rev 4 · 29/09/2026. It builds on PLAN.md rev 5 and PLAN-ask.md rev 4, both approved
100/100. Done contract v7 (`w_9a6c73db7577`, criteria C12–C16) is locked against this plan.
Rev 1 scored 72/100 (`judge-scale-r1.md`) and rev 2 scored 84/100 (`judge-scale-r2.md`). Rev 3
scored 94/100 (`judge-scale-r3.md`). Rev 4 answers its three items; see "Rev 4 changes" at the end.

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

## The boundary: positive admission only (rev 3)

**Nothing leaves the machine unless its exact content was reviewed, or code assembled it from reviewed
parts.** Screening with `sensitive()` stays, but only as defence in depth; it is never the reason
something may be sent. Public visibility is not used at all.

`.jev-approved.json` at HEAD holds three reviewed lists:

- **`files`** — path → sha256, exactly as Level 8. Reads use Level 8's `admit()`: a confined
  `O_NOFOLLOW` read, the deny-list, `sensitive()`, the 32,000-byte cap, and a digest match.
- **`questions`** — reviewed templates, exactly as Level 8. They gain one optional field,
  `"state": ["content"] | ["task", "content"] | ["task", "files"]`, which says which code-assembled
  state fields the template reads. It defaults to `["content"]`.
- **`prompts`** (new) — prompt id → exact operator prompt text. The runner takes `--prompt-id`,
  **never free text**. The three screenshot prompts are approved verbatim in the live-run repo's
  manifest.

**What the agent may choose, and what code sends.**

- **The agent chooses only identifiers:** template ids, approved paths, and glob patterns. Glob
  patterns are matched against the manifest's `files` keys, never the disk, and are never sent to
  anyone.
- **Every Jev request is assembled by code** from reviewed parts:
  - template text
  - approved file bytes
  - `task` = the approved prompt's exact text
  - pick-first `files` = `{f001: path, ...}` over approved paths
- **No model-written text reaches Jev.**
- **Gemini receives:**
  - the approved prompt
  - the list of approved paths and template ids, with each template's reviewed text
  - code-built tool results
  - `read_file` bytes, which pass through `admit()`
  - its own earlier turns echoed back, since Gemini already holds them and that is no new
    disclosure
- **Tool results shown to the model are a minimal projection:**
  - per file: `path` and `template_id`, then the typed answer, `unavailable: <reason>`, or
    `refused: <reason>`
  - **no sha256, no bytes, no error bodies**
  - hashes, raw responses and costs stay in the local ledger only
  - the projection is tested to pass `sensitive()` (its hex rule would otherwise reject sha256
    strings, `client.py:27`)
- **Agent-proposed questions.** When the agent wants a question no template covers, it may call
  `propose_template`. That records the proposal in the local run report under
  `proposed templates (not sent, needs review)` and returns `recorded, not sent`. A human
  reviewing it and committing it to `questions` is the only way it can ever be sent **to Jev**. The
  proposal's own function-call arguments are echoed back to Gemini in the conversation history,
  which is Gemini's own output and no new disclosure (the echo rule above). This is how
  the video's "agent writes its own questions" arrives here: the agent drafts them and a human
  admits them.
- **Defence in depth.** Every serialised outbound payload, Jev or Gemini, still passes
  `sensitive()`. A hit refuses the request and is recorded.
- **Bulk approval.**
  - `python -m jev_platform approve --glob G` prints `files` entries for matching tracked files
    that pass `_DENY_NAMES` and `sensitive()`, and lists the refused ones with reasons.
  - `approve --prompt-file F --id ID` prints a `prompts` entry.
  - Neither ever writes the manifest; a human reviews and commits it.
- **Template/state compatibility, checked before any send.** Each tool builds exactly one state
  shape and accepts only templates that declare it:

  | Tool | State built by code | Templates accepted (`state` field) |
  |---|---|---|
  | `ask_jev_files` without a prompt id | `{content}` | `["content"]` (the default) |
  | `ask_jev_files` with a prompt id | `{task, content}` | `["content"]` or `["task", "content"]` |
  | `pick_first_file` | `{task, files}` | `["task", "files"]` |
  | `ask_jev` (Level 10) | `{task, files}` | `["task", "files"]` |

  - An incompatible template id is refused before any request, with
    `refused: template <id> reads <fields>, this tool sends <fields>`.
  - Templates must name, in their own text, every field they declare (checked at load).
  - The live-run manifest gets `known-issue`, `touches-auth` and `layer` as `["content"]`,
    `relevant-to-task` as `["task", "content"]`, and `pick-first-for-task` and
    `triage-bundle` as `["task", "files"]`.
- **Question shape (templates).**
  - At most 8 questions per call, each at most 1,000 characters.
  - `noul` needs non-empty `true` and `false` criteria.
  - `choice` needs 2–250 options, and `other` is added when absent.
- **Git subprocess environment.**
  - `approved_manifest()` runs `git show HEAD:.jev-approved.json` with a **fixed minimal
    environment**: `PATH=/usr/bin:/bin:/opt/homebrew/bin`, `HOME`, `GIT_CONFIG_NOSYSTEM=1`, and
    `GIT_TERMINAL_PROMPT=0`. It never uses the inherited environment, so neither `GEMINI_API_KEY`
    nor `TYPESAFE_API_KEY` reaches a child process.
  - It is the only subprocess in the Level 9/10 and runner paths.

## Level 9: `ask_jev_files` and `pick_first_file` (`jev_platform/scout.py`)

- **`scout_files(repo, patterns, template_ids, post, budget, prompt_id=None)`:**
  - expands `patterns` over the manifest, then prunes
  - enforces the **255-file cap before any request**; the rest are listed as
    `over the 255 file cap; narrow the pattern`
  - makes one Jev call per file, **sequentially**; concurrency is deferred
  - output per file: path, sha256, then answers or `unavailable`; plus the `skipped` list
- **Budget.** It reuses the atomic `client.Budget`, whose `reserve()` holds a lock (`client.py:52-59`).
  - Each attempt reserves US$0.002688, so 255 files need US$0.685.
  - The scout's `--max-usd` default is **US$0.75**, which is 279 attempts.
  - Files left unsent when the cap is hit are listed as `budget exhausted`.
- **`pick_first(prompt_id, template_id, candidates, post, budget, floor=0.3)`:**
  - Candidates are deduplicated, capped at **250**, and keyed `f001…f250`. Keys are never the path
    text, so a file named `none` or `other` cannot collide.
  - The state is built by code as `{task: <approved prompt text>, files: {key: path}}`, and the
    question is the reviewed template's text. The choice is `f001…fN` plus `none`, and
    `other` is added automatically, so there are at most 252 options, under Jev's 255.
  - **Results are distinct:**
    - `picked`: path, confidence, probabilities
    - `none`: Jev chose `none` or `other`, or confidence was under the floor, with the numbers
      shown
    - `unavailable`: transport failure, malformed, a missing answer, or a key outside the sent set.
      No numbers are given.
    - Empty candidates give `none`, with zero requests.

## Level 10: `ask_jev` (same module)

`ask_jev(repo, prompt_id, paths, template_ids)` makes **one** Jev call. Code builds the state as
`{task: <approved prompt text>, files: {path: content}}` from:
- up to 20 approved `paths`, each admitted as above
- up to 8 templates declaring `state: ["task", "files"]` (any other is refused before sending)

Size is checked on the **serialised request bytes**, not on tokens. When the aggregate goes over
`client.MAX_REQUEST_BYTES` (64,000), the call is refused before sending, with the per-part byte
sizes. Twenty files that are each valid can still be refused this way.

**What Level 10 means here.**
- The agent decides when to call Jev, which approved paths to bundle, and which reviewed questions
  to ask, and it can draft new questions through `propose_template`.
- It does **not** send its own prose. That is a deliberate narrowing of the video's Level 10, and
  the reason is in the boundary section.

**No `command` field.** The video runs the agent's command through its Level 6 bash gate. We have
no Level 6 gate: that is RA-7841, a founder decision. The video's own `ask-jev.ts:31` also passes
the key to the child's environment. The command half is filed under RA-7841.

## The Gemini agent runner (`jev_platform/agent.py`, `python -m jev_platform agent`)

A Python loop over Gemini `generateContent` with function calling.

- **Model, key and prompt.**
  - The model is pinned to `gemini-3.8-flash`, with `thinking_level: "low"`.
  - A missing `GEMINI_API_KEY` prints `BLOCKED` plus the route
    (`cd ~/Pi-Dev-Ops/dashboard && vercel env run -e production -- …`, where the founder placed the
    key on 29/09), then exits 2.
  - The key goes only in the `x-goog-api-key` header and is never logged.
  - `--prompt-id` must name an approved prompt. Anything else means exit 2 with zero requests.
- **Tools:**
  - `ask_jev_files(patterns, template_ids)`
  - `pick_first_file(template_id, paths)`
  - `ask_jev(paths, template_ids)`
  - `read_file(path)` — the only way file bytes reach Gemini, through `admit()`
  - `propose_template(...)` — records the proposal locally, never sends it
- **No tools for:** write, edit, shell, approve or the network. The screenshots' "fix it and run
  npm test" step is out of scope.
- **Prepaid, provider-counted reservation before every attempt** (`GeminiBudget`, a lock plus a
  fixed attempt cap, the same pattern as `client.Budget`):
  1. **Input is counted by Google.** Before each `generateContent`, the **identical request body**
     goes to `models/gemini-3.8-flash:countTokens` as `generateContentRequest`. The API reference
     describes that field as "the prompt as well as other model steering information like system
     instructions, and/or function declarations". Its `totalTokens` is the input reservation.
     - A `countTokens` failure means the request is not sent: the run ends `incomplete`, with the
       reason.
     - **Billing of the count call is documented as zero.** Google's Firebase AI Logic docs, which
       front the Gemini Developer API, say: "There's no charge for calling `countTokens` (the Count
       Tokens API). The maximum quota for the Count Tokens API is 3000 requests per minute (RPM)."
       (firebase.google.com/docs/ai-logic/count-tokens, fetched 29/09.)
     - **The price table carries the count price explicitly** (`"count": 0.0`), with the same
       `valid_until` expiry. When it is non-zero, it is reserved **before each count attempt** as
       `serialised request bytes × count` under the same lock and cap. A count call that the cap
       cannot cover is not made.
     - **A hard count-call cap:** at most `2 × turn cap` (24) per run, including retries, and
       likewise per writer batch. The cap stops the run as `incomplete: count cap`.
     - Count calls are recorded in the ledger (attempts, successes, reserved US$). A 429 on count is
       retried under the same retry rule and cap.
  2. **Output is hard-bounded by Google.** `maxOutputTokens: 2048`. The thinking doc says
     `max_output_tokens` "sets the maximum number of tokens a response can generate, including
     thought tokens" and "acts as a hard cutoff enforced by the infrastructure". A reply cut off
     there is `incomplete`.
  3. **Reservation formula:** `totalTokens × in_rate + 2048 × out_rate`, taken under the lock. If
     it would pass the cap, the request is not sent.
  4. **Settling.** Reported `usageMetadata` settles the spend down. **Missing usage, a timeout or
     a 5xx keeps the full reservation.**
  5. **Overrun tripwire.** If the reported `promptTokenCount` is ever above the counted
     `totalTokens`, the run stops `incomplete: overrun`, keeping the larger figure. This is a
     tripwire on the provider's count, not the bound itself.
  6. **Retries** (429/503 only, at most 2) count and reserve again.
- **Caps:**
  - Run cap: **US$0.10**.
  - Turn cap: 12.
  - Jev keeps its own `client.Budget`.
  - The case writer uses its own `GeminiBudget` (default US$1.00).
- **Price table in code**, with an expiry date:
  - `{"gemini-3.8-flash": {"in": 0.75e-6, "out": 3.75e-6, "valid_until": "2026-12-31"}}`
  - After that date the runner prints `BLOCKED: price table expired` and sends nothing.
- **Failure contract:**
  - A Gemini outage, safety block, empty candidate, malformed function call, overrun or cap ends
    the run as `incomplete`, with the reason.
  - Jev `unavailable` results reach the agent as `unavailable`.
  - The ledger's `jev_calls` is counted from the client's own send log, never from the model's
    claims.
- **Report.** The run report is **rendered by code from the ledger**: every Jev answer or
  `unavailable`, every `read_file`, every `propose_template`, and the costs. Gemini's closing prose
  is shown underneath, labelled `agent summary (unverified)`. It never fills a gap in the ledger.
- **Ledger:**
  - agent model, turns, Jev calls, questions, `files_read`
  - Gemini tokens (counted, reserved and reported), `countTokens` calls
  - Jev US$, Gemini US$, the price table used
  - outcome: `complete` or `incomplete: reason`

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

## Tests (offline; fake Jev `post`, fake Gemini transport)

- **Boundary**
  - A glob never yields an unapproved path, even when that file exists on disk.
  - An approved path whose bytes have changed is refused.
  - An unknown `--prompt-id`, or free text in its place → exit 2, zero requests.
  - A Jev request body contains only template text, approved bytes, the approved prompt text and
    `f`-keys. The test recomputes the body from those parts and compares bytes.
  - `propose_template` never reaches Jev: no Jev request body contains any proposal text, at any
    point in the run. Its arguments do appear in later Gemini requests, only as Gemini's own echoed
    function call, which is the same-provider echo the boundary already permits. The test asserts
    that and nothing wider. The function result returned is the fixed string `recorded, not sent`.
  - The model-visible projection holds no sha256 and no bytes, and passes `sensitive()`. The local
    ledger still holds the hashes.
  - A secret planted in an approved file whose digest is refreshed by a bad actor is still refused
    by `sensitive()`.
  - `approve --glob` and `approve --prompt-file` never write the manifest.
  - The git subprocess environment holds no variable matching `KEY|TOKEN|SECRET`, even when the
    parent has `GEMINI_API_KEY` and `TYPESAFE_API_KEY` set.
- **Level 9**
  - `cap_255`: 300 approved files → 255 requests, and 45 skipped with the cap reason.
  - Prune reasons are reported.
  - A budget of US$0.01 leaves the rest listed as `budget exhausted`.
- **pick_first**
  - `pick_first_only_real_path`: a key outside the sent set → `unavailable`.
  - `none` or `other`, or confidence under the floor → `none`, with numbers.
  - Malformed → `unavailable`, with no numbers.
  - Duplicates are removed.
  - A file named `none` is keyed `f00N`.
  - More than 250 candidates are capped.
  - Empty candidates → `none`, with zero requests.
- **Compatibility**
  - Each tool with a compatible template → sends, and the body holds exactly the declared fields.
  - Each tool with an incompatible template → refused, with zero requests.
  - A template whose text omits a declared field → rejected at manifest load.
- **Level 10**
  - One call per `ask_jev`.
  - 21 paths → refused.
  - An aggregate over 64,000 bytes → refused, with per-part sizes.
  - A `command` argument is rejected by the tool schema.
- **Runner**
  - No key → `BLOCKED`, exit 2.
  - An expired price table → `BLOCKED`, zero requests.
  - The `countTokens` body equals the `generateContent` body, byte for byte.
  - A `countTokens` failure → no `generateContent`, and the run is `incomplete`.
  - A price table with `count > 0` reserves before each count; a cap too small for the count
    reservation → no count call and no generate call.
  - The 25th count call in a run is refused (`incomplete: count cap`), retries included.
  - A 429 on count is retried within the cap, and exhausted retries → `incomplete`.
  - A reservation over the cap → no request.
  - Missing `usageMetadata` keeps the full reservation.
  - Reported prompt tokens above counted → `incomplete: overrun`.
  - A scripted fake Gemini calling `ask_jev_files` → `jev_calls=1`, `files_read=0`.
  - A fake Gemini claiming extra Jev calls in its prose → the ledger still counts the sends.
  - `read_file` on an unapproved path → refusal with no bytes.
  - The turn cap → `incomplete`.
  - A Gemini 500 → `incomplete`, with the ledger intact.
  - The key string never appears in the ledger, stdout or stderr.
- **Writer**
  - A fake reply is parsed into the case shape.
  - Malformed JSON → counted as malformed, not written.
  - The deliberately failing control → `do-not-use`.
  - Anchor maths is computed by code.
- **Mutation** (`tests/mutation/jev_platform_mutants.py`, all killed, C11). One mutant each for:
  - glob over the disk instead of the manifest
  - a free-text prompt accepted
  - agent text placed into a Jev body
  - `propose_template` sending
  - a sha256 leaking into the projection
  - the inherited environment passed to git
  - `countTokens` skipped
  - the count cap removed
  - a non-zero count price not reserved
  - reserving before the count
  - usage retention dropped
  - overrun ignored
  - price expiry ignored
  - the pick key check removed
  - `unavailable` converted to `none`
  - `unavailable` converted to an answer with numbers
  - the ledger counting model claims
  - the 255 cap
  - the 64,000 aggregate
  - each writer verdict clause

## Live evidence (after the offline gates are green)

- **`level9-live.json`**
  - **Target:** the video's own sandbox (`disler/ten-levels-of-jev@777adaf`,
    `apps/ten-levels/sandbox`), copied into a scratch git repo.
  - **Approval:** its `.jev-approved.json` is produced by `approve --glob` and `approve
    --prompt-file`, then reviewed. Every approved file and the three screenshot prompts are read
    by the reviewer before commit. The templates are `known-issue`, `touches-auth`, `layer`
    (http_handler, domain_logic, data_access, other), `relevant-to-task` and `pick-first-for-task`.
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

## Rev 3 changes (answers to judge-scale-r2)

1. **Positive admission replaces screening as the boundary.** Reviewed `prompts` (by id) and
   reviewed templates only. The agent selects identifiers, and code assembles every Jev body. Agent
   drafts go through `propose_template`, which records and never sends.
2. **A provider-counted reservation.** `countTokens` runs on the identical `generateContentRequest`.
   `maxOutputTokens` is documented as including thinking and as a hard infrastructure cutoff. A
   `countTokens` failure means no send. An overrun is a tripwire. `countTokens` billing is
   UNVERIFIED and counted.
3. **A model-visible projection** with no hashes, bytes or error bodies. Hashes stay in the local
   ledger, and the projection is tested against `sensitive()`.
4. **The git subprocess gets a fixed minimal environment**, tested with both keys set in the parent.
5. **Mutations added** for unavailable→none, unavailable→answer, ledger fabrication, and every new
   disclosure and reservation guard.
6. **Case writer disclosure, stated.** The Gemini writer sends the rule's verbatim Constitution
   quote plus the fixed writer prompt in `generate.py`. That is the same content `claude_write()`
   already sends to Claude, now also to Google, at the founder's 29/09 direction. No file bytes
   are included.

## Rev 4 changes (answers to judge-scale-r3)

1. **Count-call billing.** It is documented as free (quoted, with source and fetch date). The
   price table still carries an explicit `count` rate with an expiry, reserved before each count
   attempt whenever it is non-zero. A hard count-call cap is added (24 per run, retries included).
   All of it is tested, with bypass mutants.
2. **Proposal echo.** The contract is explicit: proposals never reach Jev. Gemini sees only its own
   echoed function call. The test is narrowed to exactly that.
3. **Template/state compatibility.** There is one state shape per tool, a declared `state` on every
   template, refusal before send on a mismatch, and a load-time check that the template text names
   its fields. Tests cover both paths.
