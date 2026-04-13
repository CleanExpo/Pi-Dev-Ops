# Board Meeting Minutes — Cycle 21 (2026-04-12)

## Attendees
- Pi CEO Autonomous Agent
- Gap Audit Agent

## Phase 1 — STATUS
- ZTE Score: unknown
- Urgent Issues: 10
- Cron Health: unknown

## Phase 2 — LINEAR REVIEW
- Urgent: 0 | High: 0
- Stale: None
- Unassigned: None

## Phase 3 — SWOT
# Phase 3 — SWOT Analysis
**Pi-CEO Board Meeting | 2026-04-13 | Sprint 9**

---

## STRENGTHS

- **Multi-path execution architecture is sound.** SDK dual-path (generator + evaluator) wired with subprocess fallback; `bypassPermissions` granted at all three required layers (settings.json, ClaudeAgentOptions, subprocess flag). No single point of failure in the execution stack. *(Lesson: marathon-session/permissions)*
- **Parallel agent dispatch proven.** ~8x throughput gain over sequential dispatch documented and adopted. Constraint (no shared file targets) is understood and enforceable. *(Lesson: orchestration-pattern/architecture)*
- **Telegram pipeline is production-simple.** Bidirectional loop operational with zero heavy dependencies — urllib POST suffices, no `python-telegram-bot` required. Inbound ideas gated at `.harness/ideas-from-phone/` (no auto-promotion to Linear). *(Lesson: ?/? — bidirectional Telegram loop)*
- **10 Urgent issues on the board** — backlog is populated and prioritised; sprint has concrete, actionable work rather than vague queues.
- **Lessons corpus is operationally useful.** 20 entries spanning SDK, scheduler, deployment, architecture — covering root causes, not just symptoms. Pattern density is high enough to inform Sprint 9 decisions without re-learning.

---

## WEAKNESSES

- **ZTE Score unknown this cycle.** Two consecutive prior cycles showed 60/60 but this cycle has no confirmed score. Cannot assess whether any leverage point has degraded without a fresh audit.
- **Pi-SEO canary never activated.** Scanner built, triage engine wired, 10 repos registered — but zero baseline scan data exists across the portfolio. Infrastructure without execution produces no value. *(Prior minutes: Phase 4, Priority 2)*
- **SDK canary Phase A still at 0% traffic.** `TAO_USE_AGENT_SDK_CANARY_RATE=0.10` unset in Railway as of last two cycles. Dual-path implementation risks bitrot the longer real-traffic validation is deferred. *(Lesson: WARN — use public `async for` loop, not private `_query.receive_messages()`)*
- **`/health` endpoint reports process liveness, not work execution state.** LINEAR_API_KEY absence produces silent poll-skipping with a green health response. `autonomy.armed` and `last_successful_tick` are not surfaced. *(Lesson: ?/? — health endpoints should report work state)*
- **Scheduled-task environment is unreliable for validation.** `anthropic>=0.90` dependency missing from Cowork sandbox triggered false CRITICAL Telegram alert. Test-truth must come from GH Actions, not the watchdog sandbox. *(Lesson: ?/? — marathon watchdog false CRITICAL)*

---

## OPPORTUNITIES

- **`/health` hardening is a one-ticket fix with high systemic value.** Add `linear_key_ok: bool` and `last_poll_at: timestamp` to the endpoint. Eliminates the entire class of silent-success-theatre failures. *(Lesson: ?/? — Pi-Dev-Ops silent failure mode)*
- **Do-while poller pattern eliminates cold-start delay.** Replace `sleep-first` loops with `startup_delay=10s` + immediate first fetch. Removes the 5-minute Railway cold-start dead zone that has repeatedly caused false "system stuck" alerts. *(Lesson: ?/? — sleep-first bootstrap-delay bug)*
- **Semantic RAG memory layer is architecturally scoped.** Per-project `memory/` folder + retrieval step before session start + weekly summarisation is the correct answer to context scaling — not GPU-dependent KV cache quantization (TurboQuant is irrelevant on CPU-only Railway). Implementation plan exists in TURBOQUANT-ASSESSMENT.md. *(Lesson: ?/? — TurboQuant assessment)*
- **Pre-commit `detect-secrets` hook deployment.** Pi-SEO scan found 6 exposed keys across dr-nrpg, synthex, ccw-crm in docs/runbooks and scripts/. Adding the hook to all portfolio repos before Pi-SEO full activation prevents the scanner from surfacing the same findings repeatedly. *(Lesson: pi-seo-dryrun/security)*
- **Cron scheduler silent-regression fix is documented and ready to implement.** Root cause known: `abs()` missing in debounce, no startup catch-up, no watchdog Linear ticket on 12h scan gap. Fix is three targeted changes. *(Lesson: HIGH — RA-579/scheduler)*

---

## THREATS

