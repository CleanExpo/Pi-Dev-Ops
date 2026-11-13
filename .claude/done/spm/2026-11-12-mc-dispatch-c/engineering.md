---
type: engineering-requirements
spec: ./spec.md
spec_sha256: 7f1218cc7cd596cc24fee14ffb85b52a85c9998206bfab781522b6ca05476719
reviewer: bench
seated: [boris, eng-failure, eng-observability, eng-test, eng-frontend, eng-secrets]
reviewed_at: 2026-11-12T13:07:00+10:00
status: PASS
categories:
  data_model:         {state: N/A, reason: "No table, column, writer or row is added or changed. The change only reads mesh_machines fields the existing heartbeat route already writes (status, last_seen, agent_runtimes).", by: boris}
  invariants:         {state: PRESCRIBED, ref: "#invariants", by: eng-frontend, blocking: false}
  failure_modes:      {state: PRESCRIBED, ref: "#failure-modes", by: eng-failure, blocking: false}
  interface_contract: {state: PRESCRIBED, ref: "#interface-contract", by: boris, blocking: false}
  concurrency:        {state: N/A, reason: "Every new path is an idempotent read: launchctl getenv and GET /api/mesh/fleet share no mutable state and a retry gives the same answer. The pane's existing inFlight guard is unchanged.", by: boris}
  migration:          {state: PRESCRIBED, ref: "#migration", by: boris, blocking: false}
  rollback:           {state: PRESCRIBED, ref: "#rollback", by: eng-secrets}
  observability:      {state: PRESCRIBED, ref: "#observability", by: eng-observability, blocking: false}
  budget:             {state: N/A, reason: "No paid call, loop or storage growth. The only added cost is up to three launchctl calls, made only when the process environment lacks the pair, each with a 3 s timeout.", by: boris}
  test_oracle:        {state: PRESCRIBED, ref: "#test-oracle", by: eng-test, blocking: false}
disagreements:
  - "boris advised splitting the lane-config fallback (Tier 1) from the held-status display (Tier 2) into two pull requests. Author ruled one Tier 1 pull request: the task brief allows a mixed PR as long as the whole PR is reviewed as Tier 1, and both halves share the fleet_status result shape (configSource, holdReason), so splitting them means two release cycles over the same files. Overturnable if review rounds on the display half start to delay the secret half."
  - "eng-observability asked that GREEN require a mesh-runner entry, or failing that a runner state at most 120 s old. Author ruled against both. The Mini and the Desktop heartbeats send no such entry today (live read 12/11/2026), so requiring one turns every healthy machine GREY. The age rule raises false alarms: mesh/runner_report.py:3-6 says the runner writes its state once at the start of a build, so the state is legitimately old during any long build. A dead runner is already reported as `runner-down` by heartbeat.runner_down(), which both screens treat as not healthy. GREEN therefore needs a fresh heartbeat and a healthy status word, nothing more."
  - "eng-failure suggested relying on the engine's 30 s process.run default. Author set 3 s: the kit passes init.timeoutMs to the stub, so the option is real and testable, and a 30 s stall inside a tool call is worse than a launchd read reported as unreadable."
  - "eng-secrets asked that mission-control use the read-only TAO_FLEET_READ_SECRET through a new MC_FLEET_READ_SECRET key. Deferred to Phill as a follow-up: it needs a secret written to a new store, which the task brief reserves for him."
  - "boris asked for a criterion that reads the live fleet row for Phills-Mac-mini. Answered by evidence instead of a new criterion: the live read on 12/11/2026 showed Phills-Mac-mini status working with no mesh-runner entry, which is why the held text has a 'reason not reported' form. C6 prints every host and status on each run."
---

Round 1, spec amendment 1. Seats: boris (chair), eng-failure, eng-observability, eng-test, eng-frontend, eng-secrets.
Every finding the author accepted is in spec amendment 1, the locked contract w_c64ca48a3f14, and the sections
below.

## Invariants

