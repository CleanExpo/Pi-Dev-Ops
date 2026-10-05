---
name: sow-draft
description: Drafts a milestone-based Statement of Work for a Unite-Group client. Verifies the client's ABN + GST status via the ABR public lookup, lays out 4-7 milestones with deliverables and deposit %, outputs Markdown + a machine-readable sow.json ready for `stripe-milestone-invoice`. Use when the user says "draft SOW", "scope of work", "write the milestones for", "proposal for {client}", or after the `discovery-12q` flow finishes.
---

# SOW Draft

Generates the **legally-defensible, GST-correct, milestone-shaped SOW** that gates every Unite-Group client engagement.

## When to invoke

- "draft SOW for {client}"
- "scope of work for {client}"
- "write the milestones for {client}"
- "proposal for {client}"
- Immediately after a discovery questionnaire (12-Q via ContextBot) completes

## Pre-flight inputs

| Input | How to obtain |
|---|---|
| Client legal entity name | `discovery-{client}-{date}.json` or `project_{client}` memory |
| Client ABN | ABR Lookup — `https://abr.business.gov.au/Search/ResultsActive?SearchText={name}` |
| Client GST status | ABR Lookup — extract `Goods & Services Tax (GST): Registered from {date}` |
| Service Provider entity | Unite-Group Nexus Pty Ltd, ABN `95 691 477 844`, GST registered |
| Engagement type | "Build" / "Retainer" / "Workshop" — defaults to Build for first engagement |
| Total budget bound (AUD) | From discovery `budget_max` field; if missing, ask Phill (one question only) |

## Steps

1. **ABR verify both parties.** Use Chrome MCP if signed in, else hit the public search HTML and regex out the 11-digit ABN + GST date. Capture: entity name, ABN, ACN if present, GST start date, state + postcode. Both parties MUST be GST registered — if client isn't, surface that as a billing-structure question BEFORE drafting.
2. **Load the template.** The canonical milestone shape is in `[[playbook-client-onboarding-7stage]]`. Copy the structure (Parties → Background → Scope → Payment Terms → Acceptance → Change Requests → Timeline → IP → Confidentiality → Compliance → Termination → Liability → Disputes → Governing Law → Signatures).
3. **Generate 4-7 milestones.** Defaults to 4 for a build (Discovery & Architecture / MVP Build / Integrations & Launch / Stabilisation & Handover) but expand if the discovery surfaced 6+ distinct workstreams. Each milestone:
   - Name + day window (e.g. "Days 0–14")
   - 4-6 concrete deliverables
   - Acceptance gate
   - Payment trigger (deposit upfront, Net 7 thereafter)
   - Suggested AUD range — **DO NOT** invent specific dollar amounts; mark every fee as `$<TBD>` and surface a `Pre-send Phill checklist` at the end of the document for him to fill
4. **Emit two artefacts:**
   - `~/pi-seo-workspace/unite-group/docs/sows/sow-{client}-{YYYY-MM-DD}.md` (signable document — same structure as `duncan-itr-platform-sow-2026-05-14.md`)
   - `~/pi-seo-workspace/unite-group/docs/sows/sow-{client}-{YYYY-MM-DD}.json` (machine-readable hand-off for `stripe-milestone-invoice`):
     ```json
     {
       "client": {"slug": "...", "legal_entity": "...", "abn": "...", "gst_registered": true, "contact_email": "..."},
       "service_provider": {"entity": "Unite-Group Nexus Pty Ltd", "abn": "95691477844"},
       "currency": "AUD",
       "gst_handling": "exclusive",
       "milestones": [
         {"id": "discovery", "label": "...", "days": "0-14", "deliverables": [...], "fee_aud_excl": null, "payment_trigger": "30% deposit + 70% on acceptance"},
         ...
       ],
       "total_aud_excl": null
     }
     ```
5. **Hand-off prompt.** End the response with a `[[always-recommend]]`-compliant recommendation that points at the next move (typically: "Fill the 4 milestone amounts in `Pre-send Phill checklist`, then I'll run `stripe-milestone-invoice` to mint the deposit Payment Link.").

## Constraints

- **NEVER** invent dollar amounts. Phill fills these — they're commercially sensitive and per-client.
- **NEVER** skip ABR verification — false ABN = invoice rejection + ATO compliance risk.
- **GST exclusive** is the default for both parties registered — invoice line items show net + GST line added by Stripe Tax. If the client isn't GST registered, flag this and ask Phill whether to charge inclusive or absorb 10%.
- AU jurisdiction (QLD law) defaults. Override only if the client SPECIFICALLY requests another state.
- Liability cap = 6 months of fees paid. Don't increase without Phill saying so explicitly.
- Match the structure of the Duncan SOW exactly — Phill has already approved that shape (`docs/sows/duncan-itr-platform-sow-2026-05-14.md`).

## Output

End with `[[always-recommend]]`-compliant recommendation. Example:

> ✅ SOW v1 drafted at `docs/sows/sow-{client}-{date}.md` — both ABNs verified, GST handling exclusive, 4 milestones over 86 days. Awaiting your 4 milestone $ amounts in the checklist. Once filled, I run `stripe-milestone-invoice` and Duncan gets the deposit Payment Link in 2 minutes.

## Related

- Playbook: `[[playbook-client-onboarding-7stage]]`
- Template reference: `docs/sows/duncan-itr-platform-sow-2026-05-14.md`
- Next skill in chain: `[[stripe-milestone-invoice]]`
- Memory: `[[project-duncan-perkins]]` for milestone-pace reference
