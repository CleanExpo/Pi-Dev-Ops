# Option B — command centre migration, Phase 1 scope

**Date:** 2026-08-01 · **Status:** SCOPE ONLY. Nothing built, nothing deployed, nothing live touched.
**Target:** one command centre on `cc.unite-group.ink`, six ported capabilities + two Pi-Dev-Ops wins.

---

## The number that reorders everything

Raw closure sizes are misleading. Separating generated code and CSS from hand-written code:

| Capability | Files | Total | Generated | CSS | **Hand-written** |
|---|---|---|---|---|---|
| hermes-control-panel | 3 | 245 | 0 | 0 | **245** |
| knowledge | 7 | 568 | 0 | 0 | **568** |
| wiki-graph | 5 | 729 | 0 | 0 | **729** |
| providers | 7 | 915 | 0 | 0 | **915** |
| operations | 47 | 8,225 | 0 | 479 | **7,746** |
| operator-gateway | 19 | 14,492 | 0 | 0 | **14,492** |
| **SHARED CORE** | 15 | 17,446 | 15,020 | 992 | **1,434** |

**Totals: 26,129 lines hand-written · 15,020 generated · 1,471 CSS.**

Two findings that change the plan:

1. **The shared core is 1,434 real lines, not 17,446.** `types/database.ts` is 15,020 lines of *generated* Supabase types — that is a `supabase gen types` command against the target project, not a port. The rest is CSS.
2. **`operator-gateway` is 55% of the entire migration on its own** (14,492 of 26,129). With `operations` it is 85%. The other four capabilities together are 2,457 lines — **9% of the work for 4 of 6 capabilities.**

That asymmetry sets the build order.

---

## The six capabilities

### 1 · hermes-control-panel — 245 lines, 3 files
Hermes v0.16 "Surface Release" control panel. Mirrors the Hermes web admin module list inside the command centre. Its own header states: *"READ-ONLY foundation. No external connections, no MCP, no remote gateway, no messaging-channel activation."*

**Dependencies:** `lib/operator-gateway/control-panel.ts` (shared core), `DeckDetails`, deck CSS. **No Supabase.**
**Effort:** smallest. **Risk:** lowest — read-only, no data layer.

### 2 · knowledge — 568 lines, 7 files
Wiki knowledge base + capability-bus tiles, relocated from the main deck when it went "calm-cockpit".

**Dependencies:** `lib/command-centre/tools/catalogue`, `WikiGraphTile`, `DeckDetails`. No direct Supabase in the page (tiles fetch client-side).
**Effort:** small. **Risk:** low. **Note:** shares `WikiGraphTile` with capability 3 — build 2 and 3 adjacently.

### 3 · wiki-graph — 729 lines, 5 files
Obsidian-style interactive force-directed graph of the founder wiki. **Queries `wiki_pages` directly server-side.**

**Dependencies:** `lib/supabase/server`, `lib/command-centre/wiki-graph`, `WikiGraphCanvas`.
**Effort:** small. **Risk:** low-moderate — first capability with a real server-side Supabase query, so it is the one that proves the data layer works in the target.
**Data:** `wiki_pages` on `lksfwktwtmyznckodsau` — already reachable from Pi-Dev-Ops. No migration needed.

### 4 · providers — 915 lines, 7 files
LLM provider pool, usage cockpit, cost allocation tiles.

**Dependencies:** `ProviderAccountsTile`, `ProviderUsageTile`, cost-allocation components.
**Effort:** small-moderate. **Risk:** moderate — **this is a spend-visibility surface.** It reports cost; it must not acquire the ability to change plans or purchase. Fence-relevant: confirm the port carries no write path to a billing API.

### 5 · operations — 7,746 lines, 47 files
Live agent / queue / approvals / health tiles.

**Dependencies:** `lib/command-centre/dashboard-summary`, `dashboard-health-supabase`, `evidence-stream`.
**Effort:** large by file count (47 files, mostly small tiles) — the work is breadth, not depth.
**Risk:** moderate — contains **approvals**. An approvals surface that renders but does not correctly gate is worse than one that is absent. The review spec must include: does approving here actually approve anything, and is that intended at this stage?

### 6 · operator-gateway — 14,492 lines, 19 files
The operator execution surface. Its own header is the most important text in this document:

> *"SANDBOX DRY-RUN + CONTROLLED REAL-LOCAL FOUNDATION MODE. This page may create sandbox planned jobs and dry-run them only: no production DB writes, no external execution, no live runner, no API keys, no web-session scraping. No real execute button."*

