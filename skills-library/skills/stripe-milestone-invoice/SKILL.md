---
name: stripe-milestone-invoice
description: Creates a Stripe Customer + Product + AU GST Tax registration + Payment Link for the deposit milestone, plus draft invoices for the remaining milestones. Reads sow.json from `sow-draft`. Resolves Stripe API key from ~/.hermes/.env (NEVER asks user to paste). Use when the user says "send invoice", "stripe link", "bill {client} deposit", "set up billing", or hands off from sow-draft with milestone $ filled.
---

# Stripe Milestone Invoice

Mints the **deposit Payment Link** that gates every Unite-Group engagement. The one financial trigger that fires the entire Hour-1 automation cascade.

## When to invoke

- "send invoice for {client}"
- "Stripe payment link for {client}"
- "bill {client} deposit"
- "set up Stripe billing"
- Immediately after `sow-draft` completes AND Phill has filled the milestone $ amounts in the SOW's `Pre-send Phill checklist`

## Pre-flight checks

1. **`sow.json` exists** at `~/pi-seo-workspace/unite-group/docs/sows/sow-{client}-{date}.json` AND `total_aud_excl` is populated (Phill filled the numbers).
2. **Stripe live key resolvable** — `STRIPE_SECRET_KEY=sk_live_*` in `~/.hermes/.env`. Verify the prefix is `sk_live_` not `sk_test_` per [[secrets-handling]] — never ask user to paste keys.
3. **Stripe Tax registered for AU GST** — if not, register via `POST /v1/tax/registrations` with `country=AU, country_options[au][type]=standard`. Idempotent.
4. **Stripe webhook endpoint live** at `https://unite-group.in/api/webhooks/stripe` (`we_*` exists in `GET /v1/webhook_endpoints`). If missing, register it first — without it, the Hour-1 provisioner won't fire.

## Steps

1. **Idempotent Customer create.** Search by email first: `GET /v1/customers/search?query=email:'{email}'`. If exists, reuse. Else create with:
   ```
   POST /v1/customers
     name=Legal Entity Pty Ltd
     email=...
     description=Engagement label from sow.json
     address[country]=AU
     metadata[nexus_slug]={slug}
     metadata[abn]={abn}
     metadata[sow_version]=...
     tax_id_data[0][type]=au_abn
     tax_id_data[0][value]={abn}
     preferred_locales[]=en-AU
   ```
2. **Idempotent Product create.** Search `metadata['engagement']:'{slug}-build'`. Else create:
   ```
   POST /v1/products
     name=Engagement label
     description=From sow.json + reference to signed SOW path
     metadata[engagement]={slug}-build
     metadata[sow_version]=...
     tax_code=txcd_10000000
     shippable=false
   ```
3. **Create Payment Link for deposit** (30% of first milestone, AUD, GST exclusive). Use Stripe Tax (automatic_tax). Idempotency key = `{slug}-deposit-v1`.
   ```
   POST /v1/payment_links
     line_items[0][price_data][currency]=AUD
     line_items[0][price_data][product]={prod_id}
     line_items[0][price_data][unit_amount]={deposit_cents}
     line_items[0][price_data][tax_behavior]=exclusive
     line_items[0][quantity]=1
     after_completion[type]=hosted_confirmation
     automatic_tax[enabled]=true
     metadata[nexus_slug]={slug}
     metadata[milestone]=deposit
   ```
4. **Draft invoices for remaining milestones.** For each `milestone[1..N]`, create a draft invoice with `collection_method=send_invoice, days_until_due=7, currency=AUD`. Do NOT finalize — Phill sends them as each milestone gates.
5. **Back-fill Supabase.** `PATCH /rest/v1/nexus_clients?slug=eq.{slug}` with `stripe_customer_id={cus_}` and `plan='build-milestone'` (only valid plan values from current schema — check before sending). Use the service-role key.
6. **Verify webhook trigger path.** Manually trigger a test event on the webhook endpoint via `POST /v1/webhook_endpoints/{we_}/test`. Confirm an entry lands in `stripe_events` table. If not, the Hour-1 cascade won't fire — flag immediately.
7. **Compose email body.** Use the Resend SDK (or hit `https://api.resend.com/emails` directly). Subject: `"{Client first name}, your deposit link for {Engagement label}"`. Body in Gun Metal + Candy Red template (per [[design-preferences]]) — link to Payment Link + SOW PDF attachment.
8. **DO NOT send the email automatically.** Always show Phill the draft + recipient + amount and ask explicit confirm before sending. This is the single highest-stakes step in the entire flow.

## Constraints

- **Idempotent.** Re-running this skill on the same `sow.json` MUST NOT create duplicate Customers, Products, or Payment Links. Always search first.
- **Never accept pasted keys.** Pull from `~/.hermes/.env` or 1Password via `op` CLI per [[secrets-handling]].
- **AU GST exclusive** default. Stripe Tax must be ON and the customer's `tax_id_data` must include the ABN so the invoice shows their ABN too.
- **No Test mode unless requested.** Stripe key must be `sk_live_*`. If the key is `sk_test_*`, ABORT and surface a clear "you're on test keys" message — never silently bill on test.
- **Confirm before sending email.** The Payment Link itself can be minted autonomously (it's a URL — minting is reversible). Sending the email to the client is the one step that requires Phill's explicit go.
- AU payout hold: first live-account payout sits 7 days. Don't promise downstream payments (contractors, infra) before Day 8.

## Output

End with explicit recommendation per [[always-recommend]]. Example:

> ✅ Stripe Customer `cus_xxx` + Product `prod_xxx` + Deposit Payment Link `https://buy.stripe.com/xxx` minted (AUD ${amount} excl. GST → ${amount_inc} inc. GST). Email drafted, not sent. **Confirm send?** Once Duncan pays, the provisioner cascade fires within 60 seconds.

## Related

- Previous skill in chain: `[[sow-draft]]`
- Next skill in chain (auto-triggered on `checkout.session.completed` webhook): `[[client-portal-provision]]`
- Playbook: `[[playbook-client-onboarding-7stage]]`
- Code: `~/pi-seo-workspace/unite-group/src/app/api/webhooks/stripe/route.ts`
- Memory: `[[feedback-secrets-handling]]`, `[[project-duncan-perkins]]`
