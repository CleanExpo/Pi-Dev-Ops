---
type: spec
created: 2026-05-17
status: approved-pre-implementation
owner: phill-mac
parent_project: plaud-margot-realtime
sub_project_of: 3
implements: sub-project 2 of 3 (meeting follow-through — actions only)
related_specs:
  - 2026-05-17-plaud-brain-ingestion-design.md  (sub-project 1, foundation)
  - TBD  (sub-project 3, live in-meeting display — separate session)
---

# Plaud Actions — meeting follow-through (sub-project 2)

## Context

Sub-project 1 lands every Plaud recording in `~/2nd Brain/2nd Brain/Wiki/plaud/` as a markdown page with frontmatter, AI summary, and full transcript. Sub-project 2 turns those pages into actionable Linear tickets in the right portfolio project, with one Telegram digest per cron batch.

Scope is deliberately narrow: **actions only**. No meeting-vs-voicenote classifier, no follow-up email drafts, no Unite-Group CRM writes, no Slack (there is none — Telegram only). Substrate corrections from user 2026-05-17: HubSpot does not exist; Unite-Group CRM is the in-house product (future expansion path, not v1).

## Decisions (locked in brainstorm)

| Decision | Choice |
|---|---|
| V1 scope | Actions only → Linear tickets. No emails, no classifier, no UG CRM. |
| Linear routing | LLM-classified per recording, mapped via `.harness/projects.json` portfolio registry. Falls back to Pi-Dev-Ops project when LLM picks `unknown` or low-confidence. |
| HITL gate | Auto-file. Single Telegram digest per cron batch listing all tickets created. User deletes bad tickets manually in Linear UI. |
| Trigger | Inline with sub-project 1's 5-min cron (Approach A from brainstorm). One substrate, one state file, one digest DM. |
| LLM model | `claude-haiku-4-5` via direct HTTPS POST to `api.anthropic.com/v1/messages`. No `anthropic` Python SDK dependency — consistent with Linear/Telegram stdlib-urllib pattern already in the repo. |
| Linear API | Reuse the proven `linear_create_issue` pattern from `scripts/process_ideas_inbox.py:49-93`. Extract into a shared helper, extend to accept `team_id` + `project_id` per call. |

## Architecture

```
Plaud cloud
   │
   ▼  (sub-project 1 — unchanged)
Hermes cron */5 * * * *  →  plaud_ingest.py
   │
   ▼  (for each new recording, after write_page())
plaud_actions.process(plaud_id, page_path, file_meta, batch_results)
   ├─ skip if page frontmatter already has `tickets:` (idempotent)
   ├─ skip if state.action_status_by_id[plaud_id].attempts ≥ 3 (poison-pill guard)
   ├─ skip if env PLAUD_ACTIONS_ENABLED=0 (kill switch)
   │
   ├─ extract_actions(page_md) → Anthropic Haiku 4.5 (HTTPS POST)
   │     → ActionExtraction(portfolio, confidence, reasoning, actions[])
   │
   ├─ resolve_linear_route(portfolio) → (team_id, project_id)
   │     ↳ reads .harness/projects.json (11 portfolio entries)
   │     ↳ falls back to Pi-Dev-Ops if portfolio unknown
   │
   ├─ create_linear_tickets(actions, team_id, project_id, wiki_link)
   │     → list[TicketRef(id, identifier, url)]
   │     ↳ POSTs to Linear GraphQL; each ticket body ends with wiki backlink
   │
   ├─ rewrite wiki page frontmatter:
   │     tickets: [CCW-247, CCW-248, CCW-249]
   │     action_portfolio: ccw
   │     action_status: ok  (or partial / parse_failed / etc.)
   │
   └─ append to batch_results
   ▼
After plaud_ingest's for-loop:
plaud_actions.send_batch_digest(cfg, batch_results)
   ↳ Skips if no actions filed across the whole batch (silent run)
   ↳ Otherwise: ONE Telegram DM via existing notify_margot()
```

## Components

### 1. `scripts/plaud_actions.py` (new, ~250 lines)

Public entry points:

- `async def process(plaud_id, page_path, file_meta, batch_results, cfg) -> None` — called by `plaud_ingest._ingest_one` after a successful `write_page()`. Mutates `batch_results` in place. Wrapped by caller in try/except; never raises.
- `def send_batch_digest(cfg, batch_results) -> None` — called by `plaud_ingest.run_once` after the for-loop. Builds and sends ONE Telegram digest. Silent when no tickets filed.