- For every status word `s`: healthy(s) holds exactly when s is `online` or `working`. The `/mc` alert, the
  `fleet_status` alert and the Live page chip all derive from the same set, exported as `HEALTHY_STATUSES` in both
  `mods/mission-control/hooks/fleet.ts` and `dashboard/lib/wall/snapshot.ts`. Any other word, including a missing
  one, `updating`, or one added to the runner later, is never green. (boris: spec section 9 originally gave a
  deny-list on one screen and an allow-list on the other; `updating` showed GREY on the Live page and `alert:
  false` in `fleet_status`.)
- `HELD_STATUSES` only picks the wording ("held: quota"). It never decides whether to alert.
- `tests/test_fleet_status_vocabulary.py` pins both copies to the words `mesh/heartbeat.py node_status` can return.
- URL and secret come as a pair from one place (environment, else launchd). A URL from one place is never sent
  with a secret from the other.

## Failure modes

| Failure | What the user sees |
|---|---|
| Environment and launchd both lack the pair | `state: unknown`, reason names both places by setting name only |
| launchctl refused, missing or timed out (3 s) | `state: unknown`, "launchd: unreadable (<error type>)" |
| launchd filled after the session started | the next tool call, `/mc` or mc-lane flush finds it; a miss is never cached |
| Transport error whose message quotes the secret | the secret is replaced before the text reaches the result or the log |
| Heartbeat sends `quota` with no `mesh-runner` entry (Mini today) | RED "held: quota (reason not reported by this machine's heartbeat)" |
| Status missing or unrecognised | GREY "status <x>: not a healthy state", raised as an alert on the command wall |

## Interface contract

- `fleet_status` result gains `configSource` (`env` or `launchd`, absent when not configured) and each machine
  row gains `holdReason` (string or null). Existing fields are unchanged.
- `MC_LANE_HOST` resolves through the same fallback, so lane events from an app-started process are not filed
  under host `unknown` (boris).
- Settings are resolved on every entry point: the `fleet_status` call, `/mc`, and mc-lane's flush tick.

## Migration

- Nothing runs until a human merges and each machine refreshes its plugins: installed mods live in
  `~/.claude/plugins/cache`. The PR body carries that step.
- The Mini's heartbeat runs from `pdo-runtime` at 42b0bcc2 (5 Nov), which sends `quota` but no `mesh-runner`
  entry and none of `outdated`, `version-unknown`, `hard_stop`. Those appear only once the runtime updates, which
  waits on the STORAGE_GUARD_V1 change reaching main (item 4; owner named in the final report and a follow-up card).

## Rollback

Revert the merge commit, redeploy the dashboard, then refresh plugins on each machine (a revert alone leaves the
new mods in the plugin cache). ssh aliases: copy `~/.ssh/config.bak-mc-dispatch-c-20261112` back. (boris)

Secret rotation, Phill's step, in this order (eng-secrets). The lane secret is probably the shared fleet write
secret, so rotating it is fleet-wide, not one edit:
1. List every holder first: the server's accepted secret, each machine's `~/.zshenv`, and the launchd copy the
   launch agent made.
2. Change the server and each holder.
3. Run `launchctl kickstart -k gui/$UID/com.unite-group.mc-lane-env` on each Mac. launchd keeps the old value
   until the agent runs again, and this change now reads launchd.
4. Restart the desktop app, then check `fleet_status` returns a real read.
A failed read after step 2 is the expected window, not a fault in this change.

## Observability

- Each mod logs which place supplied the settings (`env` or `launchd`), never a value.
- The not-configured text names the state of each place by setting name.
- The Live page tile and the command-wall alert carry the held word and, when the heartbeat sends one, the hold
  reason trimmed to 120 characters.

## Test oracle

- Each new test is watched failing on the old code first (red runs recorded in red-baseline.md and the session).
- Stubs use the real shapes: `launchctl getenv` of an unset name exits 0 with empty output; the test asserts
  `e.argv` is exactly `['/bin/launchctl', 'getenv', NAME]` and `e.init.timeoutMs` is 3000.
- Secret-absence assertions run only after a positive control proves the configured path ran (the fetch header
  equals the sentinel, state is ok, a source log line exists). Tests use a sentinel, never a real value.
- C6 runs a fresh `claude -p` process with no `MC_LANE_*` and requires a real read, `configSource` launchd, and
  the live secret absent from its output (compared in the shell, never printed).
