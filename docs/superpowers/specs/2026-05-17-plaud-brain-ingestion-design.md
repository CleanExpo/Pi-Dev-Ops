---
type: spec
created: 2026-05-17
status: approved-pre-implementation
owner: phill-mac
parent_project: plaud-margot-realtime
sub_project_of: 3
implements: sub-project 1 of 3 (foundation)
related_specs: TBD (sub-project 2 follow-through, sub-project 3 live-display)
---

# Plaud → Brain ingestion (sub-project 1)

## Context

Plaud NotePin S is now the user's primary capture device. Recordings need to land in the Brain-1 wiki and Margot's Supabase corpus within minutes so Margot can act as a personal assistant on the project in real time. Plaud is record-then-upload (no live stream) and has no webhook — so the integration is polling-based.

This is the foundation. Two later sub-projects build on it:

- **Sub-project 2** — meeting follow-through (classify + extract actions + file to Linear/HubSpot).
- **Sub-project 3** — live in-meeting visual display ("Unite Nexus showcase"), uses a separate browser-based capture path (Plaud is not real-time).

## Decisions (locked in brainstorm)

| Decision | Choice |
|---|---|
| Ingestion scope | Everything, automatic. Plus a manual delete escape hatch. |
| Polling cadence | 5 min cron via Hermes. |
| Wiki organisation | One file per recording at `wiki/plaud/YYYY-MM-DD-{slug}.md`. |
| Page content | Plaud AI summary + full timestamped transcript. Split >50k-char content into `…-part2.md`, `…-part3.md`. |
| Architecture | Wiki-first; reuse existing `sync_wiki_to_supabase.py` (patched to recurse). Plaud MCP stays available for Margot's verbatim drill-down. |

## Architecture

```
Plaud cloud
   │  (Plaud MCP @plaud-ai/mcp@latest, already wired in ~/.hermes/config.yaml)
   ▼
Hermes cron */5 * * * *   →  plaud-ingest.py
   │     - reads ~/.hermes/plaud-state.json (last_seen_id/ts)
   │     - calls Plaud list_files, get_note, get_transcript
   │     - writes wiki/plaud/{date}-{slug}.md (summary + transcript)
   │     - appends wiki/log.md
   │     - regenerates wiki/plaud/_index.md
   │     - kicks sync_wiki_to_supabase.py
   │     - sends Telegram DM to Margot
   ▼
~/2nd Brain/2nd Brain/Wiki/plaud/*.md
   │
   ▼
sync_wiki_to_supabase.py (rglob, not glob)
   │
   ▼
Supabase wiki_pages table  ──►  Margot (ambient context, search)
                           └─►  Plaud MCP on-demand drill-down (verbatim quotes)
```

## Components

### 1. `plaud-ingest.py` (new)
Location: `~/Pi-CEO/Pi-Dev-Ops/scripts/plaud-ingest.py`
Run by: Hermes cron, every 5 min.
Responsibilities:

- Read `~/.hermes/plaud-state.json` (`last_seen_id`, `last_seen_ts`, `last_run_status`, `consecutive_failures`).
- Acquire PID lock at `~/.hermes/plaud-ingest.lock`. Exit cleanly if held by a live process; clear if stale (>15 min, dead PID).
- Call Plaud MCP `list_files(date_from=last_seen_ts.date())`. Iterate result, filter to IDs strictly after `last_seen_ts`.
- For each new ID: `get_note(id)`, `get_transcript(id)`. Compose markdown page.
- Slug: lowercase ASCII-folded name with non-alphanum → `-`. Empty name falls back to `plaud_id`. Collision suffix `-2`, `-3`.
- Write to `~/2nd Brain/2nd Brain/Wiki/plaud/YYYY-MM-DD-{slug}.md`. If content >50k chars, split on transcript-segment boundaries into `…-part2.md`, `…-part3.md`. Each part keeps the same `plaud_id` frontmatter and adds `part: N/M`, `transcript_continues_in: …`.
- Append a line to `~/2nd Brain/2nd Brain/Wiki/log.md`:
  `YYYY-MM-DDTHH:MM | plaud-ingest | plaud/<file> | new recording (<duration>, <chars>)`
