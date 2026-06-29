# SPM Spec — margot_router client-to-Board path (CIP production forwarder)

Date: 2026-06-29 · Status: DRAFT (read-only; no build until accepted) · Branch context: `claude/syn-921-nir-explainer`

## 1. Task
Make the Client Intake Pipeline's `forward_to_spm` path actually reach the Board in production by supplying a concrete `SpmForwarder` implementation (the SPM→Board executor) and the minimum provider wiring to run it — replacing the `NotImplementedError` stub at `swarm/intake/cli.py:_build_default_providers` (CIP-PR7). This is the correct home for the capability the reverted `ProductionSpmForwarder` hack tried to bolt onto `intake_router.py`.

## 2. Project context (verified, read-only this session)
- Pipeline = Telegram → Margot → SPM → Board → Production (`swarm/intake/SPEC.md:1`).
- `margot_router.py` is **pure logic, no DB/network** — `route_inbound(...)` returns a `RouterDecision` whose `action` enum includes `forward_to_spm` (`margot_router.py:60,359,627`).
- `intake_dispatch.py` executes decisions: `_apply_decision(...)` returns `(new_thread, pending_forward_body)`; after persisting the thread it calls `spm_forwarder.forward(thread_id, project_id, bot_id, body)` (`intake_dispatch.py:281,299–304`).
- `SpmForwarder` is a **Protocol** with exact contract `forward(*, thread_id, project_id, bot_id, body) -> None`, documented "async-fire-and-forget in production; tests just record the call" (`intake_dispatch.py:147–158`).
- `run_once(...)` (`cli.py:83`) already injects 8 providers (`registry, poller, llm, threads, projects, persister, reply, spm_forwarder`) and is fully unit-tested via fakes (`tests/test_cli.py`, `__tests__/test_intake_dispatch.py`).
- SPM logic exists: `build_spm_brief(...)` (`spm.py:291`) and `aggregate_board_response(...)` (`spm.py:374`).
- Board entry exists: `board.from_margot(*, topic, insight, citations?, requested_decisions?, repo_root?) -> str` (`board.py:62`).
- **Stub today:** `_build_default_providers()` raises `NotImplementedError("...CIP-PR7...")` (`cli.py:162`).

## 3. Problem statement
The pipeline is fully built as pure logic behind Protocols, but no concrete `SpmForwarder` exists and the provider constructor is a deliberate stub. So `python -m swarm.intake.cli run-once` cannot run in production — partner messages classified `forward_to_spm` reach a seam that has no executor. The capability is real and specced; only the I/O adapters are missing.

## 4. Desired outcome
A partner message that Margot classifies as `in_loop` results in: SPM brief built → Board deliberates → an `intake_board_rounds` row persisted → a partner-facing reply delivered — driven by the existing dispatcher, with no change to `margot_router` / `intake_dispatch` logic and no bypass in `intake_router.py`.

## 5. Scope and non-goals
**In scope (reduced — see §11):** a concrete `SpmForwarder` adapter that orchestrates `build_spm_brief → board.from_margot → aggregate_board_response → reply`, persists the board round, and is fire-and-forget; plus a real `intake_board_rounds` writer.
**Non-goals (defer):** full `_build_default_providers` wiring of all 8 providers; Duncan/Toby bot provisioning (CIP-PR7 ops); n8n; first-class `intake_workspaces` table (SPEC G5); production-handoff (`intake_production_handoffs`) automation.

## 6. Existing capability review (do not rebuild)
Reuse: `margot_router.route_inbound`, `intake_dispatch.dispatch_telegram_update`/`_apply_decision`, `spm.build_spm_brief`/`aggregate_board_response`/`trusted_partner_id_for_inbound`, `board.from_margot`, and the Supabase access helpers already in `intake_router.py` (`_sb_request`). The `SpmForwarder` Protocol + fakes are the test harness.

