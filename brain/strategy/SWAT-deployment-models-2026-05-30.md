# SWAT Analysis: Cloud-Hosted vs Connected-Local Deployment Models

> **Origin:** Plaud recording 2026-05-30 — RestoreAssist deployment strategy shift
> **Scope:** All Unite Group ecosystem projects
> **Decision Owner:** Phill McGurk (Board)
> **North Star Context:** $2B by 2028-06-30 — architecture must support scale, margin, and optionality

---

## Model Definitions

| Dimension | **Cloud-Hosted (Current)** | **Connected-Local (Proposed)** |
|-----------|---------------------------|-------------------------------|
| **Code execution** | UG servers (Vercel/Railway) | Client device / infrastructure |
| **Data residency** | UG databases (Supabase) | Client-managed (local DB, files) |
| **UG infrastructure** | Full stack per client | Thin "spine": updates, billing, telemetry |
| **Client connectivity** | Always-on required | Intermittent / periodic sync okay |
| **UG revenue model** | SaaS subscription | License + subscription hybrid |
| **Client value prop** | "We run everything" | "We give you control; we stay connected" |
| **UG control level** | High (full stack) | Moderate (thin channels only) |
| **Client lock-in** | High (data + code on UG infra) | Lower (client can disconnect/update later) |

---

## Strengths

### Cloud-Hosted (Current Model)

| # | Strength | Impact | Notes |
|---|----------|--------|-------|
| CH-1 | **Unified codebase, unified environment** | Low operational complexity | One deploy to Vercel/Railway serves all clients |
| CH-2 | **Real-time data & collaboration** | High product value | All clients see same state instantly |
| CH-3 | **Centralized security patching** | High security posture | Fix once, all clients protected simultaneously |
| CH-4 | **Direct data access** | Strategic asset | Full analytics, ML training, trend detection |
| CH-5 | **Faster feature rollouts** | Higher velocity | Push to prod = instant availability |
| CH-6 | **Easier support / debugging** | Lower cost | Reproducing bugs is deterministic |
| CH-7 | **Simple billing** | Lower admin | Metered usage or flat subscription |

### Connected-Local (Proposed Model)

| # | Strength | Impact | Notes |
|---|----------|--------|-------|
| CL-1 | **Near-zero per-client infra cost** | High margin improvement | UG servers only for spine services |
| CL-2 | **Enterprise-grade data privacy** | Market expansion | Client data never leaves their premises |
| CL-3 | **Compliance & audit advantage** | Regulatory moat | GDPR, HIPAA, SOX friendly |
| CL-4 | **Offline capability** | Product resilience | Works without internet; syncs when connected |
| CL-5 | **Channel partner / MSP model** | GTM expansion | Partners install, configure, support locally |
| CL-6 | **Reduced liability** | Legal protection | Not holding client-sensitive data |
| CL-7 | **Performance (local compute)** | UX improvement | No network latency for core operations |

---

## Weaknesses

### Cloud-Hosted (Current Model)

| # | Weakness | Risk | Notes |
|---|----------|------|-------|
| CW-1 | **Per-client infra cost scales linearly** | Margin compression | Every new client = more DB, compute, storage |
| CW-2 | **Single point of failure** | Business continuity | UG outage = all clients down |
| CW-3 | **Data residency concerns** | Enterprise blocker | EU/AU/enterprise clients won't store data offshore |
| CW-4 | **Vendor lock-in perception** | Sales friction | "What if UG shuts down?" |
| CW-5 | **Regulatory exposure** | Legal risk | Holding client data = breach liability |
| CW-6 | **Network dependency** | UX degradation | Slow/unstable internet = poor experience |
| CW-7 | **Scaling limits** | Growth ceiling | Eventually need multi-region, multi-tenant |

### Connected-Local (Proposed Model)

| # | Weakness | Risk | Notes |
|---|----------|------|-------|
| LW-1 | **Fragmented environments** | High support cost | Every client runs different OS, versions, configs |
| LW-2 | **Patch delivery complexity** | Security risk | How to ensure all clients update? |
| LW-3 | **No direct data access** | Strategic loss | Telemetry only; can't train models on full data |
| LW-4 | **License circumvention risk** | Revenue loss | Clients could modify/disable billing |
| LW-5 | **Installation friction** | Churn risk | Download + install + configure > "just sign in" |
| LW-6 | **Reverse engineering exposure** | IP risk | Code on client device = decompilation risk |
| LW-7 | **Support nightmare** | Operational cost | "It works on my machine" × 1,000 clients |

---

## Architecture Implications

