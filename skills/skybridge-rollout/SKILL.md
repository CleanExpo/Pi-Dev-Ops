---
name: skybridge-rollout
description: Unite-Group rollout plan for Skybridge MCP-Apps framework — which businesses get an MCP App, in what order, with what auth, and how to productize it via Synthex. Invoke when planning, scoping, or building any MCP App across the portfolio.
version: 1.0.0
sources:
  - https://github.com/alpic-ai/skybridge
  - https://docs.skybridge.tech
  - https://alpic.ai/blog/skybridge-v1-framework-building-mcp-apps
  - https://github.com/alpic-ai/webmcp-proxy
companion_skill: skybridge (installed at .agents/skills/skybridge/ via `npx skills add alpic-ai/skybridge -s skybridge`)
---

# Skybridge Rollout — Unite-Group Nexus

> **This skill is the strategic SSOT.** The technical "how" is in the installed `skybridge` skill (architecture, fetch-and-render, OAuth, deploy, publish, UI-guidelines references). This file decides **what we build, for whom, in what order, and why**.

## When to invoke

- Planning a new MCP App for any portfolio business
- Adding Skybridge to an existing site
- Scoping a Synthex client engagement that includes an MCP-App deliverable
- Reviewing a PR that touches `/mcp/`, `webmcp-proxy`, or any Skybridge-related code

If the task is pure technical implementation (writing a tool handler, designing a view, fetching data), invoke the installed `skybridge` skill instead — that's the canonical how-to.

## §1 — Why Skybridge fits Unite-Group right now

We landed 8 portfolio sites with WebMCP form annotations on 2026-05-25 (see [[geo-optimization]]). That made our forms discoverable to **browsing agents** only. Skybridge closes three adjacent gaps:

| Gap | Skybridge piece that closes it |
|---|---|
| Agents NOT in a browser can't see our annotations | `webmcp-proxy` advertises MCP-server tools to ANY MCP client (Claude Desktop, ChatGPT direct, VSCode, Goose) |
| HTML-form ceiling on agent UX richness | MCP Apps render real React UIs inside Claude / ChatGPT |
| Per-site duplicated WebMCP work (we did 7 PRs by hand) | One canonical MCP server + `webmcp-proxy` script tag = DRY |
| No agent-usage analytics | Alpic-hosted analytics: MCP clients, sessions, tool calls, user intent |

## §2 — Per-business priority matrix

Order = highest revenue or strategic impact first.

| # | Business | App concept | Auth | Phase | Why |
|---|---|---|---|---|---|
| 1 | **Synthex** | "Your social-media agency inside Claude/ChatGPT" — campaign brief → brand-voice generation → preview → schedule → approve | Google Workspace OAuth (org default — see §6) | Flagship | New SKU. First-mover in AU. The killer use case. Direct path to recurring client revenue. |
| 2 | **Pi-CEO operator dashboard** | Portfolio CI health, swarm status, /shipit trigger, Pilot V1 outcomes | Internal-only (no auth needed for first POC) | POC | Lowest stakes. Validates the agent-build loop. Proves we can deliver. |
| 3 | **Disaster-Recovery** | "Submit a DR claim" — postcode lookup → contractor match → live response-time → claim summary card | None (consumer-facing) | Flagship | Highest public traffic. Real consumer use case. Bypasses the website entirely. |
| 4 | **ATO Tax Optimizer** | "Ask about your tax position" — Xero connect → forensic analysis → findings rendered as interactive cards with ITAA citations | OAuth via Xero | Flagship | Highest per-customer value. ITAA-cited findings are a credibility moat. |
| 5 | **Pilot V1 UI** | Render existing Pilot V1 suggestions as Skybridge cards inside Claude (in addition to current Telegram dispatch) | (already cron-driven) | Quick win | Reuses existing scheduler. Just adds a view layer. |
| 6 | **RestoreAssist** | Mobile inspection capture via voice in Claude — IICRC water-class, moisture readings, photos | Supabase Auth | Phase 2 | Workflow that benefits hugely from voice-first agent UX. |
| 7 | **CARSI** | Course catalogue + enrolment wizard + CEC progress dashboard, plus `verify_credential(id)` as a first-class tool | Google Sign-In (org default — escalate to Stytch only if a school cohort requires it) | Phase 2 | `verify_credential` is the single most-valuable agent tool — employers running checks. |
| 8 | **DR-NRPG** | Contractor onboarding wizard with discipline picker + document upload | Google Workspace OAuth (org default — escalate to WorkOS only on B2B SCIM/SSO demand) | Phase 2 | High-friction current flow benefits most from agent assist. |
| 9 | **CCW-Online ERP** | Quote-to-cash agent — customer search → SKU lookup → quote build → email | Existing CCW auth | Phase 3 | Specialised niche; revenue ceiling capped by the equipment-supplier TAM. |
| 10 | **Unite-Hub** | Founder workflow tools (gated) | Existing Supabase auth | Phase 3 | Internal-only; lowest external-revenue value. |

