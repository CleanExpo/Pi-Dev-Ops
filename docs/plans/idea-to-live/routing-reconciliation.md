# Routing reference vs Pi-Dev-Ops code — reconciliation, 28 September 2026

**Reference under test:**
[model-and-plan-routing.md](../plan-to-done-v1.1/plan-to-done/references/model-and-plan-routing.md)
(package v1.1, unmodified; byte-identical to the text supplied in session except one trailing blank line).
**Code revision:** `6121037` (main). Every code cite below was re-read in this session.

**Rule for reading this file.** Code is what runs. Where the reference disagrees with code it is a
**PROPOSAL**: nothing changes until a code change lands with its own tests. Where they agree the row
says **MATCHES CODE**. Nothing here edits either side.

## Disagreements and agreements

| # | Reference says | Code says | Status |
|---|---|---|---|
| 1 | Metered lanes (MiniMax M3, TypeSafe Jev) may run inside $5/day | `require_transport` allows only `ollama`, `codex`, or the Claude subscription check; everything else is refused `subscription_only` (dispatch `app/server/provider_policy.py:36-43`, refusal `:77-78`), asserted for `minimax`, `openai`, `openrouter` by `tests/test_subscription_policy.py:22-25`. `docs/plans/mission-control-jev-next-five.md` says policy "must continue to deny" Jev | PROPOSAL — needs a code + test change to allow a metered lane |
| 2 | $5/day metered ceiling | `swarm/budget_tracker.py:45` `DEFAULT_DAILY_LIMIT_USD = 20.00`; line 6 "visibility only. No ceiling enforcement at call sites yet". `TAO_MAX_COST_USD` = 5.00 is per-run, not per-day (`app/server/kill_switch.py`) | PROPOSAL — no daily ceiling is enforced today |
| 3 | Lane order: Max → Codex → MiniMax → Jev | `_DEFAULT_PLAN_ORDER` = max_1, max_2, max_3, minimax, openrouter, codex (`swarm/fleet_value_optimizer.py:37-44`) | PROPOSAL |
| 4 | Codex pinned to `gpt-6-sol`, as the cross-model reviewer | Default `gpt-5.3-codex`, env `TAO_CODEX_MODEL`; described "Precision-only; no autonomous loops" (`fleet_value_optimizer.py:128-132`). No `reviewer` role exists | PROPOSAL. The reference says GPT-5.5 leaves Codex on 14 Oct 2026; whether `gpt-5.3-codex` is still served was not checked |
| 5 | MiniMax M3 via `ANTHROPIC_BASE_URL` + `ANTHROPIC_API_KEY` | Default model `MiniMax-M2.5` (`fleet_value_optimizer.py:138`). The Claude lane guard fails on `ANTHROPIC_API_KEY` (`scripts/estate/guard_claude_lane.sh:45`) and on any `ANTHROPIC_BASE_URL` not in its approved allowlist (`:56-58`) | PROPOSAL — must run in a process that never shares env with the Claude lane |
| 6 | Fable 5.1 for whole-project reconciliation | Only `claude-fable-5` is known (`app/server/model_registry.py:75`); Fable is off by default and meant for the adversary canary (`app/server/config.py:207-215`); `assert_model_allowed` raises only for ids it classifies as opus or fable (`model_policy.py:168-185`) — a new Fable 5.1 id would not be classified and would pass unchecked | PROPOSAL — needs a model id, a role, and the allow-list |
| 7 | Planner on Opus 5.5 at effort `high` | `ANTHROPIC_OPUS = "claude-opus-5-5"` (`model_registry.py:71`); planner is in `OPUS_ALLOWED_ROLES` (`config.py:193`) and `ROLE_EFFORT` planner = high (`model_policy.py:93-106`) | MATCHES CODE |
| 8 | Haiku 4.5 as the eval judge | `evaluator` role runs Sonnet (`app/server/config_loader.py:119`). The reference means the `claude plugin eval` judge, which is a separate tool, not the harness evaluator | No conflict once scoped — the harness evaluator stays Sonnet |
| 9 | Headless runs set effort by flag | The plan lane runs `claude -p <prompt> --disallowedTools=…` with no `--effort` or `--model` (`mesh/plan_lane.py:40`) | PROPOSAL — the plan lane inherits the CLI default today |
| 10 | Four lanes | Code also has a Tier-0 free/OpenRouter/Ollama lane (`app/server/tier0_lane.py`), the `adversary` and `portfolio` Opus roles, and the seven Model Fabric lanes (`docs/model-fabric-mission-control.md`) | Reference is incomplete, not wrong — read alongside these |

