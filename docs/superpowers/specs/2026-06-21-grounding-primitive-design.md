# Grounding Primitive — Design Spec

- **Date:** 2026-06-21
- **Status:** Approved direction (brainstorming complete); awaiting spec review before implementation plan.
- **Author:** Pi-Dev-Ops session
- **Related:** RA-1967 (`tao_context_vcc`), RA-1968 (`tao_codebase_wiki`), RA-1969 (`tao_context_mode`), RA-1974 (board research mode), `plaud_actions`, `pm_scoper`.

## Problem

The system has one **primary source** — the founder's voice (a Plaud recording). Everything else is **derived**: the summary, the Linear ticket, the spec, the build brief, the board minutes, the per-directory `WIKI.md`. Once a primary source is summarized, every later step reads the *derived artifact* instead of re-touching the source. Quality bleeds out at each hop.

Traced cascade (founder intent → build):

| Stage | Reads from | Evidence | Fidelity |
|---|---|---|---|
| Plaud recording → `brain/plaud/*.md` | the voice | transcript preserved | ~100% |
| `extract_actions()` → Linear ticket | full transcript | `scripts/plaud_actions.py:207-224` | ~15% |
| `pm_scoper` → Gemini spec | **the ticket only** | `swarm/pm_scoper.py:183-212` (prompt at `:200`) | ~5% |
| feature orchestrator → build | **the spec only** | — | ~2% |

Two **self-feeding loops** are worse — no human in them, so they collapse silently:

- **Wiki-on-wiki:** `tao_codebase_wiki._read_short_context` (`app/server/tao_codebase_wiki.py:150-157`) seeds each new `WIKI.md` from the *previous* `WIKI.md`, not from the source code it documents.
- **Stale research re-feed:** `board_meeting` injects month-old `prior_deep_research` (`app/server/agents/board_meeting.py:1117,1131`) into new persona debates without re-verifying it.

This is the documented **model-collapse** failure mode (Shumailov et al., *Nature* 631, 2024 — "access to the original data distribution is crucial"). The convergent fix across Anthropic's guidance and the literature: **keep the primary source in the loop and re-touch it before every generation; derived artifacts are pointers, never replacements.**

### Research basis (completed)

- **Anthropic, "Effective context engineering for AI agents":** prefer *just-in-time* references (file paths/URLs) over pre-digested copies; "overly aggressive compaction can result in the loss of subtle but critical context." Context rot: recall degrades as context grows — keep the smallest high-signal set.
- **Anthropic, "Building effective agents":** "it's crucial for the agents to gain 'ground truth' from the environment at each step."
- **Anthropic, "Effective harnesses for long-running agents":** a single canonical SSOT state file re-read on a fresh context, not an accumulated narrative.
- **Anthropic Citations API:** bind each claim to a verbatim source span; reported source-hallucination drops (Endex 10% → 0%).
- **Model collapse:** Shumailov *Nature* 2024; "Is Model Collapse Inevitable?" (arXiv:2404.01413) — *accumulating* real data alongside synthetic avoids collapse (finite error bound); "Self-Consuming Generative Models Go MAD" (ICLR 2024).
- **Provenance backbone:** W3C PROV-O (`wasDerivedFrom` + `hadPrimarySource`, acyclic — chain terminates at a primary); C2PA ingredient refs with SHA-256 hard binding.
- **Grounding/verification patterns:** RAG span-citations, Self-RAG/Corrective-RAG re-retrieval, RAGAS/FActScore faithfulness gates, TTL+confidence on cached derived knowledge.

## Goals / Non-goals

**Goals**
1. One reusable primitive that (a) **records** a back-pointer + source hash on every derived artifact and (b) **re-grounds** — re-fetches the primary source before the next generation.
2. An **enforced gate**: a generation step refuses (or loudly flags) when its input cannot be grounded.
3. **Cycle detection** — the structural alarm for self-feeding collapse loops.
4. Retrofit the highest-value seam first (`pm_scoper`), then the two self-feeding loops, then close the provenance gap at the top (`plaud_actions`).