- Regenerate `~/2nd Brain/2nd Brain/Wiki/plaud/_index.md` (table of all entries).
- Shell out to `sync_wiki_to_supabase.py` (best effort; failure logs but does not error).
- Send a Telegram DM to Margot via the Bot API: `POST https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN_MARGOT_BOT}/sendMessage` with `chat_id={MARGOT_DM_CHAT_ID}` and `text="📼 New Plaud: {title} ({duration}). I've added it to the brain."`. Env values are read from `~/.hermes/.env`. Bot-API failures are logged but do not fail the run.
- Update state file (`last_seen_id`, `last_seen_ts`, `last_run_status=ok`, `last_error=null`, reset `consecutive_failures`).
- Release lock.

Approximate size: ~150 lines.

CLI flags:

- (no args) — normal run.
- `--backfill SINCE` — one-shot, ignore state file, ingest everything since `SINCE` (ISO date). For initial history seeding only.
- `--dry-run` — log what would be done; no writes.

### 2. `sync_wiki_to_supabase.py` (patch — 2 lines)
Location: `~/Pi-CEO/Pi-Dev-Ops/scripts/sync_wiki_to_supabase.py`
Changes:

- `WIKI_DIR.glob("*.md")` → `WIKI_DIR.rglob("*.md")` (recurse into `plaud/`).
- `page_id = p.stem` → `page_id = str(p.relative_to(WIKI_DIR).with_suffix(""))`. For top-level files this is unchanged (just the stem); for `plaud/2026-05-17-foo.md` it becomes `plaud/2026-05-17-foo` so the directory survives into the Supabase `id` column.

Validation: run the script after patching with one dummy file `plaud/zzz-test.md` already present; confirm a top-level file's id is unchanged and the nested file's id is `plaud/zzz-test`.

### 3. `~/.hermes/cron/plaud-ingest.cron` (new)
Schedule: `*/5 * * * *`.
Command: `python3 ~/Pi-CEO/Pi-Dev-Ops/scripts/plaud-ingest.py >> ~/.hermes/logs/plaud-ingest.log 2>&1`
Log rotation: weekly via existing Hermes logrotate config.

### 4. `wiki/plaud/_index.md` (new, auto-generated)
Table of contents regenerated at end of every ingest run. Columns: date, title, duration, link, tags.

### 5. Margot tool surface (no change)
`@plaud-ai/mcp@latest` is already wired in `~/.hermes/config.yaml`. Margot can call `get_file`, `get_transcript`, `list_files` directly for verbatim drill-down when the wiki page summary is insufficient.

### 6. `delete-plaud-recording.sh` (new)
Location: `~/Pi-CEO/Pi-Dev-Ops/scripts/delete-plaud-recording.sh`
Single arg: wiki page slug OR `plaud_id`.
Actions:

- Resolve slug → wiki file path(s) (handle multi-part files via shared `plaud_id`).
- Delete wiki file(s).
- `DELETE` Supabase `wiki_pages?id=eq.{id}` (via service role key from `~/.hermes/.env`).
- Append to `wiki/log.md`: `… | plaud-delete | <file> | <reason>`.
- Optionally also call Plaud's delete endpoint (if exposed by MCP). v1 leaves the Plaud cloud copy alone unless the user explicitly opts in with `--purge-plaud`.

## Data flow

```
14:32:00  User stops Plaud recording on NotePin S
14:32-14:45  NotePin syncs to phone, phone uploads to Plaud cloud
14:35:00  cron fires → ingester runs → list_files: 0 new → exit
14:40:00  cron fires → ingester runs
            list_files → 1 new ID: abc123
            get_note(abc123) → AI summary markdown
            get_transcript(abc123) → 28 timestamped segments
            slug = "acme-q2-pricing"
            write wiki/plaud/2026-05-17-acme-q2-pricing.md
            append to wiki/log.md
            regenerate wiki/plaud/_index.md
            sync_wiki_to_supabase.py
            Telegram → Margot DM
            state file advanced
14:40:08  Supabase contains the row; Margot's next turn can reference it
```

