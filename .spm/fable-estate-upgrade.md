# SPM Spec — Fable-Level Estate Upgrade Program

Date: 2026-07-05 · Author: /nexus + /spm + /storm-method + /judge composed · Status: see §8 (97/100 honest ceiling; Waves 0–2 executable, Wave 3 Board-gated)
Evidence base: 7-perspective discovery workflow `wf_35050e1a-800` (1.106M tokens, 172 tool calls, 0 errors; per-claim file:line + official-URL citations in journal.jsonl), plus 4 orchestrator spot-checks re-verified at source.

## 1. Task
Make every system in the estate run on the right current-generation Anthropic tier (Fable 5 / Opus 4.8 / Sonnet 5 / Haiku 4.5), switch on the Fable-5 capability levers the estate has already paid for but never enabled, and reserve the (possibly closing) Fable window for durable judgment work.

## 2. Project context — what discovery established
- **Doctrine layer is complete; capability layer is dark.** FABLE_PLAYBOOK injected globally; Nexus wrapper v1.1 calibrated; refusal-fallback guards shipped at all 6 dynamic Anthropic call sites (PR #305/#306) — and all of it is a no-op because Fable 5 runs ONLY in Phill's interactive seat (`~/.claude/settings.json`: `claude-fable-5[1m]`). Every server-side default is Sonnet 5/Opus 4.8/Haiku 4.5 or older.
- **Pi-Dev-Ops** is the reference: SSOT registry (`app/server/model_registry.py`) on current tiers + 3-layer RA-1099 policy gate. Residual drift: Supabase seed `analysis_model='claude-sonnet-4-6'` (migration.sql:22, overrides env — spot-checked), `_deploy.py:99` MODEL_MAP regresses opus→4-7 on rerun (spot-checked), mixed Haiku alias/dated forms (two prompt-cache namespaces), 4 skills' frontmatter still `claude-sonnet-4-6`.
- **Unite-Group Nexus** (canonical `~/pi-seo-workspace/unite-group`, main@e154be49): FOUR disagreeing model registries (lib/ai/types.ts 4.5-era whitelist; lib/anthropic/models.ts 4.5; packages/shared 4-6; nexus/provider-config.ts mixes sonnet-4-6 with retired gpt-3.5-turbo/gemini-1.5). Judgment gates (board-review.ts:188, spec-board critic) on opus-4-5. Anti-mandate third-party lanes live (gpt-4o-mini/gemini-flash). Max-OAuth impersonation of Claude Code from a Next.js server route (client.ts:63-107) — compliance flag.
- **Synthex**: uniformly one generation behind (sonnet-4-6/opus-4-6 across ≥5 routing layers) plus **retired Claude 3.x IDs in live routes** (nlp-analyzer.ts:149 et al. — these fail NOW). BYOK validation pings `claude-sonnet-4-20250514` (will reject valid keys when it retires).
- **RestoreAssist**: tier doctrine already encoded in dispatch (types.ts:38 names fable-5/opus-4.8/sonnet-5/haiku-4.5) but executor `lib/anthropic-models.ts:56-59` still serves opus-4-7→sonnet-4-6 (spot-checked). One-file fix closes most of the gap. BYOK allowlist caps at 4-6.
- **CARSI**: dual registries a generation apart; workflow-builder UI offers users retired claude-3-opus/sonnet/haiku; LMS chat + review replies on gpt-4o-mini (anti-mandate).
- **Always-on layer**: Hermes gateway brain = Codex gpt-5.5 (empire profile); 48 cron jobs paused with stale sonnet-4-7/opus-4-7 pins; operator-jobs launchd sweep (every 60s, `--dangerously-skip-permissions`) inherits `claude-fable-5[1m]` — burning the judgment tier on queue work with no explicit pin.
- **Fable levers documented-but-off**: `effort` param (GA, `output_config.effort`, xhigh recommended for agentic work) used in ZERO Anthropic calls (only the OpenRouter provider sets reasoning effort); `send_to_user` pattern named for the Hermes/Telegram bridge with zero implementations; distill pipeline starved by `cleanupPeriodDays: 14` (Part 3 rests on 18 sessions, corpus deleted every fortnight — spot-checked); compaction/context-editing betas unwired.

## 3. Problem
Model drift is no longer cosmetic: retired Claude 3.x IDs are failing in Synthex/CARSI production paths today; registry disagreement means any single-file bump silently doesn't propagate; the founder's #1 documented lever (effort) is unused; and the flagship tier the estate is doctrinally built around runs nowhere autonomous.

## 4. First-source model facts the program must respect (scholar, official URLs in journal)
- Lineup: Fable 5 $10/$50/MTok, 1M ctx, 128K out, adaptive-thinking-only, Covered Model (mandatory 30-day retention, no ZDR); Opus 4.8 $5/$25, recommended default for complex agentic coding; Sonnet 5 **intro $2/$10 ends 2026-08-31 → $3/$15**; Haiku 4.5 $1/$5, 200K ctx, **no adaptive thinking**.
- **Fable Max-window "closing July 7-9" is officially UNSUPPORTED** (Tier-3 creator claim). But precedent is real: access was suspended 2026-06-12 and restored 2026-07-01 with no notice. Practical conclusion unchanged: spend the window on durable, compounding artifacts now.
- **Blind ID swaps break**: on Opus 4.7+/Sonnet 5/Fable 5, `budget_tokens`, non-default temperature/top_p/top_k, and assistant-turn prefills return 400. Every upgrade = ID bump + parameter audit.
- **New tokenizer ≈ +30% tokens** vs Sonnet 4.6 era: re-baseline max_tokens, compaction triggers, cost dashboards (RA/Synthex cost maps have no rows for new tiers).
- sonnet-4-6/opus-4-6/4-7 are Active (NST 2027) — those upgrades are opportunity-driven; the Claude 3.x removals are the only break-fixes.
- Opus 4.7 fast mode errors after 2026-07-24; Opus 4.6 fast already silently degrades.

## 5. Scope
IN: model-ID/tier alignment, registry consolidation, effort plumbing, retention fix, Fable judgment-gate flips (behind existing guards, Board-gated), Hermes/cron re-tiering via COMPLIANT lanes, cost-map updates, per-swap smoke gates.
OUT (no-gos): new providers or models outside the registry; touching DR/NRPG (Windows machine); reviving the 48 Hermes crons (separate decision); paid unlocks; **routing raw Anthropic API calls through Max OAuth in third-party harnesses** (locked memory `claude-max-third-party-harness-ban`) — Hermes's Claude lane must go via `claude -p` (Claude Code harness) as TAO already does, or stay on its current substrate; **Fable 5 on client-data pipelines** (PII classify, client docs) — Covered Model retention conflicts, keep them on Sonnet/Haiku.

## 6. Existing capability (reuse, don't rebuild)
refusalFallback() guards (6 sites) · Pi-Dev-Ops model_registry.py SSOT pattern (template for Unite/CARSI consolidation) · RestoreAssist dispatch doctrine (already names target tiers) · Fabel Prompt Engineer (already fully current — the reference implementation) · nexus wrapper for every sub-tier dispatch · distill pipeline for measurement.

## 7. Specialist board (condensed)
- Architect: consolidate registries BEFORE bumping (Unite: 4→1, CARSI: 2→1), else every bump is 4 edits and a silent miss.
- Security: Unite client.ts OAuth-impersonation + instrumentation.ts env mismatch are pre-existing compliance/ops flags — surface in the Unite PR, don't silently "fix" beyond scope. Hermes .env holds ~20 credential snapshot backups (rotation hygiene, separate ticket). Margot gemini key world-readable.
- QA: every swap ships with a smoke: one real call per changed lane + JSON-contract check (board_meeting/tao_judge parse strict JSON) + count_tokens re-baseline on one representative prompt.
- Devil's advocate: (a) "upgrade everything" churn risk on Active-status models — answered by wave ordering: break-fix first, opportunity bumps only with smoke gates; (b) prompt-cache invalidation cost on swap day — schedule bumps with batch/cron windows; (c) tokenizer +30% inflates Sonnet-5 costs vs 4-6 despite lower unit price — cost re-baseline is mandatory, and intro pricing ends Aug 31 (act before September assumptions calcify).

## 8. Judge challenge — score 97/100 (honest ceiling today)
Evidence 25/25 · Problem 20/20 · Reuse 15/15 · Security 14/15 · UX 9/10 · Testability 9/10 · Simplicity 5/5.
Named gaps to a real 100: (1) tokenizer/cost re-baseline defined but not yet run (one count_tokens session closes it); (2) Unite registry consolidation needs its own micro-spec + grill per that repo's gates; (3) Wave 3 Fable flips are RA-1099 Board-gated — approval artifact doesn't exist yet (memo drafted below as the closer).
Verdict: **Waves 0–2: APPROVE EXPERIMENT-to-BUILD path is open — close gaps 1–2 as the first two tasks, then Waves 0–2 meet the bar. Wave 3: Board memo required first.** No 100 claimed until the gap-closers run — per the PR #461 hardline.

## 9. Proposed solution — four waves, tier-routed per nexus doctrine
**Wave 0 — Fable-window work (this/next session, Fable 5 itself, no code):** this discovery (done); Board memo for Wave 3 (draft: flip adversary/board-synthesis/escalation + Unite board-review + spec-board critic + RA fanOut/judge to claude-fable-5 behind existing refusalFallback→opus-4-8, excluding client-data lanes; cost delta ≈ 2x Opus on judgment calls only); Unite registry-consolidation micro-spec; skills-prune A/B design.
**Wave 1 — Break-fix + hygiene (Haiku-tier mechanical, hours each):** Synthex retired Claude-3.x routes → haiku-4-5/sonnet-5; CARSI workflow-builder retired options + registry unify; RestoreAssist stragglers (sonnet-4-5 Margot chat, retired 3-5-sonnet ref); Synthex BYOK validation ping → current ID; Pi-Dev-Ops: migration.sql seed → sonnet-5, _deploy.py MODEL_MAP → opus-4-8, Haiku ID form standardised, 4 skill frontmatters de-pinned; operator-jobs explicit `--model claude-sonnet-5`; hermes top-level default → doctrine model; `cleanupPeriodDays` 14 → 365 + JSONL archive cron.
**Wave 2 — Doctrine alignment (Sonnet-tier, 1-3 days each):** effort map plumbed into models.ts/claude.ts/ClaudeAgentOptions (WORKER low, ANALYST high, adversary/judge xhigh); Unite: consolidate 4 registries → SSOT then bump (execution → sonnet-5, coach/analyze → opus-4-8, mechanical → haiku-4-5, third-party lanes → haiku per mandate); Synthex tier router bump (3 files) + orchestrator → opus-4-8; RestoreAssist executor one-file bump + BYOK allowlist + cost-map rows; CARSI LMS/review lanes → haiku; cost re-baseline everywhere (gap-closer 1).
**Wave 3 — Fable ignition (Board-gated):** flip the named judgment gates to claude-fable-5 behind existing guards; verify agent-SDK refusal behaviour first (half-day verification task the wiki left open); send_to_user on Hermes/Telegram bridge; distill re-run on the enlarged corpus.

## 10-13. UX / Technical / Security / Verification (binding rules)
Per-swap recipe: bump ID at the SSOT → parameter audit (no temperature/top_p/budget_tokens/prefill) → one live smoke + JSON-contract check → count_tokens re-baseline → cost-map row → commit via branch+PR (Pi-Dev-Ops main is push-gated; Unite/Synthex/CARSI per their CI). Serial per repo, parallel across repos via nexus-wrapped Sonnet 5 dispatches. Fable never receives the sub-tier wrapper corrections (NEXUS_PROMPT pass-through rule). No reasoning-echo instructions anywhere (refusal trap). No context-counters surfaced to models.

## 15. Acceptance criteria
[ ] Zero retired/phantom model IDs greppable in live code paths across the 5 repos · [ ] one registry per repo · [ ] effort set on every Anthropic call site by tier · [ ] distill corpus ≥ 90-day retention with archive cron · [ ] every changed lane has a recorded smoke result · [ ] cost maps carry all 4 current tiers · [ ] Wave-3 items each carry a Board approval reference · [ ] no Max-OAuth-in-third-party-harness lane created anywhere.

## 16. Goal command
`/goal Execute Waves 1-2 of .spm/fable-estate-upgrade.md: per-swap recipe (SSOT bump → param audit → smoke + JSON contract → count_tokens re-baseline → cost row → branch+PR), one nexus-wrapped Sonnet 5 dispatch per repo in parallel, Haiku for the mechanical Wave-1 items. Stop-conditions: any smoke fail = halt that repo's lane and report; never touch DR/NRPG, PII lanes, or create OAuth-API lanes.`

## 17. Implementation sequence
Gap-closer 1 (count_tokens baseline, hours) → Gap-closer 2 (Unite micro-spec, Fable session) → Wave 1 (all repos parallel) → Wave 2 → Board memo → Wave 3.

## 18. Session-handoff seed
Discovery journal: `~/.claude/projects/-Users-phill-mac/8dfa6c8d-51d9-4534-8290-380a0b183927/subagents/workflows/wf_35050e1a-800/journal.jsonl` (full per-claim evidence). Spec: this file (PR pending). Wiki distillation: `research-fable-estate-audit-2026-07-05` in brain-1. Pick up at: gap-closer 1.

## 19. Final recommendation
The estate doesn't need more Fable doctrine — it needs the switches flipped. Do the break-fixes immediately (they're failing now), consolidate registries before any bump, plumb effort (the cheapest documented capability win), fix the distill starvation, and take the Fable judgment-gate decision to the Board this week while the window is provably open. Everything else is a controlled, smoke-gated ID bump.
