# Pi Dev Ops — Sprint Plan

_Sprint 12 active | 2026-04-16 | ZTE v2: 85/100 | 98+ features shipped_

---

## Sprint 12 — Active (2026-04-16 → 6 May 2026)

**Theme:** Swarm Activation + ZTE v2 → 90 + NotebookLM KB Build

**Board decision (15 Apr 2026):** Unanimous activation. 3-week parallel compounding sprint.

### Open PRs — merge queue

| PR | Title | Status |
|----|-------|--------|
| #22 | RA-1027: Multi-persona parallel evaluator with JSON findings | Open — review required |
| #24 | RA-1014/1015/1016/1017: Token revocation, WebSocket cap, CSP, login audit | Open — review required |
| #25 | RA-1018/1019/1021/1023: Task ref storage, body size limit, worker cap | Open — review required |
| #30 | RA-1011: Routine run outcome tracker — webhook + dashboard page | Open — review required |

### Active sprint items

| Issue | Priority | Title | Status |
|-------|----------|-------|--------|
| RA-822 | High | NotebookLM KB — RestoreAssist (5 criteria, incl. top-3 risks) | In Review |
| RA-823 | High | NotebookLM KB — Synthex (5 criteria, incl. top-3 risks) | In Review |
| RA-824 | High | NotebookLM KB — CleanExpo (5 criteria, incl. top-3 risks) | In Review |
| RA-838 | High | SDK Canary Phase B — set `TAO_USE_AGENT_SDK_CANARY_RATE=0.5` in Railway | Railway env var required |
| RA-886 | High | Branch protection — CI required before merge | In Review |
| RA-830 | Medium | Gemini Enterprise API vs community MCP — post Google Cloud Next decision | In Progress |

### Swarm activation conditions

| Condition | Status |
|-----------|--------|
| `TAO_SWARM_SHADOW=0` in `.env.local` | ✅ Done |
| `TAO_SWARM_SHADOW=0` in Railway | ⬜ Pending — set after PR #12 confirmed merged |
| 3 PR/day rate limit | ✅ Implemented (`swarm/config.py` + `builder.py`) |
| 20 green merge tracker | ✅ Created (`.harness/swarm/green_merge_counter.json`) |
| `TAO_PASSWORD` in `.env.local` | ⬜ Required for builder to fire `/api/build` |

### Board conditions (2026-04-15 activation vote)

- **Rate limit:** 3 autonomous PRs/day. Lifts after 20 consecutive green supervised merges.
- **NotebookLM 5th criterion:** Top 3 open risks per entity from Linear + Pi-SEO. Added to RA-822/823/824.
- **UPS purchase:** AUD ≤$500 approved. Owner action before 6 May board.
- **Next board:** 6 May 2026 — Enhancement Review (RA-949).

### Completed 2026-04-16

| Issue | Title |
|-------|-------|
| RA-1052–1059 | Self-improvement review — 8 categories, 2 new CLAUDE.md patterns added |
| RA-1051 | CI failure closed (CI green, superseded by prior commits) |

---

## Sprint 11 — Complete (2026-04-14)

**Theme:** Gemini Automation Layer + Dep Health + ZTE v2 → 85

| Issue | Priority | Title |
|-------|----------|-------|
| RA-839 | Urgent | Sprint 11 deadline alert |
| RA-816 | Urgent | Google account for Gemini automation |
| RA-817 | Urgent | notebooklm-mcp-cli v0.5.23 on Mac Mini |
| RA-818 | Urgent | Gemini Scheduled Action — Google Cloud Next '26 daily briefing |
| RA-819 | Urgent | Gemini Scheduled Action — daily calendar and email digest |
| RA-843 | High | Dep health PRs merged — carsi, DR-NRPG, Synthex, unite-group |
| RA-844 | High | Synthex CVEs 28→22 |
| RA-588 | High | MARATHON-4: first autonomous loop run end-to-end |
| RA-948 | Urgent | First autonomous PR pushed |
| RA-937 | High | main.py decomposed 922L → 11 focused modules |
| RA-821 | High | NotebookLM entity ranking — RestoreAssist/Synthex/CleanExpo selected |
| RA-837 | High | Anthropic docs synthesis script |
| RA-847 | High | CI failure → Linear ticket webhook handler |

**ZTE v2: 85/100**

---

## Sprint 10 — Complete (2026-04-14)

**Theme:** MARATHON-4 + BVI Baseline + ZTE v2 Section C

| Issue | Title |
|-------|-------|
| RA-814 | BVI First Baseline — Cycle 24 snapshot |
| RA-815 | Harness doc regeneration |
| RA-834 | Scanner false-positive audit — 28 exclusions added |
| RA-835 | carsi hardcoded admin password removed |
| RA-672 | ZTE v2 Section C — C4 live, C2 wired |
| RA-690 | CCW-CRM code quality 50→90 |
| RA-786 | Synthex error message leakage — 107 API routes fixed |

---

## Sprint 9 — Complete (2026-04-13)

**Theme:** Karpathy Enhancement Layer + Gap Audit | **ZTE v2: 81/100**

RA-674 confidence-weighted evaluator · RA-675 reality-check sprint (41→60/60 ZTE) · RA-676 AUTONOMY_BUDGET · RA-677 Session Scope Contract · RA-678 progressive brief complexity · RA-679 plan variation discovery · RA-680 layered abstraction · RA-681 dependency alerting · RA-682 Vercel drift monitoring · RA-683 Ship Chain series · RA-684 Scout Agent · RA-686 CEO Board Skill (9 personas) · RA-651 Supabase gate_checks · RA-660 incident history RAG · RA-696 BVI framework · RA-694 Gap Audit
