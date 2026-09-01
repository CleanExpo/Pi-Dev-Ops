# Runbook: fleet operations

The human half of the three-machine fleet. What the system does unattended, and where the
boundary sits, is [ADR 008](../adrs/008-fleet-autonomy-charter.md); this file is the procedures.

Fleet: `phills-macbook-pro` (mobile — leaves and rejoins), `unite-mac-mini` (always on),
`phill-desktop` (Windows, always on when powered). Transport is HTTPS to the Railway API, not
peer-to-peer, so a machine on hotel wifi works exactly like one on the LAN.

## ACTION REQUIRED — the six things only you can do

Everything below this section is reference. This section is the work queue for a human, ordered
by what unblocks the most. Each item names what stays broken until it is done, so nothing here
can be quietly reported as finished while it is still outstanding.

Nothing in this list is waiting on code. Every one of them needs a credential, a machine you are
sitting at, or a Google consent screen — none of which an agent can supply.

| # | Do this | Where | Until then |
|---|---|---|---|
| 1 | `bash mesh/bootstrap.sh`, then on `phill-desktop` the two `schtasks` commands it prints | each of the 3 machines | No machine is fully enlisted and dispatchable. Dispatch has nothing to assign to. The script exits non-zero and names the gap if a node only half-joined. |
| 2 | Set `MESH_DISPATCH_ENABLED=1` | Railway | Work is never assigned. The fleet is awake but idle. |
| 3 | Set `SUPABASE_UNITE_GROUP_URL` + `SUPABASE_UNITE_GROUP_SERVICE_KEY` | Vercel | `cc-wiki-graph` 500s. This is the **last remaining production e2e failure**. |
| 4 | Apply the `conversation_digests` migration, then set `CONVERSATION_SYNC_ENABLED=1` | Supabase, then Railway | No machine can search another's conversations. |
| 5 | Run `scripts/setup-pc-ssh.ps1`, then run it again with `-SyncCommands` | the Windows PC | `/done` and the other PC-only commands cannot be read, so they cannot be ported. **Both runs are needed** — without the flag the script proves the connection and copies nothing. |
| 6 | Grant YouTube OAuth **or** drop a Takeout export | browser | The transcript producer has no input; the wiki pipeline stays empty. |

Optional, unblocks the free-model research lane rather than a broken surface:
set `OPENROUTER_API_KEY` on Railway. Without it the OpenRouter harness raises on first call, so
any "run the swarm on free models" request fails at the first request rather than degrading.

### Before 1 and 2 on `unite-mac-mini` — check for an ambient `MESH_REPO_DIR`

```bash
echo "${MESH_REPO_DIR:-(unset — good)}"
```

If it prints a path, **do not set `MESH_DISPATCH_ENABLED` yet** — it is one
Railway variable for the whole fleet (item 2), not a per-node switch, so turning
it on to use the other machines also starts feeding this one. `mesh/runner.py`
`_repo_dir_for()` falls back to it, so the runner does its claimed work in whatever
directory that variable names rather than in the checkout it claimed the ticket
against — and the claim still reads as served. RA-7375 records it exported on
`Phills-Mac-mini` pointing at a Codex worktree on an external volume, which also
breaks whenever that volume is unmounted.

**No test can tell you this** — check the variable itself, above. `_repo_dir_for()`
cannot distinguish an ambient export from an operator's deliberate relocation, and
`tests/test_mesh_runner_service.py` pins both branches on purpose: one `delenv`s the
variable to test the fallback, the other sets it to prove the override is honoured.
Both pass on an affected node. That is correct unit-test behaviour, not a gap in the
suite — the gap is that the two cases are indistinguishable at runtime, which is
RA-7375's second half.

### Order that wastes the least of your time

1 and 2 together (one sitting, all three machines), then 3 (two minutes, closes the last red
e2e probe), then 5 (unlocks porting `/done`), then 4 and 6 whenever.

### How to confirm each one actually took

Do not trust the setting screen — confirm from the system:

| # | Confirm with |
|---|---|
| 1 | Two checks, not one. **Visibility:** `curl -s "$PI_CEO_API_URL/api/mesh/fleet" -H "X-Pi-CEO-Secret: $PI_CEO_API_KEY"` → `degraded` false AND 3 rows, all fresh within ~20 s. Zero rows with `degraded` true is a failed read, not a failed join — retry rather than re-joining. **Execution:** only macOS has services `bootstrap.sh` installed, so only there is there something to query without setup: `launchctl list \| grep unite-group.mesh` → 2 entries. On Windows and Linux the script installs nothing, so the check is against whatever *you* created from the commands it printed — `schtasks /Query /TN NexusMeshRunner` once you have run its `/Create`, or your own systemd user unit. Nothing to query means supervision was never installed, which is a fail, not an inconclusive. A fresh row proves only that the heartbeat published — see below. |
| 2 | Railway logs show `mesh_dispatch id=… assigned=N online=[…]` within 5 minutes |
| 3 | The `e2e` workflow on `main` reports `113 passed · 0 failed` |
| 4 | `GET /api/conversations/recent` with the secret returns 200 rather than 503 |
| 5 | The `-SyncCommands` run reports every file verified **by name** in the remote listing. A run without that flag stops at "Re-run with -SyncCommands" and is not step 5. |
| 6 | `python3 scripts/youtube_transcripts.py --dry-run` plans a non-zero number of clips |

