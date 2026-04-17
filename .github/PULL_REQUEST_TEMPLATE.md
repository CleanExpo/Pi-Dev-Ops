<!--
  RA-1109: mandatory PR template to prevent "surface treatment" merges.

  History: PR #48 (RA-1100) shipped a "Fix with Claude" button that technically
  hit HTTP 200 but had zero user-visible progress. User (rightly) called it
  "a placeholder and not actually working." Lint was clean. Types were clean.
  The only thing that would have caught it was a human verifying the UX path
  end-to-end. This template makes that step mandatory and visible.
-->

## Summary
<!-- 1-3 sentences. What user-visible outcome changed? -->

## User-observable verification — REQUIRED for any interactive change
<!-- Tick every box. If a box is not applicable, explain why in a note. -->

- [ ] **Clicked the button / ran the action on the live deployment** (not localhost, not dry-run) — describe the exact path below
- [ ] **UI changed visibly** in response — not just an HTTP 200 echoed to console
- [ ] **Error states tested** (disconnect, timeout, 4xx, 5xx) — each shows the user something actionable
- [ ] **Progress surface** exists for actions >2 seconds (spinner, log stream, status chip — NOT a toast that disappears)
- [ ] **If partial / async / fire-and-forget** — feature is labelled `(preview)`, `(background)`, or has a "watch live" affordance

**Manual verification path:**
<!-- e.g. "opened /control on pi-dev-ops.vercel.app, clicked a Portfolio Health tile, clicked ▶ Fix with Claude on a Ruff finding, watched the streamed log output until 'complete' appeared." -->

## Test plan
- [ ]

## Karpathy check (from CLAUDE.md §4 Goal-Driven Execution)
- [ ] Success criteria defined BEFORE writing code — not after
- [ ] Loop ran until verified — not stopped at first green signal (lint / HTTP 200)
- [ ] If any step is "I'll check it later", state that explicitly here

## Backend changes
- [ ] New endpoint? → existing frontend surface wired to it in the SAME PR
- [ ] New table? → `supabase/migration.sql` updated + CLAUDE.md observability table updated in SAME PR (per RA-1105)
- [ ] Model usage? → respects RA-1099 policy (Opus only for planner/orchestrator)

<!-- Only skip the above if the change is pure docs / refactor / config. Note why here. -->
