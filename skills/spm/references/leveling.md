# Bench leveling — the self-leveling ramp for /spm's MOA board

`leveling_version: 1.0` · calibrated 2026-07-10 · change-control: agent-workflow 5-clean-runs

This file defines how `/spm` sizes its specialist bench to the task. It is consumed at
workflow step 4, **after** step-2 recon (the rubric needs recon data). The output of this
file's procedure is a tier (T0–T3) and, via `moa-board.md`, a seated bench. The axis scores
and tier are always printed in spec §7 — every run leaves a receipt for why the bench was
the size it was. The §7 receipt always cites both `leveling_version` and `board_version`
(reading moa-board.md's version header at T0 is not "opening the roster" — seats stay
closed). Windows recon note for step 2: scope Glob/Grep to subdirectories with the `path`
parameter and keep patterns flat — repo-root or subdirectory-in-pattern searches can time
out or miss on large repos.

Reused primitives (do not reimplement elsewhere): the two-axis "higher wins" rule is
autonomy-ladder's; ramp-up-on-failure is tier-evaluator's; the divergence gate adapts
boardroom's Jaccard escalation to role-contracts; the cost guard is nexus G4's
(`TAO_MAX_COST_USD`, `~/.claude/HARD_STOP`).

## 1. Classification rubric

Score five axes from step-2 recon. Each axis is 0/1/2 by **checkable** definition — if you
cannot point at the evidence for a score, you are guessing; take the higher value.

| Axis | 0 | 1 | 2 |
|---|---|---|---|
| **F — Footprint** (files-touched estimate) | ≤2 files / one component | 3–10 files or one subsystem | >10 files, cross-repo, or a new service |
| **I — Irreversibility** | fully undoable (local edit, draft, doc) | costly to unwind (additive migration, public API addition, config with rollback) | prod deploy / publish / spend / destructive schema / secret rotation / vendor commitment |
| **N — Novelty** | known pattern already in the repo | new pattern, familiar domain | new domain vocabulary/entities (Unknown-Unknowns dense) |
| **X — Cross-domain count** (product/UX, architecture, security, data, infra/ops, compliance, marketing/content) | 1 domain | 2 domains | ≥3 domains |
| **S — Security surface** | no auth/PII/money/untrusted input | touches an authed surface or parses external input | auth/authz change, PII/tenant isolation, payments, secrets, RLS |

## 2. Tier mapping

Sum the axes (0–10), then apply floors — floors beat sums:

- **T0**: sum ≤1 AND I=0 AND S=0
- **T1**: sum 2–3 AND I≤1 AND S≤1
- **T2**: sum 4–6, **OR any single axis = 2** (a single maxed axis floors the tier at T2)
- **T3**: sum ≥7, **OR I=2, OR S=2**, OR (N=2 AND X=2) — irreversibility and security auto-promote
- **Tie-break**: unsure between two tiers → take the higher (autonomy-ladder rule).
- **Fast-lane interplay**: the fast-lane micro-spec is T0/T1 by construction — more than ~8
  bullets already escalates to the full spec, which re-scores.
- **Under /nexus**: G1's small/broad seeds the estimate (small≈T0/T1, broad≈T2/T3); spm
  re-scores with this rubric because it holds recon data G1 lacks.
- **Operator override**: "no board" / "bench=T0" (or any explicit tier pin) in `$ARGUMENTS`
  pins the tier. Log it in §7 as `operator override`. The override is honored without
  argument — the receipt keeps it auditable.

## 3. Tier table

| Tier | Seats | Models / effort | Rounds | Verification depth | Spec form |
|---|---|---|---|---|---|
| **T0** | **0** — no Agent dispatch | n/a | 0 | judge rubric run inline by the spec author | micro-spec or direct answer; §7 = one line: `T0, no seats (F… I… N… X… S…) · rounds 0 · board_version: X.Y · leveling_version: X.Y` |
| **T1** | 1–2 (most-relevant lens; add the disconfirming seat only if seat 1 is not a clean `pass`) | Sonnet 5, low/medium effort | 1 pass | inline judge rubric | full or micro-spec |
| **T2** | 3–4, **≥1 mandatorily disconfirming (judge seat)** | Sonnet 5 default; security/architect seats Opus 5 | max 2 | divergence measured (§4); sandbox-policy compliance stated in §13–14 | full 19-section spec |
| **T3** | 6–8 + **adversarial verify pass** (non-author model, opus-adversary style — a pass, not a seat) | synthesis/security/adversary Opus 5 at high effort; rest Sonnet 5 | max 2 | flip-test folded into §8; §13–14 **must name the container strategy** (sandbox-policy.md) | full spec, hard-floor rules active |

