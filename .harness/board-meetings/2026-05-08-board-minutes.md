# Board Meeting Minutes — Cycle 0 (2026-05-08)

## Business Velocity Index (RA-696)
**BVI: 7** (+1 from prior cycle)
- CRITICALs resolved: 7
- Portfolio projects improved: 0
- MARATHON completions (positive outcomes): 0
- Prior cycle BVI: 6

## Attendees
- Pi CEO Autonomous Agent (Orchestrator)
- CEO Board: 9 personas (CEO, Revenue, Product Strategist, Technical Architect,
  Contrarian, Compounder, Custom Oracle, Market Strategist, Moonshot)
- Gap Audit Agent

## Phase 1 — STATUS
- ZTE Score (v1): 85/100
- ZTE Score (v2): 87/100 [Zero Touch] (v1 base 75 + Section C 12/25)
- Urgent Issues: 10
- Cron Health: unknown

## Phase 2 — LINEAR REVIEW
- Urgent: 1 | High: 29
- Stale: RA-1694 (4d stale), RA-1670 (4d stale), RA-1663 (4d stale), RA-1685 (4d stale), RA-1089 (4d stale), RA-1882 (4d stale), RA-1925 (4d stale), RA-1935 (4d stale), RA-1937 (4d stale), RA-1920 (4d stale), RA-1918 (4d stale), RA-1915 (4d stale), RA-1914 (4d stale), RA-1758 (4d stale), RA-1741 (4d stale), RA-1897 (4d stale), RA-1904 (4d stale), RA-1895 (4d stale), RA-1894 (4d stale)
- Unassigned: RA-2073, RA-2077, RA-2076, RA-2075, RA-2074, RA-2072, RA-2020, RA-2015, RA-1957, RA-1958, RA-1694, RA-1670, RA-1663, RA-1685, RA-1089, RA-1882, RA-1925, RA-1935, RA-1937, RA-1920, RA-1918, RA-1915, RA-1914, RA-1758, RA-1741, RA-1897, RA-1904, RA-1895, RA-1894

## Phase 2.4 — RESEARCH BRIEF (RA-1972)
_Stage skipped — no empirical questions surfaced from intelligence brief._ Personas argue from priors only this cycle.


## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)
**CEO:** The system is improving — 87/100 ZTE is directional progress — but 19 stale items and a P0 schema drift sitting unresolved tells me execution velocity has stalled on the things that actually matter. The highest-leverage move this cycle is not adding capability, it's clearing the production debt: RA-1807 first, dedup triage second, nothing else until those two are done.

**Revenue:** RA-1807 is not an engineering problem — it is a client-trust problem. If 37 tables are missing from production despite migrations recorded as applied, any client-facing feature built on top of that schema is delivering on a lie, and in restoration/insurance-adjacent verticals, that is a termination-event waiting to be discovered. The commercial priority is zero new demos until the schema is verified clean.

**Product Strategist:** Seven of ten urgent tickets are duplicates or canceled, which means the autonomy loop is generating noise faster than it is producing signal. When the product's own backlog is this polluted, the ZTE score becomes a vanity metric — we are measuring activity, not outcomes. The dedup and triage hygiene is a product problem, not just an ops problem.

**Technical Architect:** RA-1807 — migrations recorded as applied but 37 tables absent in production — is a decoupled migration-tracking state, and that is the most dangerous class of infrastructure bug because it makes the system believe it is consistent when it is not. Before any new migration ships, we need a reconciliation script that diffs `supabase/migration.sql` declarations against live `information_schema` and fails CI if they diverge; that gate is non-negotiable.

**Contrarian:** The Technical Architect is right about the reconciliation script, but I challenge the CEO's framing that we should resolve RA-1807 "first" — if 37 tables have been missing in production for however long without a client-visible failure, we need to ask why nobody noticed, and the honest answer is that those tables may not be actively queried in production paths. Fixing schema drift is correct, but the urgency framing may be masking a deeper question: do we actually know which schema surfaces are live versus aspirational?

**Compounder:** The duplicate ticket problem is a compounding tax — every duplicate that stays open as "Urgent" is a false signal that degrades the autonomy engine's ability to prioritise correctly on future cycles. Nineteen stale items at 4+ days each means the system is not compounding toward 90/100; it is eroding the quality of its own input data, and that erosion accelerates if left unaddressed.

**Custom Oracle:** In Australian B2B SaaS serving insurance-linked and restoration industry clients, a production schema drift incident that surfaces during a client audit or integration review is categorically not recoverable with an apology. The Custom Oracle's highest-priority read here is: get RA-1807 resolved under a documented change-management process, not a hot-patch, because the paper trail matters as much as the fix in regulated environments.

