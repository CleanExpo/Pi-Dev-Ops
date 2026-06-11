# ZTE Framework v2 — 100-Point Design

**Status:** Draft — RA-661  
**Author:** Board Cycle 22 recommendation  
**Replaces:** 75-point v1 framework (`.harness/leverage-audit.md`)

---

## Design Goals

v1 (75 points) measured internal pipeline quality. A system can score 75/75 while having:
- Zero real user adoption
- Broken deployments that nobody notices
- Drifting model quality that internal evaluators don't catch
- No visibility into whether the output actually solved the problem

v2 adds 25 points of **external validation** — signals that can only come from outside the pipeline.

---

## Section A — AI Pipeline Quality (60 points, unchanged from v1)

Dimensions 1-12 remain identical. A 60/60 here still means the pipeline is fully autonomous and self-correcting.

| # | Dimension | Max | v1 Score |
|---|-----------|-----|----------|
| 1 | Spec Quality | 5 | 5 |
| 2 | Context Precision | 5 | 5 |
| 3 | Model Selection | 5 | 5 |
| 4 | Tool Availability | 5 | 5 |
| 5 | Feedback Loops | 5 | 5 |
| 6 | Error Recovery | 5 | 5 |
| 7 | Session Continuity | 5 | 5 |
| 8 | Quality Gating | 5 | 5 |
| 9 | Cost Efficiency | 5 | 5 |
| 10 | Trigger Automation | 5 | 5 |
| 11 | Knowledge Retention | 5 | 5 |
| 12 | Workflow Standardization | 5 | 5 |

**Section A max: 60**

---

## Section B — Operational Health (15 points, unchanged from v1)

| # | Dimension | Max | v1 Score |
|---|-----------|-----|----------|
| 13 | Infrastructure Reliability | 5 | 3 |
| 14 | Operational Observability | 5 | 5 |
| 15 | Incident Response | 5 | 5 |

**Section B max: 15**

---

## Section C — External Validation (25 points, NEW in v2)

These dimensions measure whether the output of the pipeline has real-world effect. They cannot be self-reported — each requires an external signal source.

### C1: Deployment Success Rate (max 5)

**Question:** Of builds that reach the push phase, what fraction deploy without rollback within 24h?

| Score | Criteria |
|-------|----------|
| 5 | ≥95% of pushed builds survive 24h without rollback or manual hotfix |
| 4 | 85–94% survival rate |
| 3 | 70–84% survival rate |
| 2 | 50–69% survival rate |
| 1 | <50% survival rate or no deployment tracking |

**Data source:** `gate_checks` table + Railway deployment history. Track via `shipped=true` rows cross-referenced against rollback events.

---

### C2: Output Acceptance Rate (max 5)

**Question:** What fraction of completed builds are accepted by the requester without revision requests?

| Score | Criteria |
|-------|----------|
| 5 | ≥90% accepted without revision (Linear ticket → Done without re-open) |
| 4 | 75–89% accepted |
| 3 | 55–74% accepted |
| 2 | 35–54% accepted |
| 1 | <35% accepted or no tracking |

**Data source:** Linear — measure tickets that go In Progress → Done vs. tickets that re-open after Done. Requires `linear_sync` to record state transitions.

---

### C3: Mean Time to Value (max 5)

**Question:** How quickly does a trigger (webhook / Linear ticket) translate into a live deployment?

| Score | Criteria |
|-------|----------|
| 5 | Median trigger-to-deploy ≤ 20 minutes |
| 4 | 21–40 minutes |
| 3 | 41–90 minutes |
| 2 | 91–180 minutes |
| 1 | >180 minutes or not measured |

**Data source:** `workflow_runs` table — `started_at` vs. `push_timestamp`. Compute rolling 30-day median.

---

### C4: Security Posture (max 5)

**Question:** Does the Pi-SEO portfolio maintain an acceptable security baseline across all repos?

| Score | Criteria |
|-------|----------|
| 5 | All repos ≥80 security score, no criticals anywhere |
| 4 | All repos ≥60, no criticals in active repos |
| 3 | Portfolio average ≥60, at most 1 critical across all repos |
| 2 | Portfolio average 40–59 |
| 1 | Portfolio average <40 or critical findings unaddressed >7 days |

**Data source:** `scanner.py get_health_summary()` — security scores. Already implemented. Feeds directly from Pi-SEO scan cycle.

---

### C5: Knowledge Accumulation Velocity (max 5)

**Question:** Is the system getting smarter over time, or is it stagnant?