## §3 — `webmcp-proxy` rollback strategy for the GEO sites

The WebMCP form annotations we added today across 7 sites are **not deprecated** by Skybridge — they still work for the browsing-agent path. But they're hand-maintained. The rollback to a single source of truth:

1. Stand up a single `unite-group-mcp-server` that defines all tools (`submit_contact_enquiry`, `find_contractor_by_postcode`, `request_signup`, `verify_credential`, etc.)
2. Add `<WebMCPProxy url="https://mcp.unite-group.com.au/mcp" />` to each site's React root
3. Per-form `toolname`/`toolparamdescription` annotations remain as a fallback for environments where `webmcp-proxy` can't load
4. Tool definitions live in one place; updating them updates every site simultaneously

Order: ship Phase 1+2 of the Skybridge work first, then sweep this as Phase 3.

## §4 — Synthex productization angle

This is where Skybridge stops being engineering work and starts being revenue.

**Current Synthex GEO-audit module roadmap** (Phase 3 of the GEO rollout, scoped in [[geo-optimization]] §10): audit client URL, report gaps, generate remediation pack.

**With Skybridge added, Synthex sells three new SKUs:**

| SKU | What it delivers | Pricing model |
|---|---|---|
| **GEO Audit + Remediation** (existing roadmap) | One-off scan, gap report, remediation pack for the client's stack | Fixed-fee per audit |
| **"Your business as an MCP App"** (NEW) | Synthex builds + hosts the client's Skybridge app, deploys to Alpic, submits to Claude/ChatGPT app stores | Monthly recurring + setup fee |
| **`webmcp-proxy` deployment-as-a-service** (NEW) | Drop-in script that exposes the client's existing API to browsing agents without rewriting forms | Monthly recurring (low-touch, high-margin) |

The middle SKU is the headline. As of v1.0 (May 2026) Skybridge powers ~10% of apps on the Claude + ChatGPT stores — there is a real category of "agency that builds MCP Apps for clients" forming. Synthex would be a first-mover in Australia.

## §5 — Deployment decision tree

When deploying ANY MCP App in this rollout:

```
Is the app revenue-critical (Synthex flagship, ATO, DR, paid client deliverable)?
├── YES → Deploy on Alpic (analytics + compliance auditing + app-store help worth the cost)
│         BUT request pricing first — not on their public site as of 2026-05-25
└── NO  → Self-host on any Node.js platform (Vercel, Railway, Fly.io)
          Pi-CEO operator dashboard, Unite-Hub internal app, POCs all self-host
```

Compliance + app-store submission is where Alpic earns its keep — for a flagship Synthex app intended for the Claude store, the time saved on the review-cycle is the value-add.

## §6 — Auth integration choice per business

**Org-wide default: Google Workspace OAuth** (confirmed by Phill 2026-05-25). Unite-Group runs on Google Workspace. OWNER_EMAILS across the portfolio are already Google addresses. OAuth client lives in the existing Unite-Group Google Cloud Console project. Do not introduce a new auth SaaS dependency unless the per-business row below has a specific reason it can't use Google.

| Business class | Auth | Why |
|---|---|---|
| Multi-tenant SaaS (Synthex) | **Google Workspace OAuth** | Org default; existing OWNER_EMAILS are Google addresses; one Google Cloud OAuth client services every Unite-Group MCP App |
| B2B with team/org structure (DR-NRPG, RestoreAssist contractors) | **Google Workspace OAuth** (default) — escalate to WorkOS AuthKit only if a B2B customer requires SCIM/SAML | Org default first; WorkOS adds B2B SCIM/SSO when a contract demands it |
| Passwordless education (CARSI learner-side) | **Google Sign-In** as default — Stytch reserved if a non-Google learner cohort emerges | Learners are largely on Gmail already; Stytch only if a school requires its own IdP |
| Enterprise B2B (ATO accountant partners) | **Google Workspace OAuth** — Auth0 reserved if an enterprise partner requires their own SSO | Most accounting firms have Google or Microsoft Workspace; only escalate to Auth0 on contract demand |
| Internal tools (Pi-CEO, Unite-Hub) | **No external auth** — gated by Supabase or repo-private | POCs don't need OAuth |
| Consumer-facing one-shot (DR claim intake) | **No auth** (Skybridge supports unauthenticated tool calls) | Friction kills consumer flows |

