---
title: Self-Improving System — B.U.I.L.D. Loop (gap build)
type: spec
status: shaped
author: SPM (Claude Opus 4.8)
created: 2026-06-29
source: "2nd Brain/Sources/How to Build A Self-Improving System with Claude Code.md (Austin Marchese, B.U.I.L.D.)"
appetite: 1w
---

# SPM Spec — Self-Improving System (B.U.I.L.D. loop)

## 1. Task

Implement a self-improving knowledge loop, modelled on Austin Marchese's **B.U.I.L.D.**
framework (Base / Upload / Inflow / Loop / Drive), so the empire's knowledge base and
output compound every week instead of stagnating. Build **only the gaps** — our Base
layer already exceeds the source.

## 2. Project context (verified this session)

| Layer | What exists | Evidence (this-session tool result) |
|---|---|---|
| **Base** (knowledge base) | OKF-compliant vault: `Sources/` (≈386) + `Wiki/` (**319 recursive / 201 top-level** `.md`), `index.md` per folder, `CLAUDE.md` contract, generator `okf-index.py`, Supabase mirror (`wiki_pages`) | `find ~/2nd Brain/.../Wiki -name '*.md'` → 319; `okf-knowledge-layer.md` |
| **Base** (skills) | ~60 skills incl. `wiki-ingest`, `source-ingest`, `evidence-board`, `curator-scheduled-tasks` | scout 1 inventory + `ls ~/.claude/skills` |
| **Upload** (bulk data) | `source-ingest` captures research → `Sources/`. Session lake **is** mined by FABLE distill — but **only for working-rhythm metrics**, not content/knowledge. | `find ~/.claude/projects -name '*.jsonl'` → **808 files / 442 MB / 126 dirs**; `~/Fabel Prompt Engineer/scripts/fable-distill.mjs` |
| **Inflow** (pipelines) | LaunchAgents (all active): `wiki-sync` (16:00 UTC), `repo-ingester` (17:00 UTC), `brain-1-autocommit` (03:33 AEST), `plaud-ingest` (5-min loop); Hermes `cron`; `sync_wiki_to_supabase.py` | `ls ~/Library/LaunchAgents` (scout 2 confirmed cadences) |
| **Loop** (improvement) | Partial: `analyse_lessons.py` clusters `.harness/learning/*.jsonl` → Linear tickets (**manual, unscheduled**); FABLE distill updates playbook Part 3 (**manual** `npm run distill` + POST). **No `improve-system` skill, no bucketed sign-off, no content-distillation, weekly training runner UNWIRED (RA-1745).** | `analyse_lessons.py`, `fable-distill.mjs`; `improve-system` dir MISSING; no Sat-23:00 cron/LaunchAgent |
| **Drive** (operating doctrine) | FABLE_PLAYBOOK injected each session; no documented self-improve cadence | `~/.claude/FABLE_PLAYBOOK.md` |

## 3. Problem

