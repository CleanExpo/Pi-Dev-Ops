# Client Intake Pipeline — Telegram → Margot → SPM → Board → Production

> **Status:** SPEC draft 2026-05-26. Phill reviewed + locked architecture decisions 2026-05-26. Implementation underway.

## Locked decisions (2026-05-26)

| Decision | Pick |
|---|---|
| Stack | Python in Pi-CEO (n8n rejected) |
| Repo strategy | One main repo per client (`intake_client_bots.github_repo`). Production handoffs create feature branches + PRs INTO that repo — not new repos per project. |
| Margot voice for clients | Same founder voice as existing `swarm/margot_bot.py` |
| Board round cap | 3 rounds → mandatory human checkpoint |
| Bot token storage (Phase 1 default) | Env vars on Railway; DB stores env-var NAME, not the secret |
>
> **Triggered by:** Phill — "I have 2 clients (Duncan, Toby). Each gets a Telegram bot. Margot pulls their input, passes to that project's Senior Project Manager, who passes to the board for SWOT + suitability + framework, who returns the project outline + questions back to Margot, who relays to the client. Loop until production-ready → generate PR + Linear project."

## 0. Architecture decision (CIP-4): **Python in Pi-CEO**, NOT n8n

| | Python in Pi-CEO | n8n |
|---|---|---|
| Existing inbox pattern | ✅ `swarm/inbox/intake_router.py` already long-polls per-bot Telegram, dedupes, persists offsets | ❌ would need new workflow per bot OR generic router |
| Existing board engine | ✅ `swarm/board.py` + `swarm/bots/board.py` — 9-persona deliberation via ceo-board skill | ❌ would need to shell out to Python anyway |
| Existing Linear writer | ✅ `swarm/linear_tools.py` GraphQL wrapper | ⚠️ n8n Linear node works but limited |
| Existing Margot bot | ✅ `swarm/margot_bot.py` — founder Telegram assistant with board-trigger sentinels | ❌ separate codebase |
| Tenant isolation | ✅ existing `set_app_tenant(slug)` RLS pattern from Pilot V1 | ❌ would need to plumb tenant context through nodes |
| Operational story | Single `python -m swarm.intake.cli` cron entry, one log file, one process | Two systems to monitor + auth + deploy |
| Test surface | pytest with existing fixtures | manual JSON workflow tests |

**Pick: Python in Pi-CEO. n8n would split the codebase across languages with no offsetting gain.** If a Phase 2 visual-debug surface is wanted for non-engineers to inspect a thread, that's a Synthex web view, not n8n.

## 1. Pipeline state machine

