---
name: ai-website
description: Build an "AI website" for a local business — a normal-looking site with an AI agent, lead capture, follow-up, and a CRM under the hood. Entry-point orchestrator for the AI-Websites product line. Triggers on "AI website", "build an AI website", "GBP to site", "turn this Google Business Profile into a website", "AI-website for {business}".
disable-model-invocation: true
argument-hint: "<business name or GBP location>, plus any brand/deploy target"
allowed-tools: Bash, Read, Grep
---

# ai-website — the AI-Websites pipeline orchestrator

The one entry point for the AI-Websites product line: a normal-looking small-business site
with an AI chat agent, lead capture, automated follow-up, and a CRM built in under the hood
(the Ponte "AI website" model — businesses buy the site, not "an agent"). This skill owns
the **sequence**; each stage is a sub-skill or service it dispatches. It does not
re-implement any stage.

**Read the state table before running** — most stages beyond *generate* depend on the
Phase-2 Unite-Group engine, which is built separately. Run only what is live; report the
rest as pending, do not fake them.

## Pipeline stages

| # | Stage | Dispatches | State |
|---|---|---|---|
| 1 | **Intake** | inline — collect business + GBP location, brand, deploy target | ready |
| 2 | **Generate** | [[ai-website-generate]] (GBP → validator-gated site section) | **live** (Synthex Phase 3/4) |
| 3 | **Embed agent** | Unite-Group chat widget + ElevenLabs voice CTA | pending Phase 2 |
| 4 | **Wire capture → CRM** | Unite-Group `crm_leads` + lead-capture route | pending Phase 2 |
| 5 | **Follow-up (drip)** | Unite-Group drip queue → SendGrid | pending Phase 2 |
| 6 | **Deploy** | Next.js page + ISR revalidate (human deploy gate) | pending Phase 2 |
| 7 | **Provision into Synthex** | `ai-website-provision` (client onboarding/pricing) | pending Phase 5 |

## Run order

1. **Intake.** Confirm: the business's **GBP location resource name**
   (`accounts/{id}/locations/{id}`), the org's connection status, the brand (defaults to
   the org's name/voice), and the deploy target. Missing GBP connection → stop; the account
   must connect Google Business Profile first (Prohibited: do not enter their credentials).
   - **Completion criterion:** location id + connected org confirmed.
2. **Generate.** Dispatch [[ai-website-generate]]. Inspect `ok` + `validations`; a blocked
   result is not shippable — surface the rule and stop.
   - **Completion criterion:** a validated site section (`ok: true`, `html` + `jsonLd`).
3. **Stages 3–7.** For each, check the state column. If **pending**, report it as a gated
   next step with its dependency (Unite-Group engine / Phase 5) — do NOT stub or simulate
   it. As those engines land, wire the named dispatch here.

## Boundaries
- **Orchestrator only** — never re-implement a stage; dispatch it. If a stage skill is
  missing, that stage is not ready — say so.
- **Deploy is a human gate.** Never push to production without the founder's authorisation.
- **No fabrication anywhere in the chain** — business facts come from GBP; copy is
  validator-gated (Aid Rule, ACL §18, brand voice).
- Client-facing copy that ships to a real site still routes through the estate content gate
  ([[feedback-nexus-copywriter-gate]]) before go-live.

## Provenance
Plan: `docs/superpowers/specs/2026-07-10-ai-websites-design.md`. Concept: the AI-Websites
gold-rush ingest. Engine: Synthex `lib/site-generator` (generate) + Unite-Group `apps/web`
(agent/CRM/drip, Phase 2).