| Score | Criteria |
|-------|----------|
| 5 | ≥5 new lessons added to lessons.jsonl per week AND evaluator threshold holding (≥7.5/10 avg over 30 days) |
| 4 | 3–4 new lessons/week OR evaluator avg 7.0–7.4 |
| 3 | 1–2 new lessons/week OR evaluator avg 6.0–6.9 |
| 2 | <1 lesson/week or evaluator avg <6.0 |
| 1 | No lessons added in 30 days or no evaluator data |

**Data source:** `lessons.jsonl` line count delta over 7 days. Evaluator scores from `workflow_runs` or `gate_checks`.

---

## Section C Total: max 25

---

## Band Thresholds (v2, 100-point scale)

| Band | Range | Description |
|------|-------|-------------|
| Manual | 1–33 | Human drives every step |
| Assisted | 34–55 | AI helps but human orchestrates |
| Autonomous | 56–79 | AI orchestrates, human reviews |
| Zero Touch | 80–94 | Fully autonomous with operational integrity |
| Zero Touch Elite | 95–100 | Externally validated autonomous delivery |

---

## Migration: v1 → v2 Score

| Section | v1 Score | v1 Max | v2 Score (estimated) | v2 Max |
|---------|----------|--------|----------------------|--------|
| A: AI Pipeline | 60 | 60 | 60 | 60 |
| B: Operational Health | 13 | 15 | 13 | 15 |
| C: External Validation | — | — | ~12 | 25 |
| **Total** | **73** | **75** | **~85** | **100** |

Section C estimated score (day-1, data not yet collected):
- C1 Deployment success: 3 (no tracking yet — assume ~70–84% based on board meeting data)
- C2 Output acceptance: 3 (no Linear state-transition tracking yet)
- C3 Mean time to value: 3 (pipeline runs ~30–40 min end-to-end)
- C4 Security posture: 2 (portfolio average now ~65 post scanner fix, dr-nrpg/synthex drag it down)
- C5 Knowledge accumulation: 1 (lessons.jsonl exists but velocity not tracked; evaluator avg unknown)

**v2 launch score: ~85 / 100 — Zero Touch band**

---

## Implementation Roadmap

### Phase 1 — Data Collection (prerequisite before scoring C1–C5)

| Ticket | Work |
|--------|------|
| new | `workflow_runs` — add `push_timestamp` column; populate in `_phase_push()` |
| new | Linear state-transition log — record Done/Re-open events in `workflow_runs` |
| new | `scripts/zte_v2_score.py` — compute all 5 C-section scores from live data |
| new | Board meeting Phase 1 — extend `run_status_phase()` to call `zte_v2_score.py` |

### Phase 2 — Scoring in Production

Replace `.harness/leverage-audit.md` hand-scoring with `scripts/zte_v2_score.py` output.
Board meeting shows v2 score. ZTE reality-check (RA-608) uses v2 thresholds.

### Phase 3 — Close the Gaps

| Gap | Target score | Work |
|-----|-------------|------|
| Infrastructure Reliability (B13) | 3→5 | RA-641: UPS purchase |
| C2 Output acceptance | 3→5 | Linear state-transition tracking (30 days of data needed) |
| C3 Mean time to value | 3→5 | Evaluator parallelism + faster clone phase |
| C4 Security posture | 2→5 | Resolve ccw-crm/dr-nrpg/synthex findings over 2 sprints |
| C5 Knowledge velocity | 1→5 | Auto-lesson extraction from evaluator low-scorers (already partial via RA-660) |

**Target v2 score at sprint 10: 95+ / 100 — Zero Touch Elite**

---

## Rationale for Each C Dimension

**Why deployment success (C1)?** The pipeline can generate and push code that immediately breaks prod. Internal evaluators don't catch runtime errors, environment-specific failures, or dependency conflicts. A 24h survival gate is the minimum external signal.

**Why output acceptance (C2)?** Evaluator scores measure code quality, not whether the requester got what they asked for. A ticket marked Done that gets re-opened within 3 days is a pipeline failure the internal evaluator missed.

**Why mean time to value (C3)?** A 3-hour pipeline is not zero touch — it's just slower manual work. Sub-20-minute end-to-end delivery is the target that makes autonomous operation genuinely faster than human execution.

**Why security posture (C4)?** A fully automated pipeline that ships insecure code is delivering negative value. Pi-SEO already produces this signal; adding it to ZTE makes security a first-class score dimension rather than a background concern.

**Why knowledge accumulation (C5)?** An autonomous system that doesn't improve is a liability that accumulates technical debt at machine speed. The lessons.jsonl velocity and evaluator trend are the leading indicators of whether the pipeline is getting better or stagnant.