- **Linear API auth failing for two consecutive cycles (401).** Board reports and triage silently gap. No alerting mechanism exists when the key expires. With 10 Urgent issues on the board, a missed triage cycle means real work goes unscheduled. *(Prior minutes: Phase 2 both cycles)*
- **`triage-cache.json` at 353KB with no rotation.** Scanner startup degradation is a compounding risk — each sprint adds weight. No pruning strategy defined after two cycles of flagging it.
- **Railway is the single always-on component; everything else is topology-dependent.** Cowork/Mac-sleep failures have already caused one overnight autonomy failure. Any feature that requires the local Mac to be awake is not autonomous by definition. *(Lesson: ?/? — autonomy is a property of topology)*
- **`cron-triggers.json` `last_fired_at` resets on Railway redeploy.** Combined with the bogus-future-timestamp debounce bug, every deploy silently suppresses the next scheduled scan window. Pi-SEO activation on broken cron infrastructure produces zero scans. *(Lesson: HIGH — RA-579/scheduler)*
- **Reconnaissance-before-planning discipline is fragile under time pressure.** The 2026-04-11 Pi-SEO swarm lost ~2 hours to a duplicated `/Pi-CEO/Pi-SEO/` folder because agents drafted plans without reading actual `.harness/` state first. One lapse costs more time than the speedup gained by skipping recon. *(Lesson: WARN — orchestration-pattern/architecture)*

## Phase 4 — SPRINT RECOMMENDATIONS
## Phase 4 — Sprint Recommendations

**Context:** Linear board shows no open urgent/high issues this cycle. Two consecutive prior cycles both deferred the same three items. Deferral ends now.

---

**PRIORITY 1: Activate SDK Canary Phase A (10% traffic)**
*Proposed ticket: RA-SDK-CANARY-A (no existing ticket found in open issues)*

Set `TAO_USE_AGENT_SDK_CANARY_RATE=0.10` in Railway environment variables. No code changes required — rollout plan exists at `.harness/agents/sdk-phase2-rollout.md`, config vars are wired in `config.py` (RA-578), smoke test flags ready in `scripts/smoke_test.py --agent-sdk` (RA-575). Three consecutive board cycles have flagged this as Priority 1 and it has not moved. The SDK dual-path (RA-571, RA-572) is dead code until real traffic touches it — every week without activation increases bitrot risk.

**Estimate:** XS (<1h) — one Railway env var + one smoke test run
**Impact:** Eliminates highest-priority dead-code risk. Begins real-traffic evidence collection for Phase B eligibility. ZTE *Feedback Loops* leverage point upgrades from theoretical to validated.

---

**PRIORITY 2: Execute Pi-SEO First Full Sweep (all 10 repos)**
*Proposed ticket: RA-PISEO-SWEEP-1*

Run the Pi-SEO scanner across all 10 repos registered in `.harness/projects.json`, review finding volume, tune severity thresholds if output exceeds 50 findings, and allow the triage engine to auto-create Linear tickets from critical/high findings. The scanner has been production-ready since Sprint 6. Zero baseline scan data exists across the entire portfolio despite the full infrastructure being in place (scanner, triage engine, 3 skill layers, cron rotation, auto-PR). This is the clearest case of built-but-never-run in the harness.

**Estimate:** S (1–2h) — run sweep + review output + threshold tuning if needed
**Impact:** Populates sprint backlog with concrete, data-driven work. Establishes portfolio health baseline. Activates the Pi-SEO investment that has been sitting idle. ZTE *Trigger Automation* leverage point gains its first real-world execution cycle.

---

**PRIORITY 3: Fix Linear API Authentication (401 recurring)**
*Proposed ticket: RA-LINEAR-AUTH-FIX*

Diagnose and resolve the `LINEAR_API_KEY` 401 error that has caused two consecutive board cycles to run blind (no issue data, fallback-only sprint planning). Steps: (1) verify key expiry in Linear workspace settings, (2) rotate key and update `%APPDATA%\Claude\claude_desktop_config.json` MCP server config, (3) add a health-check assertion to the board meeting startup sequence that surfaces auth failure before Phase 1 proceeds rather than silently falling back. Without live Linear data, sprint planning relies on stale harness files — a structural gap that compounds every cycle the auth failure persists.

**Estimate:** XS (<1h) — key rotation + config update + one-line health check
**Impact:** Restores board meeting data integrity. ZTE *Feedback Loops* and *Workflow Standardisation* leverage points are degraded while the board operates blind. Fix is prerequisite for any future cycle where issue triage drives sprint planning.

## Phase 6 — GAP AUDIT SUMMARY
- Critical: 3
- High: 4
- Low: 8
- Tickets created: RA-665, RA-666, RA-667, RA-668, RA-669, RA-670, RA-671

_Generated 2026-04-12T22:20:17.336589+00:00_