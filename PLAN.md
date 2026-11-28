# PLAN.md: Mission Control Command Deck, from planned to shipped

Written 28 November 2026 on branch `uni-2412-mission-control-plan` of CleanExpo/Pi-Dev-Ops,
base commit `e67473e3` (origin/main, pull request 1035). One file. A fresh session runs it
with the single prompt in section 7.

How to read the tags. Every fact carries its proof:

- `[E: path:line]` a file in this repo, read today.
- `[E: command -> result]` a command run today and what it printed.
- `[E: Linear ISSUE]` an issue read through the Linear connector today.
- `UNVERIFIED` nobody checked it today. It is not a fact until a step below proves it.

Rules that bind this plan and every step in it:

- Plain English. No emoji. No Tailwind or shadcn default look. The bespoke CSS-Modules
  command deck is the house style. Open Horizon is the design authority.
- Subscription accounts only. No API-key lanes. The only exception is TypeSafe Jev.
- Synthex is internal. It never appears here as a product, launch or billing item.
- No hardware security keys, suggested or bought.
- Done means the Done gate (donectl) says so on the exact commit. Push needs the
  pr-release-gate receipt. GitHub must be green on the exact head. Phill merges. Nothing
  auto-merges.
- Fix the design when a defect repeats. Three failed review rounds on one change stops the
  work and goes to Phill with a kind table.

---

## 1. Current state: what exists, what runs, what is broken, what is missing

### 1.1 "Mission Control" is three different things

| Name | What it is | Proof |
|---|---|---|
| The plugin | `mods/mission-control`: a Claude Code plugin. `/mc` opens a terminal pane; `fleet_status` is a tool. Read-only. | `[E: mods/mission-control/.claude-plugin/plugin.json]` description: "Read-only Mission Control fleet view: /mc pane ... and a fleet_status tool" |
| The Command Deck | `dashboard/`: a Next.js web app with a `/command-centre` route and a flight-deck CSS module. This is the thing Phill designed. | `[E: dashboard/components/command-centre/command-deck.module.css:1]` "Command Deck, flight-deck console aesthetic for the Nexus Command Centre" |
| A money folder | `~/mission-control`: Xero and debt-recovery scripts plus one plugin marketplace. Not the deck. | `[E: ls ~/mission-control -> tools/, money/, baselines/, data/]` |

This plan ships the first two as one product. The third is left alone.

### 1.2 What exists

The plugin (7 files, 1,031 lines including tests):

- `hooks/hooks.json` loads one module, `./register.ts` `[E: mods/mission-control/hooks/hooks.json]`.
- `register.ts` registers the `fleet_status` tool (`$.tool.register`) and the `/mc` command
  that opens a pane which refreshes every 30 seconds `[E: mods/mission-control/hooks/register.ts, 197 lines]`.
- `fleet.ts` turns `GET {MC_LANE_URL}/api/mesh/fleet` into machines, heartbeat age, stale
  (over 60 s), held, open claims and the last five ships `[E: mods/mission-control/hooks/fleet.ts, 186 lines]`.
- `lane_config.ts` reads `MC_LANE_URL` and `MC_LANE_SECRET` from the environment, else from
  `launchctl getenv`, and scrubs the secret from errors `[E: mods/mission-control/hooks/lane_config.ts, 86 lines]`.
- Three test files `[E: mods/mission-control/tests/]`.
- Four sibling plugins in the same marketplace: `mc-lane`, `fleet-guard`, `ato-guard`,
  `synthex-main-status` `[E: ls mods -> five directories]`.

The backend the plugin reads:

- `GET /api/mesh/fleet` is served by `fleet()` `[E: app/server/routes/mesh.py:131]`.
- Auth is a shared `X-Pi-CEO-Secret` header; anything else gets 401 `[E: app/server/mesh_fleet_auth.py:34]`.
- The snapshot comes from `app/server/mesh_fleet.py`; runbook at `docs/runbooks/fleet-operations.md`.

The Command Deck (web):

- `dashboard/` is `pi-ceo-dashboard` 2.0.0, Next.js, React, Vitest, Playwright
  `[E: dashboard/package.json -> name pi-ceo-dashboard, version 2.0.0, scripts test = vitest run, test:e2e = playwright test]`.
- Seven command-centre pages: home, hermes, knowledge, providers, wall, wiki-graph,
  youtube-intent `[E: find dashboard/app/(main)/command-centre -name page.tsx -> 7 files]`.
- The deck is styled by CSS Modules, not Tailwind classes:
  `command-deck.module.css` (618 lines), `shell.module.css` (294), `deck-details.module.css` (80)
  `[E: dashboard/components/command-centre/]`.
- Tailwind and Radix are still in the dependency tree and style the rest of the app
  `[E: dashboard/package.json -> tailwindcss, @tailwindcss/postcss, tailwind-merge, @radix-ui/react-slot, class-variance-authority]`.
- The current design system is `DESIGN.md`: "Pi-CEO Design System", dark-first, gun-metal
  surfaces, candy-red brand `#ff3b5c`, Geist `[E: DESIGN.md sections 1 and 2]`.
- Open Horizon is not referenced anywhere in the repo
  `[E: grep -rIil "open horizon|open-horizon" excluding node_modules -> nothing]`.
- A naming defect in the deck: `--deck-cyan` is set to green `#2dbb57`
  `[E: dashboard/components/command-centre/command-deck.module.css:12]`.

The repo's own MCP servers:

