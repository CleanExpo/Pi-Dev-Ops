# Board Meeting Minutes — Cycle 0 (2026-07-02)

## Business Velocity Index (RA-696)
**BVI: 1** (-1 from prior cycle)
- CRITICALs resolved: 1
- Portfolio projects improved: 0
- MARATHON completions (positive outcomes): 0
- Prior cycle BVI: 2

## Attendees
- Pi CEO Autonomous Agent (Orchestrator)
- CEO Board: 9 personas (CEO, Revenue, Product Strategist, Technical Architect,
  Contrarian, Compounder, Custom Oracle, Market Strategist, Moonshot)
- Gap Audit Agent

## Phase 1 — STATUS
- ZTE Score (v1): 85/100
- ZTE Score (v2): 94/100 [Zero Touch] (v1 base 75 + Section C 19/25)
- Urgent Issues: 10
- Cron Health: unknown

## Phase 2 — LINEAR REVIEW
- Urgent: 8 | High: 22
- Stale: RA-6469 (4d stale), RA-6470 (4d stale), RA-3045 (4d stale), RA-3900 (4d stale), RA-3971 (4d stale), RA-4190 (4d stale), RA-4191 (4d stale), RA-6464 (4d stale), RA-6471 (4d stale), RA-6472 (4d stale), RA-6475 (4d stale), RA-6495 (4d stale), RA-6669 (4d stale), RA-6671 (4d stale), RA-6838 (6d stale), RA-6850 (6d stale), RA-6847 (6d stale), RA-6842 (6d stale), RA-6841 (6d stale), RA-6678 (13d stale), RA-6801 (13d stale), RA-6792 (13d stale), RA-6791 (14d stale)
- Unassigned: RA-6888, RA-6887, RA-6774, RA-6886, RA-6873, RA-2989, RA-6469, RA-6470, RA-3045, RA-3900, RA-3971, RA-4190, RA-4191, RA-6464, RA-6471, RA-6472, RA-6475, RA-6495, RA-6669, RA-6671, RA-6838, RA-6850, RA-6847, RA-6842, RA-6841, RA-6801

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
_Stage skipped — no empirical questions surfaced from intelligence brief._ Personas argue from priors only this cycle.


## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)
**CEO:** The three P0s (RA-6801, RA-6792, RA-6678) are the same funnel breaking in three places — ABN lookup, Anthropic key gating, and end-to-end signup flow — and RA-5036's organic campaign is driving cold traffic into that exact funnel today. Highest leverage this cycle is treating those three as one unified sprint, not three backlog items, and confirming an actual client can walk signup → report → PDF before touting ZTE v2's 94. Everything else — RA-6469 cleanup, stale 4–14 day items — is follow-up, not this week's work.

**Revenue:** Every lead RA-5036 generates today that hits the ABR_API_GUID failure or the Anthropic-key wall is a burned acquisition cost with no recovery — Australian B2B buyers don't retry a broken onboarding. Either the campaign pauses until RA-6678 and RA-6801 verify green end-to-end, or Marketing accepts it's spending budget to demonstrate the product doesn't work yet.

**Product Strategist:** These aren't hypothetical roadmap bets — real users are failing at concrete, reproducible steps (ABN lookup, key requirement) that the trial-credit promise explicitly said wouldn't exist. Ship the fix and click-test it live per RA-1109 before any other feature work gets prioritized; "In Review" status on all three P0s means someone believes they're close, which needs verifying, not assuming.

**Technical Architect:** ABR_API_GUID missing in prod and the Anthropic key requirement conflicting with platform-managed trial credits are both env/secrets-provisioning failures, and RA-6886's fallback-dryrun also failing on the direct Anthropic-key path this same cycle makes three independent credential failures in one intelligence window — that's not three bugs, that's a gap in how secrets reach Railway. Fix the provisioning pipeline once, not each symptom separately.

**Contrarian:** Revenue's instinct to pause RA-5036 is the wrong reflex — if RA-6801/6792/6678 are genuinely "In Review" and near-merge, killing campaign momentum in a niche restoration-industry market costs more than a few days of leaky-funnel leads, because launch momentum doesn't restart on command. The actual failure mode nobody's naming: ZTE v2's 94/100 "Zero Touch" score was computed while three P0 client-blocking bugs sat open — that number measured system automation, not client-usable outcome, and treating it as a win before verifying live signup is exactly the surface-treatment trap RA-1109 exists to catch.

**Compounder:** Fixing the secrets-provisioning pipeline (ABR_API_GUID, Anthropic key routing) compounds — it protects every future client's onboarding, not just this week's leads — while a ZTE score bump is a snapshot that means nothing if the funnel it's measuring is broken underneath. Prioritize the durable fix over the vanity metric.

**Custom Oracle:** In an insurance-linked, regulated B2B space, ABN verification isn't cosmetic UX — it's the KYB gate that makes the client relationship compliant in the first place, and a MALFORMED failure on every lookup means zero new clients can be legally onboarded right now. That's a termination-event-adjacent risk, not a P1-flavored inconvenience, and it should outrank the ZTE narrative entirely until closed.

**Market Strategist:** Launching organic acquisition today against a funnel that fails at signup is externally visible in a small, word-of-mouth-driven industry — the restoration/insurance niche is small enough that a bad first-touch experience travels. Timing the campaign to land after RA-6678/6801/6792 verify would cost days; timing it before costs reputation that's harder to buy back.

**Moonshot:** A signup → report → PDF flow with zero manual friction — no key wall, no ABN failure — is the actual productization ceiling: it's the difference between a service business and a self-serve SaaS that scales without founder involvement. These three P0s are not maintenance work, they are the ceiling constraint itself, and closing them is worth more than any feature shipped this quarter.

