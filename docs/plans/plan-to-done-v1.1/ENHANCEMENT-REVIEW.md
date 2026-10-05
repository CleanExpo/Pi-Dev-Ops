# plan-to-done — enhancement review, v1.0 → v1.1

Review date: 28 September 2026, Australia/Brisbane. Reviewer: Claude (claude.ai session),
author-side review with tool evidence. Not an independent model review; not a behavioural trial.

## 1. What was actually verified here

| Check | Result | Evidence |
|---|---|---|
| Package integrity | All 15 files match `MANIFEST.sha256` | `sha256sum -c` → 15 × OK |
| skill-creator structural validation (`scripts/quick_validate.py`) | **FAIL** | `Unexpected key(s) in SKILL.md frontmatter: argument-hint, disable-model-invocation. Allowed properties are: allowed-tools, compatibility, description, license, metadata, name` |
| skill-creator packaging (`scripts/package_skill.py`) | **FAIL** (same error; no `.skill` produced) | validator is a hard gate in the packager |
| Entry length / links (v1.0) | 154 lines; 16 relative links resolve when laid out as `plan-to-done/references/` | matches VALIDATION-REPORT.json |
| v1.1 SKILL.md | 182 lines (≤200); 14 links resolve; description 367 chars (<1,536 cap) | measured |
| Boundary hook | deny/allow behaves as specified on 6 synthetic tool calls | run locally with a `jq` shim; real `jq` required on hosts |
| Eval suite | 30 cases + graders written in `claude plugin eval` format | **not executed** |

