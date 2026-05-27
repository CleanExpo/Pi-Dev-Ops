# Nexus Webhook Activation Runbook

Phase C / C4. Step-by-step to wire provider webhooks into Pi-CEO's
`/webhooks/*` endpoints. Order doesn't matter between providers, but
run the verification step after each.

**Prereq:** Phase A/B/C1/C2 merged. `/api/nexus/ingest/health` returns 200.

---

## Common pattern

For each provider:

1. **Generate HMAC secret:** `openssl rand -hex 32` — copy the output.
2. **Set Railway env:** add `<PROVIDER>_WEBHOOK_SECRET=<secret>` to the
   `Pi-Dev-Ops` service variables. Railway will auto-redeploy.
3. **Configure provider webhook:** see provider-specific section below.
4. **Send a test event** from the provider's dashboard.
5. **Verify:** hit `https://pi-dev-ops-production.up.railway.app/api/nexus/ingest/health`
   and confirm `count_24h ≥ 1` for that provider.

---

## Stripe

**Dashboard:** https://dashboard.stripe.com/webhooks (or `/test/webhooks` in test mode)

**Settings:**
- **Endpoint URL:** `https://pi-dev-ops-production.up.railway.app/webhooks/stripe`
- **Events to subscribe:**
  - `invoice.paid`
  - `customer.subscription.created`
- **HMAC secret:** Stripe-generated webhook signing secret (`whsec_…`)
  → set on Railway as `STRIPE_WEBHOOK_SECRET`

**Workspace attribution (one of):**
- **Preferred:** populate `metadata.workspace_slug` + `metadata.workspace_id` on Stripe
  customers / invoices when creating them.
- **Fallback:** map the workspace's `stripe_customer_id` column in `client_workspaces`
  (column added by C2). The resolver from C2 picks up.

**Test event:** Stripe dashboard → Webhooks → your endpoint → "Send test webhook" →
pick `invoice.paid`.

**Verify SQL:**
```sql
SELECT id, metric, value_numeric, captured_at
FROM outcomes
WHERE source = 'stripe'
ORDER BY captured_at DESC
LIMIT 5;
```

---

## Vercel

**Dashboard:** https://vercel.com/account/integrations → Outgoing Webhooks
(or per-project Settings → Git → Deploy Hooks)

**Settings:**
- **Endpoint URL:** `https://pi-dev-ops-production.up.railway.app/webhooks/vercel`
- **Events to subscribe:**
  - `deployment.succeeded`
  - `deployment.error`
- **HMAC secret:** Vercel-generated → set on Railway as `VERCEL_WEBHOOK_SECRET`

**Workspace attribution:** populate `client_workspaces.vercel_project` with the
Vercel project ID for each workspace. The resolver from C2 picks up.

**Test event:** push a no-op commit to any tracked branch, OR use Vercel CLI:
```bash
vercel deploy --prod
```

**Verify SQL:**
```sql
SELECT id, metric, value_text, captured_at
FROM outcomes
WHERE source = 'vercel'
ORDER BY captured_at DESC
LIMIT 5;
```

---

## Linear

**Dashboard:** https://linear.app/settings/api/webhooks (workspace admin)

**Settings:**
- **Endpoint URL:** `https://pi-dev-ops-production.up.railway.app/webhooks/linear`
- **Event types:**
  - **Issues** (covers `Issue` updates including state → `completed`)
- **HMAC secret:** Linear-generated → set on Railway as `LINEAR_WEBHOOK_SECRET`

**Workspace attribution:** populate `client_workspaces.linear_team_id` with the
Linear team key (e.g. `ENG`, `OPS`). The resolver from C2 picks up.

**Test event:** create + complete a throwaway issue in Linear.

**Verify SQL:**
```sql
SELECT id, value_text, captured_at
FROM outcomes
WHERE source = 'linear' AND metric = 'issue_completion'
ORDER BY captured_at DESC
LIMIT 5;
```

---

## Deferred providers (not in this runbook)

- **PostHog** — webhooks are a paid add-on; activate when budget allows.
- **Sentry** — issue webhooks need org admin setup + workspace mapping plumbing
  (no `sentry_org_slug` column on `client_workspaces` yet).

The parsers exist (B4) and tests pass; activation is purely operator-side and
can land in a follow-up C-series PR once business need surfaces.

---

## Smoke test (after all three live)

```bash
curl -sS https://pi-dev-ops-production.up.railway.app/api/nexus/ingest/health | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'as_of={d[\"as_of\"]}')
for src, bucket in d['providers'].items():
    status = '🟢' if bucket['count_24h'] > 0 else '⚪'
    print(f'  {status} {src:8s} count_24h={bucket[\"count_24h\"]:3d} last={bucket[\"last_seen_at\"]}')"
```

Expected after activation + test events: `stripe`, `vercel`, `linear` all 🟢.

---

## Rollback (per provider)

1. Delete the webhook in the provider's dashboard.
2. (Optional) Unset `<PROVIDER>_WEBHOOK_SECRET` on Railway.

Webhook deliveries stop immediately. Already-ingested outcomes stay (they
represent real historical signals).