**Non-goals**
- No central lineage ledger/graph DB (rejected: second source of truth, new infra).
- No formal PROV-O/C2PA/OpenLineage manifests or signing (rejected: overkill for an internal pipeline).
- No rewrite of the pipeline; this is additive — a primitive plus call-site retrofits.
- Not changing model routing, budgets, or the autonomy loop.

## Design

### 1. The source anchor

A small metadata block every derived artifact carries. YAML frontmatter for markdown artifacts; an equivalent dict embedded as a fenced block for JSONL/ticket bodies.

```yaml
primary_source: brain/plaud/2026-06-20-the-itr-button.md   # root — the voice
derived_from:   linear://RA-512                            # immediate parent
source_sha256:  9f3c…                                       # parent content hash at derive time
derived_at:     2026-06-21T03:14:00Z
ttl_hours:      168                                         # freshness window for the parent
confidence:     0.0–1.0                                     # optional, producer-supplied
```

`primary_source` and `derived_from` may be equal (a first-order derivation). `derived_from` may be a list when an artifact has multiple parents.

### 2. Module — `app/server/grounding.py`

**Location decision:** `app/server/grounding.py` (not `src/tao/`). Verified: every reused sibling (`tao_context_mode._sha256_hex`) and retrofit target (`tao_codebase_wiki`, `board_meeting`) lives in `app/server/`; `scripts/` already import `app.server.*` at runtime (`run_codebase_wiki.py`, `run_tao_loop.py`), so it is reachable from all three consumer trees (`scripts/`, `swarm/`, `app/server/`). `src/tao/` houses the skill engine (skills/tiers/budget) — a different concern.

Pure functions, < 300 lines, type-hinted, `logging.getLogger()` per conventions. Reuses `_sha256_hex` and the drift-detection shape from `app/server/tao_context_mode.py:87,259-262`.

Public API:

```python
@dataclass
class GroundResult:
    status: str          # FRESH | DRIFTED | STALE | MISSING | CYCLE
    primary_text: str | None
    primary_uri: str | None
    chain: list[str]     # resolved derived_from path, primary last
    detail: str          # human-readable reason

def record(artifact_uri: str, *, primary_source: str, derived_from: str | list[str],
           ttl_hours: int = 168, confidence: float | None = None) -> dict:
    """Compute source_sha256(s) + derived_at, return the anchor dict.
    Caller persists it (frontmatter for md, fenced block for ticket/JSONL)."""

def reground(artifact_uri: str, *, max_depth: int = 16) -> GroundResult:
    """Read the artifact's anchor, walk derived_from back to primary_source,
    re-fetch each hop via the resolver registry, verify sha + TTL, detect cycles.
    Returns the primary text + status."""

def require_grounding(artifact_uri: str, *, allow_ungrounded: bool = False) -> GroundResult:
    """The gate. Returns a FRESH GroundResult or raises GroundingError.
    allow_ungrounded=True downgrades to a logged warning (escape hatch)."""

class GroundingError(Exception): ...   # mirrors KillSwitchAbort pattern
```

### 3. Resolver registry

Maps a URI scheme to a fetcher returning `(text, sha256)`. Reuses existing access code:

| Scheme | Fetcher | Reuses |
|---|---|---|
| repo path / `file://` | read from disk | `tao_context_mode` disk read + `_sha256_hex` |
| `brain/plaud/…` | read transcript markdown | `plaud_actions.read_frontmatter` (`scripts/plaud_actions.py:240`) |
| `linear://<ID>` | GraphQL fetch of issue body | `pm_scoper._linear_gql` (`swarm/pm_scoper.py:85`) |
| `https://` | `httpx`, `follow_redirects=True` | per CLAUDE.md redirect rule |

Registry is a dict `{scheme: callable}`; new schemes register without touching core logic.

### 4. Gate semantics

`reground` returns exactly one status:

| Status | Meaning | Gate action |
|---|---|---|
| `FRESH` | re-fetched, hash matches, within TTL | proceed |
| `DRIFTED` | source changed since derive (sha mismatch) | re-fetch + re-derive; do **not** trust the stale child |
| `STALE` | past TTL | refresh before use |
| `MISSING` | primary cannot be resolved | refuse |
| `CYCLE` | derived_from chain revisits an artifact | refuse — **collapse alarm** |

`require_grounding` proceeds only on `FRESH`; everything else raises `GroundingError` unless `allow_ungrounded=True` (logged). This is the literature's "abstain if not grounded."

### 5. Cycle detection (collapse alarm)

`reground` tracks visited URIs while walking `derived_from`. A revisit ⇒ `CYCLE`. This is the precise structural signature of the wiki-on-wiki and board re-feed loops, obtained for free from the back-pointer walk — no separate ledger required.

## Retrofit plan (ordered; primitive lands first)

1. **`swarm/pm_scoper.py` (highest leverage).** Before building the Gemini prompt at `:200`, call `reground(ticket)` and prepend the **original Plaud transcript** to the prompt (currently only `ticket['description']` — ~30 words). The ticket already carries a `Source:` link (`plaud_actions.py:223`); step 4 makes that pointer structured/reliable. Reverses the 5% fidelity collapse. Also add `plaud_source` to the `hf_traces.record(...)` `input_context` (`pm_scoper.py:330-338`) so training signal carries provenance.
2. **`app/server/tao_codebase_wiki.py`.** Re-ground `_read_short_context` (`:150`) against the **source files**, not the prior `WIKI.md`; cycle-detection refuses wiki-on-wiki. Hooks into the existing SHA recording (`_find_last_recorded_sha:90`).
3. **`app/server/agents/board_meeting.py`.** Put a TTL on `prior_deep_research` (`:1117,1131`) using the existing `fetched`-date contract (`:1057-1078`); `STALE` forces re-verification before personas argue.
4. **`scripts/plaud_actions.py`.** In `create_linear_tickets` (`:207`), `record()` a structured anchor (not just the prose `Source:` link) so downstream `reground` is reliable. Reuse `rewrite_frontmatter` (`:271`) to stamp anchors on markdown artifacts.

## Ponytail's role

Ponytail (installed globally, user scope) stays the default-on discipline that asks "does this derived artifact need to exist at all?" before generating it. Fewer derived artifacts = fewer things to drift from. Complementary, not competing: grounding ties each generation to truth; ponytail minimizes how many generations exist. Run ponytail in `lite` for autonomous Pi-Dev work so it never fights the CLAUDE.md conventions (explicit error handling, structured logging, RA-1109 surface-treatment rules win on conflict).

## Testing

`tests/test_grounding.py`, pure-function, no network (resolvers mocked), mirroring the SDK test pattern:

- hash matches → `FRESH`
- mutate source after derive → `DRIFTED`
- expire TTL → `STALE`
- self-referential `derived_from` → `CYCLE`
- unresolvable primary → `MISSING`
- `require_grounding` raises `GroundingError` on every non-FRESH status; `allow_ungrounded=True` downgrades to a logged warning
- resolver registry dispatches by scheme; unknown scheme → `MISSING`

## Risks / open questions

- **Runtime import path from `scripts/`.** Pattern is established (other scripts import `app.server.*`), but `plaud_actions.py` currently uses bare sibling imports; the implementation must confirm `app.server.grounding` resolves when `plaud_actions` runs standalone (likely a `sys.path` insert already present in the runner). Verify during implementation.
- **Linear ticket body as anchor carrier.** Storing a fenced anchor block in the ticket description is simplest; confirm it survives Linear round-trips and doesn't disrupt the human-facing body. Alternative: a Linear attachment.
- **Re-fetch cost.** Re-opening primary sources adds latency/tokens. Mitigated by TTL (skip re-fetch within window) and by just-in-time loading only at the gate, not eagerly.
- **DRIFTED re-derive policy.** Spec marks DRIFTED as "re-derive"; the *who* re-derives (caller vs primitive) is a call-site decision deferred to the implementation plan per seam.
