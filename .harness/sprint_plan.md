# Pi Dev Ops — Sprint Plan

_Sprint 12 active | 2026-04-15 | ZTE v2: 85/100 | 98 features shipped_

---

## Sprint 12 — Active (2026-04-15 → 6 May 2026)

**Theme:** Swarm Activation + ZTE v2 → 90 + NotebookLM KB Build

**Board decision (15 Apr 2026):** Unanimous activation. 3-week window is a parallel compounding sprint.

### Blocker (OPS veto — must close before swarm fires on carsi scope)

| Issue | Priority | Title | Status |
|-------|----------|-------|--------|
| RA-950 | Urgent | OB-4: Set ADMIN_PASSWORD in DigitalOcean for carsi | **Developer action required** |

### Immediate merge queue

| Issue | Priority | Title | Status |
|-------|----------|-------|--------|
| PR #11 / RA-948 | Urgent | Merge `pidev/auto-0e474d30` — first autonomous PR | **Pending human review** |
| PR #12 | High | Merge swarm active mode + bots | **Pending human review** |
| PR #13 | High | Merge dashboard redesign (Zinc/Geist/sidebar) | **Pending human review** |
| PR #14 | High | Merge RA-837/847 (docs synthesis + CI webhook) | **Pending human review** |

### Active sprint items

| Issue | Priority | Title | Status |
|-------|----------|-------|--------|
| RA-822 | High | NotebookLM KB — RestoreAssist (5 criteria, incl. top-3 risks) | In Review |
| RA-823 | High | NotebookLM KB — Synthex (5 criteria, incl. top-3 risks) | In Review |
| RA-824 | High | NotebookLM KB — CleanExpo (5 criteria, incl. top-3 risks) | In Review |
| RA-838 | High | SDK Canary Phase B — set TAO_USE_AGENT_SDK_CANARY_RATE=0.5 in Railway | **Railway env var required** |
| RA-886 | High | Branch protection — CI required before merge | In Review |
| RA-830 | Medium | Google Cloud Next '26 (22-24 Apr) — capture NotebookLM API delta | Todo |

### Swarm activation conditions

| Condition | Status |
|-----------|--------|
| `TAO_SWARM_SHADOW=0` in `.env.local` | ✅ Done |
| `TAO_SWARM_SHADOW=0` in Railway | ⬜ Requires Railway env update after PR #12 merges |
| OB-4 CARSI ADMIN_PASSWORD | ⬜ Developer action (RA-950) |
| PR #12 merged | ⬜ Pending human review |
| 3 PR/day rate limit | ✅ Implemented (`swarm/config.py` + `builder.py`) |
| 20 green merge tracker | ✅ Created (`.harness/swarm/green_merge_counter.json`) |
| `TAO_PASSWORD` in `.env.local` | ⬜ Required for builder to fire `/api/build` |

### Board conditions (2026-04-15 activation vote)

- **Rate limit:** 3 autonomous PRs/day (CONTRARIAN). Lifts after 20 consecutive green supervised merges.
- **NotebookLM 5th criterion (ORACLE):** Top 3 open risks per entity surfaced from Linear + Pi-SEO. Added to RA-822/823/824.
- **UPS purchase:** AUD ≤$500 approved. Owner action before 6 May board.
- **Next board:** 6 May 2026 — Enhancement Review (RA-949).

---

## Sprint 11 — Complete (2026-04-14)

**Theme:** Gemini Automation Layer + Dep Health + ZTE v2 → 90

| Issue | Priority | Title | Status |
|-------|----------|-------|--------|
| RA-839 | Urgent | Sprint 11 deadline alert — RA-818 before April 22 | **Done** |
| RA-816 | Urgent | Google account for Gemini automation (primary account used) | **Done** |
| RA-817 | Urgent | notebooklm-mcp-cli v0.5.23 on Mac Mini | **Done** |
| RA-818 | Urgent | Gemini Scheduled Action — Google Cloud Next '26 daily briefing | **Done** |
| RA-819 | Urgent | Gemini Scheduled Action — daily calendar and email digest | **Done** |
| RA-843 | High | Dep health PRs merged — carsi, DR-NRPG, Synthex, unite-group | **Done** |
| RA-844 | High | Synthex CVEs 28→22 (6 migrations done) | **Done** |
| RA-588 | High | MARATHON-4: first autonomous loop run end-to-end | **Done** |
| RA-948 | Urgent | First autonomous PR pushed — swarm_enabled/swarm_shadow in /health | **Done** |
| RA-937 | High | main.py decomposed 922L → 11 focused modules | **Done** |
| RA-821 | High | NotebookLM entity ranking — RestoreAssist/Synthex/CleanExpo selected | **Done** |
| RA-837 | High | Anthropic docs synthesis script | **Done** |
| RA-847 | High | CI failure → Linear ticket webhook handler | **Done** |

**Remaining:** RA-950 carsi `ADMIN_PASSWORD` (DigitalOcean, developer action required)

---

## Sprint 10 — Complete (2026-04-14)

**Theme:** MARATHON-4 + BVI Baseline + ZTE v2 Section C

| Issue | Priority | Title | Status |
|-------|----------|-------|--------|
| RA-814 | High | BVI First Baseline — Cycle 24 snapshot | **Done** |
| RA-815 | High | Harness doc regeneration — sprint_plan.md + feature_list.json | **Done** |
| RA-834 | High | Scanner false-positive audit — 28 exclusions added to config.py | **Done** |
| RA-835 | High | carsi hardcoded admin password removed | **Done** |
| RA-672 | High | ZTE v2 Section C — C4 live (4/5), C2 wired (session-outcomes.jsonl) | **Done** |
| RA-690 | High | CCW-CRM code quality 50→90 | **Done** |
| RA-786 | High | Synthex error message leakage — 107 API routes | **Done** |

---

## Sprint 9 — Complete (2026-04-13)

**Theme:** Karpathy Enhancement Layer + Gap Audit

| Issue | Change |
|-------|--------|
| RA-674 | Confidence-weighted evaluator — three-tier routing |
| RA-675 | Reality-check sprint — closed 19-pt self-scan gap (41/60 → 60/60 ZTE) |
| RA-676 | AUTONOMY_BUDGET single-knob |
| RA-677 | Session Scope Contract |
| RA-678 | Progressive brief complexity |
| RA-679 | Plan variation discovery |
| RA-680 | Layered abstraction |
| RA-681 | Dependency alerting |
| RA-682 | Vercel drift monitoring |
| RA-683 | Ship Chain Educational Series |
| RA-684 | Scout Agent |
| RA-686 | CEO Board Skill — 9 personas |
| RA-651 | Supabase gate_checks table |
| RA-660 | Incident history RAG |
| RA-696 | BVI framework |
| RA-694 | Gap Audit |

**ZTE v2: 81/100**
