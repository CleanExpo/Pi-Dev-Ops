---
name: nexus-recall
description: "The wiki-first recall gate. Before answering, researching or planning any task, pull grounding from the 2nd-Brain wiki via brain.js: score every estate index (vault OKF, MEMORY.md, skills index) without opening files, open the single best-matching section, and ground the answer in it before reaching outward. Cheap and deterministic first, evidence-tagged, one section never a vault dump. The read-gate counterpart to nexus-copywriter; Nexus G2 runs it as the wiki-mine."
disable-model-invocation: false
allowed-tools: Bash, Read, Grep, Glob
---

# nexus-recall

**Check the wiki before you think.** The estate has accumulated hundreds of decisions, outcomes, and
lessons in the 2nd-Brain vault. Answering from the model's memory when the vault already holds the
answer is how drift and contradiction get in. This skill makes deterministic wiki recall a standing
first step — the read-gate counterpart to `nexus-copywriter`'s content gate.

## When it fires (global)

Any task that could turn on prior estate context: a question, a research request, the start of a
plan / spec / decision, "what do we know about X", "have we decided Y", "is there prior context".
Nexus's **G2 (Frame & mine)** runs it as the deterministic wiki-mine before any external research.

## The recall ladder (deterministic first, cheap first)

Run top to bottom; stop at the first hit. This is the Fable-5 **effort** discipline — the cheapest
step that answers wins, and recall stays **context-lean** (pull one answering section, never dump the
vault).

1. **Deterministic index scan (brain.js).** One command, ~10-80ms, no files opened until the winner:
   ```bash
   node "$HOME/2nd Brain/2nd Brain/_system/brain.js" find "<the question>"
   ```
   It scores every estate index line (vault OKF indexes + `MEMORY.md` + `skills/index.md`), opens the
   single best file, and returns its answering section + runners-up. Add `--json` for the structured
   `{file, section, evidence}` when a skill consumes it programmatically.
2. **On a miss (weak/empty score) → Grep the vault**, then **add the missing index line** so next time
   is deterministic (self-healing — the estate standard: a miss must leave the index better). Vault
   root: `~/2nd Brain/2nd Brain/`.
3. **Only then reach outward** (WebSearch / deep-research) — and when the external answer is durable,
   it should be ingested back (`wiki-ingest`) so recall covers it next time.

## Fable-5 calibration

- **Effort** — recall is the low-effort first pass; it must run before any high-effort research so the
  expensive tier only fires on genuine gaps.
- **Evidence tag** — recalled context is `[VERIFIED]` grounded in the returned **file path + section**
  (cite it: `per Wiki/<file> §<section>`). Never restate recalled content as the model's own claim.
- **Context-lean** (context-editing / compaction aware) — pull the one answering section, not the
  whole vault; brain.js opens exactly one file. Keeps the working context small by construction.
- **Memory-tool aware** — `MEMORY.md` is one of the scored indexes, so durable feedback/decisions are
  recalled alongside wiki pages in the same pass.

## Output contract (for orchestration)

Emit, don't just prose:
```
recall{
  question,
  hit: true|false,
  source: "Wiki/<file> §<section>"   // the grounding citation, when hit
  evidence: "<the answering section, verbatim-trimmed>",
  tag: VERIFIED,                     // grounded in a real vault file
  go_external: true|false,           // true only on a miss or stale-but-time-sensitive
  index_repair?: "<line added to which index>"  // when a miss was self-healed
}
```
`go_external: false` when the wiki answers and the topic isn't time-sensitive — that is the whole
point (avoid redundant external calls). `go_external: true` on a miss or when the wiki answer exists
but the data is stale and the question is time-sensitive (then supplement, don't replace).

## Hard rules
1. **Recall before research.** No external call on an estate-context question until brain.js has run.
2. **A miss must repair the index.** Grep-found answer → add the index line; never leave the miss.
3. **Cite the grounding.** Recalled facts carry `per Wiki/<file> §<section>`, never ungrounded.
4. **One section, not the vault.** Never dump whole files/folders into context — brain.js returns the
   one answering section by design; honour it.
5. **Don't rebuild retrieval.** brain.js is the engine; this skill orchestrates it. `wiki-query`
   (Margot-scoped) and `wiki-ingest` (write-back) are the siblings — this is the global read-gate.

## Verification (this session, 2026-07-08)
`brain.js find "fable free model routing"` → scored 1812 index entries, opened 1 file, returned
`Wiki/opus-fable-mode-skill-model-routing-herk-…` §"Model routing table" in 78ms. `--json` returns
`{file, section, evidence}`. Engine confirmed working.

## Provenance
Built 2026-07-08 to make the estate's existing deterministic-retrieval engine (`brain.js`, see memory
[[second_brain_deterministic_retrieval]]) a **global, always-on recall gate** usable inside Nexus —
rather than a CLI only some flows remember to run. Standard: vault `Wiki/second-brain-standard.md`.