## 4. Divergence measurement

Adapted from boardroom's Jaccard gate — but measured over structured role-contracts, not
model text. Requires every `must_fix` item to carry a short topic `slug` (see the contract
in `moa-board.md`).

- **`verdict_split`** = 1 − (count of the modal verdict ÷ seats). Example: pass/pass/pass/fail → 0.25.
- **`fix_overlap`** = mean pairwise Jaccard similarity over the seats' `must_fix` slug sets —
  **canonicalized first**: map each slug to its topic (merge synonyms/aliases across seats)
  before computing Jaccard, and print both numbers (`lexical / canonical`) in §7. Seats slug
  independently, so raw-lexical overlap systematically under-reads agreement.

Both numbers are printed in §7.

## 5. Ramp rules

| Reading | Condition | Action |
|---|---|---|
| **Consensus** | split = 0, all `pass`, no must_fix | **RAMP DOWN**: early-exit, skip round 2, synthesize now |
| **Unanimous criticism** | split = 0 with non-`pass` verdicts (any overlap) | fold ALL must_fix, synthesize, no round 2 — round 2 exists to resolve contradictions, not unanimity |
| **Convergent criticism** | split ≤ 0.25 AND overlap ≥ 0.5 | fold the agreed must_fix into the spec; no round 2 |
| **Divergent** | split ≥ 0.5, OR (overlap < 0.2 AND ≥1 non-pass) | **RAMP UP**: escalate synthesis to Opus 5; add the judge seat if absent; run round 2 (final); round-2 briefs carry peers' round-1 must_fix (cooperation gate) |
| **Hard floor** | any `fail` with confidence ≥ 0.8 from the security seat, or on an irreversibility finding | the spec **cannot reach APPROVE BUILD 100/100** until the finding is resolved — regardless of the other seats' consensus |

Additional ramp triggers:

- **UP**: a seat returns `"escalate": true` with a named need; or mid-recon axis discovery
  (e.g. a hidden schema migration turns I to 2) — re-tier upward and top up seats.
- **DOWN**: consensus early-exit (above); or a smaller-than-estimated footprint re-tiers
  down **max one level per run** (never T3→T0 mid-flight).
- **Cost guard**: bind the bench to `TAO_MAX_COST_USD`; if a fan-out would exceed it,
  narrow in this order: drop domain-specialist duplicates → drop ops-cost-realist →
  drop ux-reviewer (if surface is internal) → reduce round cap to 1. **The disconfirming
  seat is never dropped.** Log every narrowing in §7.
- **Hard caps**: 2 rounds, always. Check `~/.claude/HARD_STOP` before the first dispatch
  and between rounds — if present, halt and report.

## 6. Worked examples

**T0 — "rename `getUser` to `fetchUser` in one file".** F=0 (1 file), I=0, N=0, X=0, S=0.
Sum 0 → T0. Zero seats. §7: `T0, no seats (F0 I0 N0 X0 S0)`. Micro-spec, done.

**T2 — "add CSV export to the reports page".** F=1 (4 files: route, component, lib, test),
I=0 (feature-flagged, additive), N=0 (export pattern exists), X=1 (product + data), S=1
(authed surface). Sum 3… but recon shows the export touches a shared query builder → F=1
holds, S=1 holds; a re-check finds the download endpoint parses user-supplied column lists
→ S stays 1. Sum 3 = T1? Recon flags the column-list parsing as injection-adjacent →
tie-break rule: take the higher → **T2**. Seats: product-manager, architect,
security-reviewer, devils-advocate-judge. Round 1: 3 pass, security `needs-work`
(must_fix: `csv-injection`, `column-allowlist`). split 0.25, overlap n/a→ convergent
criticism path: fold must_fix, no round 2. Spec §15 gains two mandatory criteria.

**T3 — "move tenant isolation from app-layer checks to RLS".** I=2 (destructive schema +
policy change), S=2 (tenant isolation). Auto-promote → **T3** regardless of sum. Seats (7):
product-manager, architect (Opus), security-reviewer (Opus), qa-verification-lead,
devils-advocate-judge (Opus), domain-specialist(data), ops-cost-realist. Security seat
returns `fail` @0.9 (must_fix: `rls-bypass-service-role`) → hard floor: APPROVE BUILD
blocked; spec reports the honest ceiling with the unresolved finding at the top. §13–14
name the shadow-DB container strategy per sandbox-policy.md.