**Effort:** largest — 55% of the migration.
**Risk: highest in the estate.** Those constraints are prose in a header, enforced by code scattered across 19 files. **A port that loses them silently converts a dry-run surface into a live execution surface.** That is the single failure mode this migration must not have.

⚠️ **Capability 6 has a blocker that predates this work.** Its sandbox target was `xgqwfwqumliuguzhshwv`, the mirror sandbox **deleted 2026-06-15**. A test at `lib/operator-gateway/__tests__/sandbox-approval.test.ts:21` now asserts that ref is *not* approved. So before porting, a decision is required: **what sandbox does the operator gateway target now?** Current doctrine says Supabase database branching. Until that is answered, capability 6 cannot be ported faithfully — it has no valid execution target.

---

## Build order

**Smallest first, deliberately.** The first capability through the pipeline also proves the pipeline — the cross-model review loop, the preview deploy, the incident-memory logging. Prove that on 245 lines, not 14,492.

| # | Step | Lines | Why here |
|---|---|---|---|
| 0 | **Shared core** | 1,434 + 992 CSS + regenerate types | Hard prerequisite. Nothing builds without it. |
| 1 | hermes-control-panel | 245 | Cheapest possible proof of the whole pipeline |
| 2 | knowledge | 568 | Small; shares a component with 3 |
| 3 | wiki-graph | 729 | First real server-side Supabase query — proves the data layer |
| 4 | providers | 915 | First spend-adjacent surface — proves the fence review |
| 5 | operations | 7,746 | Breadth; 47 tiles; approvals semantics |
| 6 | operator-gateway | 14,492 | **Blocked** pending the sandbox-target ruling |

**Milestone after step 4: 4 of 6 capabilities done for 2,457 lines — 9% of the code.** That is the natural checkpoint to reassess whether 5 and 6 are worth their 85%.

---

## The review discipline, and one honest limitation

Every capability follows the chain: builder builds → **different model, fresh session, no builder history** reviews against spec → flags, does not fix → fail returns to `propose-fix` → pass proceeds → logged to `.harness/incidents.jsonl`.

The reviewer receives **only** the four inputs `adversarial-review` permits: the spec, the failing/passing loop, the diff, and the test. Not the build reasoning, not the hypotheses, not the confidence. Two axes — **Standards** and **Spec** — as independent sub-agents, findings unmerged.

**Reviewer options, and they are not equivalent:**

| Option | Model diversity | Honest assessment |
|---|---|---|
| Sub-agent on **Sonnet / Haiku / Fable** | Different model, same vendor, fresh session | Real separation of context. Shared training lineage means correlated blind spots. |
| **OpenRouter, non-Anthropic** | Different vendor entirely | Genuinely independent. The stronger control. |

I default to **cross-vendor via OpenRouter for capabilities 4–6** (spend, approvals, execution) and **same-vendor sub-agent for 1–3**, and I record which was used on every review. Say the word if you want cross-vendor throughout.

**Per-capability definition of done:** preview builds green · the capability renders against real data · cross-model review returns explicit PASS on both axes · incident record written with `reviewer_model` and `reviewer_verdict` · no fence STOP triggered by the build.

**Reviewer silence, timeout or crash is not a pass.** An absent verdict means the review did not happen.

---

## Phase 3 preview — go-live (not run, not yet written in full)

Unchanged from the earlier plan and still fully gated: add `cc.unite-group.ink` to the `pi-dev-ops` project · Vercel creates the DNS record in `.ink` (owned outright, `vercel dns ls` succeeds) · promote production · verify · soak. Every step that changes anything is founder-gated. Rollback is deleting the subdomain; `unite-group.in` is untouched throughout.

The full go-live plan is written once capability 5 passes review, because its content depends on which capabilities actually shipped.

---

## Open decisions blocking the build

1. **What sandbox does the operator gateway target?** Blocks capability 6 entirely.
2. **Cross-vendor review throughout, or only for 4–6?**
3. **Do approvals in `operations` gate anything on arrival, or render read-only first?**
4. **Stop after step 4?** 4 of 6 capabilities for 9% of the effort is a legitimate finish line.

---

## Confirmation

Read-only. `find`, `grep`, `wc`, and a Python import-closure walker over source files. No build, no deployment, no branch, no domain change, no env change. `unite-group.in` and Authority-Site untouched.

Fence in **shadow**. No `HARD_STOP`. No denials seeded.
