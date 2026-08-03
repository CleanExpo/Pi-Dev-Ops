# MOA board — the /spm specialist bench roster

`board_version: 1.0` · `contract_v: 1` · calibrated 2026-07-10
Change-control: roster/threshold changes ride agent-workflow's promotion ladder — 5 clean
hand-run executions before a change is considered calibrated. Every emitted spec prints the
`board_version` used in §7.

**Precedence:** a project-local `.spm/agent-board.md` overrides this file when present
(spm step 2 already inspects `.spm/`); log `project board override active` in §7. This
file is the global default — projects inherit it automatically and customize by copying it
into `.spm/` and editing. spm never writes either file.

Tier selection, divergence math, and ramp rules live in `leveling.md` (read it first —
T0 never opens this roster).

## Consult contract (per seat, returned as ONE JSON block in the seat's final text)

Adopted verbatim from `specialist-council`'s consult-response contract (credited), plus two
fields: `slug` on each must_fix item (for divergence math) and `escalate` (the seat's only
way to ask for more than its brief).

```json
{
  "specialist": "security-reviewer",
  "verdict": "pass | needs-work | fail",
  "must_fix": [
    {"slug": "csv-injection", "issue": "...", "why": "...", "evidence": "file:line or doc §"}
  ],
  "suggestions": [{"change": "...", "impact": "high | medium | low"}],
  "confidence": 0.0,
  "escalate": false,
  "escalation_need": null
}
```

Rules: `must_fix` items become **mandatory 100/100 criteria** in spec §15 unless explicitly
retired by evidence in a later round. `confidence` is the seat's own calibration (0–1).
A malformed contract gets ONE re-ask, then the seat abstains (excluded from divergence
math, noted in §7). Seat failures are reported, never swallowed (boardroom rule).

## The 8 seats

Each seat is defined with agent-workflow's 5-part contract (name · soul · job · keys · stop).

| # | Seat | Lens (soul) | Default model | Seated when |
|---|---|---|---|---|
| 1 | `product-manager` | value, scope, appetite; ruthless about what NOT to build. Does NOT design solutions | Sonnet 5 | feature-shaped work, T1+ |
| 2 | `architect` | boundaries, complexity, data flow; folds in council-of-logic's Turing (complexity) + Von Neumann (architecture) checks | Sonnet 5 → Opus 4.8 at T3 | F≥1 or N≥1 |
| 3 | `ux-reviewer` | flows, empty/error states, friction; the user's advocate | Sonnet 5 | any user-facing surface |
| 4 | `security-reviewer` | auth/authz, PII, secrets, tenancy, RLS, untrusted input | **Opus 4.8 always — never cost-downgraded** | S≥1; mandatory at S=2 |
| 5 | `qa-verification-lead` | test + verification plan; proof-discipline embedded ({proven \| observed \| assumed} claim classes); owns the sandbox-policy check (§13–14) | Sonnet 5 → Opus 4.8 at T3 | T2+ |
| 6 | `devils-advocate-judge` | **the designated disconfirming seat** — argues against the build; judge's 7-lens rubric; returns a score /100 with its contract | Opus 4.8 | mandatory T2+; conditional at T1 (only if seat 1 isn't a clean pass) |
| 7 | `domain-specialist` | parametric slot — filled per task shape from the nexus G4 menu vocabulary (seo / geo-optimization / eeat / marketing-orchestrator / remotion / data / readiness / …) | Sonnet 5 | X≥1 with a non-engineering domain in play |
| 8 | `ops-cost-realist` | deploy, rollback, monitoring, run-cost; enforces sandbox-policy in the verification plan | Sonnet 5 | I≥1 or an infra/ops domain |

Seat-count by tier: T1 seats {most-relevant one of 1–3, + 6 conditionally} · T2 seats
{3–4 of the above by relevance, 6 always} · T3 {6–8, with 2/4/5/6 required}. At T3 the
adversarial verify is a **pass over the synthesis** (opus-adversary style, non-author
model), not a ninth seat.

Keys (inputs a seat receives): the task statement, spec-in-progress excerpts relevant to
its lens, step-2 recon summary, axis scores, and — in round 2 — peers' round-1 must_fix
items (cooperation gate: a round-2 contract must cite and address at least one peer
objection). Stop (when a seat is done): exactly one contract JSON returned; no follow-up
turns.