| Dimension | Cloud-Hosted | Connected-Local |
|-----------|-------------|-----------------|
| **Update mechanism** | Git push → Vercel/Railway → instant | Delta patch or full package → client pull/install |
| **Database** | Supabase (single shared instance) | SQLite/local PostgreSQL per client + sync layer |
| **Authentication** | Supabase Auth (centralized) | Local auth + license validation + optional cloud sync |
| **LLM integration** | UG manages API keys, bills client | Client brings own API key (BYO-LLM) |
| **File storage** | Supabase Storage (central) | Local filesystem + optional cloud backup |
| **API surface** | Single Next.js app + FastAPI backend | Electron/Docker app + thin spine API |
| **Observability** | Central logs (Sentry, PostHog) | Telemetry batch upload + local log files |
| **Backup/DR** | UG-managed (Supabase PITR) | Client-managed + optional cloud backup |
| **Multi-tenancy** | Built-in (schema separation) | Single-tenant by design |

### Critical Architecture Decisions

1. **Package Format** (for Connected-Local)
   - **Docker**: Best for server-savvy clients. Hard for non-technical SMBs.
   - **Electron**: Broadest desktop compatibility. Large bundle size.
   - **Tauri**: Smaller than Electron, Rust-based. Good middle ground.
   - **Capacitor/Cordova**: Mobile-native wrapper. For field-use apps.
   - **PWA (offline-capable)**: Zero install. Limited local storage.

2. **Sync Strategy**
   - **Continuous sync** (real-time WebSocket when connected)
   - **Periodic sync** (hourly/daily batch upload)
   - **Event-driven sync** (only when user explicitly syncs)

3. **License Validation**
   - **Online check**: Simple but requires connectivity.
   - **Offline grace period**: License valid for N days without check.
   - **Hardware fingerprint**: Bind license to device ID.
   - **Enterprise license server**: Self-hosted KMS for large clients.

---

## Tactics (Decision Framework)

### When to Choose Cloud-Hosted

| Scenario | Rationale |
|----------|-----------|
| SMB-focused product | Low technical sophistication; "just sign in" wins |
| Heavy collaboration | Real-time shared state requires central server |
| Frequent feature evolution | Push changes fast without client action |
| Data-as-a-product | UG monetizes insights from aggregated data |
| Low regulatory sensitivity | No HIPAA, GDPR, SOX concerns |
| Freemium / free tier | Zero friction signup; viral growth |

### When to Choose Connected-Local

| Scenario | Rationale |
|----------|-----------|
| Enterprise / government clients | Data residency, compliance, audit requirements |
| Field / offline-first use cases | Works without internet (e.g., disaster recovery on-site) |
| High-margin target | Infra cost is \>20% of revenue at scale |
| Channel / MSP partner model | Partners install, configure, bill locally |
| Regulatory-heavy industry | Healthcare, finance, legal, defense |
| Client IP sensitivity | Client won't let their data leave their premises |

---

## Project-by-Project Deployment Model Fit

| Project | Current Stack | Client Type | Best Model | Confidence | Rationale |
|---------|--------------|-------------|-----------|------------|-----------|
| **Pi-Dev-Ops** | FastAPI + Next.js | Internal (UG) | Cloud | 95% | Internal orchestrator; no client data |
| **RestoreAssist** | Next.js + Supabase | Restoration companies | **Hybrid** | 75% | Recording says shift to local. But: SMBs may lack IT. Plot: tiered — Enterprise = local, SMB = cloud |
| **DR-Sandbox** | Next.js | Disaster restoration | **Connected-Local** | 80% | Field-first; often no internet on disaster sites. Offline critical. |
| **DR-NRPG** | Next.js + Supabase | Insurance / adjusters | Cloud | 70% | Collaboration-heavy; shared claim state. But: insurance data sensitivity argues for local. |
| **NRPG-Onboarding** | Next.js | Contractors | Cloud | 85% | Low-complexity workflow; real-time status tracking between stakeholders |
| **Synthex** | Next.js + Supabase | Content teams / marketers | Cloud | 90% | Social media management = inherently cloud. No offline need. |
| **Unite-Group** | Next.js + Supabase + Supabase | Internal + clients | Cloud | 95% | CRM/Command Center = central hub by definition |
| **NodeJS-Starter** | Next.js + FastAPI | Developers | Cloud | 90% | Template for cloud deployment |
| **Oh-My-Codex** | Python CLI | Developers | **Connected-Local** | 85% | CLI tool = inherently local. Sync config/extension catalog only. |
| **CCW-CRM** | Next.js + FastAPI + Supabase | Clean Craft Works ops | Cloud | 80% | Internal ERP/CRM for now. Later: franchise model may need local |
| **CARSI** | Unknown (likely field ops) | Field teams | **Connected-Local** | 70% | Field operations = offline-first need. Need charter review. |