Pure functions (testable without I/O):

- `extract_actions(page_md, anthropic_api_key) -> ActionExtraction | None` — single HTTPS call to Anthropic Messages API with Haiku 4.5 + tool-use structured output. Returns None on parse / API failure (caller decides what to do).
- `resolve_linear_route(portfolio: str, projects_json_path: Path) -> LinearRoute` — returns a named-tuple `LinearRoute(team_id: str, project_id: str, status: str)` where `status` ∈ `"matched" | "fallback_unknown" | "fallback_low_confidence"`. Named-tuple keeps test assertions on `route.team_id` and `route.status` readable.
- `create_linear_tickets(actions, team_id, project_id, wiki_link, linear_api_key) -> list[TicketRef]` — extends `linear_create_issue` pattern. Returns one `TicketRef` per successful ticket; partial-success surfaces via `len(returned) < len(actions)`.
- `build_digest_text(batch_results) -> str | None` — returns None if zero tickets across whole batch.
- `rewrite_frontmatter(page_path, updates: dict) -> None` — reads existing markdown, updates frontmatter block in place, writes atomically (tmp + rename).

Dataclasses:

```python
@dataclass
class Action:
    title: str           # imperative, ≤80 chars (truncated by create_linear_tickets)
    description: str     # 1-3 sentences; the wiki backlink suffix is appended by
                         # create_linear_tickets, NOT here, so this stays the raw LLM output
    priority: int        # Linear scale: 1=urgent, 2=high, 3=normal, 4=low; default 3

@dataclass
class ActionExtraction:
    portfolio: str       # one of the projects.json `id` values, or "unknown"
    confidence: float    # LLM self-reported, 0.0-1.0
    reasoning: str       # one-line rationale (logged, NOT sent to Linear)
    actions: list[Action]

@dataclass
class TicketRef:
    id: str              # Linear internal UUID
    identifier: str      # e.g. "CCW-247"
    url: str             # https://linear.app/...

@dataclass
class BatchResult:
    plaud_id: str
    title: str
    wiki_path: str       # relative to wiki root, e.g. "plaud/2026-05-17-acme-q2-pricing"
    portfolio: str
    tickets: list[TicketRef]
    status: str          # "ok" | "partial" | "no_actions" | "parse_failed" | "skipped"
```

### 2. `scripts/prompts/action_extraction.md` (new, ~80 lines)

Version-controlled prompt template. Loaded at module import via `Path(__file__).parent / "prompts" / "action_extraction.md"`.

Structure:

- System framing: who the LLM is acting as ("action-extraction analyst for Phill McGurk's portfolio")
- Portfolio enum: lists exactly the 11 `id` values from `.harness/projects.json` plus `"unknown"`
- 3 few-shot examples:
  - Real meeting → 3 actions, clear portfolio (ccw)
  - Voice memo / thinking out loud → 0 actions, portfolio guess
  - Mixed call covering multiple businesses → routes to most-discussed portfolio with reasoning
- Output schema: single JSON object matching `ActionExtraction`. Forced via Anthropic tool-use API.

### 3. Integration changes to `scripts/plaud_ingest.py` (~30 lines added)

**Three edits, all surgical:**

1. After `write_page()` returns in `_ingest_one`, before `append_log_line`:
   ```python
   if os.environ.get("PLAUD_ACTIONS_ENABLED", "1") != "0":
       try:
           await plaud_actions.process(plaud_id, written[0], file_meta, batch_results, cfg)
       except Exception as e:
           log.warning("plaud_actions.process failed for %s: %s", plaud_id, e)
   ```

2. New `batch_results: list[BatchResult]` accumulator declared at top of `run_once`, passed into `_ingest_one`.

3. After the for-loop and `regenerate_plaud_index(...)`:
   ```python
   try:
       plaud_actions.send_batch_digest(cfg, batch_results)
   except Exception as e:
       log.warning("send_batch_digest failed: %s", e)
   ```

Result dict gains two new fields: `"tickets_created": int`, `"portfolios_touched": list[str]`.

### 4. State file additions (`~/.hermes/plaud-state.json`)

