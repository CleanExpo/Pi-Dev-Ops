# Claude Code mods → Mission Control, Synthex, ATO-AI — integration spec (round 0)

**Status:** draft for review · **Author:** Claude (Cowork) for Phill · **Date:** 2026-10-04
**Base:** `Pi-Dev-Ops` `main` @ `b4bb532d` (RA-7898 modular boards spec)
**Related:** UNI-2412 (MC-P1 single-monitor Mission Control), UNI-2409 (L3 gate at the real tool-call boundary),
RA-7898 (modular boards), UNI-2669 (ATO-AI books runtime), SYN-1205 / SYN-1211 (Synthex main unbuildable)
**Vendored docs:** `docs/reference/claude-mods/` (Claude Code v2.1.289)

Every "fact" line below cites the vendored doc it came from. Everything under "Proposal" is design, not fact.

---

## 1. What mods are (facts)

- A mod is a TypeScript/JS hooks module inside a plugin. `on(event, matcher?, hook)`; each hook gets `($, e, next)` and can run before, after, or instead of Claude Code's own behaviour. (`overview.md`, `events.md`)
- Shipped in Claude Code **v2.1.287**; current is **v2.1.289** (`CHANGELOG-2.1.287-289.md`).
- **Hooks run in `claude -p` and the Agent SDK; drawing does not.** Panes/bands render only in the terminal and the Desktop Code tab. (`overview.md` → "Where mods run")
  → Pi-Dev-Ops runners use `claude_agent_sdk` (`CLAUDE.md`, `TAO_USE_AGENT_SDK=1`), so a telemetry/gate mod runs inside fleet lanes with no UI change.
- Relevant events: `tool.call` (deny / rewrite / answer), `tool.check` (final allow/ask/deny), `prompt.submit`, `prompt.compose` (system prompt sections), `turn.start/step/complete`, `session.start/end`, `session.measure` (after each turn, and when plan-limit % changes), `agent.spawn`, `session.receive/send`. (`reference.md` → Events)
- `$.session.usage()` → `{ startedAt, context{tokens,window,percent}, rateLimits[{kind,percentUsed,resetsAt}], cost }`. (`reference.md` → `$.session`)
- `$.http.fetch`, `$.process.run`, `$.clock.every`, `$.store` (shared by every session on the machine), `$.session.send` (message another session/subagent), `$.prompt.submit` (start a turn from a background job). (`api.md`)
- Limits: 10 s per hook (excluding time in `next`/API calls), `$.process.run` 30 s default / 10 min max. (`reference.md` → Limits)
- **Not sandboxed** — same access as Claude Code. Org control: `allowManagedModsOnly`, `allowManagedHooksOnly`, `disableAllHooks`, `strictKnownMarketplaces`; managed `PreToolUse` hooks run first and their block is final. (`admin.md`)
- Mods are Claude Code only. Codex and Hermes lanes are not covered and keep their current adapters.

## 2. Where Mission Control gets lane data today (facts, from `main`)