- `mcp/estate-connector/`: a remote Streamable-HTTP MCP server using `server.registerTool`,
  Bearer `ESTATE_MCP_TOKEN` plus a `?bot=` name, audit log, no delete tool. Tools include
  `mc_live`, `mc_queue`, `mc_post_note`, `mc_update_queue_item`, `mc_claim_work`,
  `mc_release_work` and adapters for ATO, CARSI, DR/NRPG, Pi-Dev-Ops, RestoreAssist,
  Synthex, Unite `[E: mcp/estate-connector/README.md tool table; mcp/estate-connector/adapters/]`.
- `mcp/pi-ceo-server.js`: the older local stdio server, version 3.0.0, SDK `^1.29.0`
  `[E: mcp/package.json]`.
- Python MCP SDK pinned at 1.27.1 `[E: uv.lock:673-674]`. Its protocol constant reads
  `2025-11-25` `[E: .venv/bin/python -c "import mcp.types as t; print(t.LATEST_PROTOCOL_VERSION)" -> 2025-11-25]`.

Planning material already written:

- `docs/plans/mission-control/work-packages.md`: WP-01 to WP-12 with completion tests and
  live run results from 29 September 2026 `[E: docs/plans/mission-control/work-packages.md, 64 lines]`.
- `aaa-rating.md`, `coverage-register.md` (20 rows), `promise-register.md` (33 promises,
  0 proven on 29 Sept), `engineering.md`, `handoff.json` in the same folder `[E: ls docs/plans/mission-control]`.
- Two screenshots of the wall from 4 November 2026 `[E: docs/plans/mission-control/command-wall-2026-11-04-desktop.png, -laptop.png]`.

### 1.3 What runs (observed today)

| Check | Result | Proof |
|---|---|---|
| Plugin tests | 29 pass, 0 fail, 3 files | `[E: claude plugin test mods/mission-control]` |
| Sibling plugins | mc-lane 21, fleet-guard 13, ato-guard 60, synthex-main-status 10, all pass | `[E: claude plugin test mods/<name>]` |
| Python tests that cover Mission Control | 78 passed in 1.41 s | `[E: .venv/bin/python -m pytest tests/test_mods_lane_config_parity.py tests/test_mesh_fleet_endpoint.py tests/test_fleet_status_vocabulary.py tests/test_mission_control_truth.py ...]` |
| Dashboard unit tests for mission-control, wall, mesh | 7 files, 70 tests pass | `[E: npx vitest run <7 files>]` |
| `fleet_status` tool, live | answers; state "ok"; configSource "env" | `[E: mcp__mission-control__fleet_status call]` |
| Full dashboard suite, Playwright | not run today | UNVERIFIED |

### 1.4 What is broken

| Defect | Proof |
|---|---|
| Nightly "Mission Control live" is red three nights running on the current main | `[E: gh run list --workflow mission-control-live.yml -> failure 46033215466, 45858408225, 45653845830, all headSha e67473e3]` |
| Three scheduled workflows red six days or more; Linear and Vercel auth failing in Actions | `[E: Linear RA-8289, state Todo]` |
| Live pages show no live data or empty state | `[E: Linear RA-8433, state Backlog]` |
| The fleet the deck reports is itself unhealthy: Phill_Desktop stale 247,901 s, Mac Mini stale 195,020 s, MacBook runner-down | `[E: fleet_status call today]` |
| Plugin validate warnings: TS2322 at `register.ts` line 195, no `network.hosts`, no version, `ui.close` and `tool.call` hooks have no `.catch` | `[E: claude plugin validate mods/mission-control]` |
| Nothing in CI runs `plugin test` or `plugin validate` for `mods/` | `[E: grep .github for "mods/", "plugin test", "plugin validate" -> nothing]` |
| estate-connector tests: 26 pass, 1 fail, `ERR_MODULE_NOT_FOUND @modelcontextprotocol/sdk` because node_modules is not installed there | `[E: node --test in mcp/estate-connector]` (code defect UNVERIFIED until `npm ci`) |
| The repo's MCP server is not registered for Claude Code on this machine | `[E: ls ~/.mcp.json, ./.mcp.json -> absent; claude mcp list -> empty]` |
| Every surface is below Level 1 on the AAA rubric: real-data assertions are not built | `[E: docs/plans/mission-control/work-packages.md WP-06, WP-11]` |

### 1.5 The missing layers

These are the layers Phill feels are missing. Each one is a numbered step in section 5.

| Layer | State | Proof |
|---|---|---|
| L1 Design system. Open Horizon tokens applied to the deck. | MISSING | grep in 1.2; `DESIGN.md` is a different system |
| L2 Layout. One founder screen: fleet, lanes, tool calls, costs, controls, approvals. | PARTIAL | `[E: Linear UNI-2412 "[MC-P1] Single-monitor founder Mission Control", In Progress]` |
| L3 Own MCP server with tools AND resources, registered where Claude Code finds it. | PARTIAL | tools exist in estate-connector; no resources; no `.mcp.json` |
| L4 Consumption of Linear, Supabase, Vercel, Railway, GitHub through MCP, with proof each answers. | PARTIAL | adapters exist; proof is the red nightly run |
| L5 Install everywhere. bootstrap.sh installs the marketplace, the plugins and the env pair. | MISSING | `[E: grep -i "plugin\|marketplace\|mods" ~/.claude/bootstrap.sh -> nothing]` |
| L6 Roles staffed. A registry that names which skill or plugin fills each business role. | MISSING | no such file; see section 2 |
| L7 Truth. Nightly run green with real-data assertions, not empty states. | MISSING | 1.4 |
| L8 Release wiring for `mods/`. | MISSING | 1.4 |
| L9 One current architecture document. | PARTIAL | plans folder exists; no single current doc |

