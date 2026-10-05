---
name: ai-website-generate
description: Generate an on-brand, schema-marked website section from a Google Business Profile location, gated by the estate's copy validators. Dispatched by ai-website; not a standalone entry point.
disable-model-invocation: true
allowed-tools: Bash, Read
---

# ai-website-generate — GBP location → validator-gated site section

The **generate** stage of the AI-Websites pipeline. Turns one Google Business Profile
location into a deterministic, on-brand, `schema.org`-marked site section whose copy has
passed the same validators as every estate surface (Aid Rule, ACL §18 superlatives,
schema/copy match, brand forbidden-words). It never deploys — it returns the artifact.

Owned by [[ai-website]], which dispatches this skill. Do not invoke it directly as an
entry point.

## Prerequisites (verify first)
- The Synthex generator pipeline is live: `lib/site-generator` + `generate_site_from_gbp`
  MCP tool + `POST /api/ai-websites/generate` route (Phase 3/4 PRs merged + deployed).
- The target organisation has a **connected Google Business Profile** (`googlebusiness`
  OAuth connection). No connection → the tool returns `{ ok: false, error }`; stop and
  report that the account must connect GBP first. Do NOT fabricate a profile.
- **Completion criterion:** you hold the GBP location resource name
  (`accounts/{id}/locations/{id}`) and confirmed the org is connected.

## Two invocation paths (pick by caller)

### A. MCP tool (agent-to-agent, preferred)
Resolve the tool by capability via ToolSearch — never hardcode a server prefix — then call
`generate_site_from_gbp` with `{ locationId, serviceSlug? }`. It carries the caller's org
context (bearer → organizationId), so no auth args are passed.
- **Completion criterion:** the tool returns `{ ok, slug, canonicalUrl, html, jsonLd,
  copy, validations, profile }`.

### B. HTTP route (session/browser context)
`POST /api/ai-websites/generate` with a Bearer/session auth header and body
`{ locationId, serviceSlug? }`. Same payload shape as the tool.
- **Completion criterion:** HTTP 200 with the site payload; 400 means no connection or a
  bad body (read `error`).

## Read the result — the gate is the point
- `ok === true` → the copy passed every validator; `html` + `jsonLd` are safe to hand to
  the deploy stage. Note: on an LLM-copy block the generator silently falls back to
  deterministic copy, so `ok: true` may still mean "deterministic copy shipped" — check
  whether `copy.headline` reads bespoke or templated if that distinction matters.
- `ok === false` with `validations` containing `severity: 'block'` → surface the specific
  rule(s) that blocked; the copy is NOT safe to publish. This only happens on the route
  path if a `copyOverride` was forced; the normal path always resolves to valid copy.
- `ok === false` with `error` → an operational failure (no GBP connection, org missing).
  Report it verbatim; do not retry blindly.

## Boundaries
- **Generate only.** Embedding the chat/lead-capture agent, wiring CRM/drip, and deploying
  are other stages ([[ai-website]] owns the sequence). Do not deploy from here.
- **No fabrication.** Every fact (name, phone, address, services, reviews) comes from the
  GBP fetch. Missing FAQs are filled from an industry starter (generic, non-claiming),
  never invented specifics.
- **Australian English**; the brand's forbidden-words list is enforced by the validator,
  not by you.

## Provenance
Design: `docs/superpowers/specs/2026-07-10-ai-websites-design.md` (AI-Websites Phase 3/4).
Code: Synthex `lib/site-generator/`, `lib/ai-websites/generate-for-org.ts`.
