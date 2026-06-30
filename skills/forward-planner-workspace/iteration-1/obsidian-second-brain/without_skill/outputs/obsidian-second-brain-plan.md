# Obsidian Vault → Pi-CEO Swarm Second Brain — End-to-End Plan

**Author:** Forward planning pass
**Date:** 2026-06-07
**Status:** Plan for review (no folders created yet — this is the think-through you asked for)

---

## 0. The one decision that changes everything (read this first)

You already have most of this built. The Pi-CEO codebase ships with:

- `swarm/config.py:109` → `BRAIN1_WIKI_DIR`, defaulting to `~/2nd Brain/2nd Brain/Wiki`. This is "Brain-1," a local markdown directory **injected into Margot's context on every turn.**
- `swarm/wiki_ingest.py` → a `wiki-ingest` skill that **writes** research findings, board outputs, and Margot insights back into that directory as frontmatter-tagged markdown pages, appends to `log.md`, and re-syncs changed files to a Gemini File Search corpus.
- `swarm/wiki_query.py` / `swarm/wiki_lint.py` → read + lint paths.
- `swarm/research_provider.py` → NotebookLM-first research routing (free) with Perplexity fallback (≤$5/day cap), feeding the Discovery SCAN loop.
- `swarm/pii_redactor.py` + `swarm/audit_emit.py` → redaction and observability the writers already call.

**So the real task is not "build a second brain from scratch." It is: make your Obsidian vault BE Brain-1 — cleanly, safely, bidirectionally — instead of letting the swarm write into a separate orphan `~/2nd Brain/` tree that you never open in Obsidian.**

The single highest-leverage move is to point `BRAIN1_WIKI_DIR` at a subfolder of your actual Obsidian vault, then harden the contract around it. Everything below serves that.

```
Decision: Obsidian vault root == knowledge base. A dedicated, agent-owned
subfolder inside it == Brain-1 == BRAIN1_WIKI_DIR. Humans own the rest of the
vault; agents own that one subtree. The boundary is the safety model.
```

---

## 1. The end-to-end picture (what "done" looks like)

```
                    ┌─────────────────────────────────────────────┐
   YOU (Obsidian)   │              OBSIDIAN VAULT                  │
   read + write     │                                             │
   everywhere ─────►│  /00-Inbox/        (you drop raw notes)      │
                    │  /10-Areas/        (your hand-curated MOCs)  │
                    │  /20-Projects/     (per-portfolio project)   │◄──┐
                    │  /90-Archive/                               │   │
                    │                                             │   │
                    │  /Agent/           ◄── BRAIN1_WIKI_DIR ─────┼───┤
                    │    ├─ Wiki/        (durable agent pages)    │   │ swarm
                    │    ├─ Research/    (dated research notes)   │   │ reads
                    │    ├─ Inbox/       (agent → you handoff)    │   │ +
                    │    ├─ _meta/       (schemas, manifests)     │   │ writes
                    │    └─ log.md       (append-only audit)      │   │ HERE
                    └─────────────────────────────────────────────┘   │ ONLY
                              ▲                    │                    │
                read context  │                    │ wiki-ingest        │
                every turn    │                    ▼                    │
                    ┌─────────┴───────────────────────────────────────┴──┐
                    │                  PI-CEO SWARM                        │
                    │  Discovery SCAN → research_provider (NotebookLM/    │
                    │  Perplexity) → Finding → pii_redactor → wiki_ingest │
                    │  → Gemini corpus sync → audit_emit                  │
                    └─────────────────────────────────────────────────────┘
```

Done means: you work in Obsidian like normal; the swarm continuously deposits cited, redacted, well-tagged research into `/Agent/`; you can promote anything good into your own areas; nothing the swarm does can corrupt your hand-written notes; and you can always answer "who wrote this, when, from what source, and can I trust it."

---

## 2. The 18 moves, sequenced

