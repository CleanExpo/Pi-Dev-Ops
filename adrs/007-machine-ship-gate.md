# ADR 007: Machine ship gate — autonomous spec pipeline without planning HITL

**Date:** 2026-07-01
**Status:** Accepted

## Context

The command chain `/judge → STORM → /spm → /boardroom → build → /review → /session-handoff` exists as read-only skills. Planning stages require explicit human approval after each gate. Operators want machine-only approval when evidence, boardroom triangulation, and oracles pass — with audit artifacts replacing chat approval.

## Decision

1. **`TAO_MACHINE_SHIP_MODE=1`** enables the machine spec pipeline (`app/server/spec_pipeline/`). Default off.
2. **Machine gates replace human HITL for planning** when all hold:
   - Prebuild judge score == 100 with no `UNSUPPORTED` / `NOT CHECKED` evidence rows
   - Boardroom synthesis parses to `APPROVE_BUILD`
   - Boundary scan finds no 🚫-tier paths in proposed scope
3. **Immutable launch-charter limits are NOT waived:**
   - No direct push to `main` (PR via `pidev/auto-{id}` only)
   - No production deploy (Railway/Vercel)
   - No 🚫-tier file edits (`config.py`, `auth.py`, `.env*`, `middleware.ts`, `api/actions/`, `seed.sql`)
   - No secrets in generated code, no client comms, no billing
4. **Merge** proceeds only when review verdict `PASS`, pytest/import (and tsc if dashboard touched) green, evaluator ≥ 8, and GitHub required checks green.
5. **Audit:** every machine approval logs to Supabase `gate_checks` via `supabase_log.log_gate_check` with `pipeline_id` prefix `spec-`.
6. **Escalation:** honest judge ceiling, boardroom `REJECT`, or 🚫 boundary → Telegram edge alert (state-change only); pipeline writes `08-handoff.md` and stops.

## Consequences

**Easier:** Repeatable spec-to-PR flow; artifact dir `.harness/spec-pipelines/{id}/` is the audit trail.

**Harder:** Risk of false 100/100 — mitigated by structured evidence rows + boardroom divergence + honesty ceiling.

**Ops prerequisite:** `GITHUB_TOKEN` with PR merge permission; branch protection must allow bot merge when checks pass.