**Why item 1 needs a local check too.** A `mesh_fleet` row is written by the
heartbeat daemon alone, and nothing in the snapshot reports whether the work
runner is supervised. `agents[]` does not cover it either: `running_agent_sessions()`
scans for `claude`/`codex`/`hermes` binaries rather than the runner daemon, and the
runner's breadcrumb only produces an agent row when it is *actively on a task* —
`mesh/heartbeat.py:171` skips an idle one deliberately, so as not to fabricate an
agent. A supervised idle node and a node running only the heartbeat are therefore
indistinguishable from the API. On macOS `bootstrap.sh`'s own exit code is the
reliable signal, because it now reports supervision separately; elsewhere it
installs nothing and says so.

A step that reports success but fails its confirmation is not done — say so rather than moving on.

## Check the fleet is alive

```bash
curl -s "$PI_CEO_API_URL/api/mesh/fleet" -H "X-Pi-CEO-Secret: $PI_CEO_API_KEY" | python3 -m json.tool
```

**Read `degraded` first.** If it is `true`, the read itself failed and every list in the
response is empty for that reason — `errors[]` names which source broke and why
(`not-json` = something in front of Supabase answered with a page rather than data;
`not-a-list` = PostgREST refused the query; `http-error` = it answered non-2xx). Retry
before concluding anything. Until RA-7392 the response could not say this: a failed read
returned the same four empty lists as a healthy fleet nobody had joined, so the instruction
below sent operators to re-run a join that had in fact already succeeded.

With `degraded` false, read `machines[].is_stale` — a node whose heartbeat is older than
60 s reads stale and is skipped by dispatch. `agents[]` shows what is running; `claims[]`
shows open work. A machine missing from a NON-degraded response never enlisted: run the
join below on it.

## Join a machine to the fleet

```bash
bash mesh/bootstrap.sh          # idempotent; safe to re-run
```

Wires the agent hooks, writes credentials to `~/.hermes/.env` (mode 600), publishes one
heartbeat, and **on macOS only** installs the heartbeat daemon and work runner as launchd
services. The machine holds only `PI_CEO_API_KEY` — never the Supabase service-role key.

**Read the last line and the exit code.** The script reports `enlisted` only when the heartbeat
published *and* supervision was installed, and exits non-zero otherwise, naming which half
failed. It used to print `Done. $HOST is enlisted with visibility + work execution.` and exit 0
unconditionally — including on a node where the heartbeat returned `{"published": false}` and no
daemon was installed at all. Still verify with the fleet call above rather than the output: a new
row should appear within ~20 s.

`bootstrap.sh` is bash. On `phill-desktop` run it under WSL or Git Bash; without either, that
node cannot run it at all and needs a PowerShell port. Under Git Bash it **enlists visibility but
not execution** — it does not install supervision, so the node goes stale ~60 s later and
dispatch skips it. The script now prints the two `schtasks /Create /SC ONLOGON` commands you
must run to finish the join; the same gap applies on Linux, where it prints the two daemon
commands for systemd.

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

1. **Is anything online?** `…/api/mesh/fleet` → `degraded` true means the read failed and the
   emptiness tells you nothing; retry first. Otherwise, all `is_stale`? The machines are
   asleep or the heartbeat daemon died. Re-run `bootstrap.sh` on one and watch the row
   refresh.
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

## Getting files off the Windows PC (the SSH lane)

Some work on `phill-desktop` cannot reach the estate through git at all. `~/.claude`
on that machine **is** the repo `CleanExpo/skills-library`, whose `.gitignore` is
deny-all (`*`) plus an allowlist — and `commands/` is not on it. So
`~/.claude/commands/*.md` is structurally invisible: `git status` cannot see it, the
scheduled estate sync cannot see it, and committing cannot move it. That file's own
comments record the identical bug ten times over for `.github/`, `scripts/`,
`agents/` and `hooks/`.

Allowlisting `commands/**` would fix the sync and **publish those files** —
skills-library is public. That is the same trade the repo already refused for session
handoffs. SSH avoids it: the files travel PC → brain host over the tailnet and never
touch GitHub.

```powershell
# On the Windows PC, once:
.\scripts\setup-pc-ssh.ps1 -BrainHost "<mac-mini>.ts.net" -BrainUser "<user>"
# It prints one command to paste on the brain host, then proves the connection.

# Then, to move the commands across:
.\scripts\setup-pc-ssh.ps1 -BrainHost "<mac-mini>.ts.net" -BrainUser "<user>" -SyncCommands
```

