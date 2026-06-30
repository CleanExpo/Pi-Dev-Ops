# Forward plan: Obsidian vault → swarm-readable/writable second brain

Generated: 2026-06-07 · Horizon: 20 moves · Planner: forward-planner

The brief sounds like "make folders." It is not. The actual project is **a bidirectional knowledge interface between a markdown vault and an autonomous multi-agent system**, with all the failure modes that "two writers, one filesystem, no schema" implies: concurrent-write corruption, an unbounded read context, agents inventing their own folder conventions, no provenance on machine-written notes, and a human who can no longer tell which notes are theirs. Below is the full path, mapped backward from a defined win condition, not forward from "start making folders."

## Win condition (Definition of Done)

What "complete" means, as checkable conditions. `[auto]` = machine-verifiable, `[human]` = needs judgment.

- `[auto]` **wc1** — A documented, version-controlled vault schema exists (folder taxonomy + frontmatter contract + naming rules) and is the single source of truth both human and swarm follow.
- `[auto]` **wc2** — The swarm can **read** an arbitrary note by path and return its content + parsed frontmatter + outgoing links, via a stable interface (MCP tool or REST endpoint).
- `[auto]` **wc3** — The swarm can **search** the vault (full-text + tag + frontmatter field) and get back ranked note paths, not the whole vault dumped into context.
- `[auto]` **wc4** — The swarm can **write** a new research note that lands in the correct folder, carries valid required frontmatter, and links to at least one existing note — verified by a round-trip test (write → read back → assert).
- `[auto]` **wc5** — The swarm can **surgically edit** a section of an existing note (append/replace under a heading) without clobbering the rest of the file — verified by a patch test.
- `[auto]` **wc6** — Every machine-authored note is provenance-stamped (frontmatter: `author: swarm`, `agent`, `session_id`, `source`, `created`) so human-authored and agent-authored notes are always distinguishable.
- `[auto]` **wc7** — Concurrent / repeated writes do not corrupt or silently duplicate notes — there is a write-path that is idempotent and conflict-aware (lock, deterministic filename, or merge), verified under a 2-writer test.
- `[auto]` **wc8** — The vault is a git repository with automated commits on swarm writes, so every machine edit is diffable and revertable.
- `[auto]` **wc9** — Secret-safety: the swarm never writes API keys / tokens / PII into the vault; `detect-secrets` runs on the vault and passes.
- `[human]` **wc10** — A human can open the vault in Obsidian and the graph view / folder tree is *legible* — agent notes are organized, not a dumping ground.
- `[auto]` **wc11** — The integration is registered in the Pi-CEO system: a config entry pointing the swarm at the vault path/endpoint, plus routing so research outputs flow to it.
- `[auto]` **wc12** — An operator runbook + restore procedure exists (how to re-index, how to roll back a bad agent write, how to disable swarm writes).
- `[auto]` **wc13** — Observability: swarm vault writes are logged to the existing observability path so silent failure is detectable.

## Board state

**Internal:**
- This is a Pi-Dev-Ops / Pi-CEO problem. Project routing (`.harness/projects.json`): `pi-dev-ops` → Linear project `f45212be-3259-4bfb-89b1-54c122c939a7`, team `a8a52f07-63cf-4ece-9ad2-3e3bd3c15673` (key `RA`). This is where tickets file.
- **Reusable prior art exists.** The Synthex sandbox already contains an Obsidian integration: `lib/obsidian/client.ts`, `lib/obsidian/client-knowledge-base.ts`, `lib/obsidian/business-dna-vault.ts`, `lib/markdown/obsidian-parser.ts`, `lib/content/obsidian-importer.ts`, plus tests (`tests/unit/lib/obsidian-parser.test.ts`). This is a markdown/frontmatter parser and a vault client — do not rebuild from scratch; harvest it. (Note: it lives in `.harness/artefacts/synthex/sandbox/` — sandbox code, not production; treat as reference + lift-and-adapt.)
- Pi-CEO has an existing **observability write path** (`observability.py`, fire-and-forget Supabase) and a `detect-secrets` pre-commit convention (CLAUDE.md: 6 keys found in past audits — secret leakage is a *known live risk*, not hypothetical).
- The swarm writes research today via deep-research / board-meeting flows; output currently lands in `.harness/` artefacts and Linear, **not** a vault. There is no vault read/write interface wired into the swarm today.
- No Obsidian vault is registered anywhere in `projects.json` or `.harness/` config. Greenfield on the integration side.