**Market Strategist:** The board meeting timing slip — odd cycles 81, 83, 85 all missed — is an external positioning risk that nobody is naming. If this system is being positioned as an autonomous executive-intelligence layer for clients, and it cannot reliably fire its own governance cadence, that is a live demonstration of the product's reliability ceiling. The market will not distinguish "technical scheduling bug" from "the AI can't keep its own calendar."

**Moonshot:** At 87/100 ZTE the system is functional, but the ceiling question is whether this architecture can reach 95+ without a structural fix to dedup, schema integrity, and governance reliability — because those three failures are not independent bugs, they are symptoms of the same root cause: the autonomy loop lacks a self-healing reconciliation layer. Fix that layer and the compound gains become exponential; leave it and the system plateaus here permanently.

---

**CEO SYNTHESIS:** The single highest-signal output from this debate is that RA-1807 (schema drift) and the duplicate-ticket pollution are not two problems — they are one: the system's source-of-truth layer (database schema, Linear backlog) has diverged from its declared state, and every autonomous decision made on top of corrupted inputs is compounding the error. This cycle's mandate is purely reconciliatory — ship the schema diff gate, run the dedup triage pass, and restore backlog integrity before adding any new capability. When the foundation is verified clean, the path from 87 to 90+ ZTE is a sprint; until it is, every point gained is borrowed against hidden risk.

## Phase 3 — SWOT
## SWOT — Pi-CEO (ZTE Cycle · 2026-05-08)

---

**STRENGTHS**

- **Measurable velocity trajectory.** ZTE 85→87 with BVI +1; the score movement is real because it traces to 7 CRITICAL resolutions, not estimates. The metric has earned credibility.
- **Topology-correct autonomous pipeline.** Railway + Vercel + GH Actions form the always-on spine — the overnight-failure lesson (`[INFO] marathon-session`) was internalized and the architecture was rebuilt around it. Cowork is no longer a dependency.
- **Kill-switch depth (RA-1966/RA-1973).** Three orthogonal abort axes (`TAO_MAX_ITERS`, `TAO_MAX_COST_USD`, `HARD_STOP_FILE`) plus per-iteration crash recovery in the poller prevent runaway spend and silent loop death. The watchdog-around-poller pattern is wired in production.
- **Codified lessons base.** 20 high-signal operational lessons with priority tags exist and are surfaced every cycle — the system literally learns from its own failures and routes fixes into the codebase (e.g., `abs()` debounce fix from RA-579, XFF trust from `[WARN] RA-1043`).
- **Model routing policy enforced in three layers (RA-1099).** Opus cannot leak into generator/evaluator roles by accident. Cost ceiling is structural, not advisory.

---

**WEAKNESSES**

- **Corrupted source-of-truth layer — the cycle's #1 problem.** CEO board synthesis is explicit: RA-1807 schema drift + 29 unassigned + 19 stale issues + duplicate ticket pollution mean every autonomous decision is made on bad inputs. Compounding is already happening.
- **Health endpoints still theatre in places.** `[INFO]` lesson on `/health` and `[HIGH]` on LINEAR_API_KEY: the health surface reports process-alive, not work-actually-armed. `linear_api_key: bool` + `autonomy.armed` + `last_successful_tick` are required; their absence masks silent failure for full poller intervals.
- **Environment hygiene gaps are systemic, not one-off.** Three separate `[WARN]` lessons cover the same class: empty `ANTHROPIC_API_KEY` inheritance, `op://` refs parsed as literals, Vercel trailing `\n` on API keys. Each was fixed in isolation; a unified env-validation layer at startup still doesn't exist.
- **Cron state resets on every Railway redeploy (RA-579).** `last_fired_at` reverts to git-committed values. The `abs()` + startup-catchup fix is in lessons but the vulnerability recurs whenever a new cron trigger is added without the pattern applied.
- **Backlog is a black hole for autonomous pickup.** 29 unassigned issues are invisible to the Linear poller's Urgent/High Todo filter. The autonomous system cannot work on what it cannot see, so high-priority items sit untouched while lower-signal ones cycle through.

---

**OPPORTUNITIES**