Grouped into five phases. Each move states **what, why, and how to verify.** Phases are ordered so that safety lands before write-access is widened.

### Phase A — Foundation & boundaries (do before any agent writes)

**Move 1 — Carve the agent-owned subtree.**
Create exactly one top-level folder in the vault (suggest `/Agent/`) and declare it the *only* place the swarm may write. Inside it: `Wiki/`, `Research/`, `Inbox/`, `_meta/`, plus `log.md`. Everything else in the vault is human-owned and read-only to agents.
*Why:* a hard write-boundary is the difference between "agent helps" and "agent silently rewrites my thesis notes." Blast radius must be a known subtree.
*Verify:* the boundary is a single path prefix you can grep for in every write call.

**Move 2 — Repoint `BRAIN1_WIKI_DIR` at the vault.**
Set the env var (Railway + local `.env`) to `<vault>/Agent/Wiki`. Confirm the default in `config.py:109` is overridden everywhere the swarm runs (Railway, local dev, scheduled-tasks MCP sandbox).
*Why:* otherwise the swarm keeps writing to the orphan `~/2nd Brain/` tree and your Obsidian vault never sees a thing. This is the literal wire.
*Verify:* trigger one `wiki-ingest` and watch a file appear inside the vault, visible in Obsidian.

**Move 3 — Define the canonical note schema (frontmatter contract).**
`wiki_ingest.py:142` already writes `---\ntype: wiki\nupdated: <date>\n---`. Extend this into a documented, enforced schema and store it in `/Agent/_meta/schema.md`. Minimum fields: `type` (wiki | research | finding | moc), `title`, `created`, `updated`, `source_type` (research | board | board_trigger | manual), `sources` (list of URLs/citations), `confidence` (high | medium | low | unverified), `tags`, `author` (which bot/persona), `turn_id`, `pii_scrubbed: true`.
*Why:* a schema is what makes the vault *machine-readable*. Without `confidence` and `sources`, you can't trust agent notes; without `author`/`turn_id` you can't audit them.
*Verify:* `wiki_lint.py` rejects any agent-written page missing required fields.

**Move 4 — Make the schema enforceable, not aspirational.**
Extend `swarm/wiki_lint.py` to validate the Move-3 frontmatter on every write and as a pre-commit / CI gate. Fail closed: a finding that can't be tagged correctly goes to `/Agent/Inbox/` as a quarantined draft rather than into `Wiki/`.
*Why:* CLAUDE.md's whole "silent success is worse than failure" ethos applies — an unschema'd note that looks fine is a trust landmine.
*Verify:* feed the linter a deliberately malformed page; it must error and quarantine.

**Move 5 — Lock the PII boundary on the write path.**
Confirm every path into `/Agent/` runs through `swarm/pii_redactor.py` before the file is written, and stamps `pii_scrubbed: true`. NotebookLM/Gemini corpus sync must only ever see redacted content (CLAUDE.md notes 6 exposed keys were found in docs once — the vault must never become the new leak surface).
*Why:* the vault will be synced to Gemini File Search (`MARGOT_FILE_SEARCH_STORE`) and read into context every turn. Anything secret that lands here propagates.
*Verify:* run `detect-secrets scan` over `/Agent/` in CI; plant a fake key in a finding and confirm it's redacted before write.

### Phase B — Read path (let agents *use* the brain well)

**Move 6 — Define what gets injected into context, and cap it.**
`BRAIN1_WIKI_DIR` is "injected into Margot's context every turn." Decide the injection policy: probably not the whole `Wiki/` (token blowout), but an index/MOC + the top-N relevant pages. Reuse the RA-1969 context-mode pattern (`build_index` → `expand` only needed files) rather than dumping the tree.
*Why:* a second brain that injects everything every turn is a second brain that bankrupts your token budget and drowns signal.
*Verify:* measure tokens-per-turn before/after; index-based injection should cut it sharply (the wiki-context-validator board memo targeted ≥30% reduction).