```
┌────────────────────────────────────────────────────────────────────────┐
│  Client (Duncan)         Client (Toby)         Client (future N)       │
│       │                       │                       │                │
│       ▼                       ▼                       ▼                │
│  Duncan's Telegram bot   Toby's Telegram bot     Client N's bot        │
│       │                       │                       │                │
│       └───────────┬───────────┴───────────┬───────────┘                │
│                   ▼                                                    │
│       swarm/inbox/intake_router.py — long-poll all client_bots         │
│                   │                                                    │
│                   ▼                                                    │
│       swarm/intake/margot_router.py — route to thread + classify       │
│                   │                                                    │
│       ┌───────────┴───────────┐                                        │
│       ▼                       ▼                                        │
│  new intake_thread       existing intake_thread                        │
│       │                       │                                        │
│       ▼                       ▼                                        │
│       └───────────┬───────────┘                                        │
│                   ▼                                                    │
│       swarm/intake/spm.py — Senior Project Manager                     │
│       — assess: layout / framework / suitability / SWOT                │
│       — generate brief for board                                       │
│                   │                                                    │
│                   ▼                                                    │
│       swarm/board.py — request_deliberation (existing)                 │
│       9-persona debate via ceo-board skill                             │
│                   │                                                    │
│                   ▼                                                    │
│       swarm/intake/spm.py — aggregate board response                   │
│       — produce reply to client                                        │
│       — decide: ready for production? OR more questions?               │
│                   │                                                    │
│       ┌───────────┴───────────┐                                        │
│       ▼                       ▼                                        │
│  more questions          ready for production                          │
│       │                       │                                        │
│       ▼                       ▼                                        │
│  Margot relays via       swarm/intake/handoff.py:                      │
│  client's bot ────loop   1. create GitHub repo + first PR              │
│                          2. create Linear project + intake issue       │
│                          3. notify client "project N is live"          │
│                          4. close intake_thread                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Roles

| Role | Where it lives | Identity / persona |
|---|---|---|
| **Client** | Their own Telegram chat | Human (Duncan, Toby, future) |
| **Per-client bot** | Telegram, registered via BotFather | One bot per client (`@DuncanClientBot`, `@TobyClientBot`) |
| **intake_router** | `swarm/inbox/intake_router.py` (extend existing) | System — fetches messages, persists, dedupes |
| **Margot router** | NEW `swarm/intake/margot_router.py` | LLM — classifies (new vs continuation) + assembles thread context |
| **SPM** | NEW `swarm/intake/spm.py` | LLM persona — Senior Project Manager. Reads thread, produces brief for board. Aggregates board response into client-facing reply. |
| **Board** | `swarm/board.py` (existing) | 9 personas: CEO, Revenue, Product Strategist, Technical Architect, Contrarian, Compounder, Custom Oracle, Market Strategist, Moonshot |
| **Margot relay** | `swarm/intake/margot_router.py` (same module) | LLM — formats SPM's reply for the client's voice, sends via their bot |
| **Production handoff** | NEW `swarm/intake/handoff.py` | System — gh repo create + gh pr create + Linear save_issue + close thread |

### Termination

SPM decides when a thread is "ready for production" by checking a structured field in its assessment:
```json
{ "readyForProduction": true, "rationale": "Scope locked, framework picked, success metrics defined" }
```
Only then does `handoff.py` fire. Otherwise the loop continues with the client's reply.

## 2. Data model

All tables in Pi-CEO Supabase (`zbryrmxmgfmslqzizsto`), RLS-protected, tenant_slug-scoped via existing `set_app_tenant(slug)` function.

### `intake_client_bots` (NEW)
One row per Telegram bot we've provisioned for a client. Replaces/extends the assumed `context_bots` table found in intake_router.py.
```
id                    TEXT PRIMARY KEY (cuid)
client_slug           TEXT NOT NULL  -- 'duncan' | 'toby' | etc
display_name          TEXT NOT NULL  -- 'Duncan Smith — Acme Co'
bot_username          TEXT NOT NULL UNIQUE  -- '@DuncanClientBot'
bot_token_env_name    TEXT NOT NULL  -- 'INTAKE_BOT_TOKEN_DUNCAN' — name of the env var on Railway holding the actual token
linear_team_id        TEXT NOT NULL  -- where Linear issues get created
linear_project_id     TEXT  -- pin to existing project, else null
github_repo           TEXT NOT NULL  -- single main repo for this client, e.g. 'CleanExpo/Duncan-Acme-Co'. Production handoffs branch + PR into this.
authorized_chat_ids   TEXT[]  -- only these Telegram chat ids can use the bot
long_poll_offset      BIGINT NOT NULL DEFAULT 0
greeting_template     TEXT  -- shown on /start
max_board_rounds      INTEGER NOT NULL DEFAULT 3  -- per-thread cap before mandatory human checkpoint
status                TEXT NOT NULL DEFAULT 'active'  -- active | paused | archived
config                JSONB
created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

### `intake_threads` (NEW)
One row per ongoing project conversation.
```
id              TEXT PRIMARY KEY (cuid)
client_bot_id   TEXT NOT NULL REFERENCES intake_client_bots(id) ON DELETE CASCADE
client_slug     TEXT NOT NULL  -- denormalized for RLS
chat_id         TEXT NOT NULL  -- Telegram chat id
title           TEXT  -- SPM-generated short title
status          TEXT NOT NULL DEFAULT 'open'  -- open | in_board | awaiting_client | ready_for_production | shipped | cancelled
spm_assessment  JSONB  -- last SPM brief
board_rounds    INTEGER NOT NULL DEFAULT 0
last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
production_handoff_id TEXT  -- set when handoff completes
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()

INDEX (client_slug, status)
INDEX (chat_id, last_message_at DESC)
```