The frontmatter failure is not a defect in the Library's Claude Code usage — those two fields are
valid there — but it means the package as shipped cannot be uploaded to claude.ai, sent through the
Skills API, or packaged with `package_skill.py`, so it cannot reach Cowork or cloud sessions by the
account-sync route. Source: Claude Code skills reference, "Using skill frontmatter outside Claude Code"
(https://code.claude.com/docs/en/skills).

## 2. Findings against skill-creator

| # | Finding | Consequence | Disposition in v1.1 |
|---|---|---|---|
| S1 | Frontmatter uses two Claude Code–only fields | Upload/packaging hard-fails (verified above) | Kept, deliberately: `disable-model-invocation: true` is the correct safety semantics for a planning skill in an autonomous fleet (it also stops preloading into subagents and scheduled-task invocation). The trade-off is recorded; the alternative (spec-only frontmatter + `skillOverrides: "user-invocable-only"`) is shipped as `hooks/settings-snippet.json` for a host that must sync via claude.ai. Decide once at Library level; see §6 D1. |
| S2 | skill-creator asks for a "pushy" description with explicit trigger contexts | v1.0 description was one sentence; with `disable-model-invocation` the description is not in Claude's context anyway, so triggering is moot — but the `/` menu and any future flip to model-invocable both benefit | Description rewritten with trigger contexts and an explicit "not for" clause (367 chars). |
| S3 | skill-creator's core loop is draft → run with/without → grade → iterate; the package's `evaluation-cases.json` is a custom format neither skill-creator nor `claude plugin eval` can read | 30 well-specified cases that cannot run | Converted to the official `claude plugin eval` suite (`evals/`, 30 cases, 128 files). The custom JSON stays in `references/` as the source of record; the format is retired for execution. |
| S4 | skill-creator recommends bundling repeated helper work as `scripts/` | The package repeated "observe tool attempts, not text" in prose only | Deterministic graders (`tool_used`, `file_exists`, `regex`) now encode every must_not_do that maps to an observable action. |
| S5 | skill-creator: "explain the why", avoid all-caps MUSTs where possible | v1.0 is heavy on hard rules; acceptable for a safety-critical command skill | No change. The Library's house manner (single-job boundary, fixed section order) governs. |
| S6 | `allowed-tools` is a per-turn permission grant, not a restriction ("It does not restrict which tools are available") | VALIDATION-REPORT's `no_blanket_shell_tool_declared` is a paperwork check, not enforcement | `hooks/planning-boundary.sh` (PreToolUse `permissionDecision: deny`) is the enforcement layer; the skill now says so in step 1. |

## 3. Findings against the harness doctrine already in force

These are conflicts between the package and decisions recorded since 10 September 2026. They are new
information for the package, not re-diagnosis.

| # | Package says | Standing doctrine says | v1.1 |
|---|---|---|---|
| H1 | `ACCEPTED` = "the relevant human acceptance is recorded"; "Human authority determines whether an action may happen" | 10/09/2026: all PRs authorised autonomously by cross-model audit (Board members + SPM), Phill out of the loop; the only guardrails are money ($0 new spend, $5/day metered), no irreparable change, no change to the foundation | Step 1 binds the live authority model; Output format redefines ACCEPTED as the cross-model audit receipt; Hard rule 9 encodes the spend guardrail. |
| H2 | Receipts bind to "candidate commit or dirty-tree digest"; pr-release-gate "exact-head" language | THROUGHPUT LAW v1: receipts bind to the diff (`git patch-id`), not the SHA; review rounds capped at two; gate once per lap | Step 7 and Output format updated; patch list §5 for `delivery-design.md`, `writing-contract.md`, `reuse-map.md`. |
| H3 | Planning-only; "Deliver and stop" | "Every session must produce build output or a named blocker; never end in planning mode"; valid endings SHIPPED / BLOCKED-EXTERNAL / AWAITING PHILL | Step 10 writes `handoff.json` (machine-readable next action) and ends only in REVIEW_READY-with-next-action or BLOCKED-EXTERNAL. The dispatcher, not the skill, decides whether a grant covers the next action. |
| H4 | "No live Jev calls, even for shadow" | $5/day metered ceiling exists precisely so cheap advisory calls can run | Step 8 permits a shadow call only on non-sensitive, ≤32k state, under the ceiling, recorded ADVISORY; otherwise DISABLED. Cost never gates it (a 32k-state call ≈ $0.0013); egress does. |
| H5 | Independent review "when authorised and available; otherwise NOT_RUN" | The cross-model audit board is the standing reviewer | Step 9 names the mechanisms: Codex `gpt-6-sol` read-only pass (receipt), then `workflows/plan-review.js` clean-context pass (advisory). NOT_RUN is retired as the default. |

## 4. Findings against the platform as it stands on 28 September 2026

All rows are from primary vendor pages unless marked (third-party). URLs are in
`references/model-and-plan-routing.md`.

| # | Fact (verified) | Effect on this skill |
|---|---|---|
| P1 | Opus 5.5 is current ($4/$20, 1M ctx, always-on thinking, default effort `medium`); Fable 5.1 is the top tier ($10/$50) and on Max is capped at 50% of the weekly limit and draws it faster | Planner runs Opus 5.5 at `effort: high` (frontmatter field verified); Fable reserved for final reconciliation; Sonnet 5 workers under workflows. |
| P2 | `claude -p` and the Agent SDK still draw from the subscription (separate credit paused 15 June 2026) | Headless Pi-Dev-Ops runs on Max cost $0 marginal but share the same limit pool as Cowork/chat. |
| P3 | The `ultracode` keyword is inert from `-p`, the SDK, scheduled tasks and webhooks (v2.1.210+) | Any headless orchestration must use `--effort ultracode` / the `ultracode` setting or Workflow permission rules; a prompt containing the word does nothing. |
| P4 | A workflow pauses at a usage limit only in an interactive claude.ai-subscription session; in `-p`, SDK, background and teammate sessions the agent fails | Dispatcher retry design must treat usage-limit failures as expected and schedule on reset. The package's recovery plan lists "quota limits" but assumes a pause. |
| P5 | Dynamic workflows: script-held plan, schema-validated `agent()` output, deterministic replay, 1,000 agents/run, 16 concurrent, saveable as a command, distributable in a plugin; official docs describe adversarial cross-review as a supported pattern | The review step is now a saved workflow (`workflows/plan-review.js`, DRAFT_UNTESTED), which is the runtime the Snake Build Pattern wants (orchestrator visible, agents underground). |
| P6 | `claude plugin eval` (v2.1.269+): with/without arms, six grader types, `--threshold`, `--max-cost-usd`, exit codes, isolated `claude -p` children | This is the AAA gate. The suite is written; the gate definition is in `evals/README.md` as *proposed*. |
| P7 | Claude Code skills follow the Agent Skills spec; only six fields survive upload; `allowed-tools` grants, doesn't restrict; `disallowed-tools`, `context: fork`, `hooks`, `effort`, `model` exist | See S1, S6; `effort: high` added; `context: fork` deliberately not used on the main skill (untested behaviour change). |
| P8 | Codex: GPT-6 Astra/Sol/Luna are the recommended models; **GPT-5.5 retires from Codex with ChatGPT sign-in on 14 Oct 2026**; `codex exec -m gpt-6-sol`; `sandbox_mode = "read-only"` + `approval_policy = "on-request"` (`untrusted` removed) | Pin `gpt-6-sol` in the audit board config now. Read-only sandbox makes Codex a genuine non-editing reviewer. |
| P9 | MiniMax M3: 1M context; Anthropic-compatible endpoint `https://api.minimax.io/anthropic`; $0.30/$1.20 per MTok (≤512K input), cache read $0.06 | $5/day ≈ 16.7M input tokens of read-only discovery. Reader lane only; never the writer; never on secret material. |
| P10 | Jev 1.13: `POST /v1/systemone`, $0.042/MTok input, output free, **64k per request / 32k state**, text only, rate limits adjusting dynamically; official Claude Code install is a plugin marketplace (`typesafe@typesafe-ai`) | The package's decision contracts must be chunked/shortlisted to 32k state (typesafe-planning.md already implies it; now explicit). The Library's pinned-vault intake and the vendor's auto-updating plugin are two different routes — §6 D2. |
| P11 | Agent SDK / Opus 5.5 breaking changes: thinking can't be disabled, forced tool use errors, thinking blocks tied to model+conversation (also Fable 5.1) | Any harness code that forced tool choice or toggled thinking on Opus 5 must be migrated before pointing it at 5.5. Not a skill change; recorded for the platform team (Rana). |

## 5. Change log — every addition retires something

| Added | Retired |
|---|---|
| `evals/` — 30 cases in `claude plugin eval` format, deterministic safety graders, README with the proposed AAA gate | `evaluation-cases.json` as an *executable* format (kept as source of record) |
| `hooks/planning-boundary.sh` + `hooks/settings-snippet.json` — PreToolUse deny outside planning paths; deny build/install/push/network commands | Reliance on `allowed-tools` prose and the `no_blanket_shell_tool_declared` paperwork check as "boundary" |
| `workflows/plan-review.js` (DRAFT_UNTESTED) — adversarial, clean-context, schema-validated review with a second verification pass | "Independent review: NOT_RUN" as the default outcome of step 9 |
| `references/model-and-plan-routing.md` — verified lanes, prices, limits, headless constraints, $5/day arithmetic | Unwritten assumptions about which plan pays for what; the "Do not assume a product subscription includes API access" caution is now a verified fact table |
| `.claude-plugin/plugin.json` — so `claude plugin validate` / `claude plugin eval` can target the directory | Nothing; explicitly *not* a catalogue registration (integration-and-portability.md step 6 still governs) |
| SKILL.md v1.1: `effort: high`; authority binding; patch-id; Jev shadow rule; concrete review mechanisms; `handoff.json`; Hard rule 9 | Human-signature ACCEPTED; SHA-bound receipts; "NOT_RUN" default; prose-only boundary |

Nothing in `references/` (the eleven v1.0 files) was edited. Their v1.0 hashes still verify. The
edits they need are listed below so an authorised revision can apply them without transplanting
this review's wording as if it were accepted.

## 6. Patch list for the unchanged v1.0 references (apply on an authorised revision)

- `delivery-design.md` › "Verification and release evidence": replace "candidate commit or dirty-tree
  digest" with "the diff's `git patch-id` (THROUGHPUT LAW v1); a SHA is recorded for provenance, not
  binding". › "Three different controls": add that for repositories under the 10/09/2026 decision the
  authority receipt is the cross-model audit record, and that the three guardrails are deterministic gates.
  › "Durable work and recovery design": add "a usage-limit failure in a headless run is a scheduled
  retry at the reset time, not a diagnostic case" (source: workflows doc, P4).
- `writing-contract.md` › "Planning manifest": add `patch_id`, `authority_model`, `review_receipts[]`
  (kind, model, identity, input patch-id, outcome) and a `handoff.json` mirror of the operator brief.
- `review-and-evaluation.md` › "Packet review sequence" step 4: name the two mechanisms (Codex read-only
  pass = receipt; `plan-review` workflow = advisory). › "Skill evaluation protocol": point at `evals/`
  and `claude plugin eval`; keep the multi-trial and held-out rules (they map to `--runs 3` and a
  `--tag` split). › "Proposed promotion requirements": add "Δ > 0 on `smoke`; `arm: both` safety
  graders at 1.0; `--max-cost-usd 5`".
- `reuse-map.md` › "Upstream TypeSafe adoption": record that the vendor's official route is now a Claude
  Code plugin marketplace with auto-update; the Library's pinned-vault route is a deliberate divergence
  and must be justified (decision D2). › "Unresolved bindings": add "`claude -p` slash-invocation of
  `/plan-to-done`" and "`jq` present on every host for the boundary hook".
- `typesafe-planning.md` › "Roles": replace "This planning skill makes no live TypeSafe calls, including
  observation-only calls" with the step-8 shadow rule. › "Decision contract fields": add "state size
  ≤32k tokens; request ≤64k; chunking strategy". › "Suitable advisory decisions": note the official
  skill-suggestion cookbook already targets the Hermes catalog the harness runs on.
- `integration-and-portability.md` › "Host contract": add `jq` and the hook's install path; note that
  `permissions.deny` does not protect hook files from Edit/Write (anthropics/claude-code#11226) so the
  hook must live in managed settings or a path the session cannot write.
- `source-ledger.md`: append the 28/09/2026 sources listed in `model-and-plan-routing.md`.

Decisions this package cannot make (owner: Library maintainer, i.e. the audit board under the 10/09
decision, or Phill for the money line):
- **D1** Frontmatter policy: keep Claude Code fields (no claude.ai sync) or go spec-only + `skillOverrides`.
- **D2** TypeSafe intake: vendor plugin marketplace (auto-update, official) vs the Library's pinned vault.
- **D3** Whether the `plan-review` workflow counts toward the "two review rounds" cap or sits outside it.

## 7. What remains unverified after this review

- No eval case has run. No Δ, pass rate, cost or latency exists. The "AAA gate" is a proposal.
- `workflows/plan-review.js` has not been executed; it uses only documented primitives but the
  exact `schema` handling and return shape were not exercised.
- The boundary hook was exercised with a Python `jq` shim, not real `jq`, and not inside Claude Code.
- Whether `claude -p` treats a leading `/plan-to-done` as a skill invocation was not tested.
- The Library's current frontmatter schema (private repo) was not re-read on this date.
- No pressure-test trials, no cross-model review of this review, no host installation.
- Third-party figures (Max/Pro dollar prices, "5-hour limits raised 20%") were not confirmed on a
  first-party page and are labelled as such in the routing reference.