---

## 2. The target and who staffs it

### 2.1 The target in one paragraph

A non-engineer founder opens one screen and sees the whole business machine: every machine
and agent, what each lane is doing, what it costs, what is waiting for a yes, and what shipped.
From the same screen he gives the yes or the no. Claude Code sessions, Codex and Cursor read
and write the same state through one MCP server. Every number on the screen is live or says
plainly that it is not. The screen looks like nothing else: Open Horizon, bespoke CSS Modules,
bright, calm, high contrast, legibility over spectacle `[E: open-horizon-design-system wiki page, "Technical architecture" bullet "Design"]`.

One founder decision sits inside that sentence. `DESIGN.md` says "Dark-first. Light mode is
never the default" `[E: DESIGN.md section 1]`. Open Horizon says "bright, calm, high-contrast,
not dark cyberpunk" `[E: wiki page line 143]`. Step 3 in section 5 puts both side by side as
real renders and asks Phill once. It is the only design question the plan asks him.

### 2.2 Every role, and what fills it today

Verified today: every skill folder named below exists under `~/.claude/skills/`
`[E: for s in ...; do test -e ~/.claude/skills/$s; done -> all OK]`. Every agent named exists
under `~/.claude/agents/` `[E: ls ~/.claude/agents]`.

Anthropic-shipped plugins. What the files say:

- `superpowers@claude-plugins-official` 7.0.2 is installed at user and project scope and
  enabled `[E: ~/.claude/plugins/installed_plugins.json; ~/.claude/settings.json enabledPlugins superpowers true]`.
- `vercel@claude-plugins-official` 0.56.0 is installed and enabled `[E: same two files]`.
- `engineering`, `design`, `product-management`, `operations`, `sales`, `marketing`,
  `data`, `legal`, `human-resources`, `customer-support`, `brand-voice`, `productivity`,
  `enterprise-search` are present only under
  `~/.claude/plugins/synced/<session-id>/` for this desktop session
  `[E: ls ~/.claude/plugins/synced/1773b01a-...]`. They are absent from
  `installed_plugins.json` and every one of them reads `false` in `enabledPlugins`
  `[E: ~/.claude/settings.json enabledPlugins -> engineering@synced false, design@synced false, ...]`.
  Their skills still appear in this session's skill list, so the desktop app loads them on
  its own. They are NOT installed on every machine, and a terminal `claude` session on the
  Mac Mini or the PC does not have them. UNVERIFIED on those machines until step 8 probes them.
- `anthropic-skills` (docs, pptx, xlsx, pdf, mcp-builder, skill-creator, and others) appear in
  the session skill list. Their install location was not found under `plugins/` today.
  UNVERIFIED as a global install.

The answer to Phill's question: Anthropic-shipped skills can fill every role on paper, but
today they fill none of them on every machine, because they are synced per desktop session
and switched off in settings. The estate's own skills already staff every role and are
installed by the skills-library repo. Step 7 writes the registry so this stops being memory.

| Role | Estate skill or agent that fills it today | Anthropic plugin that could | Gap |
|---|---|---|---|
| Founder | Phill. The deck is his screen. `capture-intent` turns his words into an accepted intent | none needed | Approvals queue on the deck (step 4) |
| CEO and Board | `ceo-board`, `boardroom`, `pantheon`; `autonomy-ladder` decides what needs a human | `product-management:stakeholder-update` | none |
| Product manager | `spm` (front door), `product-manager`, `pm-core`, `spec-development` | `product-management:write-spec`, `sprint-planning`, `roadmap-update` | none |
| Architect | `engineering-requirements` (17-seat bench, agents `boris`, `eng-*`), `technical-plan`, `planner` agent | `engineering:architecture`, `system-design` | none |
| Builder | Claude builder lane; `crew-builder` agent; `superpowers:test-driven-development` | `superpowers` (installed) | none |
| Reviewer | Codex lane (live), `opus-adversary`, `adversarial-review`, `reviewer` agent, `crew-reviewer` | `engineering:code-review` | none |
| Designer | `design-system`, `design-audit`, `mobbin-ui-patterns`, `visual-qa`, `impeccable`, `frontend-design` | `design:design-critique`, `accessibility-review`, `design-system` | Open Horizon token file (step 3) |
| QA | `qa-lead`, `visual-qa`, `reticle-verify`, `test-writer` agent, `crew-verifier` | `engineering:testing-strategy` | real-data assertions (step 9) |
| Release | `pr-release-gate`, `merge-gate`, `ship-release`, `done-harness`, `repo-captain` | `engineering:deploy-checklist` | release wiring for `mods/` (step 2) |
| Ops | `estate-tidy`, `guardian`, `fleet-compute`, `system-state`, `incident-memory` | `operations:runbook`, `status-report`, `incident-response` | fleet is stale (step 1) |
| Finance | `cfo`, `stripe-milestone-invoice`, `sow-draft`, Jev spend ledger | `small-business:cash-flow-snapshot`, `sales:forecast` | cost view on the deck (step 4) |
| Marketing | `marketing-orchestrator`, `cmo-growth`, `nexus-copywriter`, `brand-guardian`, `seo` | `marketing:campaign-plan`, `content-creation` | none; Synthex stays internal |

