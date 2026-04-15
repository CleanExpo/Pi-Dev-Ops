# Board Meeting — 15 April 2026: Activation Vote

**Meeting type:** Scheduled 3-week check-in (advanced from Week 3 — board voted to fire early)
**Outcome:** Unanimous activation vote. 3-week window repurposed as parallel compounding sprint.
**Next board:** 6 May 2026 — Enhancement Review (RA-949)

---

## Verdicts

| Persona | Vote | Condition |
|---------|------|-----------|
| ORACLE | Activate | NotebookLM 5th criterion added (top-3 risks per entity) |
| CONTRARIAN | Activate | 3 autonomous PRs/day limit + 20 consecutive green merges to lift |
| STRATEGIST | Activate | 3-week window as parallel sprint, not idle wait |
| OPS | Activate | **Blocked on OB-4 until CARSI ADMIN_PASSWORD set in DigitalOcean** |
| MARATHON | Activate | Merge RA-948 today — sets precedent for autonomous PR review path |
| BOARD | **Unanimous** | All conditions recorded below |

---

## Conditions Locked

### 1. OB-4 — CARSI ADMIN_PASSWORD (OPS veto gate)
- **Status:** OPEN — developer action required
- **Action:** Set `ADMIN_PASSWORD` env var in DigitalOcean App Platform for carsi
- **Impact:** Full swarm activation blocked until closed. Shadow mode continues.
- **Ticket:** RA-950

### 2. Rate limit — 3 autonomous PRs/day (CONTRARIAN)
- **Status:** IMPLEMENTED — `MAX_AUTONOMOUS_PRS_PER_DAY=3` in `swarm/config.py`
- **Tracker:** `.harness/swarm/pr_rate_limit.json` (resets daily)
- **Lift condition:** 20 consecutive green supervised merges (`.harness/swarm/green_merge_counter.json`)
- **Override:** `TAO_SWARM_MAX_DAILY_PRS` env var

### 3. Merge RA-948 today (MARATHON)
- **Status:** PR #11 open — `pidev/auto-0e474d30`
- **Action:** Human review + merge sets the precedent for every future autonomous PR
- **Ticket:** RA-948

### 4. NotebookLM 5th criterion (ORACLE amendment)
- **Status:** IMPLEMENTED — RA-822/823/824 updated
- **Criterion:** Surface top 3 open risks per entity from Linear + Pi-SEO scan results
- **Purpose:** Forces actionable KB, not just factual reference

### 5. UPS purchase approved (board)
- **Budget:** AUD up-to-$500
- **Purpose:** Closes the only remaining ZTE hardware gap (uninterruptible power for Mac Mini swarm node)
- **Action:** Owner to purchase before 6 May board

---

## 3-Week Parallel Sprint (15 Apr → 6 May)

Not idle waiting. Compounding sprint targets:

| Track | Target |
|-------|--------|
| NotebookLM KBs | RA-822/823/824 complete — 3 entities, 5 criteria each |
| Dashboard live | PR #13 merged + Vercel deploy |
| CI webhook | PR #14 merged + `workflow_run` events on all repos |
| Swarm active | PR #12 merged + Railway `TAO_SWARM_SHADOW=0` |
| SDK Canary Phase B | Railway `TAO_USE_AGENT_SDK_CANARY_RATE=0.5` set |
| ZTE v2 | 85 → 90 |
| Synthex health | 56 → 80+ |
| Google Cloud Next | 22-24 Apr — capture AI/NotebookLM API announcements (RA-830) |

---

## Rescheduled: 6 May 2026

**Format:** Enhancement Review (not activation vote — activation carried today)

**Agenda:**
- Post Google Cloud Next '26 delta (RA-830)
- NotebookLM KB acceptance: 10/10 queries + top-3-risks criterion per entity
- Synthex health 56 → 80+ target
- Swarm: 20-green-merge counter progress report
- ZTE v2 score update

---

*Board record filed by Pi-CEO autonomous system. 2026-04-15.*