Minor stale text found on the way (not conflicts): `model_policy.py:5` says "Opus 4.7";
`config.py:213` names the Fable fallback `claude-opus-5`; the OpenRouter Opus slug in
`model_registry.py` is `anthropic/claude-opus-5`. `model_registry.py:11` dates Opus 5.5 to
2026-09-23; the reference says 22 Sept (Australia/Brisbane vs UTC may explain it — not checked).

## Defect found in the package's boundary hook

`hooks/planning-boundary.sh` checks an allowed path with `case "$FP" in *"$prefix"*`, a substring
match on raw text. Run with real `jq` 1.7 in this session, all three of these writes received **no
deny** (i.e. would proceed):

- `/repo/docs/plans/../../app/server/main.py`
- `/repo/app/server/docs/plans/evil.py`
- `/repo/.claude/handoffs/../../dashboard/app/page.tsx`

The six intended cases (product-code write denied, planning write allowed, `SKILL.md` edit denied,
`npm install` denied, `ls` allowed, `Read` untouched) all passed. The fix is the one CLAUDE.md
records for `swarm/path_allowlist.py`: normalise with `os.path.normpath` (or `realpath -m`) and
compare as an anchored prefix of the repository root. Not patched here, because editing the package
would break its `MANIFEST.sha256`; it belongs in the package's next revision in `skills-library`.

## Re-verification of vendor figures


**Run:** 28 Sept 2026, 8 read-only fetch agents, one entry per distinct figure. Full rows with quotes:
[routing-verification-2026-09-28.json](routing-verification-2026-09-28.json).

**Result:** 124 figures checked — 107 VERIFIED, 7 MISMATCH, 10 NOT_ON_PAGE, 0 UNREACHABLE.

**The one that matters:** OpenAI's Codex models page lists **GPT-5.6 Sol / Terra / Luna** (`gpt-5.6-sol` is the default), not GPT-6 Astra/Sol/Luna. There is no `gpt-6-sol` id on the page. `plan-to-done` SKILL.md step 9 and the routing reference both pin `gpt-6-sol`; a Codex review configured from them would fail on an unknown model. The 14 Oct 2026 GPT-5.5 retirement date is also not on the page. Correction belongs in the package's next revision (skills-library).