**Move 7 — Build Maps of Content (MOCs) as the navigation layer.**
Create hand- and agent-maintained index pages (`/Agent/Wiki/_MOC-<area>.md`) per portfolio area (pi-dev-ops, restoreassist, disaster-recovery, dr-nrpg, synthex, etc. — these are your real Linear project routes). Each MOC links its child pages. Agents update the MOC when they add a page.
*Why:* Obsidian + LLMs both navigate by links. MOCs turn a flat folder into a graph you and the swarm can traverse. They also map cleanly onto your existing portfolio/Linear routing table.
*Verify:* every Wiki page is reachable from at least one MOC (lint check: orphan detector).

**Move 8 — Wire the research providers to deposit here by default.**
`research_provider.py` already produces `Finding`s (NotebookLM-first, Perplexity fallback). Route every Finding through `wiki_ingest` into `/Agent/Research/` dated notes, with the source URL in `sources` and `confidence` set from the provider (NotebookLM-grounded = medium, externally verified = high, single-source = low).
*Why:* this is the "write research notes into it" half of your request, done with the routing you already paid to build.
*Verify:* run one Discovery SCAN cycle; confirm dated research notes appear with citations.

**Move 9 — Keep the Gemini/NotebookLM corpus in sync incrementally.**
`wiki_ingest.py` already re-uploads changed files. Formalize it: only re-sync the diff (changed/new pages since last sync sha), not the whole tree, and record sync state in `/Agent/_meta/sync-state.json`. This mirrors the `update_codebase_wiki.py --since=<sha>` incremental pattern.
*Why:* full re-sync every write is slow and costs Gemini quota; incremental keeps the searchable corpus fresh cheaply.
*Verify:* edit one page; confirm exactly one file re-uploads.

### Phase C — Write path & human handoff (the part that builds trust)

**Move 10 — Establish the agent→human handoff lane (`/Agent/Inbox/`).**
Anything the swarm produces that needs your eyes (a synthesis, a flagged contradiction, a low-confidence finding, a proposed promotion into your areas) lands in `/Agent/Inbox/` with a frontmatter `status: needs_review`. You triage in Obsidian.
*Why:* this is the HITL gate. CLAUDE.md is emphatic that destructive/uncertain agent actions stop for human review — the Inbox is that stop, made native to your workflow.
*Verify:* a low-confidence finding routes to Inbox, not Wiki.

**Move 11 — Define promotion (Inbox → your curated areas).**
A note you approve in `/Agent/Inbox/` can be *promoted*: you move it into `/10-Areas/` or `/20-Projects/`, at which point it becomes human-owned and the swarm treats it as read-only. Add a `promoted_from` backlink so provenance survives the move.
*Why:* a second brain is only as good as the curation loop. Promotion is how agent research becomes *your* knowledge instead of an undifferentiated dump.
*Verify:* promote one note; confirm the swarm no longer edits it and the backlink resolves.

**Move 12 — Conflict & merge policy (two writers, one note).**
Decide what happens when the swarm wants to update a page you've also edited. Recommendation: agents never overwrite human edits in place — they append a dated `## Agent update <date>` section, or write a sibling `<page>.agent.md`, and flag it in Inbox. Use `updated:` frontmatter + content hash to detect drift.
*Why:* Obsidian has no merge engine. Last-write-wins will eventually eat a paragraph you cared about. Append-or-sibling is safe by construction.
*Verify:* edit a page in Obsidian, trigger an agent update, confirm your text is intact and the agent content is additive/flagged.

**Move 13 — Treat `log.md` as the append-only audit ledger.**
`wiki_ingest.py` already appends to `log.md`. Make it the canonical, never-rewritten record: every agent write logs `timestamp | author | action | page | source_type | turn_id`. Pair it with `audit_emit.py` so the same events hit Supabase observability.
*Why:* "who wrote this and when" must be answerable instantly. An append-only log is the cheapest durable audit and reads fine in Obsidian.
*Verify:* every write produces exactly one log line; log is never edited, only appended.