**External (researched 2026-06-07):**
- The mature read/write bridge is the **Obsidian Local REST API plugin** (coddingtonbear) + an **MCP server** in front of it (cyanheads/obsidian-mcp-server is the most complete: ~14 tools — read raw / read structured / search / create / surgical PATCH-under-heading / tag + frontmatter management). Critically, mature implementations **default to refusing whole-file overwrite** (`overwrite: true` required) and offer **section-level PATCH** — this is exactly the wc5/wc7 safety primitive, already solved upstream. Don't hand-roll the write path; wrap this.
- The dominant pattern for *agent-maintained* vaults is **Karpathy's "LLM Wiki"**: plain markdown, atomic + densely interlinked notes, agent writes/maintains them directly (bypasses RAG vector DB). Several active OSS skills operationalize it (claude-obsidian, obsidian-second-brain, NicholasSpisak/second-brain).
- Organizational schema converging on **PARA** (Projects/Areas/Resources/Archives) or **Zettelkasten**, with a **one-to-two-sentence frontmatter summary** as the highest-signal field for agent search. Methodology should be *declared in the schema*, not improvised per-write.

## The gap (win condition − current state)

| Win-condition item | Status | Notes |
|---|---|---|
| wc1 schema/contract | absent | no vault schema doc anywhere |
| wc2 read note | partial | Synthex parser can parse markdown+frontmatter; no swarm-facing interface |
| wc3 search | absent | no search interface wired to swarm |
| wc4 write note | partial | Synthex has a vault client; not swarm-wired, no folder-routing/frontmatter contract |
| wc5 surgical edit | absent | upstream MCP solves it; not adopted |
| wc6 provenance stamp | absent | no provenance frontmatter convention |
| wc7 concurrent-write safety | absent | the dangerous gap; nothing today |
| wc8 git-backed vault | absent | vault not under git/auto-commit |
| wc9 secret-safety | partial | detect-secrets exists for repos, not pointed at vault |
| wc10 human-legible graph | absent | depends on schema + discipline |
| wc11 registered in Pi-CEO | absent | no config entry, no routing |
| wc12 runbook/restore | absent | — |
| wc13 observability | partial | observability path exists; vault writes not emitting to it |

## The spine — 20 moves

Ordered current state → win condition, respecting dependencies. Each is one verifiable deliverable.