Review lanes available today, from the one registry: codex (cli, owned subscription, live),
cursor (cli, owned subscription, live); minimax, deepseek, gemini registered but not routed;
openrouter metered and never used for this work `[E: python3 ~/.claude/skills/pr-release-gate/scripts/lane_registry.py --list]`.
Codex CLI 0.172.0 is installed `[E: codex --version]`.

---

## 3. MCP readiness

### 3.1 What Mission Control exposes today

- Inside Claude Code: one tool, `fleet_status`, registered by the plugin through
  `$.tool.register` and seen as `mcp__mission-control__fleet_status`
  `[E: mods/mission-control/hooks/register.ts]`. No resources. No prompts.
- Over the network: `mcp/estate-connector`, Streamable HTTP, `server.registerTool`, Bearer
  token plus bot name, audit log `[E: mcp/estate-connector/lib/register.js; README]`.
  Deployment on Railway: UNVERIFIED today.
- Registration: no `.mcp.json` in the repo, none in `~/`, and `claude mcp list` prints
  nothing `[E: section 1.4]`.
- Spec version: the Python SDK speaks `2025-11-25` `[E: section 1.2]`. The Node SDK version
  pinned for estate-connector and pi-ceo-server is `^1.29.0`
  `[E: mcp/package.json; mcp/estate-connector/package.json]`. The protocol version the
  Node SDK negotiates is read at build time in step 5 from the installed package, not
  from memory. UNVERIFIED until then.

### 3.2 What it consumes today

Linear, Supabase, Vercel, Railway and GitHub are reachable in this desktop session as
claude.ai connectors (their tools carry connector prefixes, not repo registrations)
`[E: this session's tool list]`. The backend and estate-connector call Linear, health URLs and
Vercel through an allowlist proxy `[E: dashboard/app/api/pi-ceo/[...path]/route.ts; dashboard/lib/pi-ceo-proxy-allowlist.ts]`.
The plugin itself consumes only `/api/mesh/fleet`. The Actions runner cannot reach Linear or
Vercel right now `[E: Linear RA-8289]`.

### 3.3 Target shape (built in steps 5 and 6)

One server, `mission-control`, exposed two ways from one code path:

- Local stdio for Claude Code, Codex and Cursor on each machine, registered in the repo's
  `.mcp.json` and in each machine's user config by the installer in step 8.
- Remote Streamable HTTP for cloud sessions and other machines (the existing estate-connector).