Three new fields (none breaks existing parsers):

```json
{
  "...": "existing fields from sub-project 1",
  "actions_filed_today": 0,
  "anthropic_consecutive_failures": 0,
  "linear_consecutive_failures": 0,
  "action_status_by_id": {
    "5d65cb...": {"status": "parse_failed", "attempts": 3, "last_error": "...", "last_attempted": "2026-05-17T..."}
  }
}
```

`action_status_by_id` is LRU-capped at 100 entries. Daily counters reset at local midnight on first run of the new day (cheap inline check).

### 5. Env vars (added to `~/.hermes/.env`)

- `ANTHROPIC_API_KEY` — **already present**, just consumed here. Verified during discovery pass.
- `PLAUD_ACTIONS_ENABLED` — new. Default `1`. Set to `0` to disable action processing without touching ingest.

### 6. Test files

- `tests/test_plaud_actions.py` (~280 lines, ~21 tests) — unit tests with mocked Anthropic + Linear HTTP responses.
- `tests/test_plaud_actions_live.py` (~50 lines) — opt-in via `RUN_PLAUD_LIVE=1`. One real Anthropic call against a hand-crafted test page (NOT a real Plaud page from the account); one real Linear ticket created in a designated "Plaud Test" Linear project on the RA team. Ticket is NOT archived (no archive support in `linear_tools.py` and adding it is out of scope) — user clears manually periodically.

## Data flow

```
09:14:00  User stops Plaud recording on NotePin
09:14-09:20  NotePin → phone → Plaud cloud (transcription + summary, async)
09:25:00  Hermes cron fires plaud_ingest.py
            ├─ list_files → 1 new ID (5d65cb...)
            ├─ get_note → AI summary present
            ├─ get_transcript → segments present
            ├─ write_page → wiki/plaud/2026-05-17-acme-q2-pricing.md
            ├─ plaud_actions.process(...)
            │   ├─ read page markdown (summary + transcript)
            │   ├─ extract_actions → Anthropic Haiku 4.5 HTTPS POST (~1.5s, ~$0.002)
            │   │     → ActionExtraction(portfolio="ccw-crm", confidence=0.92,
            │   │                        reasoning="Mentions CCW, Toby, inventory sync",
            │   │                        actions=[Action × 3])
            │   ├─ resolve_linear_route("ccw-crm") → (UNI team, CCW-ERP/CRM project)
            │   ├─ create_linear_tickets → 3 × Linear GraphQL POST
            │   │     → [TicketRef("CCW-247", ...), ("CCW-248", ...), ("CCW-249", ...)]
            │   ├─ rewrite_frontmatter — adds tickets / action_portfolio / action_status: ok
            │   └─ batch_results.append(BatchResult(...))
            ├─ append_log_line — single line per ticket batch:
            │     "2026-05-17T09:25 | plaud-actions | plaud/2026-05-17-acme-q2-pricing.md
            │      | filed 3 tickets to ccw-crm (CCW-247, CCW-248, CCW-249)"
            ├─ regenerate plaud/_index.md
            ├─ sync_wiki_to_supabase.py
            └─ state file advanced (+actions_filed_today += 3)
09:25:09  send_batch_digest → ONE Telegram DM:
            "📼 Processed 1 Plaud recording (5m12s):
             • Acme Q2 Pricing → CCW (3 tickets)
                 • CCW-247  Follow up with Toby on pricing tier  [HIGH]
                 • CCW-248  Update CCW Linear with Q2 commit numbers
                 • CCW-249  Schedule next CCW review for week of 26 May  [LOW]
             📄 wiki: plaud/2026-05-17-acme-q2-pricing"
```

**Wiki page after action processing** — additional frontmatter:
```yaml
---
type: plaud-recording
plaud_id: 5d65cb...
recorded_at: 2026-05-17T...
duration_ms: 312000
duration_human: 5m12s
source: plaud-notepin-s
ingested_at: 2026-05-17T...
tags: []
tickets: [CCW-247, CCW-248, CCW-249]   # ← new
action_portfolio: ccw-crm               # ← new
action_status: ok                       # ← new ("ok" | "partial" | "parse_failed")
---

# Acme Q2 Pricing — 2026-05-17

[unchanged body]
```