Prerequisites: Tailscale up on both ends (`tailscale status`), and Remote Login
enabled on the brain host (macOS: Settings → General → Sharing → Remote Login).
`scripts/setup-brain-host.ps1` covers the Tailscale side.

The script is idempotent — it reuses an existing key rather than regenerating one,
because a new key would orphan every host that already trusts this machine. Its
connection probe runs with `BatchMode=yes`, so a missing authorisation fails fast
with a reason instead of hanging on a password prompt.

Files land in `~/estate-inbox/pc-commands/` on the brain host and are **not** in
git. Read one before copying it into a repo — that copy is the deliberate act of
publishing it.

## Turn shared conversation search on

Each machine's Claude Code transcripts live only on that machine. This lane makes them
searchable from any of them. **Raw JSONL never travels** — a machine ships only a digest it
already redacted, and the server redacts a second time before writing.

Three steps, in this order:

1. Apply `supabase/migrations/20260830T000001_conversation_digests.sql`. Idempotent, safe to
   re-run. The table is RLS service-role only: this server is its sole reader and writer, and
   machines authenticate to *it* with `X-Pi-CEO-Secret` rather than ever holding the
   service-role key.
2. Set `CONVERSATION_SYNC_ENABLED=1` on the Railway service. Unset or any value outside
   `1/true/yes/on` leaves every route answering 503 to an authenticated caller. The server
   and the collectors accept the same set — pinned by a test, because when they disagreed
   `=true` meant every machine shipped into a 503 forever while this page said it would work.
3. Install the collector on each machine — `scripts/com.piceo.conversation-collector.plist.example`
   (macOS) or `scripts/conversation-collector.task.xml.example` (Windows). Copy to a real
   `.plist`/task first; the templates derive paths from `$HOME` and bake in no username.

Check it before trusting it:

```bash
python3 scripts/conversation_collector.py --dry-run     # plans; no POST, no marker write
curl -s "$PI_CEO_API_URL/api/conversations/recent" -H "X-Pi-CEO-Secret: $PI_CEO_API_KEY"
```

Read the collector's **exit code**, not just its log: `0` ok · `2` lake missing · `3` refused
(disabled, or no credential) · `4` delivery failed · `1` an unmapped status. A scheduler that
records success for a run where nothing was accepted is the failure this lane is built to avoid.

Two behaviours worth knowing before they surprise you:

- **Ingest fails closed on a degraded redactor.** The second pass is the union of
  `app/server/scanner` and the transcript-specific bank in `scripts/sync_claude_sessions.py`.
  If that import breaks, ingest 503s rather than writing under the scanner-only bank, which
  does not match the token shapes transcripts actually carry. Reads stay up.
- **Nothing is lost when a machine is away.** Each machine keeps its own marker, so a MacBook
  that misses a week ships the backlog on its next run.

From inside any Claude session, `conversation_search` and `conversation_recent` are registered
on the MCP server. Both are read-only by design — there is deliberately no write tool, because
one would let any session fabricate another machine's history.

## Turn the YouTube transcript producer on

Writes one `Sources/*.md` clip per accepted video, which the existing `sources_watcher` →
`wiki_ingest` chain then picks up. Ships **off**:

```
YOUTUBE_TRANSCRIPTS_ENABLED=1     # unset or not in 1/true/yes writes nothing
YT_TRANSCRIPT_LIMIT=25            # fetches per run; YouTube throttles by IP
YT_TRANSCRIPT_LANGS=en
```

It reads the catalog `app.server.youtube_intent` maintains, so it does nothing until that
catalog has `accepted` rows — fill it with the OAuth pull-live route or a Google Takeout drop.
Relevance is the catalog's decision, not this script's; it cannot widen what gets ingested.

```bash
python3 scripts/youtube_transcripts.py --dry-run    # plans; issues NO network requests
python3 scripts/youtube_transcripts.py --limit 5
```

`.harness/youtube_transcripts_done.jsonl` is append-only and **permanent**: any video id it
names is skipped forever, undoable only by editing that file. Only two outcomes are recorded
there — a clip was written, or the video confirmedly has no captions. A failed fetch (a blocked
IP, a missing dependency) is counted as failed and left to retry, so one bad run cannot retire
the backlog.

Captions are attacker-controlled text. This script does not interpret them — it writes them to
a file, and interpretation happens downstream behind `swarm/ingest_guard`'s fence and target
allowlist. Nothing here is a trust boundary, and nothing here should grow one.

## After a change to any of this

```bash
bash scripts/handoff-loop.sh
```

One command, and it is the whole release gate. Do not record the individual sub-gates
separately in a receipt — running the Python suite twice exceeds the tool timeout and kills the
push mid-gate.
