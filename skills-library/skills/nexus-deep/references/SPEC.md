# NEXUS DEEP — phase-1 engineering specification

**As of 31 October 2026.** This is a candidate adapter for the existing CleanExpo skills library, not a production orchestration installation.

## Outcome
Increase **verified completed engineering outcomes per AUD and hour**, not model message count. Aim toward a 10× target through controlled experiments; do not claim 10× until compared with a frozen baseline. Eliminate duplicate agent machinery.

## Existing systems take precedence
Senior Harness controls task scope and admitted routes. Done harness controls what may be claimed complete. Skill-selector and skill-watch own candidate discovery and lifecycle. SPM owns applicable planned implementation. Proof-discipline and adversarial-review own review semantics. PR release gate and protected CI own release evidence. JEV or another reviewer must be independent from builder context.

## Task states
`PROPOSED` → `ADMITTED` → `PLANNED` → `IN_PROGRESS` → `EVIDENCE_PENDING` → `VERIFIED` or `BLOCKED`, with `AWAITING_APPROVAL` for release decisions. An AI cannot move a task to ADMITTED or VERIFIED merely by editing a JSON file.

## Risk tiers (reference, not authorisation)
- T0: read-only analysis, live provenance and limits.
- T1: contained documentation, non-executing adapters; tests and exact version.
- T2: product code, credentials/integrations, UI: stronger tests, independent review, red flags, branch evidence.
- T3: production, payments, destructive actions and access control: external approval and trusted checks mandatory.

## Required evidence
Bind objective hash, repo identity and exact SHA, execution environment, test outputs, independent reviewer identity and limits, source timestamps and permissions. Authentic social proof requires a genuine source receipt and consent; never invent reviews. Freshness checks for news, GitHub releases and models must identify actual observations, not assume the prompt date equals a source date.

## Non-goals
No second scheduler, no invented runtime, no external skill autoinstall, no universal hook claims, no forged security receipts, no human-authority bypass.

## Security boundary
The reference CLI creates proposals only. The signer, permissions broker and required GitHub checks must be outside writable agent workspaces. Provider/model selection is dynamic only after entitlement and benchmark checks.