## 7. Specialist board review
- **Architect:** the Protocol seam is correct; the adapter must live in the provider layer (e.g. `swarm/intake/providers.py` or a `forwarders.py`), never in `intake_router.py`. Keep the adapter thin; logic stays in `spm.py`.
- **Security:** G3 anti-spoofing (`SPEC.md:23`) is already enforced upstream — the forwarder only ever receives a vetted `thread_id`/`project_id`. Do not re-derive partner identity in the forwarder.
- **QA:** the adapter is unit-testable by the existing fake pattern; add a contract test asserting `forward()` calls SPM then board then persists a round.
- **Cost (Devil's advocate):** `board.from_margot` runs a full board meeting (LLM-heavy). Fire-and-forget per inbound message can stack expensive runs — must respect the TAO kill-switch / a per-thread debounce.
- **PM:** highest-leverage slice is the forwarder + round persistence; the rest of PR7 (poller/stores) can follow once this proves out.

## 8. Judge challenge
Score **84/100 → REDUCE SCOPE (APPROVE EXPERIMENT)**. Evidence 22/25, problem 18/20, reuse 14/15, security 11/15, UX 7/10, testability 9/10, cost 3/5. Just under the 85 build bar purely on cost/control: a board meeting per message is unbounded spend without a debounce/kill-switch. Building the forwarder adapter alone (not full provider wiring) clears the risk.

## 9. Proposed solution
Add a concrete `SpmForwarder` (e.g. `swarm/intake/forwarders.py: BoardSpmForwarder`) implementing `forward(*, thread_id, project_id, bot_id, body)`:
1. Load `ProjectContext` + recent `ThreadMessage`s (via existing stores/Supabase helper).
2. `brief = build_spm_brief(project, messages, llm=...)`.
3. `sid = board.from_margot(topic=project.name, insight=brief.<material>, requested_decisions=brief.<questions>)`.
4. Persist an `intake_board_rounds` row (`thread_id`, `client_bot_id`, `sid`, status).
5. On board completion, `aggregate_board_response(...)` → deliver partner reply via `ReplyDelivery`.
6. Wrap in try/except (fire-and-forget) + TAO kill-switch / per-thread debounce.
Wire it into `_build_default_providers` for the `spm_forwarder` slot only; leave other providers raising until their own slice.

## 10. UX requirements
Silent ack on `forward_to_spm` (already handled — no reply sent at forward time, `intake_dispatch.py:372`); partner sees the Board's aggregated reply when deliberation completes. Surface a board-round record so a fan-out is observable (not invisible).

## 11. Technical requirements
- No edits to `margot_router.py` or `intake_dispatch.py` decision logic.
- Adapter satisfies the `SpmForwarder` Protocol signature exactly.
- DB writes idempotent per `(thread_id, round)`; reuse `_sb_request`.
- Respect `TAO_HARD_STOP` / kill-switch; add `INTAKE_BOARD_FANOUT`-style flag default OFF for first activation.
- **NOT CHECKED:** existence/columns of `intake_threads` / `intake_board_rounds` in the live Supabase (`SPEC.md` declares them NEW). Verify before writing.

## 12. Security / privacy
Partner identity comes only from `trusted_partner_id_for_inbound` upstream (G3). No partner_id from message body. Board material may contain client data — keep within existing observability redaction; no new external surface.

## 13. Verification plan
- `python -m pytest swarm/intake/tests/ swarm/inbox/__tests__/ -q` (existing suite stays green).
- New contract test: fake LLM/board/persister → assert `forward()` invokes SPM→board→round-persist→reply in order; assert exceptions are swallowed.
- Dry-run `run_once(..., dry_run=True)` with the new forwarder injected.

## 14. Loop / stress testing
- 50 rapid inbound messages on one thread → debounce collapses to bounded board rounds (no LLM storm).
- Board failure → reply not sent, error logged, offset still acked-by-policy, next tick unaffected.
- `TAO_HARD_STOP` set mid-run → forwarder aborts cleanly.

## 15. Acceptance criteria
1. A concrete `SpmForwarder` exists and passes a contract test.
2. `forward()` builds an SPM brief, triggers a board round, persists `intake_board_rounds`, delivers a partner reply.
3. Existing intake test suite stays green; no logic change to router/dispatch.
4. Cost guard (debounce + kill-switch) demonstrably bounds board runs.
5. Feature flag default OFF; live cron behaviour unchanged until flipped.

## 16. Goal command
`/goal Implement a concrete BoardSpmForwarder satisfying the SpmForwarder Protocol (forward: thread_id, project_id, bot_id, body) that orchestrates build_spm_brief → board.from_margot → intake_board_rounds persist → aggregate_board_response reply, fire-and-forget with TAO kill-switch + per-thread debounce, flag-gated default OFF; wire only the spm_forwarder slot in _build_default_providers; until the intake test suite (swarm/intake/tests + swarm/inbox/__tests__) is green and a new forwarder contract test passes.`

## 17. Implementation sequence
1. Verify `intake_threads`/`intake_board_rounds` schema in Supabase (read-only).
2. Add `forwarders.py: BoardSpmForwarder` + contract test (TDD).
3. Wire `spm_forwarder` slot in `_build_default_providers`; keep others stubbed.
4. Add debounce + kill-switch guard.
5. Run full intake suite; dry-run `run_once`.
6. Flag-gated rollout (default OFF); branch + PR.

## 18. Session-handoff seed
- Reverted the `_maybe_fanout_to_board` bypass in `intake_router.py` (working tree clean of it; 8 `.harness/*` artifacts remain, not this work).
- Canonical path = `margot_router` → `intake_dispatch` → `SpmForwarder` Protocol; the only missing piece is the concrete forwarder + `spm_forwarder` provider slot. `_build_default_providers` raises (CIP-PR7).
- First build command: see §16. Do not edit router/dispatch logic.

## 19. Final recommendation
**REDUCE SCOPE / APPROVE EXPERIMENT.** Build the `BoardSpmForwarder` adapter + `intake_board_rounds` persistence behind the existing Protocol and a default-OFF flag; defer full PR7 provider wiring. This delivers the named client-to-Board path with bounded cost and zero change to proven logic.
