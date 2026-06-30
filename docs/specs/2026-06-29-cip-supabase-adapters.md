# SPM Spec — CIP Supabase-only adapter slice

Date: 2026-06-29 · Status: DRAFT (read-only; no build until accepted) · Judge: REDUCE SCOPE 78/100 (full PR7) → this de-risked slice

## 1. Task
Build the **Supabase-backed** concrete adapters for the Client Intake Pipeline — the data-plane providers — leaving the Telegram poller/reply (side-effecting, needs provisioned bots) to a separate gated slice. Concretely: `IntakeBotRegistry`, `ThreadStore`, `ProjectStore`, `MessagePersister`, plus the board-reply tick's `PendingRound` source + `RoundUpdater`.

## 2. Project context (verified live, read-only)
- All 7 CIP tables exist in the **Pi CEO** Supabase project `zbryrmxmgfmslqzizsto` (`information_schema`). Live row counts: `intake_partners=3`, `intake_client_bots=0`, `intake_threads=0`, `intake_projects=0` — schema applied, no bots provisioned yet.
- Reusable PostgREST client: `swarm/intake/round_store.py:_pi_ceo_sb_request` (targets `SUPABASE_PI_CEO_URL`/`_SERVICE_KEY`).
- Protocol seams: `intake_dispatch.py:81–150` (`ThreadStore`, `ProjectStore`, `MessagePersister`, `ReplyDelivery`), `cli.py:40–91` (`IntakeBotRegistry`, `TelegramPoller`, `run_once`).
- Domain types: `IntakeBot` (`intake_dispatch.py:48`), `ThreadState`/`ProjectSummary` (`margot_router.py:85,99`), `ProjectContext`/`SPMBrief` (`spm.py`).
- Merged units this slice serves: `BoardSpmForwarder`, `SupabaseBoardRoundStore`, `BoardReplyTick`.

## 3. Problem statement
`_build_default_providers` raises `NotImplementedError` and `BoardReplyTick`'s round-source/updater have no concrete impl, so none of the merged pipeline units can run against real data. The data plane (Supabase) can be built and verified now; the message plane (Telegram) cannot, because zero bots are provisioned.

## 4. Desired outcome
Concrete, unit-tested Supabase adapters that satisfy each Protocol exactly, map cleanly to the live columns, enforce tenant scoping, and are verified read-only against the live (empty) Pi CEO tables — ready to drop into `run_once`/`BoardReplyTick` once the Telegram slice lands.

## 5. Scope and non-goals
**In scope:** `IntakeBotRegistry.list_active_client_intake_bots`; `ThreadStore.{get_thread_for_chat,upsert_thread}`; `ProjectStore.{list_open_projects,create_project,rename_project}`; `MessagePersister.{record_inbound,record_outbound}`; board-reply `PendingRoundSource` + `RoundUpdater.{mark_replied,mark_failed}`. A read-only connectivity smoke script.
**Non-goals (deferred, separately judged):** `TelegramPoller`, `ReplyDelivery` (Telegram send), the full `_build_default_providers` wiring, Duncan/Toby bot provisioning, flipping `INTAKE_BOARD_FANOUT`.

