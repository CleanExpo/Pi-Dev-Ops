---
type: plaud-recording
plaud_id: manual-import-2026-05-30
recorded_at: 2026-05-30T00:00:00+10:00
duration_ms: 52000
duration_human: 0m52s
source: plaud-notepin-s
ingested_at: 2026-05-30T12:42:00+10:00
tags: [restoreassist, deployment-model, strategic-decision]
---

# RestoreAssist: Cloud-to-Local Deployment Strategy Shift

**Audio:** (manual import — no audio URL)
**Duration:** 0m52s

## Transcript

[00:00:01 - 00:00:52] Speaker 1: With the system at the moment, the RestoreAssist system, at the moment it is cloud-based, where they're using our server to use the system itself, even though they're signing in with their own large language model, it's still our cloud system that's running the system. Let's look at changing that, so it's a downloadable file that they put on their own system, and then all that's connected is the updates from us and the billing, as well as still us collecting the data meta-information from the client, so we can use that for all our new national... data logs.

## Summary

Strategic direction shift for RestoreAssist: move from fully cloud-hosted to client-local deployment. The client self-hosts the application, while Unite-Group retains update delivery, billing, and meta-data collection. This decouples the compute from the business relationship while preserving data insight and revenue.

## Key Points

1. **Current State:** RestoreAssist runs on Unite-Group's cloud servers — clients sign in via their own LLM, but the system lives on UG infrastructure.
2. **Proposed Change:** Distribute RestoreAssist as a downloadable client package that the customer installs on their own infrastructure.
3. **What Stays Connected:**
   - Software update feed (UG pushes updates)
   - Billing (UG manages subscriptions/payments)
   - Meta-data collection (UG receives client usage analytics/data logs)
4. **Strategic Rationale:**
   - Reduce UG infrastructure burden per-client
   - Potentially increase security/privacy appeal to enterprise clients
   - Retain data asset (national data logs) for future product development
5. **Open Questions:**
   - Package format (Docker? Electron? Native installer?)
   - LLM provider compatibility (client brings their own API key? bundled?)
   - Update mechanism (auto-update? manual? delta patches?)
   - Data privacy/legal implications of meta-data collection
   - Pricing model change (per-seat? per-device? enterprise license?)

## Action Items

- [x] **RA-5642** — Plaud: Shift RestoreAssist to client-local deployment model | [Linear](https://linear.app/unite-group/issue/RA-5642)
- [x] **RA-5643** — Design connected layer (update + billing + telemetry) for self-hosted RA | [Linear](https://linear.app/unite-group/issue/RA-5643)

## Strategic Analysis

### Current State
RestoreAssist is a **cloud-native SaaS** where:
- UG runs all infrastructure (servers, compute, storage)
- Clients authenticate with their own LLM provider credentials
- But the system itself executes on UG infrastructure
- UG bears per-client infra cost

### Proposed State: "Connected Local" Model
Client self-hosts the application. UG remains connected via three thin channels:

```
┌─────────────────┐     ┌──────────┐     ┌─────────────────┐
│  Client Device  │─────│ Internet │─────│  UG Cloud       │
│  (Local Install)│     │          │     │  (Updates)      │
└────────┬────────┘     └──────────┘     └─────────────────┘
         │                                         │
         │ Updates (pull/push)                     │ Billing API
         │                                         │
         │ Meta-data (usage, errors, analytics)    │
         │──────────────────────────────────────────┘
         │
    ┌────┴────┐
    │ Client  │ ← Own LLM API key
    │ LLM     │   (OpenAI, Anthropic, etc.)
    └─────────┘
```

### Why This Is Strategically Significant

| Factor | Cloud Model | Local Model |
|--------|-----------|-------------|
| UG Infra Cost | High (per client) | Low (update + billing servers only) |
| Client Privacy | Moderate (data on UG servers) | High (data stays local) |
| Enterprise Appeal | Lower (vendor lock-in) | Higher (self-hosted = enterprise preference) |
| Data Asset | Direct access | Requires explicit telemetry consent |
| Revenue Model | SaaS subscription | License + subscription hybrid |
| Go-to-Market | Digital only | Channel partners, MSPs, OEM |

### Critical Open Questions

1. **Package Format**: Docker container? Electron desktop app? Native installers (msi/pkg/dmg)?
   - Docker = easiest for tech-savvy clients, hardest for non-technical
   - Electron = broadest compatibility, larger footprint
   - Native = best UX, highest maintenance burden

2. **LLM Provider**: Client brings their own API key, or we broker?
   - BYO-API-Key = zero UG cost, zero UG liability for LLM usage
   - Brokered = recurring LLM revenue, but UG becomes middleman

3. **Update Mechanism**: How do we push security patches to offline/behind-firewall clients?
   - Over-the-air (OTA) requires persistent connection
   - Manual update = security risk (clients delay patches)
   - Delta updates = bandwidth efficient but complex

4. **Billing Integrity**: How do we prevent license circumvention?
   - Hardware-locked license? Phone-home validation?
   - Offline grace period? Time-bombed license?
   - Enterprise KMS / license server?

5. **Legal / Privacy**: Meta-data collection from self-hosted software
   - Explicit opt-in required in many jurisdictions
   - What qualifies as "meta-data" vs "client data"?
   - GDPR/CCPA implications if client is in EU/California
