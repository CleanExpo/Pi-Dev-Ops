# Mission Control visual overhaul — first implementation slice

## Judge report

**Proposal:** replace the `/control` landing composition with an evidence-aware portfolio fan and selected project focus, while retaining existing intake, fleet and activity components.

**Decision:** bounded UI experiment authorised by Phill's request to begin coding. **Score: 86/100**, not a release approval or AAA grade. The live project identity and release evidence contracts are still incomplete, so a truthful 100 is unavailable.

| Lens | First-source finding | Decision |
|---|---|---|
| Evidence | `/control` currently mounts `ControlHubTiles`, `FleetTile`, `IdeaPipelinePanel`, `LiveActivityFeed`; `/api/projects/health` serves project IDs and scan health. | Reuse those surfaces. |
| Existing capability | `/api/mission-control/live` exposes active sessions, but no per-project release stage; fleet BFF exposes heartbeat/staleness. | Show known activity only. |
| Devil's advocate | A scan score is not release progress; a session phase is not deployment proof. | Never derive percent complete or "live" from them. |
| Bloat | Multiple themes coexist. | Scope new styles to the new composition and remove the old landing tile stack from `/control`. |
| Security/privacy | Existing protected API routes and auth boundary stay in place. | No new mutation or data endpoint. |
| UX | A ten-card fan can obscure labels and keyboard selection. | Responsive, scrollable cards with full button labels and a focused detail area. |
| Test | Missing API, empty registry, stale poll, and unmatched session need honest states. | Verify these states before release. |

## SPM implementation spec

1. **Task:** start the founder-facing visual overhaul on the existing `/control` route.
2. **Context:** `CleanExpo/Pi-Dev-Ops`, clean `main` at initial inspection; existing dashboard components and contracts named above. No machine runtime verified.
3. **Problem:** the tile stack hides portfolio focus and conflates health, activity and completion.
4. **Outcome:** one selected project is raised, its current observed work is legible, and missing release evidence is explicit.
5. **Scope:** visual landing only; preserve goal intake, existing detail panels, authentication and API shapes. No auto-routing, approvals or release claims.
6. **Reuse:** `/api/projects/health`, `/api/mission-control/live`, `FleetTile`, `IdeaPipelinePanel`, `LiveActivityFeed`, `/control/goal`.
7. **Review:** product: prioritize next action; architecture: no duplicate backend; UX: keyboard/mobile; security: read only; QA: failure states; Judge: avoid synthetic progress.
8. **Judge:** 86/100, bounded experiment only; production readiness remains unproven.
9. **Flow:** select project in fan → see project ID/repo, scan health, observed session or explicit lack of evidence → navigate to intake or detailed panels. Failed reads degrade to unknown.
10. **UX:** selection is local; visible focus; horizontal scroll on narrow screens; loading, empty and error states; no color-only meaning.
11. **Technical:** modify `/control/page.tsx`, the exact-route dashboard shell, and its scoped components. Add a decorative panorama asset. No database/config/API change.
12. **Security:** fetch existing same-origin routes with credentials; display text as text; no raw HTML or stored client secrets.
13. **Verification:** `npx tsc --noEmit`, `npm run build`, targeted UI tests and browser review with clearly labelled sample data. The actual production project feed and deployment remain unverified.
14. **Stress:** empty, duplicate project IDs, missing score, backend failure, many projects and session mismatches; no misleading progress.
15. **Acceptance:** project selection is accessible; selected project and current activity are clear; unknown stage remains unknown; existing panels remain reachable; no build errors.
16. **Goal:** `/goal Implement the accepted first visual slice. Completion: verified accessible fan and selected detail on /control, with unknown evidence explicit and existing intake/fleet/activity preserved.`
17. **Sequence:** UI component → scoped styling → integrate → static/build/browser verification → independent review → draft PR.
18. **Handoff seed:** branch, base SHA, changed files, test results, remaining runtime review and release authority.
19. **Recommendation:** implement the bounded visual experiment; assess real project/release state contracts before deeper automation.

The intended later slices are mission identity and project registry, evidence-backed release pathway, attention queue, worker wall, then a unified token system. They require separate evidence and acceptance; this slice makes no claim that those systems are implemented. The visible “Needs Phill” badge says unknown until an approved attention source is wired; the pathway never treats scan health as release progress.