## 6. Existing capability review
Reuse `_pi_ceo_sb_request` (don't re-write a PostgREST client); reuse the cuid pattern `icbr_…`/add `it_/ip_/im_` prefixes; reconstruct `ProjectContext`/`SPMBrief` from JSONB. No new pipeline logic — pure DB↔domain mapping.

## 7. Specialist board review
- **Architect:** one module `swarm/intake/stores.py` (or per-store files) of thin adapter classes, transport injected (default `_pi_ceo_sb_request`), mirroring `round_store.py`. Keep `round_store` as-is; add the reply-tick source/updater alongside or in `round_store.py`.
- **Security:** the service-role key **bypasses RLS** — every query MUST explicitly filter by `client_bot_id`/`client_slug`/`workspace_slug`; never trust RLS for isolation. `submitted_by_partner_id` is passed in already-trust-derived (G3 upstream) — persist it, never read partner from the body. Bot tokens are env-var *names* (`bot_token_env_name`) — resolve via `os.environ`, never store/log the token.
- **QA:** every adapter unit-tested with a fake transport asserting method+path+payload; plus one live read-only smoke (registry returns `[]` against empty table — proves query shape + connectivity).
- **Devil's advocate:** column drift between SPEC.md and live — bind to the **live** columns (verified below), not the spec doc.
- **PM:** highest-leverage, lowest-risk half of PR7; unblocks everything except the messaging plane.

## 8. Judge challenge
Slice score **88/100 → APPROVE BUILD** (evidence 24, problem 18, reuse 14, security 13, UX 6, testability 9, cost 4). Above the 85 bar because: no client contact, no provisioning dependency, schema verified live, fully unit-testable. (Full PR7 scored 78 only because of the Telegram/provisioning risk — excluded here.)

## 9. Proposed solution (column maps — live-verified)
- **IntakeBotRegistry** → `GET /intake_client_bots?status=eq.active&select=…`; map `id→bot_id`, `kind='client_intake'` (constant), `partner_id`, `workspace_slug`, `authorized_chat_ids`, `bot_username`; `partner_telegram_user_id=None` (not a column).
- **ThreadStore.get_thread_for_chat** → `GET /intake_threads?client_bot_id=eq.&chat_id=eq.&select=…` → `ThreadState(thread_id=id, project_id, margot_state, project_status=status, last_inbound_at=last_message_at, …)`. **upsert_thread** → POST/PATCH `intake_threads` (id, client_bot_id, client_slug, chat_id, status, margot_state, board_rounds, project_id, workspace_slug, last_message_at).
- **ProjectStore.list_open_projects** → `GET /intake_projects?workspace_slug=eq.&status=eq.open&select=id,name,slug,owner_partner_id,status`. **create_project**/**rename_project** → POST/PATCH `intake_projects`.
- **MessagePersister.record_inbound/outbound** → POST `intake_messages` (id, thread_id, client_slug, workspace_slug, direction, author, body, telegram_message_id, telegram_update_id, submitted_by_partner_id). Inbound idempotent on `telegram_update_id`.
- **PendingRoundSource** → `GET /intake_board_rounds?status=in.(requested,deliberating)&select=…`; join `intake_threads`→`intake_projects` for `ProjectContext`; `requesting_partner_id` = latest inbound `intake_messages.submitted_by_partner_id` for the thread, fallback `intake_projects.owner_partner_id`; reconstruct `SPMBrief` from `spm_brief` JSONB.
- **RoundUpdater.mark_replied** → PATCH `intake_board_rounds` set `status='replied', aggregated_reply, minutes_path?, completed_at=now`; **mark_failed** → `status='failed', completed_at`.

## 10. UX requirements
None user-facing this slice (data plane). The reply text path lands when the Telegram slice ships.

## 11. Technical requirements
- All adapters take an injected `sb_request` (default `_pi_ceo_sb_request`); ids via injected factory.
- Reconstruct frozen dataclasses (`ProjectContext`, `SPMBrief`, `ThreadState`, `ProjectSummary`, `IntakeBot`) exactly.
- `Prefer: return=minimal` on writes; idempotent inbound on `telegram_update_id`.
- No 3.12-only syntax (CI runs 3.11); ruff-clean.

## 12. Security / privacy
- **Explicit tenant scoping on every query** (service-role bypasses RLS) — filter by `client_bot_id`/`client_slug`/`workspace_slug`.
- **G3**: persist `submitted_by_partner_id` as given (trust-derived upstream); never parse partner identity from message body.
- **Tokens**: resolve `bot_token_env_name` via env at use-time only; never persist/log token values.

## 13. Verification plan
- `python3.13 -m pytest swarm/intake/tests/test_stores.py -q` (and reply-tick source/updater tests) → all pass.
- CI-parity: `/tmp/ci-venv` (3.11 + `app/requirements.txt`) `pytest swarm/` → green; `py_compile` on 3.11; ruff clean.
- Live read-only smoke: registry against Pi CEO returns `[]` (0 bots) without error — proves connectivity + query shape. No writes against live.

## 14. Loop / stress testing
- Duplicate `telegram_update_id` inbound → single row (idempotent).
- Round `UNIQUE(thread_id, round_number)` respected by updater.
- Tenant-scoping test: a query without the client filter is a test failure (assert the filter is always present).

## 15. Acceptance criteria
1. Each Protocol has a concrete Supabase adapter satisfying its exact signature.
2. Column maps match the live schema (per §9); frozen dataclasses reconstructed correctly.
3. Every read/write is explicitly tenant-scoped; G3 honored; tokens never persisted/logged.
4. Unit tests (fake transport) + one live read-only smoke pass; full `swarm/` green in CI-venv.
5. `_build_default_providers` remains `raise` (Telegram providers still absent) — documented, not silently half-wired.

## 16. Goal command
`/goal Implement Supabase-backed CIP adapters — IntakeBotRegistry, ThreadStore, ProjectStore, MessagePersister, and the BoardReplyTick PendingRoundSource + RoundUpdater — each satisfying its Protocol against the live Pi CEO columns, transport-injected (default _pi_ceo_sb_request), explicitly tenant-scoped (service-role bypasses RLS), G3-safe, with unit tests (fake transport) and a read-only live registry smoke; until pytest swarm/ is green in the CI-venv (3.11) and ruff is clean. Do NOT build TelegramPoller/ReplyDelivery or wire _build_default_providers.`

## 17. Implementation sequence
1. `stores.py` with the 4 run_once data-plane adapters (TDD per adapter).
2. Reply-tick `PendingRoundSource` + `RoundUpdater` (TDD; extend `round_store.py` or new `round_query.py`).
3. Read-only live registry smoke script.
4. CI-venv full `swarm/` run + ruff + 3.11 compile.
5. Branch `feat/cip-supabase-adapters`, PR, poll CI green.

## 18. Session-handoff seed
- Three pipeline units merged (forwarder/round-store/reply-tick) on `main`; this slice adds their Supabase data plane. Telegram plane + `_build_default_providers` wiring deferred (need provisioned bots + own `/judge`).
- Live truth: tables exist in Pi CEO `zbryrmxmgfmslqzizsto`; 0 bots/threads/projects, 3 partners. Column maps in §9.
- First build command: §16.

## 19. Final recommendation
**APPROVE BUILD** for this slice. It's the de-risked half of PR7 the Judge endorsed: schema-verified, no client contact, no provisioning dependency, fully testable. Build it; hold the Telegram plane for a separate `/judge` once Duncan/Toby bots are provisioned.

SPM spec complete. Next safe action: run the §16 `/goal` to build the Supabase adapters TDD, or `/judge` the spec first if a second gate is wanted.
