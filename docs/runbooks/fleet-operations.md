# Runbook: fleet operations

The human half of the three-machine fleet. What the system does unattended, and where the
boundary sits, is [ADR 008](../adrs/008-fleet-autonomy-charter.md); this file is the procedures.

Fleet: `phills-macbook-pro` (mobile — leaves and rejoins), `unite-mac-mini` (always on),
`phill-desktop` (Windows, always on when powered). Transport is HTTPS to the Railway API, not
peer-to-peer, so a machine on hotel wifi works exactly like one on the LAN.

## Check the fleet is alive

```bash
curl -s "$PI_CEO_API_URL/api/mesh/fleet" -H "X-Pi-CEO-Secret: $PI_CEO_API_KEY" | python3 -m json.tool
```

Read `machines[].is_stale` — a node whose heartbeat is older than 60 s reads stale and is
skipped by dispatch. `agents[]` shows what is running; `claims[]` shows open work. If a
machine is missing entirely it never enlisted: run the join below on it.

## Join a machine to the fleet

```bash
bash mesh/bootstrap.sh          # idempotent; safe to re-run
```

Installs the heartbeat daemon and runner, wires the agent hooks, and writes credentials to
`~/.hermes/.env` (mode 600). The machine holds only `PI_CEO_API_KEY` — never the Supabase
service-role key. Verify with the fleet call above: a new row should appear within ~20 s.

`bootstrap.sh` is bash. On `phill-desktop` run it under WSL or Git Bash; if neither is present,
that node cannot enlist yet and needs a PowerShell port. Check before assuming it joined —
a machine that silently failed to enlist looks identical to one that is merely idle.

## Turn work assignment on

Dispatch ships **off**. Nothing is assigned until:

```
MESH_DISPATCH_ENABLED=1
```

is set on the Railway service. Within 5 minutes the logs show
`mesh_dispatch id=… assigned=N online=[…]`. Label a Linear issue `mesh:auto` to feed the pool.

To assign on demand instead of waiting for the tick:

```bash
curl -s -X POST "$PI_CEO_API_URL/api/mesh/dispatch" \
  -H "X-Pi-CEO-Secret: $PI_CEO_API_KEY" -d '{}'
```

## Stop everything

```bash
touch ~/.claude/HARD_STOP     # per machine: drains in-flight work, no restart needed
```

The runner checks it before taking work **and** while an agent subprocess runs, so an
in-flight run is terminated cleanly and its claim released back to Todo. Remove the file to
resume. To stop assignment fleet-wide instead, unset `MESH_DISPATCH_ENABLED`; to stop the
Linear poller entirely, `TAO_AUTONOMY_ENABLED=0`.

## The MacBook leaves and comes back

Nothing to do — this is designed behaviour, not an incident:

- **Leaving mid-run.** Its heartbeat goes stale. Any claim it held past the TTL is reaped and
  the Linear issue returns to the unstarted pool, so another node picks it up. The reaper runs
  inline on every dispatch and self-claim; force it with
  `curl -s -X POST "$PI_CEO_API_URL/api/mesh/claims/reap" -H "X-Pi-CEO-Secret: $PI_CEO_API_KEY"`.
- **Coming back.** The heartbeat resumes and the node is dispatchable again on the next tick.

A claim is never reaped while its machine's heartbeat is fresh — a live node may legitimately
be deep inside a long agent run.

## Something looks stuck

Work through it in this order; each step names the command that decides it.

1. **Is anything online?** `…/api/mesh/fleet` → all `is_stale`? The machines are asleep or the
   heartbeat daemon died. Re-run `bootstrap.sh` on one and watch the row refresh.
2. **Is dispatch on?** No `mesh_dispatch` lines in the Railway logs → `MESH_DISPATCH_ENABLED`
   is unset. That is the intended default, not a fault.
3. **Is there work to assign?** No Linear issues labelled `mesh:auto` in an unstarted state →
   the pool is empty. Dispatch correctly does nothing.
4. **Is a ticket stuck claimed?** `claims[]` shows it `claimed`/`working` with a stale machine
   → run the reap call above.
5. **Is the machine claiming but not working?** `python mesh/runner.py --once --dry-run` on
   that node prints its plan without touching anything. If it prints `HARD_STOP`, the kill
   switch is armed — that file is still there.

Rule that saves time: **dormant is not missing.** Most "it isn't working" in this system is a
flag that is off by design. Check the flag before debugging the code.

## After a change to any of this

```bash
bash scripts/handoff-loop.sh
```

One command, and it is the whole release gate. Do not record the individual sub-gates
separately in a receipt — running the Python suite twice exceeds the tool timeout and kills the
push mid-gate.