### Wiki page shape

```markdown
---
type: plaud-recording
plaud_id: abc123
recorded_at: 2026-05-17T14:32:00+10:00
duration_ms: 720000
duration_human: 12m00s
source: plaud-notepin-s
ingested_at: 2026-05-17T14:40:03+10:00
tags: []
---

# Acme Q2 Pricing — 2026-05-17

**Audio:** [presigned URL, expires 24h]
**Duration:** 12m00s

## Summary
{Plaud's AI summary, verbatim, Markdown}

## Action Items
{Plaud's auto-extracted actions from note_list, if present}

## Transcript
[00:00 - 00:05] Speaker 1: …
[00:05 - 00:11] Speaker 2: …
…
```

For multi-part splits, only part 1 carries the summary; transcript splits on segment boundaries. Each part includes `part: N/M` and `transcript_continues_in:` in frontmatter.

### Idempotency

State file `~/.hermes/plaud-state.json` tracks `last_seen_id`. PID lock at `~/.hermes/plaud-ingest.lock` prevents overlapping runs.

## Error model

| Failure | Detection | Response |
|---|---|---|
| Plaud auth expired (401 / "Not authenticated") | MCP exception text | DM Margot once: "Plaud token expired — run `plaud login`". Skip tick. No auto-retry of the browser login flow from cron. |
| Plaud API 500 (transient) | Non-2xx | Retry once after 30s. Still failing → log + skip. Next tick re-tries. |
| Plaud network failure / `fetch failed` / DNS | Exception | Skip tick silently. After 6 consecutive failures (~30 min) DM Margot once. |
| Wiki file slug collision | `os.path.exists` | Append `-2`, `-3` to slug. `plaud_id` in frontmatter is the real key. |
| Content >50k chars | Length check | Split on transcript-segment boundary into `…-part2.md`, `…-part3.md`. |
| `sync_wiki_to_supabase.py` fails | Non-zero subprocess exit | Wiki file is the source of truth; state advances. Hourly full-sync (existing) will reconcile. Log warning, no DM. |
| Two cron ticks overlap | PID lock file | Second tick exits cleanly; logs "previous run active". |
| State file corruption | JSON parse error | Default to `last_seen_ts = now - 24h`. Backfill last day. Log WARN. |
| Recording deleted from Plaud after ingest | Manual / via Plaud app | Wiki entry persists. User can `delete-plaud-recording.sh` if needed. |
| Supabase delete fails in escape hatch | Non-2xx | Do not delete local wiki file. User retries. |

### Explicitly not handled

- Plaud schema changes — break loudly, fix one-line, rare.
- Multi-host cron coordination — local-disk lock only. Single-Hermes assumption.
- Backfill of pre-2026-05-17 recordings — via `--backfill` flag, never automatic.

### Observability

- All logs → `~/.hermes/logs/plaud-ingest.log` with `[INFO]`/`[WARN]`/`[ERROR]`.
- `~/.hermes/plaud-state.json` mirrors last-run status (`last_run_status`, `last_error`, `consecutive_failures`).
- `empire-status` skill can pick up the state file to surface a one-line "Plaud: 23 ingested today, last run 14:40, ok".

## Testing

### Unit tests — `tests/test_plaud_ingest.py`

| Test | Purpose |
|---|---|
| `test_slug_from_name` | "Acme Q2 Pricing!?" → `acme-q2-pricing`; empty → uses `plaud_id`; unicode → ASCII-fold |
| `test_split_long_transcript` | 80k chars → 2 parts on segment boundary; both share `plaud_id` |
| `test_state_advance_idempotent` | Same response twice → second run is no-op |
| `test_collision_appends_suffix` | Existing slug → `-2`, then `-3` |
| `test_state_corruption_recovers` | Bad JSON → 24h-ago default + WARN |
| `test_state_missing_recovers` | No state file → 24h-ago default |
| `test_frontmatter_round_trip` | Write → parse → identical |
| `test_lock_blocks_concurrent_run` | Held lock → second invocation exits 0 with message |

Plaud MCP mocked throughout. Target: full unit suite under 2 seconds. Run via `pytest`.

