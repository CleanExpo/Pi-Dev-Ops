# SPM Spec — Mission Control dispatch, package C (fleet status after reboot, held machines visible)

> Amendment 1 (12/11/2026, after the engineering bench, see engineering.md). Section 7: the pull request is
> Tier 1, not T2, because it handles the lane secret. Section 9: URL and secret resolve as a PAIR from one place;
> `MC_LANE_HOST` uses the same fallback; settings are re-checked on every entry point (tool call, `/mc`, mc-lane's
> recording path) and a miss is never cached; one allow-list (`online`, `working`) decides health on both screens;
> a held machine whose heartbeat sends no `mesh-runner` entry reads "reason not reported by this machine's
> heartbeat". Section 15: C3 also pins the status vocabulary; C6 also requires the config to come from launchd and
> accepts a degraded read that still lists machines. The original text below is kept; where it disagrees, this
> amendment wins.

## 1. Task being planned

Package C of the 12/11/2026 systems-gap research (`~/session-handoffs/handoff-20261112-opus55-systems-fixes.md`
section 8). Six scoped items, in the brief's order:

1. Test whether the existing `pi-ceo` build tools reach a live backend from a desktop session.
2. Only if not: a submit tool that files a goal as the Goal page does (Backlog, no autonomy label).
3. Make `fleet_status` work after a reboot (`MC_LANE_URL` / `MC_LANE_SECRET` missing from the desktop app).
4. Diagnose the runner's refused self-update; preserve its local edits byte for byte.
5. Make a "Claude quota exhausted" hold visible to Phill, with unknown never shown as healthy.
6. Diagnose why `fleet.py probe` reaches only the Mini; fix what is reversible.

Founder ask (Phill, recorded in the handoff): "the ability to do this Agentically through MY MISSION CONTROL".

## 2. Current project context

- Grounded 2026-11-12: Pi-Dev-Ops `origin/main` = 1b2bcd96 — `git log --oneline -1` in this worktree.
- Grounded 2026-11-12: Done selftest 8/8 ENFORCED; spec-work contract w_91845c79b747 locked — donectl output.
- Grounded 2026-11-12: brain seek PASS; skills-library HEAD = origin/main 02215c2c — command output.
- Mods live in `mods/` and are installed from marketplace `pi-dev-ops-mods` into `~/.claude/plugins/cache/...`
  (`installed_plugins.json` lists `mission-control@pi-dev-ops-mods` and `mc-lane@pi-dev-ops-mods`).
- Waterline: internal tooling · Stage 1 running (rung 6/12) · usable on one machine — the Mini.

## 3. Problem statement

Observed this session (O = ran the command):

- (O) Item 1: `mcp__pi-ceo__get_pipeline` returns `Login failed HTTP 401`. `_shipLogin` reads `PI_CEO_URL`
  (unset in `~/.zshenv`, `~/.zshrc`, `~/.hermes/.env` and the wrapper), so it logs into `127.0.0.1:7777`
  (PID 882, uvicorn from `~/relint/pdo/app`, started 11:59:46) with `PI_CEO_PASSWORD` from `~/.hermes/.env`
  (set, 32 chars), which that server refuses. So `spec_idea`, `plan_build`, `build_feature` have no working path.
  `build_feature` would also start a build directly, which is Phill's decision 5, not a goal filed to Backlog.
- (O) `mcp__pi-ceo__linear_status` = CONNECTED, and `linear_create_issue` files to Linear with `status`
  and `labels` under the caller's control (`mcp/pi-ceo-server.js` handler). That is a working path from a
  Claude session that files to Backlog with no autonomy label. Item 2 is therefore not built.
- (O) Item 3: after the reboot at 11:58:36 the desktop app (PID 773) started 11:59:45; launchd registered
  `com.unite-group.mc-lane-env` at 11:59:46 (`log show`). `ps eww` shows no `MC_LANE_*` in PID 773 or in the
  Claude Code process 99502, while `launchctl getenv MC_LANE_URL` is set and `MC_LANE_SECRET` is 42 bytes.
  `launchctl setenv` never reaches a process already running, so every app start that wins the race leaves
  both mods unconfigured until the app is restarted.
- (S, scout) Item 4: `mesh/self_update.py:102-104` refuses when `git status --porcelain --untracked-files=no`
  is non-empty in the runtime `/Volumes/Storage Unit/Application-Data/nexus-mesh/pdo-runtime`. The only tracked
  file changed since the last update is `scripts/codex_failover.py` (+3 lines, `STORAGE_GUARD_V1`, default HOLD
  on MacBook failover). 461 refusals from 5 Nov 22:46 AEST to 12 Nov.
