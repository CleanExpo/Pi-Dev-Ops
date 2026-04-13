# CEO Memo — Board Minutes
**Date:** 2026-04-13  
**From:** CEO  
**Re:** Pi-CEO has a measurement problem, not just a gap problem  
**Cycle:** 23 (Sprint 9 close / Sprint 10 open)

---

## DECISION

Three-phase restructure of Pi-CEO operating priorities effective immediately.

| Phase | Timing | Focus |
|-------|--------|-------|
| 1 | This week (manual) | Fix self-awareness — regenerate spec.md, resolve RA-675 |
| 2 | Sprint 10 (autonomy poller) | Scout Agent (RA-684), Board personas (RA-686), feedback loop (RA-689) |
| 3 | Sprint 11+ | Shift primary metric from ZTE Score → Business Velocity Index (BVI) |

---

## RATIONALE

Pi-CEO at **73/75 ZTE** with portfolio stuck at **62/100 and zero improvement trend** is not a coincidence — it is evidence the system has been optimising for the wrong thing.

- ZTE measures whether capabilities exist. It does not measure whether they are working.
- 23 cycles produced a well-scored machine that isn't delivering the one outcome that matters: 11 portfolio projects improving, real clients served, founder making only strategic decisions.

**Three structural gaps are the root cause:**

| Gap | Ticket | Impact |
|-----|--------|--------|
| Stale spec.md | RA-675 / RA-685 | System self-assessment cannot be trusted |
| No Scout Agent | RA-684 | No external portfolio sensing |
| Board personas disconnected | RA-686 | Strategic deliberation layer absent |

A system missing these three is not Zero Touch — it is a well-architected system requiring constant human supervision. That is not acceptable given the design intent.

**Security is a blocking gate.** RestoreAssist (325 security findings) and CCW-CRM (4,877 findings) operate in a compliance environment where a security incident is a commercial termination event. Security health for both projects becomes a blocking gate before any new feature work proceeds.

---

## THE DISSENT THAT ALMOST CHANGED THE DECISION

The Moonshot framing — Pi-CEO as Founder OS, not DevOps tool — is correct. When fully functional this system is an intelligent business operating system for non-technical founders. That framing nearly moved the decision toward productisation infrastructure over portfolio remediation.

**What stopped it:** You cannot productise a system that hasn't proven it works for its one current user. Proof first. Then ceiling.

---

## NEXT ACTIONS

### 1. PHILL — TODAY
Run `python _deploy.py` on the Mac Mini from the Pi-Dev-Ops folder.
- Regenerates spec.md
- Restores accurate intelligence to all board meetings
- Prerequisite for everything that follows
- **Done =** `get_last_analysis` returns Sprint 9 / Cycle 23 data with ZTE 73/75

### 2. AUTONOMY POLLER — SPRINT 10
| Ticket | Description | Priority |
|--------|-------------|----------|
| RA-684 | Scout Agent | P1 Urgent |
| RA-686 | CEO Board personas wired in | P1 Urgent |
| RA-685 | Resolved by Phill's manual action above | — |
| RA-687 | CRITICAL security alerts | Parallel |

**Done =** Scout fires on Monday pre-board; board meeting includes persona debate output.

### 3. CEO — NEXT BOARD MEETING (CYCLE 24)
Introduce Business Velocity Index as the primary metric.

**Baseline (Cycle 23):**
- CRITICALs resolved: 0
- Portfolio projects with improved health: 0
- MARATHON completions: 0

**Done =** BVI is the first number on every board meeting report from Cycle 24 onwards.

---

## DECISION REVERSAL CONDITIONS

| Trigger | Response |
|---------|----------|
| RestoreAssist or CCW-CRM security incident before health reaches 80/100 | Immediate full stop on all Pi-CEO internal work until both projects remediated |
| BVI shows no improvement after 3 cycles of Phase 2 | Architecture is not the problem — examine whether autonomy poller is executing effectively |
| spec.md staleness recurs within 14 days of fix | RA-635 watchdog is broken — treat as P0 before trusting further automation |

---

## RISK TO WATCH

The most dangerous assumption: the autonomy poller will execute Sprint 10 items correctly without supervision. The self-scan gap (RA-675) means Pi-CEO's self-assessment cannot be trusted. If RA-684 builds a Scout Agent that scores well on the evaluator but doesn't work in production — we will have a 74/75 ZTE score and no external intelligence.

**The evaluator gate measures code quality, not functional correctness. Manual verification of Sprint 10 outputs is required, not optional.**

---

## BUSINESS VELOCITY INDEX — DEFINITION

Primary metric from Cycle 24. Replaces ZTE score as the opening number on every board report.

Components:
1. **CRITICAL alert resolution speed** — time from alert raised to resolved
2. **Portfolio health improvement** — projects showing positive delta cycle-over-cycle
3. **Features delivered to real users** — MARATHON completions shipped to clients

ZTE score becomes a background health check, reported but not the lead metric.