**Idempotency.** The `tickets:` frontmatter field is the durable marker. On every cron tick, `plaud_actions.process` reads the page first; if `tickets:` exists, returns immediately. State file `action_status_by_id` is a *poison-pill* guard for repeated parse failures, NOT the primary dedup key.

**Mixed-batch digest example** (3 recordings processed in one tick):
```
📼 Processed 3 Plaud recordings:
• Acme Q2 Pricing → CCW (3 tickets) [CCW-247 / -248 / -249]
• Synthex brainstorm → Synthex (1 ticket) [SYN-712]
• Voice memo (1m4s) → no actions extracted
📄 wikis: plaud/2026-05-17-acme-q2-pricing · plaud/2026-05-17-synthex-brainstorm · plaud/2026-05-17-voice-memo
```

**Zero-actions batch:** silent. No digest DM. Wiki pages still land normally.

## Error model

| Failure | Detection | Response |
|---|---|---|
| `ANTHROPIC_API_KEY` missing | env var unset | DM Margot once: "⚠️ Anthropic key missing — Plaud actions paused". Skip all processing. Ingest unaffected. |
| Anthropic 401 | HTTP 401 | Same as missing key: one DM, skip. Increment `anthropic_consecutive_failures`. |
| Anthropic 429 (rate limit) | HTTP 429 | Sleep 30s, retry once. Still failing → log WARN, skip this recording, no DM. Next 5-min tick retries. |
| Anthropic 5xx | HTTP 5xx | Retry once after 10s. Still failing → skip recording, no DM. |
| LLM returns invalid JSON | `json.JSONDecodeError` after extracting tool-use response | Log WARN with first 500 chars of raw response. Skip recording. Increment `action_status_by_id[plaud_id].attempts`. After 3 attempts → write `action_status: parse_failed` to frontmatter; stop retrying that recording. Surface in digest: "⚠️ {N} recordings have ambiguous content — manual triage needed". |
| LLM returns `portfolio: "unknown"` OR `confidence < 0.5` | structured-output check | Route to Pi-Dev-Ops project. Prefix ticket title with `[low-confidence]`. Still files. Digest shows "→ Pi-Dev-Ops (uncertain)". |
| Linear 401 (key revoked) | HTTP 401 | DM Margot once. Skip recording — no `tickets:` frontmatter → retried after key rotation. Increment `linear_consecutive_failures`. |
| Linear 5xx / network | HTTP non-2xx other than 401 | Retry once after 30s. Still failing → skip recording. After 6 consecutive Linear failures, one-time DM (mirrors Plaud-unreachable from sub-project 1). |
| Partial ticket creation (3 of 5 succeed) | Tracked per-action | Frontmatter `tickets:` lists ONLY succeeded IDs; `action_status: partial`. Digest line: "→ CCW (3 of 5 tickets — 2 retries pending)". Next tick re-runs ONLY the missing actions (compares frontmatter ticket count vs LLM-extracted count). |
| `.harness/projects.json` missing | `FileNotFoundError` | Log ERROR. Skip all action processing for the batch. DM once. Ingest unaffected. |
| Telegram digest fails | HTTP error from Bot API | Already handled by `notify_margot` (logs WARN, swallows). Tickets are filed regardless. |

### What we DON'T handle (by design)

- Duplicate tickets across machines — single-Hermes assumption (same as sub-project 1)
- Recording-content dedup — if you record the same idea twice, you get two ticket batches
- Retroactive re-processing on prompt update — manual: clear `tickets:` field from a wiki page → next tick re-runs it
- LLM priority calibration — accept the model's 1-4 choice, fix in Linear UI

### Kill switch

`PLAUD_ACTIONS_ENABLED=0` in `~/.hermes/.env` → `plaud_actions.process` is a no-op. Ingest continues, wiki pages still land, NO Linear tickets, NO digest. Useful for halting action filing during prompt iteration.

## Testing

### Unit tests — `tests/test_plaud_actions.py` (~21 tests)