1. **Audit & harvest Synthex Obsidian code** — *Deliverable:* short inventory of reusable parser/client/test code in `.harness/artefacts/synthex/sandbox/Synthex/lib/obsidian/*` + `lib/markdown/obsidian-parser.ts`, with a keep/adapt/discard call on each. *Verify:* inventory doc lists each file + decision. *Unlocks:* 4, 5. *Requires:* nothing.
2. **Decide vault location & ownership** — *Deliverable:* documented decision: vault path (e.g. a dedicated `Pi-Brain` vault), whether it's its own git repo or a folder in an existing one, who the human owner is. *Verify:* decision recorded in plan/charter. *Unlocks:* 3, 8, 11. *Requires:* nothing.
3. **Write the vault schema contract** — *Deliverable:* `SCHEMA.md` at vault root defining the folder taxonomy (PARA-based: `Projects/ Areas/ Resources/ Archive/`, plus a dedicated `Research/` and `_inbox/` agents write into), filename rules, and the frontmatter contract (required fields + types). *Verify:* file exists, lists every required frontmatter key. *Unlocks:* 6, 9, 12. *Requires:* 2. **(wc1)**
4. **Vault read interface** — *Deliverable:* swarm-callable read that returns content + parsed frontmatter + outgoing links for a path. *Verify:* unit test: read a fixture note → assert frontmatter + links parsed. *Unlocks:* 5, 13. *Requires:* 1. **(wc2)**
5. **Vault search interface** — *Deliverable:* search returning ranked note paths by full-text + tag + frontmatter field — never the whole vault. *Verify:* test: query returns expected paths, capped result count. *Unlocks:* 13, 16. *Requires:* 4. **(wc3)**
6. **Provenance frontmatter standard** — *Deliverable:* required machine-write frontmatter (`author: swarm`, `agent`, `session_id`, `source`, `created`, `summary`) codified in `SCHEMA.md` + a small validator function. *Verify:* validator rejects a note missing required keys; accepts a complete one. *Unlocks:* 7, 10. *Requires:* 3. **(wc6)**
7. **Stand up the bridge: Local REST API + MCP server** — *Deliverable:* Obsidian Local REST API plugin installed on the vault and an MCP server (cyanheads pattern) exposing read/search/create/PATCH, reachable by the swarm. *Verify:* MCP `read` and `search` tools return live data from the real vault; PATCH-under-heading leaves rest of file intact. *Unlocks:* 9, 14. *Requires:* 4, 5, 6. **(wc5)**
8. **Make the vault a git repo with auto-commit** — *Deliverable:* vault under git; a commit-on-write mechanism (git hook or post-write step) with message convention `swarm: <note title> [<session_id>]`. *Verify:* a test write produces a git commit with the convention. *Unlocks:* 12, 17. *Requires:* 2. **(wc8)**
9. **Secret-safety gate on the write path** — *Deliverable:* `detect-secrets` (and a PII check) runs on every note *before* it's committed to the vault; a hit blocks the write and logs it. *Verify:* test: a note containing `sk-ant-...` is rejected, never written. *Unlocks:* 17. *Requires:* 3, 7. **(wc9)**
10. **Idempotent, conflict-aware write path** — *Deliverable:* writes use a deterministic filename/slug + frontmatter `id`; re-writing the same logical note updates in place (PATCH) rather than duplicating; concurrent writes serialize via a lock or single-writer queue. *Verify:* **2-writer test** — two simultaneous writes of the same note yield one consistent file, no corruption, no dupe. *Unlocks:* 14. *Requires:* 6, 7. **(wc7)**
11. **Register the vault in Pi-CEO config** — *Deliverable:* a config entry (e.g. add a `vault` block to `.harness/` or `projects.json`-adjacent config) pointing the swarm at the vault path/MCP endpoint + the `Research/` write target. *Verify:* swarm resolves the vault location from config, not a hardcoded path. *Unlocks:* 16. *Requires:* 2. **(wc11)**
12. **Operator runbook + restore procedure** — *Deliverable:* runbook: how to re-index, how to revert a bad agent write (git), how to disable swarm writes (kill switch), how to back up. *Verify:* runbook exists and references real commands/paths from moves 8 & 19. *Unlocks:* — . *Requires:* 3, 8. **(wc12)**
13. **Read-context budgeting** — *Deliverable:* the read/search path returns *bounded* context (summaries + top-N notes, not full files by default) so a large vault never blows the agent's token budget. *Verify:* test: search over a 1000-note fixture returns ≤ configured cap. *Unlocks:* 16. *Requires:* 4, 5. **(wc3)**
14. **Swarm write tool: `write_research_note`** — *Deliverable:* a single swarm-facing operation that takes research output, applies the frontmatter contract + provenance + secret gate + folder routing, and writes via the bridge. *Verify:* **round-trip test** — call it → read the note back → assert correct folder, valid frontmatter, ≥1 wikilink. *Unlocks:* 15, 16. *Requires:* 7, 9, 10. **(wc4)**
15. **Auto-linking on write** — *Deliverable:* on write, the new note is linked to ≥1 existing related note (via search-for-similar + wikilink insertion), and ideally backlinked. *Verify:* test: writing into a seeded vault produces a note containing a `[[wikilink]]` to an existing note. *Unlocks:* — . *Requires:* 14, 5. **(wc4, wc10)**
16. **Wire research outputs → vault** — *Deliverable:* the deep-research / board-meeting / scan flows that currently emit to `.harness/`+Linear also write a research note to the vault via move 14. *Verify:* run a research flow → assert a note appears in `Research/` with provenance. *Unlocks:* 18. *Requires:* 11, 13, 14. **(wc4, wc11)**
17. **Observability for vault writes** — *Deliverable:* every swarm vault write emits an event (path, agent, session, result) through the existing `observability.py` fire-and-forget path. *Verify:* a write produces an observability record; a *failed* write produces a failure record (silent success ≠ silent failure). *Unlocks:* — . *Requires:* 8, 9, 14. **(wc13)**
18. **Kill switch for swarm writes** — *Deliverable:* an env/file flag (mirroring `TAO_AUTONOMY_ENABLED` / `HARD_STOP` convention) that makes the vault read-only to the swarm without touching the human's access. *Verify:* with the flag set, a write attempt is refused and logged; reads still work. *Unlocks:* — . *Requires:* 16. **(wc12)**
19. **Seed + index the existing vault** — *Deliverable:* the human's current notes are normalized to the schema (or a migration note documents what was left as-is) and the search index is built over the whole vault. *Verify:* search returns results from pre-existing human notes, not just agent notes. *Unlocks:* 20. *Requires:* 3, 5. **(wc1, wc3)**
20. **End-to-end acceptance + human legibility review** — *Deliverable:* a single scripted run exercising read → search → write → surgical-edit → git-commit → observability, plus a human opens the vault in Obsidian and confirms the graph/tree is legible. *Verify:* the e2e script passes all assertions **and** human sign-off on wc10. *Unlocks:* done. *Requires:* 15, 16, 17, 18, 19. **(wc4, wc5, wc8, wc10, wc13)**

## Branch points