### `intake_messages` (NEW)
Each message in a thread, both directions.
```
id              TEXT PRIMARY KEY (cuid)
thread_id       TEXT NOT NULL REFERENCES intake_threads(id) ON DELETE CASCADE
client_slug     TEXT NOT NULL  -- denormalized for RLS
direction       TEXT NOT NULL  -- 'inbound' (from client) | 'outbound' (to client)
telegram_message_id BIGINT  -- inbound only
telegram_update_id  BIGINT  -- inbound only, UNIQUE per bot
author          TEXT NOT NULL  -- 'client' | 'margot' | 'spm' | 'board-summary'
body            TEXT NOT NULL
metadata        JSONB  -- e.g. board minute id, SPM assessment id
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()

INDEX (thread_id, created_at)
UNIQUE (client_slug, telegram_update_id) WHERE telegram_update_id IS NOT NULL
```

### `intake_board_rounds` (NEW)
Tracks each board fan-out for a thread (one thread can trigger many rounds).
```
id              TEXT PRIMARY KEY (cuid)
thread_id       TEXT NOT NULL REFERENCES intake_threads(id) ON DELETE CASCADE
client_slug     TEXT NOT NULL  -- denormalized for RLS
round_number    INTEGER NOT NULL
spm_brief       JSONB NOT NULL  -- the brief sent to board
board_session_id TEXT  -- links to existing .harness/board/directives/<session_id>.jsonl
minutes_path    TEXT  -- existing .harness/board-meetings/<date>-<slug>.md
aggregated_reply TEXT  -- SPM's distillation back to client
status          TEXT NOT NULL DEFAULT 'requested'  -- requested | deliberating | aggregated | replied
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
completed_at    TIMESTAMPTZ

UNIQUE (thread_id, round_number)
```

### `intake_production_handoffs` (NEW)
Final exit artifact — what was shipped.
```
id                    TEXT PRIMARY KEY (cuid)
thread_id             TEXT NOT NULL UNIQUE REFERENCES intake_threads(id) ON DELETE CASCADE
client_slug           TEXT NOT NULL
github_repo           TEXT NOT NULL  -- 'CleanExpo/Duncan-Acme-Co' (from intake_client_bots.github_repo)
github_branch         TEXT NOT NULL  -- feat/<project-slug>
github_pr_url         TEXT
linear_team_id        TEXT NOT NULL
linear_project_id     TEXT  -- existing or newly-created
linear_issue_id       TEXT  -- the intake issue
linear_issue_url      TEXT
status                TEXT NOT NULL DEFAULT 'pending'  -- pending | repo_branched | pr_opened | linear_created | notified | complete | failed
error_message         TEXT
shipped_at            TIMESTAMPTZ
created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

All 5 tables ENABLE ROW LEVEL SECURITY with policies that gate on `set_app_tenant(client_slug)` matching `client_slug` column. The bot tokens column gets pgcrypto encryption (sym_encrypt with `app.bot_token_key` GUC).

## 3. Module layout (Python)

```
swarm/intake/
├── SPEC.md (this file)
├── __init__.py
├── cli.py                 # entry point: `python -m swarm.intake.cli run-once`
├── margot_router.py       # NEW — classify message, route to SPM, relay reply
├── spm.py                 # NEW — SPM persona, brief generation, aggregation, ready-check
├── handoff.py             # NEW — production handoff: gh + Linear + close thread
└── tests/
    ├── test_margot_router.py
    ├── test_spm.py
    └── test_handoff.py

swarm/inbox/intake_router.py (EXTEND existing)
  — add: route to margot_router when bot.kind == 'client_intake'

swarm/github_tools.py (NEW)
  — wrap `gh repo create` + `gh pr create` + git subprocess pattern
  — called from handoff.py
```

Cron entry: Hermes cron every 1 min runs `python -m swarm.intake.cli run-once`, which long-polls all `intake_client_bots`, processes any new messages, advances any threads waiting on board response.

## 4. Configuration / Secrets

- `INTAKE_BOT_TOKEN_<CLIENT_SLUG>` — env var per bot, NOT stored encrypted in DB initially (deferred). The DB row stores the env-var NAME, the cron looks up the actual token from env. Cleaner for rotation, no pgcrypto setup needed for Phase 1.
- `INTAKE_GITHUB_TOKEN` — gh CLI uses this for repo/PR creation
- `LINEAR_API_KEY` — already exists in 1Password
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` — already exist (for Margot, SPM, board)
- `app.current_tenant_slug` GUC — set per request via `set_app_tenant(client_slug)`

## 5. Out of scope (Phase 1)