## §7 — Rollout phases

| Phase | Scope | Deliverable |
|---|---|---|
| **A (done)** | Install Skybridge skill, write this SSOT | This skill + companion installed at `.agents/skills/skybridge/` |
| **B (POC, next)** | Pi-CEO operator dashboard MCP App | SPEC.md, scaffold, working "hello world" view, PR opened |
| **C (Synthex flagship)** | "Synthex inside Claude/ChatGPT" MCP App with Google Workspace OAuth, Alpic deploy | Production-grade app, Claude-store submission |
| **D (`webmcp-proxy` backfill)** | One MCP server for all 7 sites, retire hand-annotations | Per-site PR, ~1 day each |
| **E (DR + ATO flagship apps)** | Two more revenue-impacting flagships | Two production-grade apps |
| **F (Synthex SKU launch)** | Productize the "MCP App per client" offering | Pricing, contract template, delivery playbook |
| **G (Phase 2 + 3 apps)** | RestoreAssist, CARSI, DR-NRPG, CCW, Unite-Hub | Each as separate PR/release |

## §8 — Risks

- **API instability** — Skybridge v1.0 released May 2026. Lock to a specific version per app; upgrade deliberately not automatically.
- **Vendor lock-in to Alpic** — framework is MIT + self-hostable, but hosted analytics + app-store-submission help are paid services. Adopt the framework freely; treat Alpic hosting as one option, not the only option.
- **Multi-tenant data isolation in client apps** — Synthex's "MCP App per client" SKU means each client app needs its own tenant boundary. Use Google Workspace OAuth `hd` parameter (domain hint) + organization-scoped DB rows + Supabase RLS per the existing pattern in [[geo-optimization]] §3.
- **Claude/ChatGPT store review cycles** — apps need compliance review before going live. Alpic offers help here; self-hosted apps still need to pass review for store listing. Budget calendar time, not just engineering time.
- **WebMCP work isn't wasted** — `webmcp-proxy` complements not replaces. Browsing-agent path still works through the annotations we shipped.

## §9 — Verification checklist (for any Skybridge PR)

Before merging any Skybridge-related PR:

- [ ] SPEC.md exists in the app directory and matches the implementation (per Skybridge skill workflow)
- [ ] Auth pattern matches §6 above for the business class
- [ ] Tool definitions are server-side rendered (Skybridge handles this — verify the build output)
- [ ] CSP declared if external domains are fetched (see installed `skybridge/csp.md`)
- [ ] Local dev tested with `npm run dev` + tunnel to Claude or ChatGPT
- [ ] Deployment target chosen per §5 decision tree
- [ ] If revenue-critical: app-store submission plan documented

## §10 — Related skills

- `skybridge` (installed at `.agents/skills/skybridge/`) — canonical technical how-to: architecture, fetch-and-render, state, OAuth, deploy, publish. Always invoke this for implementation work.
- [[geo-optimization]] — the GEO/WebMCP standard from 2026-05-25. `webmcp-proxy` rollout (Phase D above) supersedes the per-site hand-annotation pattern but doesn't deprecate it.
- `synthex-client-audit` (forthcoming, per geo-optimization §10) — the Synthex SKU that builds on this skill's productization angle (§4).

## Sources

- Skybridge GitHub: https://github.com/alpic-ai/skybridge (MIT, v1.0, 1,251★, ~100k monthly downloads)
- Skybridge docs: https://docs.skybridge.tech
- Skybridge v1.0 announcement: https://alpic.ai/blog/skybridge-v1-framework-building-mcp-apps
- Alpic platform: https://alpic.ai
- webmcp-proxy: https://github.com/alpic-ai/webmcp-proxy
- WebMCP spec: https://github.com/webmachinelearning/webmcp
- MCP Apps protocol: https://modelcontextprotocol.io
- Used by (case studies): Datadog, Bitmovin, Evaneos, Touchstream, Cottages.com