- **After move 7 — bridge transport decision (decider: technical fit / security posture):** if the vault runs on the same machine as the swarm and Obsidian can stay open → use the **Local REST API + MCP** bridge (live, surgical PATCH, full feature set), continue on spine. If the vault must be operated headless / Obsidian can't be running (e.g. vault on a server, CI writes) → fork to a **direct-filesystem markdown writer** (read/parse/write files directly, no plugin), which loses surgical-PATCH guarantees and forces move 10 to do more work. Re-converges at move 14 (the `write_research_note` tool is transport-agnostic behind an adapter). *Resolver:* you (Phill), based on where the vault physically lives.
- **After move 19 — existing-vault scale (decider: size of current vault):** if the existing vault is small (≲ few hundred notes) → normalize in place during move 19. If it's large / messy → fork: leave existing notes untouched, confine the swarm to `Research/` + `_inbox/`, and schedule a separate later migration (re-run forward-planner on "migrate legacy notes to schema"). Re-converges at move 20. *Resolver:* the move-19 audit.

## Risk horizon

- **Concurrent writes corrupt or duplicate notes** (the headline risk for a two-writer system) → mitigated by move 10 (idempotent, locked, deterministic-slug write path) + move 8 (git makes any corruption revertable).
- **Agents leak secrets/PII into the vault**, which then syncs to cloud/Obsidian Sync and is hard to claw back → mitigated by move 9 (pre-write `detect-secrets` + PII gate). This is a *known* live risk in this codebase, not theoretical.
- **Vault read blows the agent's token budget** as the vault grows → mitigated by move 13 (bounded, summary-first reads).
- **Schema drift** — agents invent their own folders/frontmatter over time, vault becomes a junk drawer → mitigated by move 6's validator enforced on every write (move 14) + move 20's legibility review as a recurring gate.
- **Bridge fragility** — Obsidian must be running for the REST/MCP bridge; if it's closed, writes silently fail → mitigated by move 17 (observability surfaces failed writes) + the move-7 branch (filesystem fallback for headless).
- **Human/agent note confusion** — owner can't tell what the machine wrote → mitigated by move 6 (provenance stamp) + move 8 (git authorship).

## Red-team findings (pulled forward)

Walking the spine to its end and assuming "done" was a lie:

- **The two-writer problem was never in the brief.** "Read from and write into" silently assumes safe concurrency. Without it, the swarm and the human (or two agents) clobber each other. → inserted as move 10, with a mandatory 2-writer test.
- **No provenance = unusable second brain.** If you can't tell your notes from the machine's, you stop trusting the vault. The naive plan ("write notes") omits this entirely. → moves 6 + 8.
- **Secret leakage into a *synced* vault is worse than into a repo** — it leaves the controlled boundary. The repo has detect-secrets; the vault had nothing. → move 9, before any write is committed.
- **"Search" was assumed to mean "read the vault"** — that doesn't scale and will OOM the context window the moment the vault is non-trivial. → moves 5 + 13 (bounded, ranked search instead of dump).
- **No verification that wc-level reads/writes actually fire in production.** Silent success is indistinguishable from silent failure for fire-and-forget writes. → move 17 (observability), and move 20's e2e is the actual proof of wc4/wc5.
- **No rollback / kill path.** An agent on a bad loop could pollute the vault with hundreds of notes and nobody could stop it cleanly. → move 18 (kill switch) + move 8/12 (git revert + runbook).
- **Win-condition verification gap:** wc10 (human legibility) cannot be auto-checked — it's deliberately marked `[human]` and gated at move 20, so it isn't silently assumed satisfied by a green test suite.
- **Don't rebuild the parser.** The red-team also catches a *waste* risk: Synthex already solved markdown+frontmatter parsing. Move 1 forces a harvest pass so we adapt rather than reinvent.

## Immediate next move

**Move 1 — Audit & harvest the existing Synthex Obsidian code** (`.harness/artefacts/synthex/sandbox/Synthex/lib/obsidian/*`, `lib/markdown/obsidian-parser.ts`, and the parser test). It's first because it's pure investigation with zero dependencies, it directly de-risks moves 4/5 (read/search), and it prevents the most common waste in this exact kind of project — rebuilding a parser that already exists and is tested. Pair it with move 2 (decide vault location), which is the other zero-dependency decision everything else hangs off; the two can run in parallel and together unblock the schema (move 3), which is the real spine origin.

---

## Validation

```
$ python skills/forward-planner/scripts/validate_plan.py forward-plan.json
plan: pi-dev-ops — Turn the Obsidian markdown vault into a proper second brain
  moves: 20 | branch points: 2 | win conditions: 13
VALID
```

Clean pass: 20 moves (≥15 horizon met), 2 branch points, 13 win conditions all satisfied by ≥1 move, no dependency cycles, no dangling references, all moves Linear-routed to `pi-dev-ops`.