| Need (UNI-2412) | Today | Gap |
|---|---|---|
| Fleet + lanes | `POST /api/mesh/heartbeat` (machine + agents: runtime, session_id, repo, branch, current_task, state) → `mesh_machines`/`mesh_agents` (`app/server/routes/mesh.py:127`) | No tool-call events; task text only as fresh as the heartbeat |
| Context / session HUD | `claude_session_hud.py` reads `~/.claude/.context-ceiling/*.json` written by a PreToolUse hook | **Host-only**: on Railway it returns `available:false` (its own docstring) — the MacBook and Windows lanes are invisible |
| Live feed | `GET /api/mission-control/live` (sessions, throughput, queue, pulse, `claude_hud`) | Same host-only HUD |
| L3 gate | `claude-hooks-mirror/phone/TIER_GATE.md` — PreToolUse tier-gate classifier (#523) | UNI-2409 asks for enforcement at the real tool-call boundary |
| Costs | provider-usage feed (`/api/command-centre/provider-usage`) | No per-lane attributable cost |

## 3. Proposal — one mod: `mc-lane` (Mission Control lane mod)

Ships in the existing `unite-group-marketplace`, installed on all three machines. One mod, four jobs.

**Subtraction (standing rule — retire before adding):**
1. Retires the `context_ceiling.py` state-file → `claude_session_hud.py` path. The mod posts usage to the backend, so the HUD works for every machine, including the Railway deploy.
2. Retires the PreToolUse tier-gate shell hook in `claude-hooks-mirror` once the mod's `tool.call` gate passes the same test set (UNI-2409).
Net: one mod in, two mechanisms out.

### 3.1 Lane telemetry (read-only first — matches UNI-2412 Phase-1 scope)
- `session.start`: register lane (`$.session.id`, `repo`, `cwd`, `model`, host).
- `tool.call`: `await next(e)`, then queue `{tool, ok, ms, redacted input summary}` — never raw input/output.
- `session.measure`: queue `$.session.usage()` (context %, rate-limit %, `cost`).
- `$.clock.every(5_000)`: batch-POST to a new `POST /api/mesh/lane-events` with `X-Pi-CEO-Secret` (same scheme as heartbeat). Buffer in `$.store` when the backend is unreachable; send a cursor so reconnect resumes (UNI-2412 AC5).
- Cost shown as `unknown` when `usage().cost` is absent — never estimated (UNI-2412 "unknown rather than invented").

### 3.2 Controls (pause / resume / stop) — gated, second phase
- `$.clock.every(5_000)`: GET `/api/mesh/lane-control?session=<id>`.
- **Pause:** `tool.call` returns `{ deny: 'Paused from Mission Control' }` for every tool until resumed; ack posted back → gives the requested/acknowledged/completed states AC3 asks for.
- **Stop:** deny + `$.ui.log`; process kill stays with the existing kill-switch. (No documented "end session" call was found in the docs — do not assume one.)
- **Dispatch:** `$.prompt.submit({ text })` delivers a bounded read-only task to an idle lane (AC2). Goes through the governed dispatcher; the mod only delivers what `/api/mesh/dispatch` already approved (AC8).

### 3.3 L3 gate at the real boundary (UNI-2409)
- `tool.call` matcher on `Bash`, `Write`, `Edit`, MCP write tools: classify against the autonomy-ladder tier; deny L3 actions without an approval token from Mission Control.
- Managed `PreToolUse` hooks still run first and their block is final (`admin.md`) — so the hard stops (force-push, `--no-verify`, `PR_RELEASE_GATE_HUMAN_OVERRIDE`) stay as managed hooks; the mod handles the approval-aware middle tier.

### 3.4 Terminal / Desktop band (interactive sessions only)
- `AbovePrompt` band: approvals waiting on Phill, red guards, plan-limit %. Read from `/api/mission-control/live`. Invisible in `-p` lanes by design.

## 4. Synthex use cases

| Use case | Mod mechanism | Why (evidence) |
|---|---|---|
| **Main-is-red band** | `$.clock.every(60_000)` → `$.process.run(['gh','run','list','--branch','main','--limit','1','--json','conclusion'])` → `$.ui.status` | SYN-1205: main could not build from 07/09 to 21/09 with 15 commits stranded; SYN-1211 repeated it. A status line in every Synthex session makes that visible on the first red run |
| **Publishing gate** | `tool.call` deny on any tool/command that posts to Meta/IG/LinkedIn/GBP unless an approval exists in Mission Control | UNI-2669 names a "Synthex publishing gate" as an estate contract; SYN-1054 Meta OAuth work is about to enable FB/IG publishing |
| **Voice guide in every lane** | `prompt.compose` adds one `scope:'session'` section from `voice-guide.md` | Standing rule: voice guide auto-applies; removes copy-paste into prompts |
| **Generation spend into Mission Control** | Same `mc-lane` telemetry, tagged `project=synthex` | Generation Gateway (SYN-1116) is provider-agnostic; per-lane cost lands on the board |

## 5. ATO-AI use cases (internal books runtime, UNI-2669)

UNI-2669 (founder scope correction 2026-09-07): internal only, connected to Mission Control, regulated path, DSP Operational Security Framework drives the architecture (MFA, audit logging, Australian hosting, OWASP ASVS). The mods below support that; **they are not a compliance determination** — the OSF scoping pack decides what is required.

| Use case | Mod mechanism | Supports |
|---|---|---|
| **Redact before the model reads** | `tool.call` → `await next(e)` → rewrite the result to mask TFNs, ABNs, BSB/account numbers, Xero tokens. The launch post lists "redact secrets from tool output before Claude reads it" as a supported pattern | Keeps taxpayer identifiers out of transcripts and model context |
| **Append-only agent audit log** | Every `tool.call` + `tool.check` decision → `mc-lane` events with `project=ato`, stored append-only | OSF "audit logging" item in UNI-2669 |
| **No-lodge / no-write guard** | `tool.call` deny on Xero write endpoints, SBR/lodgement calls, production ledger writes unless an approval token exists | UNI-2669 caps: production read-only; lodgement only after the pack and sign-offs |
| **Books numbers row** | ATO lane reports into the same feed Mission Control's numbers row reads (UNI-2634) | UNI-2669: "Books runtime wires into Mission Control's numbers row" |

## 6. Org policy (managed settings, all three machines)

- `allowManagedModsOnly: true` and `strictKnownMarketplaces` → only `unite-group-marketplace` mods load. (`admin.md` → "Allow only your organization's mods")
- Keep hard-stop rules as managed `PreToolUse` hooks / deny rules; mods cannot override a managed deny. (`admin.md`)
- Reason: mods are not sandboxed, and the June 2026 credential exposure and INC-003 (public repo, prod deploy on every merge) make third-party mods a real supply-chain risk.

## 7. Build order (each step ships alone)

1. `mc-lane` telemetry only (3.1) + `POST /api/mesh/lane-events` + one board module reading it. Retire `claude_session_hud` file reader.
2. Synthex main-is-red status line (smallest, standalone, immediate value).
3. ATO redaction + audit log (before any ATO lane is armed).
4. L3 gate (3.3) against UNI-2409's tests; retire the tier-gate shell hook.
5. Controls (3.2) — only after 1–4 are green; remains review-gated per UNI-2412.

## 8. Tests (gate)

- `claude plugin validate` + `claude plugin test` for each mod (`test.md` — no session, sign-in or network needed).
- Backend: contract test for `lane-events` (auth, cursor resume, 10,000-event batch — UNI-2412 AC5).
- Redaction: fixture with TFN/ABN/BSB patterns must come out masked; control arm with the mod off shows them raw.
- Gate: every UNI-2409 case denies with the mod on; the control arm without the mod lets them through.

## 9. Open questions for Phill

1. Install `mc-lane` on all three machines, or Mac mini only for the first proof?
2. Synthex publishing gate: which platforms are in scope first (Meta only, or all)?
3. ATO: confirm the redaction list (TFN, ABN, BSB/account, Xero tokens) — anything else?