### Integration test — `tests/test_ingest_real_one_recording.py`

Opt-in via `RUN_PLAUD_LIVE=1`. Calls real Plaud (`list_files(page_size=1)`), runs ingester against a `tmp/` wiki dir, asserts file written + frontmatter parses + `tmp/log.md` updated, cleans up. Not in CI. Catches Plaud schema drift.

### Manual acceptance — 3 checks on first deploy

1. Record a 30-second test note ("test ingest — please ignore") → wait 6 min → confirm `wiki/plaud/2026-05-17-test-ingest.md` exists with summary + transcript.
2. Ask Margot in Telegram: "what's in my Plaud notes today?" → she references the test note from Supabase.
3. Run `./delete-plaud-recording.sh 2026-05-17-test-ingest` → wiki file gone, Supabase row gone, log entry recorded.

### Deliberately skipped

- Load tests (cron throughput is bounded).
- Property/fuzz testing on splitter (overkill for ~20 lines).
- Mocking the cron framework (we test the script directly).

## Rollout — one-time steps

1. Verify Plaud MCP auth: call `get_current_user` once. If expired, `plaud login`.
2. `mkdir -p ~/2nd\ Brain/2nd\ Brain/Wiki/plaud/`. Add `.gitkeep`.
3. Patch `sync_wiki_to_supabase.py`: `glob` → `rglob`. Test with a dummy file.
4. Write `plaud-ingest.py` (~150 lines).
5. Write `delete-plaud-recording.sh` (~30 lines).
6. Install Hermes cron: `*/5 * * * *`, log to `~/.hermes/logs/plaud-ingest.log`.
7. Seed state file with `last_seen_ts = today 00:00 local` to avoid backfilling history on first run.
8. Update `~/2nd Brain/2nd Brain/Wiki/index.md` to point to the new `plaud/_index.md` under a "Live ingestion" section.
9. Smoke test (record 30-sec note → 6 min wait → confirm).

## Privacy

- Supabase `wiki_pages` is reachable from cloud Margot. Anything ingested is queryable by anyone with the service role key (today: the user + Pi-CEO infra).
- For sensitive recordings (medical, legal, personal): use `delete-plaud-recording.sh` after the fact. Note: Margot's Gemini file_search store may retain content until its next sync — purge isn't immediate.
- Audio URLs in wiki are presigned with 24h expiry. The transcript text persists; only the link rots. Acceptable.
- No PII redaction on ingest in v1. If it becomes a problem, add a separate scrub pass.
- `~/.hermes/plaud-state.json` and `~/.plaud/tokens-mcp.json` are local-only — verify they're in Hermes's `.gitignore`.

## Acceptance criteria

v1 is done when:

1. A new Plaud recording lands in `wiki/plaud/` within 10 minutes of the NotePin syncing.
2. The wiki page contains frontmatter, AI summary, full timestamped transcript.
3. Recordings >50k chars split cleanly into `…-part2.md`, `…-part3.md`.
4. The Supabase `wiki_pages` table contains the new row within 1 minute of the wiki write.
5. Margot, asked "what's in my Plaud notes from today?", references the new recording from her corpus.
6. Margot, asked for a verbatim quote, can call Plaud MCP `get_transcript` and produce it.
7. `delete-plaud-recording.sh <slug>` removes the wiki page **and** the Supabase row.
8. Auth-expired path: ingester DMs Margot once, does not loop.
9. Two ingester runs within 5 sec → second exits cleanly via PID lock.
10. `wiki/log.md` has an entry for every ingested + every deleted recording.

## Out of scope for v1

- Meeting-vs-voicenote classification (sub-project 2).
- Action-item extraction to Linear/HubSpot (sub-project 2).
- Live in-meeting visual display (sub-project 3, separate capture path).
- Voice-journal routing to project pages (sub-project 2 or 3 — TBD).
- Cross-machine cron coordination.
- PII redaction.
- Plaud → Gemini file_search direct sync. Relies on the existing wiki → file_search path (whatever that is — investigate during sub-project 2 if it turns out the path doesn't exist yet).