**CEO SYNTHESIS:** Collapse RA-6678, RA-6801, and RA-6792 into one sprint against the shared root cause — secrets/credential provisioning to prod — and verify with a live signup-to-PDF click-test before crediting ZTE v2's 94 as real, since the score was computed while that exact path was broken. Do not pause RA-5036's organic campaign on the assumption these are far from done; instead treat "In Review" as unverified and confirm live before either declaring the funnel fixed or pulling campaign spend. Everything else in the Urgent/High queue, including RA-6469's stale cancel-cleanup, waits behind this one unified fix.

## Phase 3 — SWOT
STRENGTHS:
- ZTE v2 jump to 94/100 shows the harness architecture (SDK-native generator/evaluator, judge-gated loop, kill-switch axes) is fundamentally sound when the credential path isn't broken.
- BVI methodology is catching real signal — the score dropped to 1 because it's correctly penalizing zero MARATHON completions and zero portfolio improvement rather than rewarding activity theater.
- Hardwired lessons (RA-1043-1049 secret-handling patterns, RA-1966/1970 kill-switch + judge gates, RA-1973 watchdog) show the org learns from incidents once and doesn't regress — evidenced by the density of "never again" fixes already codified in CLAUDE.md.
- Autonomous topology lesson is absorbed: Railway/Vercel/GH Actions as the always-on path is now doctrine, not aspiration, closing the "cron job in someone's editor" failure mode from the first overnight attempt.

WEAKNESSES:
- ZTE v2's 94 was computed while the signup-to-PDF path was broken — the score is unverified against the exact secrets/credential provisioning gap the Board flagged, meaning current confidence in "Zero Touch" is inflated until a live click-test closes RA-6678/RA-6801/RA-6792.
- 23 stale items sitting 4–14 days unchanged (RA-6791 oldest at 14d) against only 10 open Urgent + 22 open High shows triage isn't converting into throughput — the backlog is aging faster than it's clearing.
- 26 unassigned issues, overlapping heavily with the stale list, means ownership — not prioritization — is the actual bottleneck; tickets are correctly routed by `.harness/projects.json` but nobody is claiming them.
- BVI trend is negative (1, down from prior cycle) with zero CRITICALs-resolved-to-portfolio-improvement conversion — the loop is running but not compounding, contradicting the "autonomous, always-chaining" operating mandate.

OPPORTUNITIES:
- Collapsing RA-6678, RA-6801, RA-6792 into one sprint against the shared secrets/credential root cause (Board synthesis) is a single fix that likely clears 3 of the 4 oldest stale tickets at once — highest leverage move available right now.
- RA-5036's organic campaign should keep running during the fix per Board guidance — the funnel fix and campaign are decoupled, so there's no forced tradeoff between shipping speed and marketing continuity.
- The watchdog/lesson pattern already proven for RA-579 (abs() debounce, startup catch-up, 30-min watchdog) is directly reusable for hardening whatever credential-refresh path is failing signup-to-PDF — don't design new, port the pattern.
- Unassigned-but-routed tickets (26 of them) are a cheap win: an auto-assignment pass keyed off `.harness/projects.json` ownership would immediately convert "aging" into "in progress" without new tooling.

THREATS:
- Declaring ZTE v2's 94 as ground truth before the live click-test (Board's explicit warning) risks a repeat of the Fix-with-Claude incident (PR #48→#56): green metrics, unusable feature, surface-treatment violation under RA-1109.
- Silent-failure pattern (LINEAR_API_KEY missing, /health green while poller skips) is a recurring architecture class — if the same class of gap exists in whatever credential path serves signup-to-PDF, the funnel could look "fixed" in review while still broken in prod, exactly as it is now.
- 4 CRITICAL-adjacent tickets aging 13–14 days (RA-6678, RA-6791, RA-6792, RA-6801) sitting unassigned is the same "invisible until escalation" failure mode as the In-Progress-issues-invisible-to-autonomy.py bug — stale + unassigned + Urgent is the exact combination that produced the last watchdog-triggered incident.
- BVI declining for a second cycle while Urgent/High backlog holds at 32 open items signals the autonomous loop may be picking low-leverage work over the shared-root-cause fixes the Board flagged, undermining the "highest-leverage item first" operating loop mandate.

## Phase 4 — SPRINT RECOMMENDATIONS
PRIORITY 1: RA-2989 — Rotate the 4 still-live leaked secrets (LINEAR / PERPLEXITY / swarm-ANTHROPIC / PI_CEO_PASSWORD); this is the credential-path root cause the Board flagged as making ZTE v2's 94/100 unverified, so closing it is the precondition for trusting any other score — Estimate: S — Impact: unblocks a credible re-run of the ZTE v2 signup-to-PDF click-test, closes the single highest-risk security exposure in the backlog.

PRIORITY 2: RA-6887 — Fix the dead dashboard URL (dashboard-unite-group.vercel.app, 404) in runtime code and docs; it's a live, user-visible broken path (Surface Treatment Prohibition territory) and the cheapest available win against the 23-stale/26-unassigned ownership problem — Estimate: XS — Impact: removes a broken link hit during mission-control checks, converts one aged item to done with near-zero effort, nudges throughput without competing for the same cycle as Priority 1 or 3.

PRIORITY 3: RA-6874 — Finish enforcing the autonomy ladder at the SDK tool-call hook (gate L3 before any multi-move executor); it's already In Progress and is the actual blocker on the BVI complaint that the loop runs but doesn't compound — Estimate: L — Impact: converts the largest in-flight item into a shipped safety gate, unlocking safe scaling of the autonomous loop instead of more ungated multi-move actions.

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 0
- High: 1
- Low: 2
- Tickets created: None

_Generated 2026-07-02T00:47:02.705387+00:00_