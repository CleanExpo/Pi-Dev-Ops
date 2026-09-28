# Idea → live site: the pathway as it exists on 28 September 2026

**Status:** DRAFT (planning evidence, not a build plan). **Inspected revision:** `6121037` (main).
**Method:** read-only sweep of the repository by five agents, each claim cited by file and line and
the load-bearing ones re-read by hand in this session. Line numbers rot — re-run the command in
each row before relying on it.

This answers one question: when Phill has an idea, which parts of this repository carry it to a
feature that is verifiably working on the live site, and where does the chain stop?

## The chain, stage by stage

| # | Stage | What starts it | Where it lives | Receipt it leaves | State |
|---|---|---|---|---|---|
| 1a | Capture the idea (file) | A line in `IDEAS.md` | `app/server/idea_pipeline/intake.py` | Packet in the packet store | Implemented |
| 1b | Capture the idea (phone) | Telegram `/idea` → `.harness/ideas-from-phone/*.jsonl` | daily drain `.github/workflows/ideas_inbox_drain.yml` → `scripts/process_ideas_inbox.py` | Linear ticket at Normal priority (`process_ideas_inbox.py:70-71`) | Implemented |
| 2 | Board packet → GO | Founder's one-word decision | `app/server/idea_pipeline/__init__.py`, `dispose.py` | `verdict`, `go_at`, `execution_requested=True` on the packet | Implemented — **and stops here** (break A) |
| 3 | Ticket made eligible | A person sets status `Ready for Pi-Dev` + label `pi-dev:autonomous` or `pi-dev:machine-ship` | `app/server/autonomy.py`, `autonomy_eligibility.py` | Linear state change | Manual only (break B) |
| 4 | Autonomy poller claims it | Poll every `TAO_AUTONOMY_POLL_INTERVAL` s | `app/server/autonomy.py` | `.harness/autonomy.jsonl`, Linear comment | Implemented; production switch last seen **off** on 2026-08-18 (`QUEUE.md`), current value not re-checked (break C) |
| 5a | Build: plan → generate → evaluate | Session start | `app/server/session_phases.py`, `planner_admission.py` | SSE stream; Supabase `gate_check` row | Implemented |
| 5b | Machine-ship: storm → judge → spm → boardroom → review → merge | Label + `TAO_MACHINE_SHIP_MODE=1` (default 0) | `app/server/spec_pipeline/` | `stages[]`, machine gate record, Linear comment | Implemented behind a flag; targets one repo per process, `GITHUB_REPO` env defaulting to this one (`spec_pipeline/__init__.py:37`) |
| 6 | Pre-push review + PR | End of build | `session_phases.py` (adversary phase, push to `pidev/auto-<sid>`), `board_review.py`, `session_push_pr.py` | `.git/pi-ceo-board-review.json` bound to `head_sha`; PR | Implemented. Docs-only diffs skip review (`SKIP_DOCS_ONLY`) |
| 7 | Merge to main | Human | GitHub; `routes/webhooks.py` records it | `record_merge` (`supabase_log.py`) | Manual by design — see authority conflict below |
| 8 | CI gates | PR / push | `.github/workflows/ci.yml`, `smoke_surface_gate.yml` | Check runs | Running — GitHub Actions API, read 28 Sept 2026: `ci.yml` on `main` completed runs 2000–2008 that day, e.g. [36391039527](https://github.com/CleanExpo/Pi-Dev-Ops/actions/runs/36391039527) success, 36391027842 failure. `QUEUE.md`'s "no runner since 2026-08-14" is stale |
| 9 | Deploy | Git integration on `main` | `railway.toml`, `railway.json`, `dashboard/vercel.json` | None emitted by this repo | Platform-driven, no receipt (break D) |
| 10 | Prove it works live | Push to main / schedule | `ci.yml` `smoke-prod` (`--expected-sha`), `smoke_pipeline.yml` (6-hourly), `live_nexus_smoke.yml` | `post-deploy-metrics` artifact | Partial — Pi-Dev-Ops backend only (break E) |

## Where the chain breaks

- **A. GO does not start anything.** `dispose.py:53` "Never starts a build"; `start_spec_pipeline`
  always raises (`dispose.py:64-66`). Nothing outside the packet code reads `execution_requested`.
- **B. No code promotes a GO'd idea to an eligible ticket.** `goal_ticket.py` files to Backlog with
  no autonomy markers.
- **C. The poller may be switched off in production.** Last direct evidence is the 2026-08-18
  Railway log quoted in `QUEUE.md`. Flipping it is founder-only (activation, not maintenance).
- **D. Deploy leaves no receipt.** Nothing records which commit became live, when, on which URL.
- **E. "Complete" means "merged", not "working live".** Machine-ship sets
  `status = "complete" if self.merged` (`spec_pipeline/execution.py:234`). The merge webhook only
  records. `smoke-prod` checks the Pi-Dev-Ops backend, never the specific feature that shipped,
  and never another portfolio repo's live site.
- **F. No whole-project definition of done.** "Done" is scored against the brief, not the product
  (`docs/DIAGNOSIS-autonomous-completion-gap-2026-06-07.md`).
- **G. The ship-chain docs end at "ship".** `docs/ship-chain/01-the-algorithm.md` has no merge,
  deploy or live stage.

## Authority conflict that must be settled before anything auto-merges

`plan-to-done` v1.1 binds acceptance to "cross-model audit" under the 10 Sept 2026 decision. This
repository's own record says the opposite for itself: *"this repo's default is human-merge-only and
no `UG-AUTONOMY-001` exception applies to Pi-Dev-Ops"*
(`docs/session-handoffs/20260911-1230-0eca2639.md:212`). Both cannot be live. This is a
**direction** decision (Phill's), recorded in [`handoff.json`](handoff.json) as D0.

## What the plan-to-done package contributes to closing these

The package ([`../plan-to-done-v1.1/`](../plan-to-done-v1.1/README.md)) is a *planning* skill: it
writes the packet that would close A–G, it does not close them. Its relevant pieces:

| Break | Package piece |
|---|---|
| F (definition of done) | [`completion-coverage.md`](../plan-to-done-v1.1/plan-to-done/references/completion-coverage.md) — capability and journey coverage register |
| D, E (deploy + live proof) | [`delivery-design.md`](../plan-to-done-v1.1/plan-to-done/references/delivery-design.md) — post-deployment checks and support handover as required transitions |
| A, B (hand-off to build) | Step 10 `handoff.json` — a machine-readable next action a dispatcher can consume |
| Review receipts | Step 7/9 — receipts bound to `git patch-id`, two review rounds max |

Break C is a founder switch. Breaks A, B, D, E, G are code or doc work and are ticketed separately.

A second, independent pass added breaks H–L: [second-pass-2026-09-28.md](second-pass-2026-09-28.md).