The pieces exist but the loop is **open, manual, and rhythm-only**:
- **The 808-transcript lake (442 MB) is mined only for *working-rhythm metrics*** (plan-before-act, reads-before-edits ratios → FABLE playbook Part 3) — **never for content/knowledge**: decisions made, problems solved, reusable patterns, skill-gaps. The richest signal in our own terminal history is left on the floor.
- **The improvement loop is half-built and unscheduled.** `analyse_lessons.py` clusters `.harness/learning` signal into Linear tickets, and FABLE distill updates the playbook — but both are **run by hand**, the documented weekly training runner (RA-1745, Sat 23:00 UTC) was **never wired to cron**, and nothing scans the *vault itself* for staleness, bloat, broken `[[links]]`, orphan sources, or dedup with *graded proposals*.
- **No human-in-the-loop sign-off mechanism** for higher-stakes changes (editing/creating skills, CLAUDE.md), so flipping the existing pieces to autonomous would risk "system drift" (the source's chest-only-workout failure mode).

## 4. Desired outcome

A closed weekly loop that runs mostly unattended and makes the corpus measurably better:
1. **Session miner** turns our 808-transcript lake into learnings + skill suggestions, routed into the existing `wiki-ingest` / memory / `.harness/learning` substrate.
2. **`improve-system`** scans the corpus and emits graded proposals into **3 buckets** — auto-apply (logged), need-sign-off (dated review file with checkboxes), more-context (questions).
3. **Routines** run ingestion + improvement on a schedule (Tue/Fri), with a human-review nudge.
4. **DRIVE doctrine** documents the operating habits so the loop is *used*, not just built.

Success = the loop runs end-to-end on real data, produces a review file Phill can check
off in Obsidian, and at least one auto-approved improvement lands with a changelog entry.

## 5. Scope

**IN (the gaps — MVP slice):**
- `sync-claude-sessions` skill — mine `~/.claude/projects/**/*.jsonl` → extract learnings + skill suggestions → write candidates to a `process/` staging area + feed `wiki-ingest`.
- `improve-system` skill — corpus analyzer with 3-bucket output + changelog + dated review file.
- `/data-ingestion` orchestration skill — runs session-sync + source-ingest + wiki→Supabase sync as one routine.
- Routine wiring (Tue/Fri ingestion AM, improvement PM) via `curator-scheduled-tasks` substrate.
- DRIVE doctrine note in vault + one-line CLAUDE.md pointer + a reusable "improve this skill from this conversation" reflex.

**OUT (NO-GOs — deliberately deferred; avoids the source's over-engineering trap):**
- Ecosystem connectors (Slack/Granola/YouTube live sync) — `plaud-ingest` already covers recordings; defer the rest to Phase 2.
- Newsletter / email-alias curated pipeline — `source-ingest` already covers curated research adequately.
- Periodic voice-dump pipeline — `plaud` already does this.
- Google Takeout / email-history mining — privacy-sensitive, low marginal value now.
- Any rebuild of the Base layer (vault, OKF, Supabase) — already done and superior.
- Fully-autonomous skill creation with no sign-off — explicitly rejected (drift risk).

## 6. Existing capability (reuse, do not rebuild)

- **JSONL parser** → reuse `~/Fabel Prompt Engineer/scripts/fable-distill.mjs` + `lib/playbook.ts` (`parseEvent`/`distillSession`). `sync-claude-sessions` adds a *content* extraction pass alongside FABLE's *rhythm* pass — do not write a second JSONL parser.
- **Signal clustering** → reuse `analyse_lessons.py` (clusters `.harness/learning` ≥2-entry patterns → Linear). `improve-system` wraps/schedules it, doesn't reimplement clustering.
- **Page distillation** → reuse `wiki-ingest` (index-first read, dedup, in-place update, OKF re-index, Supabase sync). `improve-system` calls it.
- **Research capture** → reuse `source-ingest`.
- **Scheduling** → reuse `curator-scheduled-tasks` (sandbox/health-check pitfalls solved). This is also where the **never-wired RA-1745 weekly training runner** finally gets a home.
- **Multi-view reasoning** → reuse `evidence-board` for any contested improvement.

## 7. Specialist board

- **PM:** Lead with the session-miner — it's the only piece touching data we have but don't use; everything else is plumbing. Ship that first as the thinnest vertical slice.
- **Architect:** Make `improve-system` a *thin orchestrator* over existing skills + a deterministic Python scanner (links/bloat/staleness/dedup are computable, not LLM-judgement). Keep LLM use for *proposals*, not *detection*, to bound cost. Stage session-mining output in a `process/` folder so re-runs are idempotent (mtime markers, like `wiki_sync.py`).
- **UX:** The review file is the whole human interface — must be one Obsidian markdown file with `- [ ]` checkboxes (approve / reject / approve-and-don't-ask), nothing else to learn.
- **Security:** Session JSONL contains secrets/tokens. The miner MUST redact (reuse the existing secret-scan patterns) before writing anything into the vault or Supabase. No raw transcript content leaves `~/.claude/projects`. This is the top risk.
- **QA:** Each skill must be tested on real data before being wired to a routine (the source is emphatic: "actually test the skill"). Gate: a dry-run mode that writes to scratch, diffed before going live.
- **Devil's advocate:** We risk building a loop that generates noise Phill never reads. Counter: start with `auto_approve` bucket OFF (everything to review) for week 1, measure how many proposals are genuinely good, only then enable auto-apply for the proven-safe categories.

## 8. Judge challenge

**Score: 88 / 100 → APPROVE BUILD (scoped to MVP slice).**
- Strong: builds on a mature substrate, targets a verified unused asset (808 transcripts), closes a real loop, honours simplicity by cutting 3 of 4 source pipelines.
- Risk deductions: secret-redaction in session mining (−5, mitigated by reusing scan patterns + dry-run), noise/drift (−4, mitigated by review-first week + bucketing), routine reliability (−3, mitigated by `curator-scheduled-tasks`).
- Below 100 because the loop's *value* is unproven until it runs on real data — hence the review-first, measure-then-automate sequencing. Not a reason to reduce scope further; the MVP is already minimal.

## 9. Proposed solution

```
                 ┌─────────────────────── DRIVE (doctrine + cadence) ──────────────────────┐
                 │                                                                          │
   ~/.claude/projects/**/*.jsonl ──[sync-claude-sessions]──▶ process/sessions/*.md ──┐      │
   (808 files, 442MB, REDACTED)                                                      │      │
                                                                                     ▼      │
   Sources/ + Wiki/ (corpus) ─────────────────────────────────[improve-system]──────┤      │
                                                                  scanner+proposer   │      │
                                                                       │             │      │
                        ┌──────────────────────────────┬─────────────┘             │      │
                        ▼ auto-apply                    ▼ need-signoff / more-context │      │
                 changelog.md + wiki-ingest      Outcomes/reviews/YYYY-MM-DD.md       │      │
                 (links/bloat/dedup/index)       (- [ ] approve / reject / always)    │      │
                        │                                    │                        │      │
   /data-ingestion (orchestrates sync + source-ingest + wiki→supabase)  ◀── routines ─┘      │
   Routine: Tue/Fri 09:00 ingest · Tue/Fri EOD improve · human-review nudge ──────────────────┘
```

## 10. UX

- **Primary surface:** `Outcomes/reviews/2026-06-29-improve-review.md` — a single Obsidian file. Each proposal block: title, rationale, affected file(s), diff preview, and `- [ ] Approve  - [ ] Reject  - [ ] Approve & don't ask again`.
- **Secondary:** `Wiki/_changelog.md` — append-only log of auto-applied changes (Phill reads only if curious).
- **Nudge:** if a review file sits unactioned >N days, a Telegram ping (reuse existing channel).

## 11. Technical

- **`sync-claude-sessions`**: Python scanner. Walk `~/.claude/projects/**/*.jsonl`, mtime-marker incremental (reuse `wiki_sync.py` pattern). Per new session: extract user corrections, decisions, repeated friction, skill-gap signals. **Redact secrets first** (reuse curator-security scan patterns). Output one OKF-formatted `.md` per session to `~/2nd Brain/2nd Brain/process/sessions/`. Summarise via local/cheap model (Gemma/Ollama free, like `wiki_ingest.py`) to bound cost; escalate to Claude only for the digest.
- **`improve-system`**: (a) deterministic scan — broken `[[links]]`, orphan sources (ingested, never cited), OKF index drift, near-duplicate pages, stale pages (cite sources older than threshold). (b) LLM proposer — read scan + `process/sessions/` digests → graded proposals. (c) bucket router → auto-apply (call `wiki-ingest` / fix links / regen index) + changelog, or write review file.
- **`/data-ingestion`**: orchestration skill calling `sync-claude-sessions`, `source-ingest` (if queued), then `sync_wiki_to_supabase.py`.
- **Routines:** local Claude Code routines (file-system access) per source's guidance; fall back to Hermes `cron` if desktop routines unavailable. Each routine references the skill by name (so editing the skill updates the routine).
- **Staging:** new `process/` top-level vault folder (add to CLAUDE.md + OKF). `Sources/Completed/` gap noted by scout — fix `sync_sources_to_supabase.py` path or create the folder.

## 12. Security

- **Top risk:** session transcripts contain API keys/OAuth tokens (e.g. the known live `GOOGLE_API_KEY`, Anthropic OAuT). The miner MUST run secret redaction before any write to vault/Supabase. Reuse `curator-security` patterns; add a unit test asserting known secret shapes (`sk-`, `AIza`, `sk-ant-oat`, Bearer) are stripped.
- No raw transcript bodies persisted outside `~/.claude/projects`. Only redacted digests.
- Review file changes that touch skills/CLAUDE.md are sign-off-gated (never auto-applied).
- Supabase writes stay service-role server-side (existing posture).

## 13. Verification

- `sync-claude-sessions --dry-run` on a 5-session sample → inspect digests, assert zero secrets present (grep for secret shapes → 0 hits).
- `improve-system --dry-run` → review file generated with ≥3 real proposals across ≥2 buckets; auto-apply writes only to scratch.
- End-to-end: run `/data-ingestion` then `/improve-system` for real; confirm one auto-approved fix lands + changelog entry + review file Phill can check off.
- Routine smoke: trigger the routine once manually; confirm it completes and logs which sub-step ran (per-routine separation, per source).

## 14. Loop + stress testing

- Idempotency: re-run session-sync immediately → 0 new digests (mtime markers hold).
- Volume: point miner at the full 808-file lake once → confirm it completes within a routine window and doesn't OOM (batch + free model).
- Noise audit (week 1): review-first mode; count good vs noise proposals; only enable auto-apply categories scoring clean.
- Drift guard: assert `improve-system` never edits a skill or CLAUDE.md without a checked sign-off line.

## 15. Acceptance criteria

1. `sync-claude-sessions` skill exists, tested, redacts secrets (test passes), writes redacted digests to `process/sessions/`.
2. `improve-system` skill exists, produces a bucketed review file + changelog, auto-applies only safe categories.
3. `/data-ingestion` orchestration skill runs the pipelines end-to-end.
4. At least one routine is wired and has run once successfully on real data.
5. DRIVE doctrine note + CLAUDE.md pointer committed to the vault.
6. One real improvement has landed via the loop (auto or signed-off) with evidence.

## 16. Goal command

```
/goal Implement the Self-Improving System MVP per docs/specs/2026-06-29-self-improving-system-build.md.
Build in this order, testing each on real data before wiring routines:
1. sync-claude-sessions skill — REUSE the JSONL parser in ~/Fabel Prompt Engineer (fable-distill.mjs /
   lib/playbook.ts parseEvent), add a CONTENT extraction pass (decisions, problems solved, reusable
   patterns, skill-gaps) distinct from FABLE's rhythm metrics. REDACT secrets first (test: 0 secret-shape
   hits), write OKF digests to ~/2nd Brain/2nd Brain/process/sessions/, mtime-incremental. Dry-run on 5
   sessions, verify, then full run on the 808-file lake.
2. improve-system skill — deterministic scan (broken [[links]], orphan sources, OKF drift, near-dupes,
   stale pages) + WRAP analyse_lessons.py (.harness/learning clustering) + LLM proposer → 3 buckets
   (auto-apply+changelog / need-signoff / more-context), review file to
   ~/2nd Brain/2nd Brain/Outcomes/reviews/YYYY-MM-DD-improve-review.md with
   - [ ] approve/reject/approve-and-dont-ask checkboxes. Week-1: auto-apply OFF (review-first).
3. /data-ingestion orchestration skill — sync-claude-sessions + source-ingest + sync_wiki_to_supabase.py.
4. Wire routines via curator-scheduled-tasks: Tue/Fri 09:00 /data-ingestion, Tue/Fri EOD /improve-system,
   + WIRE the never-scheduled RA-1745 weekly training runner (Sat 23:00 UTC) + analyse_lessons.py weekly,
   + human-review Telegram nudge. Reference skills by name.
5. DRIVE doctrine: Wiki/self-improving-system.md + CLAUDE.md pointer + reusable "improve this skill from
   this conversation" reflex.
Acceptance: §15 of the spec. Verify each acceptance criterion with a cited tool result. Commit + push.
Run /judge is already done (88/100 APPROVE BUILD) — do not re-gate; proceed.
```

## 17. Implementation sequence

1. Create `process/` vault folder + CLAUDE.md/OKF entry. → verify: folder + index.md exist.
2. Build + test `sync-claude-sessions` (dry-run → full). → verify: digests present, 0 secrets.
3. Build + test `improve-system` (dry-run). → verify: review file with bucketed proposals.
4. Build `/data-ingestion`; run end-to-end once. → verify: completes, Supabase updated.
5. Wire routines; trigger once. → verify: routine log shows success.
6. Write DRIVE doctrine + commit/push. → verify: files committed.

## 18. Session-handoff seed

- Spec at `~/Pi-Dev-Ops/docs/specs/2026-06-29-self-improving-system-build.md`.
- Source at `2nd Brain/Sources/How to Build A Self-Improving System with Claude Code.md`.
- Verified: 808 JSONL / 442MB lake (mined for RHYTHM by FABLE distill, NOT for content); Wiki 319 .md; 6 target skills MISSING; `analyse_lessons.py` + `fable-distill.mjs` exist but manual/unscheduled; RA-1745 weekly runner unwired; `.harness/learning` per-repo.
- Next: run the §16 `/goal`. First build = `sync-claude-sessions` (content pass over the lake, reusing FABLE's parser).
- Do NOT rebuild Base (OKF vault/Supabase) — done. Do NOT build ecosystem/newsletter/voice pipelines (NO-GOs).

## 19. Final recommendation

**APPROVE BUILD — MVP slice (session-miner + improve-system loop + routines + doctrine).** We have
the rarest precondition already: a mature, OKF-structured knowledge base and a 442 MB lake of our own
terminal history that nothing currently reads. The build is small (3 skills + routine wiring), reuses
`wiki-ingest`/`source-ingest`/scheduling wholesale, and is gated review-first to prevent drift. Cut the
three lower-value source pipelines. Ship the session-miner first; it is the only piece that turns
already-owned data into compounding output.