- **Schema diff gate + dedup pass can restore integrity this cycle.** CEO board identified this as the single mandate — RA-1807 gate + one triage pass closes both problems together. This is the highest-leverage action available with current infrastructure.
- **TAO judge-gated loop (RA-1970) + context compactor (RA-1967) are built but not wired into `sessions.py`.** Integrating them is a defined TODO in CLAUDE.md. Done together they reduce per-session cost and improve loop termination quality without new architecture.
- **Senior agent bots (CFO/CMO/CTO/CS) are running on synthetic providers.** Stripe-Xero wiring for CFO is the next unlock — one env-var flip (`TAO_CFO_PROVIDER=stripe_xero`) with real credentials converts a synthetic signal into an actual financial dashboard.
- **Bidirectional Telegram loop is production-ready.** The inbound idea triage surface exists and works. Connecting the RA-1807 reconciliation report as a Telegram push gives the founder a human-in-the-loop checkpoint without requiring Mac presence.
- **19 stale items are a recoverable backlog, not permanent waste.** A single triage session that moves stale-but-valid tickets back to Todo (orphan recovery state) re-arms the autonomous poller to pick them up. Cost: one Linear API pass.

---

**THREATS**

- **Compounding error on corrupted inputs — existential for cycle credibility.** Every PR opened, every session spawned, every ZTE delta computed against a drifted schema or a polluted backlog increases the divergence. CEO board synthesis names this explicitly: the system's autonomous decisions are amplifying the error, not converging.
- **False escalation fatigue destroys the alert channel.** The marathon watchdog lesson (`[INFO]`) documented a CRITICAL fired from a sandbox that had missing deps — the tests were 46/46 green. One false CRITICAL makes every subsequent alert suspect. Pi-CEO currently has no consecutive-failure threshold or cooldown on Telegram alerts (`[WARN] sprint-12-review`).
- **Rate-limit blind spot in Railway.** `request.client.host` is the internal LB IP in Railway; per-IP buckets never fill. This was found and the XFF fix was documented (`[WARN] RA-1043`) — but it requires `_IS_CLOUD` detection to be correct on every route that does rate-limiting. A misconfigured flag silently disables the entire rate-limit layer.
- **CI gate ambiguity enables bad merges.** `[INFO] sprint-12-review` documented that a failing job NOT in `required_status_checks` does not block merges. With the autonomous pipeline opening PRs and the branch-protection config under-specified, a green-CI merge could bypass a failing-but-non-required check silently.
- **10 Urgent issues unresolved while the system works autonomously on Medium/High backlog.** If the poller's priority filter is not strictly Urgent-first, the session allocation could be inverting the intended priority stack — processing easier tickets while the hardest ones age.

## Phase 4 — SPRINT RECOMMENDATIONS
## Phase 4 — Sprint Recommendations

---

**PRIORITY 1: RA-2077 (+ RA-2076, RA-2075) — Fix CI on CleanExpo/Unite-Group main**
Three consecutive identical CI failures on the same repo indicates a structural break, not a flake — the autonomous pipeline cannot safely ship to Unite-Group until the gate is green.
**Estimate: M (2–4h)**
**Impact:** Unblocks all autonomous PR merges targeting Unite-Group; restores the CI gate that RA-1099/RA-1966 depend on to keep Opus leakage and runaway spend detectable. Direct +1–2 ZTE points if any open PRs are gated behind it. Leaving it red means every subsequent autonomous fix to that repo silently skips the safety net.

---

**PRIORITY 2: RA-2072 — Diagnose and restart the board-meeting task (12h silence)**
The board meeting is the primary intelligence loop driving ZTE scoring and Linear ticket synthesis; 12h of silence means this sprint's recommendations, including these, are made on a stale signal.
**Estimate: S (1–2h)**
**Impact:** Restores the autonomous decision layer to armed status. Per the SWOT, health endpoints must surface `autonomy.armed` + `last_successful_tick` — fixing the task and wiring those fields into `/api/autonomy/status` kills two birds: the loop runs again AND the silent-failure theatre on `/health` is resolved. Operational health lift is immediate; ZTE indirectly benefits through cleaner cycle data next board meeting.

---

**PRIORITY 3: "Triage and close duplicate Linear tickets in the Urgent/High backlog" (no ticket — propose RA-2078)**
Ten-plus `[Duplicate]` tickets are currently visible in the autonomous poller's queue, meaning every cycle wastes cycles re-evaluating zombie work and the ZTE source-of-truth is actively corrupted — the SWOT names this the #1 compounding problem.
**Estimate: XS (<1h)**
**Impact:** Directly addresses the SWOT's #1 structural weakness with near-zero code cost — close duplicates via Linear API, move unassigned issues to correct team/project. Cleans the queue the autonomous poller reads, reducing false positives in sprint metrics and preventing the ticket-pollution compounding that skews ZTE scoring upward on ghost work. Expected to surface 2–3 real actionable tickets currently hidden behind the noise.

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 3
- High: 2
- Low: 0
- Tickets created: RA-2078, RA-2079, RA-2080, RA-2081, RA-2082

_Generated 2026-05-08T05:06:10.924713+00:00_