| Status | Claim in reference | What the page says |
|---|---|---|
| NOT_ON_PAGE | Usage across CLI, app, web and IDE draws one allowance (line 50) | Closest text: "Local messages and cloud chats share your plan's usage allowance." / "ChatGPT Work and Codex share usage." No explicit CLI/app/web/IDE single-allowance statement. |
| NOT_ON_PAGE | Usage across CLI, app, web and IDE draws one allowance (line 50) | Closest text: "Codex, ChatGPT Work, ChatGPT for Excel, and Workspace Agents use a shared allowance and credit pool" - no per-surface CLI/app/web/IDE statement. |
| MISMATCH | Recommended model GPT-6 Astra (most capable) (line 51) | Recommended models listed are 5.6 Sol, 5.6 Terra, 5.6 Luna, 5.3 Codex Spark; Astra not on models page. "5.6 Sol - Flagship GPT-5.6 model with the strongest capability" |
| MISMATCH | GPT-6 Sol, model id gpt-6-sol, for complex coding/agentic (line 51) | 5.6 Sol: Flagship GPT-5.6 model with the strongest capability for complex coding, computer use, research, and cybersecurity. codex -m gpt-5.6-sol |
| MISMATCH | GPT-6 Luna, model id gpt-6-luna, for focused repeatable tasks (line 51) | codex -m gpt-5.6-luna ... Luna, for clear, repeatable tasks. (version is GPT-5.6, not GPT-6; description matches) |
| MISMATCH | Recommended set omits a middle model (only Astra/Sol/Luna listed in file) (line 51) | Codex offers three GPT-5.6 models: Sol for detail and polish, Terra as the everyday workhorse, and Luna for clear, repeatable work. |
| MISMATCH | Non-interactive example: codex exec -m gpt-6-sol (line 51) | Page gives "codex -m gpt-5.6-sol"; no gpt-6-sol id anywhere on page. |
| NOT_ON_PAGE | Luna has no Ultra (line 51) | No statement restricting Ultra by model; page only says "Ultra uses subagents to handle separate parts of a complex task in parallel." |
| NOT_ON_PAGE | GPT-5.5 retires from Codex with ChatGPT sign-in on 14 October 2026 (line 52) | GPT-5.5 listed under Other models with no retirement date: "5.5 Previous-generation frontier model for complex coding..."; only GPT-5.4/5.4-mini retirement is stated. |
| MISMATCH | Pin gpt-6-sol in saved config (line 52) | Page's replacement guidance: "replace gpt-5.4 with gpt-5.6-terra and gpt-5.4-mini with gpt-5.6-luna"; default "uses gpt-5.6-sol". No gpt-6-sol. |
| NOT_ON_PAGE | The Anthropic-compatible base URL is the "recommended" one | Page gives only the Anthropic base URL in its Quick Start; the word "recommended" appears only for temperature ("recommended value: 1"), never for a base URL. |
| NOT_ON_PAGE | OpenAI-compatible base URL is https://api.minimax.io/v1 | No OpenAI-compatible URL on the page; it only says "For other models, please use the standard MiniMax API interface." |
| NOT_ON_PAGE | Jev cannot replace the model behind Codex (Codex named explicitly) | Codex is not in the named list ('Claude Code, Cursor, opencode, Copilot, Muse Spark, Grok Bot, or similar tools'); Codex appears only re the agent skill. Covered only by 'similar tools'. |
| MISMATCH | Opus 5.5 is Claude Code's default Opus model | "With Claude Opus 5 now the current Opus tier" ... "Model:`Claude Opus 5` - succeeds Opus 4.8 as the current Opus tier" (page 'Last updated on Jul 24, 2026'; no mention of Opus 5.5). Fetched via Exa; WebFetch returned EG |
| NOT_ON_PAGE | Opus 5.5 became default from Claude Code v2.1.280 | No mention of v2.1.280 or any 2.1.x version; only version cited is "/context (v1.0.86+)". |
| NOT_ON_PAGE | Launch date 22 Sept 2026 | No 22 Sept 2026 date on page; page footer reads "Last updated on Jul 24, 2026". |
| NOT_ON_PAGE | Anthropic raised five-hour limits at the Opus 5.5 launch without publishing figures | Page covers 5-hour cycles ("All plans reset every `5 hours`") and Max "increased limits" for Opus, but says nothing about a raise at an Opus 5.5 launch or unpublished figures. |

The last four rows come from `claudelog.com`, which the reference already labels third-party; the
page fetched on 28 Sept was last updated 24 Jul 2026 and predates Opus 5.5. The first-party model
page does confirm Opus 5.5's 22 Sept 2026 release (VERIFIED above).

Six more review-and-acceptance rows and three vendor notes from a second pass: [second-pass-2026-09-28.md](second-pass-2026-09-28.md).
