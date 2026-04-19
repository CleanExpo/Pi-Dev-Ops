# Task Brief

[URGENT] [PROCESS] Smoke test coverage gap: CI green ≠ new feature works

Description:
## The gap, stated plainly

`scripts/smoke_test.py` covers pre-existing generic endpoints: auth, /api/gc, /api/lessons, webhooks, rate limits, /api/autonomy/status, SDK imports. It is **invariant across PRs** — it has no knowledge of features shipped in the current PR.

When `smoke-prod` passes on main, it proves the **baseline** is intact. It does **not** prove the specific change in the last PR works end-to-end.

## Evidence this bit us today

* PR #48 shipped "Fix with Claude" button → endpoint returned HTTP 200 → CI smoke-prod passed → feature was unusable (silent spawn, no progress UI) until user (Phill) click-tested manually.
* PR #57 added the PR template + Surface Treatment Prohibition in [CLAUDE.md](<http://CLAUDE.md>) to force manual verification on interactive changes. That's procedural. The AUTOMATED smoke gap is still open.

## Proposed scope (board to refine)

Extend `scripts/smoke_test.py` with a **per-PR surface map**:

1. New file `scripts/smoke_test_ui_surfaces.json` — authored by the PR author as part of the template, lists endpoints + buttons the PR touches with expected response shapes / event streams.
2. Smoke test reads the file, exercises each surface (POST /api/build with dummy brief, connect SSE, assert first event within 5 s, etc.).
3. CI gate: if a PR touches `dashboard/components/**` or `app/server/routes/**` but doesn't update the surface map, smoke test fails with a helpful message.
4. Playwright or similar for DOM-level verification of streamed output, progress chips, error states.

## Decision requested of the Pi-Dev-Ops board

* Is this the right scope, or should it be smaller (just JSON-schema per-PR checks)?
* Who builds it? (This is a generator-role task by the model policy — Sonnet 4.6)
* Priority relative to the RA-1153 UI audit sweep?
* Deadline?

## Linked

* PR #48 (origin incident) · PR #56 (hotfix) · PR #57 (procedural prevention)
* [CLAUDE.md](<http://CLAUDE.md>) § "Surface Treatment Prohibition"
* [CLAUDE.md](<http://CLAUDE.md>) "Running Tests" — documents the smoke_test.py invocation pattern

Linear ticket: RA-1154 — https://linear.app/unite-group/issue/RA-1154/process-smoke-test-coverage-gap-ci-green-new-feature-works
Triggered automatically by Pi-CEO autonomous poller.


## Session: 6e5bf78d7edb