- (S, scout; O for the live read) Item 5: the hold already travels runner breadcrumb -> heartbeat `status`
  (`mesh/heartbeat.py node_status`) -> `/api/mesh/fleet`, and the server watchdog already pages on `quota`.
  The Live page (`/control`) draws a fresh machine GREEN "heartbeat fresh" from `last_seen` alone
  (`dashboard/lib/wall/snapshot.ts machineTile`), and `fleet_status` alerts only on stale, `runner-down`,
  `offline` (`mods/mission-control/hooks/fleet.ts`). A quota-held machine shows healthy in both.
- (S, scout) Item 6: `fleet.py` (skills-library `fleet-compute`) reaches nodes by SSH alias `macbook-ts` and
  `win-ts`; the Mini's `~/.ssh/config` has `macbook`, `pc`, `nexus-pc`, `phill-desktop` for the same Tailscale
  IPs but neither alias, so ssh fails at name lookup. Both machines are active on Tailscale.

## 4. Desired outcome

- `fleet_status` (and mc-lane reporting) works in any Claude Code process started after login, whether or not the
  app inherited the variables, with no new secret store.
- A machine whose heartbeat says it is held (quota, blocked, stuck, outdated, ...) is RED with the reason on the
  Live page and an alert row; a missing or unrecognised status is GREY "status unknown", never GREEN.
- The runner's local edit is preserved and described, with the exact step that unblocks updates.
- `fleet.py probe` resolves the MacBook and the PC; whatever it then reports is recorded truthfully.
- Customer served: Phill as operator of the agent fleet. Hard-day card: a quota hold at night. Today the Live page
  says green; after this change the tile is red with "held: quota — Claude quota exhausted until ...".

## 5. Scope

### In scope
- `mods/mission-control` and `mods/mc-lane`: read the lane settings from launchd when the process environment
  lacks them (new pure helper `hooks/lane_config.ts`, identical in both mods).
- `mods/mission-control/hooks/fleet.ts`: held statuses and unknown status alert; hold reason in the row.
- `dashboard/lib/wall/snapshot.ts`, `dashboard/lib/control/command-wall.ts`: status-aware machine chip.
- Tests for each, plus a byte-parity test for the two `lane_config.ts` copies.
- Mini `~/.ssh/config`: add aliases `macbook-ts` and `win-ts` to the existing Host lines (dated backup first).
- Notes-folder copy of the runtime's local edit (file, sha256, diff).

### Out of scope
- Auto-starting goal tickets or changing the labels the runner claims (decision 5). `mesh_lanes.py` untouched.
- A plugin submit tool (item 2 not needed). Backend auth changes. Production deploys, merging, spend.
- Restoring or committing the runtime's local edit; changing `scripts/codex_failover.py` on main.
- `cron_watchdog_mesh.py` (frozen path) and the runner/heartbeat code (the data already flows).

