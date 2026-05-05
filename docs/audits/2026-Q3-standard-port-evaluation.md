# RA-1971 — Standard-Priority Port Evaluation (post Wave 1)

**Date:** 2026-05-05
**Issue:** [RA-1971](https://linear.app/unite-group/issue/RA-1971)
**Wave 1 epic:** [RA-1965](https://linear.app/unite-group/issue/RA-1965)
**Status:** Wave 1 ports shipped. This audit decides which of the 11 standard-priority ports become Wave 2.

## Wave 1 outcome (the new baselines)

| Port | Validation | Live in prod | Compounds enable… |
|---|---|---|---|
| RA-1966 kill-switch | tests + smoke | `5ba9c16` | All TAO loops (tao-loop, codebase-wiki, judge, future) |
| RA-1967 tao-context-vcc | **56.1% median** on 10 real sessions | `7f457ca1` + `ef1c3b38` (b) | Any prompt-shrinking work |
| RA-1968 tao-codebase-wiki | 8 tests + 881 sweep | `efa1e867` | Cold-start context for every TAO session |
| RA-1969 tao-context-mode | **89.22% median over vcc** | `c67762f7` | Question-driven file expansion |
| RA-1970 tao-judge + tao-loop | 15 tests + 888 sweep | `fe282a9f` | Goal-gated autonomous iteration |
| RA-1973 autonomy watchdog | 9 tests + 860 sweep | `14efa538` | Self-recovering poller (smoke-discovered) |

## Decision criteria from RA-1971

The original Wave-1/5 spec specified four conditional triggers:

1. If **vcc** + **context-mode** both succeed → port `pi-context-prune` (compound effect)
2. If **codebase-wiki** succeeds → port `pi-ceo-session-fts` (compound effect)
3. If **judge+loop** succeeds → port `forgeflow-dev` (test-first builds on the loop)

**All three triggers fire.** All three named ports are Wave-2 candidates.

## The 11 standard ports — re-evaluated

### Tier A — Port in Wave 2 (compound triggers fired)

| Port | Target skill | Why now | Effort |
|---|---|---|---|
| `pi-context-prune` | `tao-context-prune` | Vcc compacts retrospectively (already-collected transcript). Context-prune is *prospective* — it predicts which already-emitted blocks won't be needed downstream and elides them at the source. Compounds with both vcc (further reduction) and context-mode (sharper expand decisions). Trigger 1 fires. | 1d |
| `pi-ceo-session-fts` | `pi-ceo-session-fts` | FTS5 index over past Claude Code conversations (`~/.claude/projects/**/*.jsonl`). Combined with codebase-wiki, gives every TAO session both *what changed* (wiki) and *what we last said about it* (session search). Compounds with codebase-wiki. Trigger 2 fires. | 2d |
| `forgeflow-dev` | `tao-tdd-pipeline` | Test-first loop that composes directly on `tao-loop` + `tao-judge`. The judge primitive already exists; this skill chooses test-first as the discipline and binds the judge to "all tests pass + new tests cover the change". Trigger 3 fires. | 2d |

### Tier B — Port in Wave 2 (high value, no compound trigger but unlocks new paths)

| Port | Target skill | Why | Effort |
|---|---|---|---|
| `forgeflow-pm` | `tao-pm-pipeline` | Bridges Linear ↔ TAO. Reads Linear PRD, drafts sub-issues, assigns to TAO. Replaces the ad-hoc "I file a sub-issue then start the agent" pattern observed all night. High operator-time saver. | 1d |
| `pi-boomerang` | `tao-boomerang` | One-shot dispatch with summary-only return. Composes on `parallel-delegate`. Useful for the "I just need the answer, not the conversation" pattern (which dominates research subagent calls). Marginal but cheap. | 0.5d |
| `pi-docparser` | `pi-ceo-docparser` | PDF/DOCX parser for ICP research input — the Margot research pipeline (Wave 5) will need this. No current customer interview corpus, but the foundation matters. | 1d |

### Tier C — Defer to Wave 3 (low urgency or already substantially covered)

| Port | Target skill | Reason for deferral |
|---|---|---|
| `pi-charts` | `marketing-charts` | Vega-Lite output is nice for analytics dashboards. Marketing package doesn't currently render charts inline — when it does (paid-ads dashboards, attribution reports), port. Not Wave 2. |
| `pi-mermaid` | (cross-cutting) | Mermaid → ASCII renderer. Cosmetic. Not on the critical path. |
| `pi-memctx` | `pi-ceo-memory-packs` | Topic-bundled markdown memory packs. Existing Claude Code memory at `~/.claude/projects/.../memory/` already covers per-conversation persistence. Bundle-by-topic is a marginal add. |
| `taskplane (checkpoint primitive only)` | tier-orchestrator extension | Checkpoint-resume primitive. The current orchestrator's `_wait_for_wave` + `_session_state` ring already provides workflow checkpoint behaviour. Marginal. |
| `pi-smart-fetch` | `pi-ceo-smart-fetch` | TLS-impersonating web_fetch for paywalled content. No current pain — `WebFetch` + `WebSearch` + Composio cover the actual lookups. Port when a paywall actually blocks something Margot needs. |

## Wave 2 epic — proposed contents

**Title:** Pi-Dev package adoption — Wave 2 (compound builds on Wave 1)
**Parent:** RA-1965
**Sub-issues (in sequence-recommended order):**

1. **`tao-context-prune`** — prospective compaction (Tier A, trigger 1)
2. **`pi-ceo-session-fts`** — FTS5 over past Claude Code sessions (Tier A, trigger 2)
3. **`tao-tdd-pipeline`** — test-first loop binding `tao-judge` (Tier A, trigger 3)
4. **`tao-pm-pipeline`** — Linear PRD → TAO sub-issue automation (Tier B)
5. **`tao-boomerang`** — summary-only dispatch (Tier B)
6. **`pi-ceo-docparser`** — PDF/DOCX ICP input (Tier B)

Each carries the same autoresearch envelope as Wave 1: single metric, time budget, constrained scope, kill-switch, strategy/tactic split.

## Sequencing rationale (apply Wave 1 lessons)

1. **Validate before chaining.** Wave 1 validated 2 ports against real corpora (vcc 56%, context-mode 89% over vcc). Wave 2 should validate the same way — `tao-context-prune` against the existing 10-session corpus, `pi-ceo-session-fts` against query latency targets.
2. **Short PRs, swarm pattern works.** Tonight's pattern (sandbox-clone × 2, parallel-delegate, push, gate-green, merge) shipped 5 ports in ~3 hours. Keep using it.
3. **Two CI gotchas to avoid:** (a) literal `[skip ci]` in PR body silently disables main-branch CI; (b) PRs that ADD a new `.github/workflows/*.yml` get CI blocked entirely — split the workflow into a follow-up PR.
4. **Add `ruff check` to the agent-side gate.** RA-1970 shipped with two unused imports the broad-sweep didn't catch. The next swarm cycle's prompt should require `ruff check app/ scripts/` before commit.
5. **Validate against real corpus, not just tests.** RA-1967's tests (13 PASS) said the compactor was fine. The real-corpus validation said 56% — and exposed that two of four techniques don't fire on actual transcripts. Tests prove correctness; corpora prove value.

## Recommendation

**Open a Wave 2 epic now**, file the 6 Tier-A+B sub-issues, leave Tier C in the audit doc as Wave 3 candidates. Do NOT ship Wave 2 in this session — the Wave 1 cycle has been long, and the prudent move is a daylight gap before the next batch lands so any operational issues with the Wave 1 prod deploys (post-deploy CI saturation per RA-1987, codebase-wiki workflow file per RA-1982, the Wave-1 retro insights here) get surfaced cleanly first.

## Standing Wave-1 follow-ups (already filed)

- **RA-1982** — ship `.github/workflows/codebase-wiki.yml` + add the `[skip ci]` memory note
- **RA-1987** — raise `TAO_MAX_SESSIONS` env or auto-GC before post-deploy CI smoke

## Wave 1 closure

With this audit committed and a Wave 2 epic opened from its recommendations, **Wave 1 (RA-1965) is functionally complete**: 5 of 5 high-priority ports + 1 smoke-discovered fix shipped to prod, 2 validated against real corpora, 2 follow-ups filed, 11 standard ports triaged into Wave 2/3 buckets.

Mark RA-1965 + RA-1971 as Done. Open Wave 2 epic.