## Dispatch mechanics

- Seats run as **parallel `Agent` calls in ONE message** — never serially, and **including
  the judge seat** (the disconfirming seat is part of the bench, never a follow-up dispatch).
  Agent types: `Explore` (recon-flavored lenses), `Plan` (architecture/product lenses), or
  `general-purpose`. All read-only briefs.
- Wrap every seat brief in the Nexus Prompt (`~/.claude/skills/nexus/references/NEXUS_PROMPT.md`),
  `{TASK}` = the seat brief, at the seat's calibrated model tier and effort (Model- and
  Effort-calibration blocks are in the wrapper). **Strip the wrapper's Delegation section
  when wrapping leaf seats** — it contradicts the leaf-agent guard, and the guard wins.
  Request the seat's model tier via the Agent tool's `model` parameter (sonnet/opus per the
  roster); note in §7 that the requested tier is the intent — actual serving model is not
  observable from seat output. Never append show-your-reasoning instructions (autonomy
  contract — refusal trap).
- Contracts must return to the dispatching context. If a seat's return routes elsewhere
  (e.g. a resumed seat notifying a parent coordinator), treat the externally-relayed
  contract as evidence only after verbatim capture, and note the relay in §7.
- Reconcile condensed contracts; **never paste raw seat output into the spec**. §7 carries:
  tier + axis scores, seats convened, per-seat verdict+confidence, divergence numbers,
  ramp decisions, board_version.
- Synthesis is centralized (one decision-maker — the spec author), per specialist-council's
  coordination rule. The bench consults; the SPM decides; the judge seat's must_fix
  constrains.

## Guardrails

**Leaf-agent guard — include verbatim in every seat brief:**

> You are a leaf agent — one consulting seat on a read-only spec board. You MUST NOT:
> invoke the Skill tool for any skill (not `nexus` — it is `disable-model-invocation` and
> errors; not `spm`, `specialist-council`, or `boardroom`); dispatch subagents via
> Agent/Task/Workflow; write, edit, create, move, or delete any file anywhere (including
> scratch/temp); run any state-changing command. You MAY: Read, Grep, Glob, and read-only
> Bash (`git status/log/diff`, `ls`). Return exactly one consult-response JSON block as
> text, then stop. If you need something outside your brief, set `"escalate": true` with
> the named need — do not fetch it yourself by spawning anything.

- **Depth accounting**: under `/nexus`, nexus pulls `Skill(spm)` inline, so bench seats are
  nexus's depth-1 dispatches (cap respected). Standalone `/spm` is depth 0; seats are
  depth 1. Either way seats are terminal.
- **Cooperation gate** (round 2 only): each seat must cite and address ≥1 peer objection
  before its round-2 input is accepted.
- **Diversity over redundancy**: seats are distinct domain lenses, never N copies; the
  disconfirming seat (judge) is mandatory at T2+ and survives all cost narrowing.
- **Honest degradation**: all seats fail → run the old inline persona pass, label the spec
  §7 `bench degraded — inline persona pass`, and say so in the final recommendation. Opus
  unavailable for the security seat → run it on Sonnet, mark §12 `reduced assurance`, and
  block APPROVE BUILD 100/100.
- **Kill-switches**: honour `~/.claude/HARD_STOP` and `TAO_MAX_COST_USD` per leveling.md §5.

## Task-shape → seat mapping (mirrors the nexus G4 menu)

| Task shape | Seats emphasized |
|---|---|
| Code / refactor / architecture | architect, qa-verification-lead, judge (+ security if S≥1) |
| New domain vocabulary | architect(N-focus), domain-specialist, judge |
| Outward-facing / market / content | product-manager, domain-specialist (seo/geo/eeat/marketing), ux-reviewer, judge |
| Ship / go-live readiness | qa-verification-lead, ops-cost-realist, security-reviewer, judge |
| Strategic / go-no-go | product-manager, judge (+ boardroom is nexus's tool, NOT a seat here — do not double-bench) |
| Data / schema / migration | architect, security-reviewer, qa-verification-lead, ops-cost-realist, judge |