Tools (names fixed now so every lane uses the same words):
`mc_fleet` (today's `fleet_status`), `mc_lanes`, `mc_tool_calls`, `mc_costs`, `mc_queue`,
`mc_approvals_list`, `mc_approvals_decide` (write; founder token only), `mc_claim_work`,
`mc_release_work`, `mc_post_note`, `mc_ships`, `mc_health`.

Resources: `mc://fleet`, `mc://lanes`, `mc://queue`, `mc://approvals`, `mc://costs/today`,
`mc://ships/recent`, `mc://health`.

Auth: Bearer token per bot, least privilege, read tools open to every bot, write tools only to
the founder token and the lane that holds the claim. Tokens live in the Keychain on macOS and
in the credential store on Windows; the installer reads their location from
`skills/library/connections.md` and never prints a value.

Proof per tool: a test calls `tools/list` and asserts every name above is present, then
calls each tool once against a fake backend and once against the live one, and writes a
receipt line `tool, status, ms, sha`. A tool with no receipt is not ready.

Consumption: each outside system (Linear, Supabase, Vercel, Railway, GitHub) is reached
through the official connector or CLI the estate already uses `[E: ~/.claude/skills/library/connections.md]`,
with a positive control first: break the token on purpose, watch the probe go red, restore it,
watch it go green. The green is recorded with the exact SHA.

---

## 4. Global installation: every piece on every machine, every time

The rule: enforcement hooks and plugins ship as synced, idempotent installers under
`skills/<name>/install/` in the skills-library repo and are wired into `bootstrap.sh`; never
as loose files `[E: ~/.claude/AGENTS.md "Enforcement wiring is NOT synced by this repo"]`.

What bootstrap.sh does today: installs evidence-gate, standards-egress-gate, phone-gate,
enforcement-loop, gstack, pr-release-gate, receipt-autopublish, keep-working, orchestrator,
supabase-write-gate, prettier guard, model-switch hooks, repo-visibility guard, parse-guard,
system-state, strips autogit, reports dangling symlinks `[E: ~/.claude/bootstrap.sh lines 26-180]`.
It never touches plugins or marketplaces `[E: grep -> nothing]`.

How Mission Control reaches a machine today: by hand. `claude plugin marketplace add
CleanExpo/Pi-Dev-Ops`, then `claude plugin install mission-control@pi-dev-ops-mods`
`[E: mods/mission-control/README.md]`. The env pair comes from a LaunchAgent,
`~/Library/LaunchAgents/com.unite-group.mc-lane-env.plist`, which sources `~/.zshenv` and runs
`launchctl setenv` `[E: that plist on this MacBook]`. UNVERIFIED on the Mac Mini. Impossible as
written on the PC (no launchctl).

Target: one installer, `skills/mission-control-install/install/install_mission_control.py`,
run by `bootstrap.sh`, that on every machine:

1. Adds the `pi-dev-ops-mods` marketplace to `extraKnownMarketplaces` if missing
   (today it is present on this machine with `autoUpdate: true` `[E: ~/.claude/settings.json]`).
2. Installs or updates `mission-control`, `mc-lane`, `fleet-guard` at user scope.
3. Sets `enabledPlugins` for those three to true; leaves every other key alone.
4. Writes the `.mcp.json` registration for the local stdio server (step 5).
5. Points the env pair at the machine's credential store: launchd plist on macOS,
   a user environment variable set through the Windows registry on the PC. It never writes
   a secret value; it writes where the value lives.
6. Enables the Anthropic plugins the role registry (step 7) names, by their official
   marketplace install, so a terminal session has them too.
7. Prints one line per piece: `installed`, `updated`, or `already present`, and exits
   non-zero if any piece is missing after the run. Running it twice changes nothing.
8. Backs up `settings.json` before writing, like the existing installers do
   `[E: ~/.claude/bootstrap.sh comment on system-state: "Idempotent, backs up first"]`.

Proof on each machine: `fleet.py probe` first `[E: ~/.claude/skills/fleet-compute/scripts/fleet.py]`,
then the installer, then `claude plugin list` and `claude mcp list` show the names, then the
`/mc` pane opens and shows the machine itself as fresh. Three machines, three receipts.

---

## 5. The build sequence

Dependency ordered. Each step names its files, the test that fails before and passes after,
the Done criterion recipe for `donectl`, the review tier, and the owner lane. "Claude builder"
means the Claude Code session running this plan. "Codex reviewer" means the live codex lane.
"Sonnet subagent" means a cheaper fork for grunt work.

Before any step: the Linear issue exists and is claimed with agent, machine and branch
`[E: ~/.claude/skills/pr-release-gate/SKILL.md "Linear tracking (hard rule)"]`. UNI-2412 is the
parent for the deck `[E: Linear UNI-2412, In Progress]`; each step gets its own child issue and
branch `uni-NNNN-<slug>`. Every step opens its own Done contract with the recipe given, locks
it, builds, then verifies on a clean tree.

Tier rule: if any file in a step touches auth, sessions, roles, secrets, tenancy, billing,
migrations or personal data, the whole step is Tier 1 (review until PASS). Everything else is
Tier 2 (one independent round; P2 findings become one Linear ticket) `[E: ~/.claude/CLAUDE.md "Review tiers"]`.

### Step 0. Baseline receipts

- Why first: nothing later may claim progress against a number nobody measured.
- Files touched: none in source. Writes `docs/plans/mission-control/baseline-2026-11-28.md`.
- Test that fails before, passes after: the file does not exist; after, it holds the output
  of `claude plugin test mods/mission-control`, the full `npx vitest run` in `dashboard/`,
  `.venv/bin/python -m pytest tests/`, `node --test` in estate-connector after `npm ci`, and
  the latest three `mission-control-live` run URLs with conclusions.
- donectl recipe: `test -f docs/plans/mission-control/baseline-2026-11-28.md && grep -q "vitest" docs/plans/mission-control/baseline-2026-11-28.md`
- Review tier: Tier 2. Owner lane: Sonnet subagent runs the suites; Claude builder writes the file.

### Step 1. Make the truth light honest: fleet and nightly run

- Why: the deck reports a fleet that is itself two to three days stale, and the nightly
  truth run is red `[E: section 1.4]`. A deck built on a dead feed cannot be accepted.
- Files touched: `app/server/mesh_fleet.py`, `.github/workflows/mission-control-live.yml`,
  the heartbeat agents on each machine (owned by `estate-tidy` and `guardian`).
- Test that fails before, passes after: `tests/test_mesh_fleet_endpoint.py` gains a case that
  fails when any real machine's heartbeat is older than 300 s in the snapshot the test is
  fed from the live endpoint; it fails today (247,901 s) and passes once heartbeats resume.
  The nightly workflow's `NOT_RUN` step fails loudly when Linear or Vercel auth is missing
  (it already does for `DASHBOARD_PASSWORD` `[E: work-packages.md WP-02]`); extend it to the two
  other secrets.
- Founder gate: the Actions secrets for Linear and Vercel are SECRET class. Claude names the
  exact secret names and where they are set; Phill sets them. This is the one SECRET gate in
  the plan and it is reported, not asked twice.
- donectl recipe: `.venv/bin/python -m pytest tests/test_mesh_fleet_endpoint.py -q && gh run list --workflow mission-control-live.yml --limit 1 --json conclusion --jq '.[0].conclusion' | grep -q success`
- Review tier: Tier 1 (secrets). Owner lane: Claude builder; Codex reviewer.

### Step 2. Plugin hardening and release wiring for `mods/`

- Files touched: `mods/mission-control/hooks/register.ts` (TS2322 at line 195),
  `mods/mission-control/.claude-plugin/plugin.json` (add `network.hosts`),
  `.github/workflows/mods-plugins.yml` (new: `claude plugin validate` and `claude plugin test`
  for every directory under `mods/`), `tests/test_mods_lane_config_parity.py` stays as the
  byte-for-byte pin.
- Test that fails before, passes after: the new workflow job fails on today's HEAD because
  validate prints the TS2322 warning as an error under `--strict`; passes after the fix.
  Positive control: plant a bad type in a scratch copy and watch the job go red.
- donectl recipe: `claude plugin validate mods/mission-control --strict && claude plugin test mods/mission-control`
  (if `--strict` does not exist in the installed CLI, the recipe greps validate output for
  "TS2322" and fails when found).
- Review tier: Tier 2. Owner lane: Claude builder; Codex reviewer.

### Step 3. Design foundation: Open Horizon tokens and the one founder decision

Phill's direction on 28 November 2026: "the next one is the design and layout". Steps 3 and 4
are that work. Nothing in steps 5 to 10 changes a pixel.

- Before a line of CSS: `mobbin-ui-patterns` emits a cited reference brief (founder rule,
  every UI build starts from the Mobbin library) and the Open Horizon and Niche Agentic
  Products v2.0 wiki pages are loaded `[E: nexus-doctrine rule 5.15]`.
- Files touched: `dashboard/app/styles/open-horizon.tokens.css` (new; the only place colour,
  type, space, motion and radius are defined), `dashboard/components/command-centre/command-deck.module.css`
  (consumes tokens only; the `--deck-cyan` green mislabel is fixed), `shell.module.css`,
  `deck-details.module.css`, `DESIGN.md` (gains an Open Horizon section and the decision record).
- The founder decision: two real renders of the same deck home, one on the current gun-metal
  dark ground, one on an Open Horizon bright calm ground, both at desktop and phone size,
  captured by Playwright Chromium, put side by side in one image. Phill picks one. That pick
  is written into `DESIGN.md` with the date. Until he picks, both token sets exist and the
  dark one stays live so nothing regresses.
- Test that fails before, passes after: `dashboard/__tests__/tokens.test.ts` asserts that no
  CSS module under `components/command-centre/` contains a raw hex colour or a Tailwind
  utility class, and that every custom property it uses is declared in the tokens file. It
  fails today (hex literals at `command-deck.module.css:12-30`) and passes after.
  Contrast: an axe run at WCAG 2.2 AA on the deck home passes with zero serious or critical
  findings (today 15 pages fail contrast `[E: work-packages.md WP-09]`).
- Visual acceptance: `visual-qa` captures mobile, tablet and desktop screenshots, freezes
  SHA-256 baselines, and a different reviewer than the builder writes the critique. A green
  test is not a polished design. Final visual acceptance is Phill's, on the exact rendered
  build.
- donectl recipe: `cd dashboard && npx vitest run __tests__/tokens.test.ts && npx playwright test e2e-live/level2.spec.ts --grep "command-centre" --project=desktop`
- Review tier: Tier 2. Owner lane: Claude builder (design lead); Sonnet subagent for
  token extraction; Codex reviewer; Phill for the pick.

### Step 4. Layout: the single-monitor founder deck

- Scope from `[E: Linear UNI-2412]`: fleet, lanes, tool calls, costs and controls on one
  screen. Plus the approvals queue, because the founder's job on this screen is the yes or no.
- Files touched: `dashboard/app/(main)/command-centre/page.tsx`, new components under
  `dashboard/components/command-centre/`: `FleetRail`, `LanesBoard`, `ToolCallStream`,
  `CostMeter`, `ApprovalsQueue`, `ControlsBar`, each with its own `.module.css`; data hooks
  in `dashboard/lib/control/`; the proxy allowlist for any new backend route.
- Each panel has three honest states, LOADED, EMPTY, ERROR, and a `SourceBadge` saying live,
  cached or synthetic `[E: dashboard/components/command-centre/SourceBadge.tsx exists]`.
  A panel never shows a sample number as if it were real.
- Test that fails before, passes after: `dashboard/__tests__/founder-deck.test.tsx` renders
  the home with a fake backend and asserts all six panels are present and each shows its
  three states; fails today because four of the six components do not exist. The existing
  panel-coverage registry gains the six panels `[E: dashboard/e2e-live/panel-coverage.json]`
  and `scripts/mission_control_panel_coverage.py` must pass the home.
- Phone: the 390 by 844 project re-runs the read journey; the header health light must stay
  visible on phone (today the phone layout hides it, which made passes meaningless
  `[E: work-packages.md WP-06]`).
- donectl recipe: `cd dashboard && npx vitest run __tests__/founder-deck.test.tsx --reporter=json --outputFile=/tmp/mc-v.json && python3 ../scripts/mission_control_panel_coverage.py /tmp/mc-v.json /tmp/mc-c7 --registry e2e-live/panel-coverage.json --dashboard .`
- Review tier: Tier 2. Owner lane: Claude builder; Sonnet subagent writes component tests;
  Codex reviewer; `visual-qa` with an independent critic; Phill accepts the render.

### Step 5. Mission Control's own MCP server: tools, resources, registration

- Files touched: `mcp/estate-connector/adapters/mission-control/index.js` (tools renamed and
  added per section 3.3; resources added), `mcp/estate-connector/lib/register.js`
  (`registerResource`), new `mcp/mission-control-stdio.js` (thin stdio entry that imports
  the same adapter), `.mcp.json` at repo root (stdio registration), `mcp/estate-connector/test/`.
  The plugin's `fleet_status` keeps working and is marked as the alias of `mc_fleet`.
- Spec version: read at build time with
  `node -e "console.log(require('@modelcontextprotocol/sdk/package.json').version)"` and the
  SDK's protocol constant, and written into `mcp/estate-connector/README.md` with the date.
  Not typed from memory.
- Test that fails before, passes after: `mcp/estate-connector/test/tools-list.test.js` calls
  `tools/list` and `resources/list` and asserts the twelve tool names and seven resource URIs
  from section 3.3; fails today (six tools, no resources). `npm ci` first so the existing
  `ERR_MODULE_NOT_FOUND` failure is cleared or shown to be a real defect.
- Auth test: a request with no Bearer gets 401; a read token calling `mc_approvals_decide`
  gets 403; the founder token gets 200. Three cases, all asserted.
- donectl recipe: `cd mcp/estate-connector && npm ci --silent && node --test && cd ../.. && claude mcp list | grep -q mission-control`
- Review tier: Tier 1 (auth, tokens). Owner lane: Claude builder; Codex reviewer until PASS;
  `eng-authz` and `eng-secrets` bench seats consulted through `engineering-requirements`.

### Step 6. Consume the connected systems with proof

- Files touched: `mcp/estate-connector/adapters/{pidevops,unite,...}/index.js` where they
  reach Linear, Supabase, Vercel, Railway and GitHub; `scripts/mc_probe_connections.py` (new);
  `docs/plans/mission-control/connections-receipts.md` (new).
- Rule: every reach goes through the connector or CLI the estate already authorises
  `[E: ~/.claude/skills/library/connections.md]`. No API-key lane. Supabase writes stay behind
  the write gate `[E: ~/.claude/skills/supabase-write-gate/SKILL.md]`.
- Test that fails before, passes after: the probe script calls one read per system and
  writes `system, status, ms, sha`. Positive control first: with a deliberately wrong token
  it must print `red` for that system; then green with the right one. Today Linear and Vercel
  read red from Actions `[E: Linear RA-8289]`.
- donectl recipe: `python3 scripts/mc_probe_connections.py --require linear,supabase,vercel,railway,github --receipt docs/plans/mission-control/connections-receipts.md`
- Review tier: Tier 1 (secrets). Owner lane: Claude builder; Codex reviewer.

### Step 7. Role registry: the business staffed on paper and on disk

- Files touched: `config/roles.json` (new): one row per role in section 2.2 with
  `estate_skill`, `estate_agent`, `anthropic_plugin`, `install_scope`, `gap`.
  `tests/test_roles_registry.py` (new). `docs/plans/mission-control/roles.md` (generated from
  the JSON, never hand-edited).
- Test that fails before, passes after: the test asserts every `estate_skill` path exists in
  `~/.claude/skills/`, every `estate_agent` exists in `~/.claude/agents/`, and every
  `anthropic_plugin` named appears in `installed_plugins.json` with `enabledPlugins` true.
  It fails today for every Anthropic plugin row except superpowers and vercel
  `[E: section 2.2]`, which is the honest answer, and passes after step 8 installs them.
- The deck reads this file to show the roles panel in step 4 as data, not prose.
- donectl recipe: `.venv/bin/python -m pytest tests/test_roles_registry.py -q`
- Review tier: Tier 2. Owner lane: Sonnet subagent builds; Claude builder checks; Codex reviewer.

### Step 8. Global installer, wired into bootstrap

- Repo: skills-library (`~/.claude`), by PR, since main is protected. Not this repo.
- Files touched: `skills/mission-control-install/SKILL.md`,
  `skills/mission-control-install/install/install_mission_control.py`,
  `skills/mission-control-install/tests/test_install_mission_control.py`, `bootstrap.sh`
  (one new block in the same shape as the system-state block
  `[E: ~/.claude/bootstrap.sh "SYSTEM_STATE.md at session start" block]`), one line in
  `skills/README.md` and one route in `skills/index.md` (3-place rule
  `[E: ~/.claude/AGENTS.md rule 4]`).
- Test that fails before, passes after: the test runs the installer against a copy of a
  `settings.json` and `installed_plugins.json` that lack Mission Control, asserts the copy
  gains exactly the keys in section 4 and nothing else, then runs it again and asserts the
  bytes are unchanged (idempotence). It also asserts the installer refuses to write any value
  that matches a secret shape. On the PC path it asserts the registry call is emitted and no
  `launchctl` call is. Fails today because the installer does not exist.
- Machine proof: `fleet.py probe`, then the installer on MacBook, Mac Mini and PC, then
  `claude plugin list` and `claude mcp list` on each, pasted into
  `docs/plans/mission-control/install-receipts.md` in this repo with hostnames and dates.
  A machine that cannot be reached is `UNVERIFIED`, never `installed`.
- donectl recipe (in skills-library): `python3 skills/mission-control-install/tests/test_install_mission_control.py && bash -n bootstrap.sh`
- Review tier: Tier 1 (it writes settings and names credential locations). Owner lane:
  Claude builder; Codex reviewer until PASS; the Mini run goes to Codex on the Mini.

### Step 9. Truth: real-data assertions and a green nightly run

- Files touched: `dashboard/e2e-live/read-journeys.spec.ts` (per-surface data assertions
  sized from the first live receipts `[E: work-packages.md WP-06 "Not yet a real-data assertion"]`),
  `dashboard/e2e-live/surfaces.ts` (the six new panels), `scripts/mission_control_scorecard.py`
  unchanged, `docs/plans/mission-control/promise-register.md` (promises move to proven with
  the run URL).
- Test that fails before, passes after: a surface showing its own empty state must now FAIL
  check 1 unless the backend also reports empty. Proved locally against a production build
  with no backend: all surfaces fail by name. Then three consecutive nightly runs green on
  the deployed SHA read from `/api/revision` `[E: work-packages.md WP-11 check 13]`.
- donectl recipe: `python3 scripts/mission_control_stability.py --runs 3 --require-green`
- Review tier: Tier 2. Owner lane: Claude builder; Sonnet subagent for assertion sizing;
  Codex reviewer.

### Step 10. One architecture document and the handoff gap closed

- Files touched: `docs/plans/mission-control/ARCHITECTURE.md` (new, generated sections from
  `config/roles.json`, `.mcp.json` and the tools list, so it cannot drift silently),
  `docs/plans/mission-control/README.md` points at it, `mods/mission-control/README.md`
  points at it, `WIKI.md` entry.
- Handoff gaps closed by name: a PR opened by any lane is owned by `repo-captain` until the
  receipt reads success; a note written to `docs/plans/mission-control/` is read by the next
  session because `SYSTEM_STATE.md` lists the folder `[E: ~/.claude/bootstrap.sh system-state block]`;
  a queued approval has an owner on the deck (step 4).
- Test that fails before, passes after: `tests/test_mc_architecture_doc.py` asserts the
  generated sections match the live JSON byte for byte; fails until the doc exists.
- donectl recipe: `.venv/bin/python -m pytest tests/test_mc_architecture_doc.py -q`
- Review tier: Tier 2. Owner lane: Sonnet subagent; Claude builder; Codex reviewer.

### Step 11. Close-out

- Board card closed with evidence, session leftovers removed (review worktrees, scratch
  exports, background jobs), superseded notes in `docs/plans/mission-control/` marked and
  pointed at the record that replaced them `[E: ~/.claude/CLAUDE.md "Close-out and clean data"]`.
- Lessons written the same day into the skill, wiki page or SHARED-KNOWLEDGE they belong to,
  and published `[E: seek-latest-before-task SOP, "After a durable learning"]`.
- donectl recipe: `git status --porcelain | grep -q . ; test $? -eq 1`
- Review tier: Tier 2. Owner lane: Claude builder.

### Order and parallelism

Steps 0 and 1 first. Then 2 and 3 may run at once (different files). Step 4 after 3.
Step 5 after 2. Step 6 after 5. Step 7 any time after 0. Step 8 after 5 and 7. Step 9 after
4 and 6. Step 10 after 9. Step 11 last. Two writers never touch the same file at once.

---

## 6. The ship gate

Every step ships through the same gate, once, on its own branch and PR
`[E: ~/.claude/skills/pr-release-gate/SKILL.md]`:

1. Linear issue claimed; branch `uni-NNNN-<slug>` from current `origin/main`.
2. Done contract locked before the build; `donectl verify` on a clean tree after the last
   commit; status reads `criterion_evidence PASS`, `dirty_count 0`.
3. `pr_release_gate.py provision` then the repo's own checks on the exact commit.
4. Independent non-builder review bound to the exact commit: Tier 1 until PASS; Tier 2 one
   round with the brief "Tier 2 change. Block (P1) only for security exposure, data loss or
   corruption, or a broken build or test suite. Report every other finding as P2,
   non-blocking." Codex quota is checked live first; a lane at quota moves to the next
   eligible lane, never to paid credits.
5. Push only with the receipt. GitHub runs the required checks on the exact pushed SHA and
   they are green. "Green" means GitHub's checks, not a local run.
6. Release receipt reads success. Linear moves to In Review with the PR link.
7. Phill merges. Nothing auto-merges. UG-AUTONOMY-001 does not cover Pi-Dev-Ops
   `[E: ~/.claude/CLAUDE.md "UG-AUTONOMY-001 is limited to ... Unite-Group, CARSI and RestoreAssist"]`.
8. After merge: observed runtime behaviour before anyone says "deployed". For the deck that
   means the nightly run on the deployed SHA, and Phill's own eyes on the exact render.

The stop rules: three failed review rounds on one change goes to Phill with a kind table.
A repeated finding kind means fix the design, not the instance. A long check carries a time
limit of about twice its last measured run.

What this plan does NOT authorise: spending, new subscriptions, API keys, production
database changes, pushing without a receipt, merging, or deleting anything.

---

## 7. The single prompt

Paste this into a fresh Claude Code session opened in the Pi-Dev-Ops checkout:

```text
Execute PLAN.md in this repo, from step 0 to step 11, in the order section 5 gives.

Before anything: run the seek-latest SOP (git fetch origin; compare HEAD with origin/main;
read ~/.claude/SYSTEM_STATE.md), run donectl status and selftest, read ~/.claude/CLAUDE.md
and ~/.claude/AGENTS.md, and re-verify every [E: ...] tag in PLAN.md section 1 that is older
than seven days. If a tag no longer holds, update PLAN.md first and commit that alone.

For each step: find or create the child Linear issue under UNI-2412 and claim it; branch
uni-NNNN-<slug> from origin/main; open and lock the Done contract with the recipe given;
write the failing test and watch it fail; build; make it pass; run donectl verify on a clean
tree; run the independent review at the tier named; push only with the pr-release-gate
receipt; open the PR as draft; hand it to repo-captain until GitHub is green on the exact
head and the receipt reads success; then move to the next step. Never merge.

Step 3 ends with one question to Phill: dark ground or bright ground, shown as two real
renders side by side. Step 1 ends with one report to Phill naming the two Actions secrets
he must set. Ask nothing else. Everything a check cannot prove is written as UNVERIFIED.

Report at the end of every step in plain English: what shipped, the PR link, what is
unproven, and the next step. Use Codex and Sonnet subagents for grunt work; keep Opus for
lead decisions. Stop when step 11's recipe passes or when a founder gate blocks, and say
which.
```

---

Doctrine applied: 5.1 backend first, 5.3 one canonical home, 5.5 fix the source on a repeat,
5.7 never finished with open items, 5.9 green before PR, 5.14 /spm pathway, 5.15 Open Horizon
and Niche Agentic Products loaded before design, 6.1 fifth-grade plain English.
References followed: Open Horizon design system wiki page (25/10/2026); Nexus Niche Agentic
Products v2.0 wiki page (25/10/2026); docs/plans/mission-control/work-packages.md (29/09/2026);
~/.claude/AGENTS.md enforcement-wiring rule (16/07/2026).
