# Pi Dev Ops — Sprint Plan

_Sprint 3 / Cycle 4 | 2026-04-08 | ZTE Score: 60/60 Zero Touch_

## Status

All Sprint 1 and Sprint 2 items are complete. ZTE score achieved maximum 60/60.
Sprint 3 focuses on validation, resilience, and documentation.

---

## Sprint 3 — Open Items

### RA-470 [High] — E2E Integration Smoke Test
**Problem:** 20 issues implemented across Sprint 1+2 but the full pipeline has never been
validated end-to-end. Individual components were smoke-tested at module level only.

**Required flow:**
```
Brief → PITER classify → ADW template select → Claude build (sandbox) → Evaluator grade → GitHub push
```

**Acceptance criteria:**
- Submit a real brief via POST /api/build
- Confirm PITER classifies correctly
- Confirm ADW template selected and injected into brief
- Confirm Claude Code runs in sandboxed workspace
- Confirm Evaluator grades and either approves or triggers retry
- Confirm push to GitHub on pass

---

### RA-471 [Medium] — Error Recovery: Transient Failure Retry
**Problem:** Error Recovery scored 2/5 in the original baseline. Sprint work brought it to 5/5
for clone/generator retries and sandbox auto-generate. One gap remains: network blip during
the final `git push` step.

**Required:**
- git push retry: up to 3 attempts with exponential backoff (2s, 4s)
- Network error detection: distinguish transient (retry) from auth failures (hard stop)
- Log retry attempts to session output stream

---

### RA-472 [Medium] — Update handoff.md
**Problem:** handoff.md is a minimal stub. Cross-session state relies on Linear issues.

**Required:**
- Compact summary of all 20 completed Sprint 1+2 implementation items
- Current architecture state (what changed from baseline)
- Known working configuration notes
- Outstanding gaps

---

## Completed Sprints

### Sprint 2 / ZTE Sprint (2026-04-08) — 50/60 → 60/60
RA-465 TAO wire-up, RA-464 fan-out, RA-463 harness dirs, RA-462 ZTE audit,
RA-460 auto-brief, RA-467 autonomous board, RA-466 docs pull, RA-468 sandbox,
plus ZTE sprint items: lesson injection, closed-loop evaluator, phase checkpoints,
clone/generator retry, auto-learn, cron triggers

### Sprint 1 / P1+P2 Sprint (2026-04-07) — 35/60 → 50/60
RA-450 session persistence, RA-451 workspace GC, RA-452 rate-limit GC,
RA-453 lessons.jsonl, RA-454 evaluator tier, RA-455 webhooks, RA-456 PITER+ADW,
RA-457 skills loader, RA-458 CLAUDE.md, RA-459 security, RA-449 MCP v3.0.0