### Key Finding: Hybrid is the Real Answer

No project is purely one or the other. The recording's "Connected-Local" model is actually a **tiered hybrid**:

```
Tier 1: Cloud-Native (SaaS)
   → SMBs, low-complexity, price-sensitive
   → UG hosts everything; simple subscription

Tier 2: Connected-Local (Enterprise)
   → Enterprise, compliance-heavy, IT-capable
   → Client hosts; UG provides updates + billing + telemetry

Tier 3: Air-Gapped (Defense / Critical)
   → Maximum security, no internet
   → UG provides install media + annual license
   → No telemetry, no updates without physical media
```

RestoreAssist should target **Tier 2** first, but keep **Tier 1** for SMBs.

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Local deployment too complex for target market | Medium | High | Offer "managed local" — UG installs on client's AWS/GCP/Azure via IaC |
| License circumvention | Medium | High | Hardware-fingerprinted licenses + periodic online validation |
| Support cost explosion | High | High | Tiered support: self-service docs < community < paid support < white-glove |
| Fragmented versions in the wild | High | Medium | Auto-update with configurable maintenance windows |
| Telemetry too invasive | Low | High | Anonymize by default; opt-in for detailed analytics; GDPR-compliant |
| IP theft / reverse engineering | Medium | High | Code obfuscation; split sensitive logic to server-side API; license legal framework |
| Revenue model confusion | Medium | Medium | Clear pricing page: Cloud ($/mo) vs Local (license + $/mo support) |

---

## Decision Recommendation

### For RestoreAssist Specifically

**Adoption path: Tiered Hybrid**

1. **Phase 1 (now):** Keep cloud for all existing clients. Begin architecture design for connected-local.
2. **Phase 2 (Q3 2026):** Launch Connected-Local as "RestoreAssist Enterprise." Same codebase, different packaging + config.
3. **Phase 3 (Q4 2026):** Add "Bring Your Own Cloud" option — UG deploys into client's AWS account via Terraform/Pulumi.
4. **Phase 4 (2027):** Evaluate if SMB tier should remain cloud-only or also get a lightweight local option (PWA/Electron).

### For the Ecosystem

Build a **deployment abstraction layer** in Pi-Dev-Ops:

```
┌─────────────────────────────────────┐
│  Client-Facing Application          │
│  (Next.js + React)                  │
├─────────────────────────────────────┤
│  Deployment Adapter Layer           │
│  ├─ CloudAdapter (Supabase client) │
│  ├─ LocalAdapter (SQLite + sync)   │
│  └─ HybridAdapter (configurable)   │
├─────────────────────────────────────┤
│  Business Logic (framework-agnostic)│
│  ├─ Auth (pluggable provider)      │
│  ├─ Data (ORM abstraction)         │
│  ├─ LLM (provider factory)         │
│  └─ Telemetry (batch upload)       │
└─────────────────────────────────────┘
```

This lets every UG product ship in **Cloud**, **Connected-Local**, or **BYO-Cloud** mode from the same codebase.

---

## Action Items

- [x] **RA-5642** — Strategic: Shift RestoreAssist to client-local deployment model
- [x] **RA-5643** — Design connected layer (update + billing + telemetry)
- [ ] **UNI-XXXX** — Build deployment abstraction layer (Cloud/Local/Hybrid) in Pi-Dev-Ops
- [ ] **UNI-XXXX** — Evaluate DR-Sandbox, DR-NRPG, CARSI for connected-local fit
- [ ] **UNI-XXXX** — Design license management system (hardware fingerprint, offline grace, enterprise KMS)
- [ ] **UNI-XXXX** — Create "deployment model selector" tool for sales (quiz → recommend cloud/local)
- [ ] **UNI-XXXX** — Competitive analysis: how do ServiceTitan, Jobber, Restoration Manager deploy?

---

## Appendix: Competitive Landscape (Hypothesis — Needs Verification)

| Competitor | Deployment | Notes |
|------------|-----------|-------|
| ServiceTitan | Cloud-only | Enterprise sales, high price point |
| Jobber | Cloud-only | SMB focus, simple UX |
| Restoration Manager | Unknown | Likely cloud; purpose-built for restoration |
| Xactimate | Desktop + cloud sync | Insurance adjuster standard; local install + cloud data |
| Encircle | Mobile-first, cloud | Field documentation; always connected |

**Key insight:** Xactimate's "desktop + cloud sync" model is closest to the proposed Connected-Local architecture. If they're the incumbent, matching their deployment model reduces switching friction.