- **Voice messages** — Telegram supports voice; deferred until Pilot V1 voice intake is generalized
- **Photo/video attachments** — Phase 2
- **Multi-language client messages** — assume English; auto-translate is Phase 3
- **Per-client billing / usage caps** — handled at Synthex tier level later
- **Web admin UI** to inspect threads — for now use Linear + .harness/ files
- **HITL gate on Margot relay** — Margot already bypasses draft_review per `margot_bot.py` design; client-facing replies go direct (with structured prompts to keep her on-brand)
- **n8n** — explicitly rejected; see §0

## 6. Acceptance criteria (MVP — Phase 1)

- [ ] SQL migration applied to Pi-CEO Supabase, all 5 tables verified with RLS + policies
- [ ] One `intake_client_bots` row exists for Duncan + one for Toby
- [ ] Each client can send a message to their bot and see a Margot acknowledgement reply within 1 cron tick
- [ ] SPM generates a brief and triggers a board round; minutes file appears in `.harness/board-meetings/`
- [ ] Board's aggregated reply is relayed to the client via their bot
- [ ] Client reply continues the thread (round 2, round 3, etc.)
- [ ] When SPM marks `readyForProduction: true`, `handoff.py` creates a GitHub repo + first PR + Linear project + "project live" message to client
- [ ] `intake_threads.status` correctly transitions: open → in_board → awaiting_client → ready_for_production → shipped
- [ ] All operations tenant-scoped — Duncan never sees Toby's thread, Linear ticket, or repo
- [ ] Pytest covers all 4 new modules with >80% line coverage on the happy path + cancel path
- [ ] `unite-group-ci-recovery` skill conventions followed on every PR (feature/agent-* branch + metadata block)

## 7. Implementation PR series (Phase 1)

1. **CIP-PR1** — SQL migration: 5 tables + RLS policies + indexes
2. **CIP-PR2** — `swarm/intake/spm.py` + tests (pure logic, no I/O)
3. **CIP-PR3** — `swarm/intake/margot_router.py` + tests (depends on PR2)
4. **CIP-PR4** — `swarm/intake/handoff.py` + `swarm/github_tools.py` + tests
5. **CIP-PR5** — extend `swarm/inbox/intake_router.py` to dispatch to margot_router for `kind='client_intake'` bots
6. **CIP-PR6** — `swarm/intake/cli.py` + Hermes cron entry
7. **CIP-PR7** — Provision Duncan + Toby bots: BotFather, env vars on Railway, seed rows in `intake_client_bots`

Each PR follows skill conventions; series can be merged sequentially or some in parallel (1+2 together, 3+5 together, 4 standalone, 6 last, 7 ops-only).

## 8. Risks + open questions

| Risk | Mitigation |
|---|---|
| LLM cost per board round (9 personas × verbose context) could spiral | Cap at 3 rounds per thread before mandatory human checkpoint; track in `intake_threads.board_rounds` |
| Client says something prompt-injection-shaped to their bot | Treat all client input as untrusted; sanitize before passing to SPM; never let client message change tenant slug or invoke other bots |
| Duncan's bot accidentally exposes Toby's data | RLS plus authorized_chat_ids whitelist (Telegram chat must be in list to be processed) |
| Margot misroutes reply to wrong bot | Bot id is threaded through every state machine step; reply uses `intake_threads.client_bot_id`, not message-derived |
| Production handoff creates a half-failed state (repo created, PR fails) | `handoff.py` is idempotent + transactional: each step writes a sub-status; partial failures are visible in `intake_production_handoffs` and can be resumed |
| Race between cron ticks processing same message | UNIQUE constraint on `(client_slug, telegram_update_id)` + per-bot advisory lock on long_poll_offset update |

**Open for Phill (before implementation starts):**
1. Confirm Python-in-Pi-CEO over n8n (per §0)
2. Confirm Phase 1 scope cap at 3 board rounds before human checkpoint
3. Confirm `intake_production_handoffs` triggers a new GitHub *repo* (CleanExpo/duncan-<slug>) — or just a new branch on an existing client repo?
4. Confirm Margot's voice for client-facing replies — same as current founder voice, or a more formal "Project Manager" tone?
5. Bot token storage — env-var-name-in-DB (Phase 1 default) or pgcrypto in-DB (more secure, more setup)?

---

**Next step:** Phill reviews this SPEC + answers §8 open questions → I open CIP-PR1 (SQL migration).