| Test | What it locks in |
|---|---|
| `test_extract_actions_meeting_yields_actions` | Real-shaped page → mocked Anthropic → 3 actions parsed cleanly |
| `test_extract_actions_voice_memo_zero_actions` | Stream-of-consciousness → mocked Anthropic returns `actions: []` → no tickets attempted |
| `test_extract_actions_invalid_json_returns_none` | Garbage response → `None` returned, WARN logged |
| `test_extract_actions_low_confidence_routes_unknown` | `confidence: 0.3, portfolio: "unknown"` → falls back to Pi-Dev-Ops, title prefixed `[low-confidence]` |
| `test_resolve_linear_route_known_portfolio` | `resolve_linear_route("ccw-crm")` → UNI team + CCW-ERP/CRM project IDs |
| `test_resolve_linear_route_unknown_falls_back_to_pi_dev_ops` | `resolve_linear_route("unknown")` → RA team + Pi-Dev-Ops project, status=`fallback_unknown` |
| `test_resolve_linear_route_missing_projects_json_raises` | Path doesn't exist → `FileNotFoundError` bubbles |
| `test_create_linear_tickets_happy_path` | 3 mocked successes → 3 `TicketRef` returned |
| `test_create_linear_tickets_partial_failure` | 2nd of 3 raises 500 → 2 `TicketRef` returned |
| `test_create_linear_tickets_includes_wiki_backlink` | Inspect mocked body → contains `Source: [{slug}](wiki link)` |
| `test_process_skips_pages_with_existing_tickets` | Frontmatter has `tickets:` → no Anthropic call made |
| `test_process_writes_tickets_to_frontmatter` | After success → page rewritten with tickets/portfolio/status fields |
| `test_process_partial_success_marks_action_status` | Partial Linear → frontmatter `action_status: partial` + only succeeded IDs |
| `test_process_records_attempt_count_in_state` | After 3 consecutive JSON parse failures for same `plaud_id` → `action_status_by_id` stores attempts=3 |
| `test_process_skips_after_parse_failed_threshold` | State has `attempts: 3` → skip entirely, no Anthropic call |
| `test_process_respects_kill_switch` | `PLAUD_ACTIONS_ENABLED=0` → no-op |
| `test_build_digest_single_batch` | 1 recording, 3 tickets → digest string matches expected format |
| `test_build_digest_mixed_batch` | 3 recordings (2 with actions, 1 without) → all 3 listed, no-action marked |
| `test_build_digest_all_zero_actions_returns_none` | All zero → `build_digest_text` returns None |
| `test_anthropic_auth_error_dms_once` | First AuthError → DM fires. Second consecutive → no DM. |
| `test_anthropic_rate_limit_retries_then_skips` | First 429, second succeeds → returns actions. Both 429 → returns None. |

Anthropic + Linear HTTP layers both stubbed via `unittest.mock.patch` on `urllib.request.urlopen`. Same pattern as sub-project 1's `test_notify_margot_*`. Target: full suite under 5 seconds.

### Integration test — `tests/test_plaud_actions_live.py` (opt-in)

Gated by `RUN_PLAUD_LIVE=1`. Runs once against:
- Real Anthropic API — one Haiku 4.5 call against a hand-crafted test page (verbatim string inside the test, NOT a Plaud page from the account)
- Real Linear GraphQL — files ONE ticket to the dedicated "Plaud Actions Test" project (user creates this on the RA team during rollout). Ticket is NOT auto-archived — user clears periodically.

Asserts:
1. Anthropic returns valid JSON matching `ActionExtraction` schema
2. Linear `issueCreate` returns a real ticket identifier
3. Wiki frontmatter rewrite is idempotent (running twice on the same `(temp_page, mocked_actions)` produces identical output)

### Manual acceptance — 3 checks on first deploy

