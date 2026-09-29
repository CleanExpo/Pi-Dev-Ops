---
name: client-portal-provision
description: Thin wrapper around the Pi-CEO Hour-1 provisioner. Given a client slug + email, invokes `swarm/inbox/provisioner.py` to spin up the full Linear project + Supabase portal_content + ContextBot Telegram intake bot + welcome email + Phill ping. Use when the user says "onboard {client}", "spin up portal for", "new client setup", or right after `stripe-milestone-invoice` confirms a deposit cleared.
---

# Client Portal Provision

Triggered after a client's deposit clears, this skill drives the **Hour-1 client experience** end-to-end — the moment Stripe webhook fires, this gets called.

## When to invoke

- The user says: "onboard {client}", "spin up portal", "new client setup", "provision {slug}"
- The user pastes: a Stripe `checkout.session.completed` event for a `nexus_client.status='onboarding'` row
- `stripe-milestone-invoice` skill has just confirmed a deposit cleared

## What it does

1. **Validates inputs:** kebab-case slug, contact email, signed-SOW path in the wiki. Refuses if any missing — Phill is the only one allowed to dispatch without a signed SOW.
2. **Shells out** to the live provisioner worker:
   ```bash
   cd ~/Pi-Dev-Ops && python3 -m swarm.inbox.provisioner
   ```
   (The worker is also wired as `ai.pidev.provisioner` LaunchAgent on /60s — this skill is for forced/manual invocation, e.g. "we need this NOW not next minute".)
3. **Health-checks the 5 artefacts:**
   - Linear project exists and is linked in `nexus_clients.portal_content.linear_project_id`
   - `nexus_clients.portal_content.schema_version === "hour1-v1"`
   - ContextBot row in `context_bots` with `kind='client'` (BotFather mint may still be pending if rate-limited)
   - Welcome email send confirmed in Resend logs (or graceful warning if `RESEND_API_KEY` missing)
   - Single-shot Phill ping landed on `@PiCeoOpsBot`
4. **On any failure:** escalates to the Pi-CEO Board (NOT Phill — see `[[autonomous-mandate]]`) for verdict + records to `~/2nd Brain/2nd Brain/Wiki/board-deliberation-*.md`.
5. **On success:** ONE Telegram message via `swarm.telegram_router.send(channel="ops")` with the portal URL + bot `t.me/` link. Single-shot per `[[no-repeating-alerts]]`.

## Steps

```
# 0. Pre-flight
ls ~/2nd\ Brain/2nd\ Brain/Wiki/sow-${SLUG}-*.md  # SOW exists
psql/REST query nexus_clients WHERE slug=${SLUG}  # client row exists

# 1. Dispatch
cd ~/Pi-Dev-Ops
python3 -m swarm.inbox.provisioner

# 2. Verify via PostgREST
curl -H "apikey: $SUPABASE_UNITE_GROUP_SERVICE_KEY" \
  "$SUPABASE_UNITE_GROUP_URL/rest/v1/nexus_clients?slug=eq.${SLUG}&select=portal_content"
# Expect: portal_content.schema_version = "hour1-v1"

# 3. Confirm Telegram delivery (no second ping)
tail -1 /tmp/provisioner.log
```

## Constraints

- **Never** ping Phill more than once per provisioning run (`[[no-repeating-alerts]]`).
- **Never** retry the welcome email automatically — Resend tracks failures, Phill picks up.
- **Never** mint BotFather bots from here — that's `[[project-contextbot-platform]]`'s pending-row queue. This skill enqueues, not mints.
- Verify `nexus_clients.status='onboarding'` before running — if already `active`, abort (idempotency).
- Stay inside the Pi-CEO swarm + unite-group Supabase scope per `[[unite-group-only]]`.

## Output

End with a recommendation per `[[always-recommend]]`. Example:

> ✅ Hour-1 provisioned for **{Client}**. Portal: https://unite-group.in/clients/{slug} · Linear: {url} · ContextBot: pending mint (rate-limit clears {time}). Next move: kick off Day-0 cadence — Margot drafts the discovery brief, you review tomorrow 9am.

## Related

- Code: `~/Pi-Dev-Ops/swarm/inbox/provisioner.py`
- Playbook: `[[playbook-client-onboarding-7stage]]`
- Memory: `[[project-contextbot-platform]]`
- Wiki: `~/2nd Brain/2nd Brain/Wiki/duncan-perkins-playbook-2026-05-14.md`