### Phase D — Quality, dedup & self-maintenance

**Move 14 — Deduplicate findings before they land.**
Discovery already does hash-dedup on `Finding`s. Extend it to the vault: before writing a research note, check for an existing page on the same topic (title/sha/embedding match) and *update* it (append a new dated entry + new source) rather than creating a near-duplicate.
*Why:* the failure mode of an autonomous writer is 40 slightly-different notes on the same subject. Dedup-on-ingest keeps the brain a brain, not a landfill.
*Verify:* feed the same topic twice; second pass updates the first page, count of pages stays 1.

**Move 15 — Schedule a curator/garbage-collection pass.**
Reuse the `meta_curator.py` clustering pattern, pointed at the vault: weekly, cluster related agent notes, propose merges/MOC updates/archival of stale low-confidence notes, and post the proposals to `/Agent/Inbox/` for your 👍/👎. Archive (don't delete) into `/90-Archive/`. Wire via the scheduled-tasks MCP.
*Why:* a second brain decays without curation. Borrowing the existing HITL-gated curator means you get gardening without losing control or risking deletion.
*Verify:* run the pass on a seeded vault; it proposes (never auto-executes) merges and archival.

**Move 16 — Link-graph health & backlink hygiene.**
Add a lint/health job: detect orphan pages (no inbound links), broken `[[wikilinks]]`, and MOC gaps. Agents must create backlinks when they reference another page. Surface the report in the daily six-pager or Telegram.
*Why:* the value of Obsidian *is* the graph. A swarm that writes notes without links produces a pile, not a brain. Backlink discipline is what makes it navigable for both of you.
*Verify:* graph-health report runs clean after agent writes; planted orphan is flagged.

### Phase E — Operations, safety net & rollout

**Move 17 — Version-control or snapshot the agent subtree.**
Put `/Agent/` under git (or Obsidian Sync version history, or a nightly snapshot to `/90-Archive/snapshots/`). Because agents write autonomously, you need a one-command rollback when a bad cycle floods the vault.
*Why:* CLAUDE.md's autonomy mandate explicitly carves out reversibility — destructive/irreversible actions stop for human review. A snapshotted subtree makes every agent write reversible, which is what *licenses* the autonomy.
*Verify:* simulate a bad ingest; `git checkout`/restore returns the subtree to last-good in one step.

**Move 18 — Add a kill switch + rate limit for vault writes.**
Honor the existing kill-switch pattern (`~/.claude/HARD_STOP`, `TAO_AUTONOMY_ENABLED=0`) on the ingest path, and add a per-day write cap (mirroring the 3-PRs/day autonomy limit) so a runaway loop can't write 10,000 notes overnight. A `touch /Agent/_meta/FREEZE` flag should make the vault read-only to agents instantly.
*Why:* you want to walk away and trust it. That trust requires a brake you can hit from anywhere, and a ceiling the swarm can't exceed even unsupervised.
*Verify:* set FREEZE, trigger an ingest, confirm it no-ops and logs `frozen`; confirm write cap halts the Nth+1 write.

---

## 3. Rollout order (concrete first week)

1. **Day 1 (Moves 1–2):** carve `/Agent/`, repoint `BRAIN1_WIKI_DIR`, do one manual `wiki-ingest`, see it in Obsidian. *This alone proves the wire.*
2. **Day 2 (Moves 3–5):** schema + linter + PII gate. *Now writes are safe and trustworthy.*
3. **Day 3 (Moves 6–9):** read-path tuning + research routing + corpus sync. *Now the swarm both reads well and deposits research.*
4. **Day 4 (Moves 10–13):** Inbox, promotion, conflict policy, audit log. *Now the human loop is native.*
5. **Day 5 (Moves 14–16):** dedup, curator, graph health. *Now it self-maintains.*
6. **Day 6 (Moves 17–18):** snapshots + kill switch + rate limit. *Now you can leave it running.*

Phases A and E are the safety bookends — do not widen write access (Phase C onward) until A is complete and E's kill switch exists in at least stub form.

---

## 4. Folder layout (proposed, not yet created)

```
<Obsidian Vault>/
├── 00-Inbox/                 # YOUR raw capture (human-owned)
├── 10-Areas/                 # YOUR curated knowledge (human-owned)
├── 20-Projects/              # per-portfolio (maps to Linear projects)
│   ├── pi-dev-ops/
│   ├── restoreassist/
│   ├── disaster-recovery/
│   └── ...
├── 90-Archive/               # archived + snapshots (mostly human-owned)
└── Agent/                    # ◄── BRAIN1_WIKI_DIR points HERE. Agent-owned.
    ├── Wiki/                 # durable, deduped knowledge pages
    │   ├── _MOC-pi-dev-ops.md
    │   ├── _MOC-restoreassist.md
    │   └── ...
    ├── Research/             # dated, cited research findings
    │   └── 2026-06-07-<topic>.md
    ├── Inbox/                # agent → human handoff (status: needs_review)
    ├── _meta/
    │   ├── schema.md         # the frontmatter contract (Move 3)
    │   ├── sync-state.json   # incremental Gemini sync cursor (Move 9)
    │   └── FREEZE            # touch to read-only the vault (Move 18)
    └── log.md                # append-only audit ledger (Move 13)
```

---

## 5. Frontmatter contract (the SSOT for every agent note)

```yaml
---
type: research            # wiki | research | finding | moc
title: "NRPG pricing signal — Q2 2026"
created: 2026-06-07
updated: 2026-06-07
source_type: research     # research | board | board_trigger | manual
sources:
  - "https://example.com/source-1"
  - "[[20-Projects/restoreassist/pricing]]"
confidence: medium        # high | medium | low | unverified
tags: [restoreassist, pricing, market-signal]
author: discovery-scout   # which bot/persona wrote it
turn_id: ra-2027-1734
pii_scrubbed: true
status: published         # published | needs_review | promoted | archived
---
```

This single block is what lets the swarm read selectively (Move 6), dedup (Move 14), audit (Move 13), gate on trust (Move 10), and never leak (Move 5). If a note can't be given valid frontmatter, it doesn't enter the brain — it goes to Inbox.

---

## 6. What I deliberately did NOT do

- **Did not create any folders or move your files.** You asked to think it through end to end first; this is that.
- **Did not invent a parallel system.** The plan rides the existing `BRAIN1_WIKI_DIR` / `wiki_ingest` / `research_provider` / `pii_redactor` / `meta_curator` machinery rather than competing with it.
- **Did not change `config.py` or any code.** Move 2 (repointing the env var) is the first thing to do, but it's your call to pull the trigger.

---

## 7. Open questions for you (decide before Day 1)

1. **Vault location & sync:** where does the vault physically live, and is it on Obsidian Sync / iCloud / git? This determines the Move-17 snapshot mechanism and whether the Railway-hosted swarm can even reach the path (it may need the vault mirrored to a server-accessible location or written via an API rather than a local filesystem path).
2. **Single vault vs. per-portfolio vaults:** one vault with `/20-Projects/<area>/`, or separate vaults per business? One vault is simpler for the graph; separate vaults give cleaner PII isolation between clients.
3. **Confidence default:** should unverified single-source findings auto-publish to `Research/` (fast, noisier) or always quarantine to `Inbox/` first (slower, cleaner)? Recommend Inbox-first for the first month, then relax.
4. **Write cap:** what's an acceptable max agent-notes-per-day before you'd want to be paged? (Suggest start at ~20/day, mirroring the conservative PR cap.)