1. **Record a meeting-style 60-sec test note** ("Sarah and I need to update CCW pricing by Friday and follow up with Toby on the inventory sync") → wait 10 min → confirm:
   - Wiki page has `tickets: [...]` and `action_portfolio: ccw-crm` in frontmatter
   - 2 Linear tickets exist in the CCW-ERP/CRM project with wiki backlinks
   - Telegram digest DM received (after you've `/start`ed PiMargot_bot)

2. **Record a stream-of-consciousness voice memo** ("just thinking about how to position Synthex…") → wait 10 min → confirm:
   - Wiki page exists, no `tickets:` field
   - No Linear tickets, no digest DM

3. **Toggle the kill switch.** `PLAUD_ACTIONS_ENABLED=0`, record another meeting → wait 10 min → confirm:
   - Wiki page lands, no `tickets:` field
   - No Linear tickets, no digest
   - Re-enable + kickstart → tickets land on next run

### Deliberately skipped

- Prompt regression suite (no golden files; quality validated by manual acceptance)
- Load tests (5-min cron throughput is well within rate limits)
- Auto-archive of test Linear tickets (no support in `linear_tools.py`; manual cleanup is fine)
- End-to-end test that runs real Plaud + Anthropic + Linear (too many moving parts; decompose into the two live tests)

## Rollout — one-time steps

1. Verify `ANTHROPIC_API_KEY` is set in `~/.hermes/.env`. (Already present per discovery.)
2. Create a new Linear project called "Plaud Actions Test" on the RA team. Note its project_id. Set env `PLAUD_LIVE_TEST_PROJECT_ID=<uuid>` if you want to run the live test; otherwise skip.
3. Write `scripts/plaud_actions.py`, `scripts/prompts/action_extraction.md`, and the two test files.
4. Patch `scripts/plaud_ingest.py` (three edits per Components §3).
5. Add `PLAUD_ACTIONS_ENABLED=1` line to `~/.hermes/.env` (optional — default-on if absent).
6. Reload LaunchAgent: `launchctl bootout gui/501/com.phillmcgurk.plaud-ingest && launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.phillmcgurk.plaud-ingest.plist`
7. `launchctl kickstart -k gui/501/com.phillmcgurk.plaud-ingest` to force an immediate run.
8. Inspect `~/.hermes/logs/plaud-ingest.log` for `plaud-actions` lines.
9. Once Plaud finishes processing your existing 2 deferred recordings, expect the first real digest DM.

## Privacy

Sub-project 2 inherits all sub-project 1 privacy notes plus:

- **Action items go to Linear**, which is visible to anyone on your Linear workspace. Don't ingest recordings containing sensitive personal/legal content if Linear access can't see them.
- **The Anthropic API call sends summary + transcript** to Anthropic for processing. Standard Anthropic data-handling applies (per their privacy policy + your existing API contract). No new exposure beyond what your existing TAO/Margot use already does.
- **LLM reasoning is logged** (`reasoning` field in `ActionExtraction`) in `~/.hermes/logs/plaud-ingest.log` for debugging but is NOT included in Linear ticket bodies.
- **Kill switch** (`PLAUD_ACTIONS_ENABLED=0`) halts action processing without disabling ingest, useful if you record something sensitive and want it in the wiki but NOT in Linear.

## Acceptance criteria

v1 is done when:

1. A Plaud recording with clear action items lands in `wiki/plaud/` AND the corresponding tickets appear in the right Linear portfolio project within 10 minutes.
2. The wiki page frontmatter is rewritten with `tickets:`, `action_portfolio:`, `action_status:` after successful ticket creation.
3. A voice memo with no actions lands in the wiki and produces NO Linear tickets and NO digest DM.
4. The Telegram digest DM (when PiMargot_bot is started) lists all tickets created in a cron batch with title, portfolio, ticket IDs, priorities, and wiki backlinks.
5. Re-running `plaud_ingest.py` on an already-processed wiki page is a no-op (no Anthropic call, no Linear call, no duplicate tickets).
6. After 3 consecutive JSON parse failures for the same recording, the ingester stops retrying that recording and marks it `action_status: parse_failed`.
7. `PLAUD_ACTIONS_ENABLED=0` disables action processing entirely — wiki ingest continues unaffected.
8. Anthropic auth failure path: DMs once, then silent until status transitions back to OK.
9. Linear partial-success path: only succeeded ticket IDs land in frontmatter; next tick re-attempts only the missing actions.

## Out of scope for v1

- Meeting-vs-voicenote classification (irrelevant when scope is "actions only")
- Follow-up email drafts
- Unite-Group CRM writes (own product, future expansion)
- HubSpot (does not exist in the empire)
- Slack (does not exist; Telegram is the channel)
- Sub-project 3 (live in-meeting visual display) — separate spec
- Prompt regression suite (manual acceptance tests are sufficient at this scale)
- Auto-archive of test Linear tickets (no support in linear_tools.py; manual cleanup)
- Retroactive re-processing on prompt change (manual: clear `tickets:` from frontmatter)
- LLM priority recalibration (accept model's 1-4 choice)
