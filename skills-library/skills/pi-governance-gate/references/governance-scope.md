# Governance Scope — What Requires Board Review

This document defines which Pi-CEO outputs must pass through the `pi-governance-gate` before distribution. Read this at the start of every gate invocation.

---

## REQUIRES BOARD REVIEW

### Tier 1 — Always (no exceptions)

| Output type | Examples | Why |
|-------------|----------|-----|
| Public content distribution | YouTube video publish, blog post publish, LinkedIn post | Brand / compliance risk; hard to retract |
| Strategic memos or decisions | Board memo, product decision, pivot recommendation | Sets direction for team and systems |
| External commitments | Pricing changes, partnership proposals, customer-facing announcements | Commercial and legal exposure |
| Linear issues: Priority Urgent, architectural scope | Core auth changes, billing changes, database migrations | High blast radius; autonomous agent may miss context |

### Tier 2 — Review if triggered by a Pi system autonomously (not human-initiated)

| Output type | Trigger condition | Why |
|-------------|-------------------|-----|
| Linear PR creation | Priority High + touches `lib/`, `prisma/`, `app/api/auth/`, `app/api/admin/` | Architecture-level changes need oversight |
| Content generation | New topic/format not seen in last 30 days | May introduce brand inconsistency |
| Gemini Scheduled Action recommendations | Any recommendation that suggests budget spend or partnership | Financial exposure |
| NotebookLM output distribution | Any KB output going to external audience | Knowledge accuracy |

---

## EXEMPT (no gate needed)

| Output type | Reason |
|-------------|--------|
| Bug fixes (Priority Normal or Low) | Low blast radius; standard review process sufficient |
| Dependency updates | No strategic content |
| Type-check / lint fixes | Mechanical corrections |
| Cron health check outputs | Internal only |
| Status reports to Phill (daily briefing) | For-information only; no action triggered |
| Content re-distribution (same content, new channel) | Already reviewed on first distribution |
| Failed-task logs | Internal error tracking |

---

## Decision Rule

If uncertain whether an output qualifies:

> **When in doubt, gate it.** The board deliberation takes 3-5 minutes. A bad distribution takes days to undo.

---

## Escalation

If the board issues **HOLD** or **REJECTED**:
1. Log to `D:\RestoreAssist\.claude\INBOX.md` with the full verdict block
2. Create a Linear issue in RA team with priority matching the original output
3. Notify Phill via Windows notification (settings.json Notification hook)

Never silently discard a HOLD or REJECTED verdict.

---

## Version

Governance scope v1.0 — configured 2026-04-14 (RA-832)
Next review: when Sprint 13 Gemini Scheduled Actions are live (RA-827)