### Explicit non-goals
- Fixing the pi-ceo 401 (password alignment is a credential step: Phill's).
- Rotating the lane secret (see section 12; Phill's step).

### Assumptions
- launchd keeps the values the env agent sets for the whole login session (observed true now).
- The mod engine permits `$.process.run` of `/bin/launchctl` (documented in `docs/reference/claude-mods/api.md`).

### Constraints
- Never print, log or return the secret. Subscription accounts only. Human merge only.

## 6. Existing capability review

Searched: `grep -rl MC_LANE_URL`, `goal-ticket`, `linear_create_issue`, `quota`, `self_update`, `fleet.py`.
Reused: launchd env agent (existing store), `/api/mesh/fleet` data, `node_status` vocabulary, the watchdog alert,
`linear_create_issue`. Nothing duplicated: no second submit tool, no second alert path.

## 7. Specialist board review

Tier T2 (internal tooling, one secret-handling path). Engineering bench seated for the spec (see engineering.md).
Independent post-build review through `pr-release-gate` on a non-Claude lane.

## 8. Judge challenge

Score 88/100, APPROVE EXPERIMENT (local, reversible) until the engineering gate passes and the release review runs.
Deductions: -5 the real-reboot proof is simulated by a fresh process (owner: builder; closure: Phill's next reboot,
check `fleet_status`); -4 the installed plugin copy only changes after merge and a plugin refresh (owner: Phill);
-3 item 6 may stop at authentication on the remote machines (owner: Phill, a key step).

## 9. Proposed solution

1. `lane_config.ts` (pure): `fromLaunchctl({exitCode, stdout})` returns the trimmed value or undefined;
   `pickLaneConfig(env, launchd)` takes each variable from the environment, else from launchd, and returns
   `{ cfg | null, source }`. `register.ts` in each mod calls `/bin/launchctl getenv <NAME>` through
   `$.process.run` only for variables the environment lacks, catching every failure as "absent".
   mission-control also re-resolves at tool-call time when still unconfigured. Not-configured text names both
   places looked. Source (`env` or `launchd`) may be logged; values never.
2. `fleet.ts`: `HELD` = blocked, quarantined, stuck, quota, outdated, version-unknown, hard_stop; alert when
   held, `runner-down`, `offline`, or the status is missing; `holdReason` from the `mesh-runner` entry of
   `agent_runtimes`, trimmed to 120 chars.
3. `snapshot.ts machineTile`: fresh + status in {online, working} -> GREEN "reporting"; fresh + held or down ->
   RED "held: <status>[ — <reason>]"; fresh + anything else (missing, updating, unrecognised) -> GREY
   "status <x>: not a healthy state". Stale handling unchanged. `command-wall.ts` already shows `m.reason` for a
   non-GREEN tile and raises an alert for tone != ok.
4. `~/.ssh/config`: `Host macbook macbook-ts` and `Host pc nexus-pc win-ts`.

## 10. UX requirements

Live page tile text and alert row read "held: quota — Claude quota exhausted until <time>". `/mc` pane rows for
held machines are red with the reason.

## 11. Technical requirements

TypeScript as the surrounding code; no new dependencies; mods keep `$` only in top-level functions of
`register.ts`; `lane_config.ts` and `fleet.ts` stay `$`-free.

## 12. Security and privacy requirements

- The secret is read into memory only; never in `ui.log`, tool results, errors or tests' snapshots
  (tests assert the secret string is absent from every log line and result).
- `/bin/launchctl` by absolute path, argument list, no shell.
- Incident: during recon this session's grep printed the lane secret into the session transcript (it is stored in
  plain text in `~/.zshenv`). Rotation is Phill's step; this change neither copies nor moves the secret.

## 13. Verification plan

Each criterion in section 15 runs a command whose exit code is the evidence. Every new test is watched failing on
the old code before the fix. The fresh-process proof runs `claude -p` with `MC_LANE_URL` and `MC_LANE_SECRET`
removed from the environment and the worktree's mod loaded; it must fail on the old code and pass on the new.

## 14. Loop testing and stress testing

Not applicable beyond the unit suites: no loops or queues change.

## 15. Acceptance criteria

- C1 `claude plugin test mods/mission-control` exits 0 (includes launchd fallback, secret-never-printed and
  held-status tests).
- C2 `claude plugin test mods/mc-lane` exits 0 (includes the launchd fallback test).
- C3 `python3 -m pytest tests/test_mods_lane_config_parity.py tests/test_fleet_status_vocabulary.py -q` exits 0
  (both copies byte-identical; both screens use the same healthy and held words as `node_status`).
- C4 `cd dashboard && npx vitest run __tests__/wall-snapshot.test.ts __tests__/command-wall-screen.test.tsx` exits 0.
- C5 `cd dashboard && npx tsc --noEmit` exits 0.
- C6 fresh-process proof script exits 0: `fleet_status` returns state ok or degraded with at least one machine,
  and `configSource` launchd, while the process environment has no `MC_LANE_*`.
- C7 `fleet.py probe --json` no longer reports "Could not resolve hostname" for macbook or windows.

## 16. Goal command

`/goal` Package C per this spec; criteria C1-C7; stop at an open pull request with GitHub green and receipt success.

## 17. Implementation sequence

Loadout: `spm` (plan), `engineering-requirements` (gate), `superpowers:test-driven-development` (build),
`pr-release-gate` (release). Crew: this Opus session builds; Explore sub-agents did recon; independent review via
`lane_registry.py` (Codex first). Pi Durable agents: UNAVAILABLE.
1. Tests red first (C1-C4). 2. Fix. 3. Tests green, tsc, lint, ruff, related pytest. 4. Fresh-process proof red
then green. 5. ssh aliases, probe before/after. 6. Notes-folder copy of the runtime edit. 7. Release gate.

## 18. Session handoff seed

Card M-PDO-MC-DISPATCH-C. Worktree `Pi-Dev-Ops/.claude/worktrees/mc-dispatch-c`. Notes folder
`side-session-notes/local_8f285900-...`.

## 19. Final recommendation

Build the two reversible code changes in one Tier 1 pull request (it handles the lane secret), keep item 2 unbuilt
because `linear_create_issue` already files to Backlog with no label, and hand Phill three exact steps: rotate the
lane secret, restore the runtime file once its change is upstreamed, and authorise the fleet key on the MacBook
and PC if the probe stops at authentication.
