# Runbook: rotating the fleet key (X-Pi-CEO-Secret)

Ticket: RA-8408. Code: `app/server/internal_secret.py`.

The fleet key is the value machines, schedulers and the dashboard send in the
`X-Pi-CEO-Secret` header. Until RA-8408 the server accepted exactly one value, so a
rotation had to move every holder at the same instant. On 15/11/2026 that was not
possible, and every heartbeat failed for 36 hours.

The server now accepts two values at once: the current key and an optional next key.
That lets you put the new key on the server first, move each holder across one at a
time while both keys work, and only then make the new key the current one.

**Merging the code does not end the exposure of the old key.** The exposure ends only
after steps 4, 5 and 6 are all done. Until step 4 the old key still opens every route;
until step 5 it still signs GitHub events; until step 6 it remains a dormant fallback.

## The three variables

| Variable | What it is |
|---|---|
| `TAO_INTERNAL_WEBHOOK_SECRET` | The current fleet key. If unset, the server falls back to `TAO_WEBHOOK_SECRET` (today's state). |
| `TAO_INTERNAL_WEBHOOK_SECRET_NEXT` | The next fleet key, set only during a rotation. Honoured only when it is at least 32 printable characters with no spaces, differs from the current key and differs from the read-only key. Otherwise it is ignored and the current key keeps working. |
| `TAO_FLEET_READ_SECRET` | The read-only fleet key, accepted only by `GET /api/mesh/fleet` and `GET /api/mesh/lane-events`. The read-only key must be a different value from every write key; a next key equal to it is ignored. |

Two GitHub secrets are easy to confuse, and they are rotated separately:

- `PI_CEO_WEBHOOK_SECRET` is a GitHub Actions repository secret. It sends the fleet key
  in the header from `workspace_intel_brief.yml`. It is a holder, not the signing secret.
- `TAO_GITHUB_WEBHOOK_SECRET` is the Railway variable that checks GitHub's webhook
  signature. It is not part of the two-key change; step 5 rotates it.

## What the server prints

Every deployment prints one start-up line for the key state:

| Start-up line | Meaning |
|---|---|
| `TAO_INTERNAL_WEBHOOK_SECRET not set — internal intake webhooks are disabled (503)` | No current key. Every route answers 503. |
| `internal_secret: next slot not set` | Normal running. |
| `internal_secret: next slot ACTIVE: rotation in progress, finish the swap (...)` | Both keys are accepted. |
| `internal_secret: next slot equals current: swap applied, now remove TAO_INTERNAL_WEBHOOK_SECRET_NEXT` | Step 4(a) is done; step 4(b) is next. |
| `internal_secret: TAO_INTERNAL_WEBHOOK_SECRET_NEXT is set but IGNORED (fails policy)` | The next value fails policy and is not accepted. |

Two more warnings can appear beside it: `current key comes from the TAO_WEBHOOK_SECRET
fallback`, and `read-only fleet key equals a write key`. No line ever shows a key value.

While a next key is honoured, the server also writes `internal_secret: accepted
slot=<current|next> where=<family>` at most once per family every 10 minutes. Refusals
are always written as `internal_secret: rejected reason=<missing|mismatch>
where=<family>`, at the same rate.

Every variable change takes effect only after the server redeploys. For each step:
deploy it, note the deployment, and read the start-up line from that deployment, not
from an earlier one.

## Holder table

Tick a row only when its caller-side success has been seen. A holder that cannot be
confirmed blocks step 4.

| Holder | Where the value lives | How often it calls | How to confirm it is on the new key | Confirmed |
|---|---|---|---|---|
| Windows PC | machine environment (already the new key, per the 17/11 handoff) | every 20 s | heartbeat fresh in Mission Control | [ ] |
| Mac Mini, MacBook | `PI_CEO_API_KEY` and `TAO_WEBHOOK_SECRET` in `~/.hermes/.env` and profile env files; MCP server env; `MC_LANE_SECRET` / keychain `mc-lane-secret` | every 20 s (heartbeat); on use (others) | restart the process, then heartbeat fresh; the Mission Control status tool returns data | [ ] |
| Desk voice loop | `PI_CEO_API_KEY` / `TAO_WEBHOOK_SECRET` | only while running | one call succeeds | [ ] |
| GitHub Actions secret `PI_CEO_WEBHOOK_SECRET` (sends the header; not the signing secret) | repository secrets | manual only | run `workspace_intel_brief.yml` by hand; the run is green | [ ] |
| Vercel `TAO_WEBHOOK_SECRET` (Margot bubble) | Vercel env; needs a redeploy | on use | the bubble answers | [ ] |
| Vercel `TAO_INTERNAL_WEBHOOK_SECRET` / `TAO_FLEET_READ_SECRET` (fleet tile; record which is set) | Vercel env | on page load | the fleet tile loads | [ ] |
| Vercel `WEBHOOK_SECRET` and the morning-intel outside caller (limit L1: move together) | Vercel env; n8n | daily (11:45 AEST, per the code comment) | trigger the workflow by hand; it succeeds | [ ] |
| n8n: workspace RSS monitor, weekly brief (Sunday 09:00 UTC), and any other workflow that sends the header | n8n credential store | daily / weekly | execute each workflow by hand; it succeeds | [ ] |
| Whoever posts to `/api/webhook/routine-complete` | UNKNOWN | irregular | UNKNOWN: identify before step 4 | [ ] |

The poster to `routine-complete` is not known. If it is still unidentified 7 days after
step 2, the founder decides whether to swap anyway. A lockout would then show as
`rejected reason=mismatch where=webhooks`, and the combined undo in step 4 restores it.

## Steps

Every production step is the founder's, with one yes per step.

### Step 0 — make sure the new key was never exposed

On each machine that took part in the 15/11 rotation, run a count-only search of
transcripts, handoffs and shell history for the new key. The command must print a match
count and never the value. Prove the command first with a planted fake string, which
must give a count of 1. If any real count is not zero, mint a fresh key and use that.

From here on, every copy of a key goes from its store to the holder through a pipe or a
keychain read. It is never typed as a command argument, pasted into a chat, or read into
an agent's context. The read-only fleet key stays a different value from every write key.

What you should see: a count of 1 for the planted string and 0 for the key on every machine.

How to stop: nothing has changed yet; stop at any point.

### Step 1 — deploy the merged code

What you should see: `internal_secret: next slot not set`, and (expected today) the
warning that the current key comes from the `TAO_WEBHOOK_SECRET` fallback. Record which
start config printed it (U6).

How to stop: revert the pull request and redeploy. This is safe; no holder has changed.

### Step 2 — set the next key

Set `TAO_INTERNAL_WEBHOOK_SECRET_NEXT` on Railway. Do not touch `TAO_WEBHOOK_SECRET`.
Deploy, note the deployment, and read the start-up line from that deployment.

What you should see: `internal_secret: next slot ACTIVE`. If it reads `IGNORED`, stop:
the value fails policy. Then the Windows PC heartbeat turns fresh in Mission Control
without anyone touching the PC, after that deployment went live. One `accepted
slot=current` line also appears, which proves the log reaches Railway (U5).

How to stop: remove the variable and redeploy, or revert. This is safe while no holder
has moved.

### Step 3 — move the holders one at a time

Move each holder in the order of the holder table. Restart each process. Tick its row
only when its own confirmation succeeds.

From the first move onward: roll forward only. Never revert the pull request and never
press Railway Rollback (U7), because old code accepts only the old key and every moved
holder would go dark.

What you should see: after each move, that holder's confirmation succeeds and no new
`rejected reason=mismatch` line appears.

How to stop: if the server must go back to old code, first move every moved holder back
to the old key, last moved first. Only then revert.

### Step 4 — swap the keys

The swap gate has three parts, and all three must hold at once:

1. This deployment's start-up line reads `next slot ACTIVE`.
2. Every row of the holder table is ticked by a caller-side success. A route family
   with no log line at all is unknown, not quiet: silence never ticks a row.
3. No `accepted slot=current` and no `rejected reason=mismatch` line has appeared since
   the last holder moved.

Then make two separate changes, each its own deploy, in this order:

- (a) Set `TAO_INTERNAL_WEBHOOK_SECRET` to the new value. Deploy, note the deployment,
  and read the start-up line from that deployment: `next slot equals current: swap
  applied`. Wait for one heartbeat cycle with fresh heartbeats and no `rejected` line.
- (b) Only then remove `TAO_INTERNAL_WEBHOOK_SECRET_NEXT`. Deploy and read the start-up
  line: `next slot not set`, with no fallback warning.

Removing the next key first would lock out every moved holder.

What you should see: the two start-up lines above, in that order, and fresh heartbeats.

How to stop: undo with one combined change: the old value in the current slot and the
new value in the next slot, together. If Railway applies them as two deploys, set the
next slot first. Then read `next slot ACTIVE`. Never set the current slot back alone. If
the two changes land as two deploys, the first prints `next slot equals current`; ignore
that line until the current slot has been set back.

### Step 5 — rotate the GitHub signing secret

In the same window, set `TAO_GITHUB_WEBHOOK_SECRET` on Railway and the secret in the
GitHub webhook setting together. This cannot be half-done; both sides change together.

What you should see: the next GitHub delivery shows a 2xx response in the webhook's
recent deliveries.

How to stop: put the previous signing secret back on both sides together.

### Step 6 — retire the old variable

Once steps 4 and 5 are confirmed, delete `TAO_WEBHOOK_SECRET` on Railway, or overwrite
it with a fresh random value no holder has. Do the same for the dashboard's old
variables once their callers have moved. Until this step, deleting either newer
variable would silently bring the exposed key back.

What you should see: `next slot not set` with no fallback warning, and every heartbeat
fresh.

How to stop: set the variable again. Nothing reads it once both newer variables are set.

### After the swap

For one full daily cycle and through the next Sunday run, check that every heartbeat is
fresh, the morning brief arrived, and no `rejected reason=mismatch` line appeared.

## Named limits

- **L1** The dashboard route `dashboard/app/api/webhook/morning-intel/route.ts` is a
  second, single-key check on Vercel. Its Vercel variable and its outside caller must
  move together. Follow-up ticket (b).
- **L2** Log lines name the route family, not the holder. `routing` logs as
  `cost_report`; `mesh_ship` and lane-events POST log as `mesh`; `webhooks` covers four
  callers. A server line therefore cannot confirm one holder, which is why the swap gate
  uses a caller-side success per holder.
- **L3** The structural test cannot catch a new comparison written inside a file that is
  already allowed to compare secrets (for example `routes/webhooks.py`), nor one that
  borrows a value from the owner's private functions. The route-enumeration test covers
  the direction that matters: a new route that takes the header and is not tested fails.

## Things to observe during the rollout

- **U2** What n8n holds, and which of its workflows send the header.
- **U3** Who posts to `/api/webhook/routine-complete` (the UNKNOWN row above).
- **U4** Whether a Railway variable change redeploys by itself, and whether two changes
  are batched into one deploy.
- **U5** How long Railway keeps logs.
- **U6** Which of the repository's two Railway start configs is live.
- **U7** Whether Railway Rollback also restores variables. Until this is known, treat
  Rollback as unsafe after step 3 begins.

Background on why a changed value needs a redeploy: `.github/workflows/kill-switch-proof.yml`
records the same lesson, that environment variables bind per deployment.
