# Adopting NEXUS-RELEASE-HARNESS v1.0 without duplicating what exists

**Date:** 29 September 2026 (r2 — corrected after an independent review the same day).
**Packet:** [packet-v1.0-as-received.md](packet-v1.0-as-received.md) (DRAFT_FOR_INDEPENDENT_REVIEW;
truncated on receipt — see §7). Packet citations below are `file:line` in that copy, re-derivable
with `grep -n`.
**Status of this file:** adoption decisions, made so the packet becomes the layer *above* the work
already in this repo rather than a second copy of it. Nothing here grants build, Linear-write,
paid-activation or release authority; the packet's own admission gates still apply.

## 1. The one rule for this and every later input

Every planning input lands in exactly one of four layers, and extends the layer below it by
reference. A new input may add rows, replace a definition (saying so here), or record a conflict.
It may not start a parallel tree for something a layer already owns.

| Layer | Owns | Canonical file(s) |
|---|---|---|
| **1. Method** — how plans are written | Planning procedure, evidence states, review ladder | [plan-to-done v1.1](../plan-to-done-v1.1/plan-to-done/SKILL.md) (candidate) + existing `/spm`, engineering-requirements (skills-library) |
| **2. Portfolio** — all ten tracks | Programme packages CP-00…CP-09, requirements R01–R14, milestones M0–M4, AAA rubric, release stages R0–R4, RANA support model, Linear pathway, harness acceptance tests T01–T14 | **This packet** |
| **3. Track** — one product | That product's inventory, promises, control set, work packages | [mission-control/](../mission-control/README.md) is the **MC track** instance |
| **4. Pathway** — idea → live lifecycle | Stage evidence and breaks between stages | [idea-to-live/](../idea-to-live/pathway.md), mapped onto the canonical UNI-2517 lifecycle |

The next input is classified into one layer, gets a row in §6, and its overlaps are resolved here
before any file is added.

## 2. What the packet adds that did not exist here

- **Portfolio scope:** ten tracks (DR, NRPG, HALL, RA, CARSI, SYN, ATO, CCW, UG, MC). This repo
  only ever planned MC.
- **Customer Promise Register** (intent §4, `:177`): every advertised capability must have a
  working journey, support and current evidence. New concept for MC.
- **Staged release R0–R4 and the RANA support model** (production-live, `:1474-1495`, `:1554`).
  Nothing equivalent here.
- **Two-provider independent audit** as a release requirement (scoring). Here it was only
  recorded as `NOT_RUN`.
- **Harness self-tests T01–T14** (testing §7, `:1274-1312`): the harness must reject seeded
  false-greens before its results count.
- **Receipt model** (engineering §1, `:813`): evidence tied to candidate SHA, artifact, config and
  schema digests, invalidated when any changes.
- **Critical-path method** (plan §4, `:714`): unknown durations stay unknown.

## 3. Where it overlaps existing work — decision for each

| # | Topic | Already here | Packet | Decision |
|---|---|---|---|---|
| O1 | **AAA meaning** | [aaa-rating.md](../mission-control/aaa-rating.md): per-surface tiers A/AA/AAA, lowest surface sets the grade, 3 nightly runs | scoring.md: weighted evidence score over frozen control groups, mandatory blockers outside the score, **AAA-RELEASE-READY** and **AAA-LIVE-VERIFIED**, two independent audits | **The packet's rubric is the only AAA.** The MC file is re-expressed as the MC track's *control set*; its tiers are renamed Levels 1–3. Reaching Level 3 is necessary for MC's AAA, not sufficient (aaa-rating.md lists what else the rubric needs). |
| O2 | **Evidence vocabulary** | Register rows: VERIFIED / PARTIAL / STRUCTURAL_ONLY / MISSING / UNKNOWN / CONFLICTING | Receipts: PASS / FAIL / NOT_RUN / BLOCKED / STALE / NOT_APPLICABLE | **Both kept, different jobs.** A receipt records one check; a row's state is derived from its required receipts by the rules in §4. |
| O3 | **Work packages** | MC WP-01…WP-12; idea-to-live gaps A–L | CP-00…CP-09 + per-track `P-DISCOVER → PROMISE → VERIFY → REPAIR → AUDIT → RELEASE → OBSERVE` | **MC WPs become the MC track's instance of that chain** (table in work-packages.md). No renumbering, no new tickets. Placement of every CP in §5. |
| O4 | **Lifecycle** | pathway.md 10 stages | UNI-2517 earned lifecycle `IDEA → … → POST_DEPLOY_VERIFIED → COMPLETE` | **UNI-2517 is canonical.** pathway.md keeps its evidence per stage and gains a crosswalk column. The P-chain is a per-*release* chain and is kept separate from the per-idea stages. |
| O5 | **Jev** | Founder, 28 Sept: use Jev heavily for Mission Control testing, **no daily cap**. [jev-decision-contracts.md](../mission-control/jev-decision-contracts.md); `scripts/jev_triage.py` (dry-run default, advisory only, cap optional and off) | Jev "disabled by default. Pricing, provider approval, data handling and **budget** require explicit admission before even a shadow API call" (`:1064-1066`); "No live Jev call or paid activation is authorised here" (`:263-264`); T10 requires no paid fallback at a quota boundary (`:1296-1297`) | **CONFLICT — open, founder money decision.** The packet asks for a recorded budget before any call; the founder instruction removes the cap. Both cannot bind. Until Phill says which rules, Jev stays in dry-run: no live call is made (none can be today anyway — `api.typesafe.ai` is unreachable from this environment, RA-7832). If no-cap is confirmed, the admission record says so explicitly and the ledger still records every dollar. Jev never counts as either audit reviewer (`:1440`). |
| O6 | **Model lanes** | Verified 28 Sept: Codex models are GPT-5.6 Sol/Terra/Luna; `gpt-6-sol` does not exist ([routing-verification](../idea-to-live/routing-verification-2026-09-28.json)); plan phase on Sonnet, Opus limited to `OPUS_ALLOWED_ROLES` (CLAUDE.md, RA-1099) | Preferred engineering lane Claude Opus 5.5 through an eligible Claude Max workflow; independent lane the GPT-5.6 family through eligible ChatGPT Pro/Codex (`:252-254`); exact IDs resolved at admission | **Consistent on the OpenAI side; to be reconciled on the Claude side.** The packet's GPT-5.6 wording matches the verified IDs. Its "Opus 5.5 engineering lane" must be reconciled with this repo's role policy (Opus only for planner/orchestrator/adversary/portfolio) at CP-00 — not assumed. plan-to-done still pins `gpt-6-sol` (RA-7819). |
| O7 | **Merge / release authority** | D0 decided (RA-7818): Pi-Dev-Ops is human-merge-only; cross-model audit is evidence, not acceptance | Board release controller + signed mandate; nothing widened | **Agree.** Both say an audit receipt is not an approval. |
| O8 | **Linear** | Tickets in project Pi-Dev-Ops: RA-7811–7817 (gaps A–G), RA-7820–7822 (gaps I, J, L), RA-7818 (D0 decision), RA-7819 (plan-to-done v1.2), RA-7832 (AAA secrets). Gaps H and K have no ticket. Mapping read from Linear 29 Sept | CP-05 deduplicated projection (`:664-666`); key `nexus-release:<canonical-project>:<release>:<requirement-or-failure-fingerprint>` (`:1764`); planning records stay Draft/Backlog with no autonomous labels (`:1768-1770`); no writes without a grant | **Reuse existing tickets.** On an authorised CP-05 sync they are linked under the MC first-release epic, each keyed `nexus-release:mission-control:<release>:<fingerprint>`; none are recreated. All sit in Backlog without autonomy labels today, which already matches the packet. No Linear write is made by this adoption. |
| O9 | **Harness acceptance tests** | MC control-set checks and the ungraded-until-evidence rule | T01–T14 | Full table in §4.3. Mapped where a real equivalent exists, recorded as a gap otherwise; T10 is a recorded conflict (O5). |
| O10 | **Owner entry point** | Mission Control has **six separate text entries** today, not one (`<textarea>` in `IdeaPipelinePanel`, `GoalTicketForm` ×2, `GoalDraftReview`, `GoalProjectPicker`, `BuildForm`, `SpecPipelinePanel`), plus Telegram `/idea`, `IDEAS.md` and Linear labels (pathway.md stages 1–3) | /spm v2.0 §3: `/spm <outcome>` in "the existing Mission Control text area" is the single entry | **Adopt the single-entry goal; correct the premise.** There is no single text area yet, so §12 step 3 is building one out of these, not binding an existing one. Home: the Goal screen, already marked "Primary" (`dashboard/lib/control/nav.ts:137`). Nothing is removed until the new entry proves durable submission and deduplication. |
| O11 | **Meaning of `/spm`** | `.agents/skills/spm/SKILL.md` (symlinked from `.claude/skills/spm`): "Read-only… Do not edit product code, commit, push, deploy", ends by emitting a `/goal` command (`:152`) — this confirms v2 S1 for the copy in this repo. CLAUDE.md command table says the same. Machine-ship's "spm" stage is a separate prompt (`app/server/spec_pipeline/spm_runner.py:23`, role `spm_runner`), not the skill | v2.0 §2, §12.2: public `/spm` becomes mission ownership; spec-writing stays inside it as "Plan and write" | **Adopt, staged.** The spec-writing skill is kept unchanged as the internal planning worker; the owner-facing `/spm` is a new coordinator contract above it. The shared skill lives in `CleanExpo/skills-library` (CLAUDE.md), so the public rename is a library change, versioned and routed there — not edited here. Recursion risk is real in name only today: `run_spm` does not invoke the skill, and must not start to. CLAUDE.md's `/spm` row changes when the migration lands, not before. |
| O12 | **plan-to-done's role** | Candidate, quarantined, "Planning only; never builds" (CLAUDE.md) | v2.0 header: no longer the owner's entry; stays an internal planning stage | **Agree.** Nothing to undo — it was never installed as an entry. |
| O13 | **Mission record and continuation** | `app/server/continuation_horizon.py` + `continuation_store.py`: one root objective kept stable, follow-ups appended as `objective_updates`, 15-move horizon, completion needs evidence (`docs/architecture/continuation-horizon-v2.md`). It holds **one** objective per store, not many missions. Its Supabase table (`supabase/migrations/20260827_continuation_horizons.sql`) is dated after 2026-08-14, so by the CLAUDE.md ledger rule it is not applied in production (RA-7403) | v2.0 §3, §9: many missions, each with identity, request id, verbatim original, revisions, leases, events | **Extend, don't duplicate.** The horizon is the seed of the mission record: verbatim original + revisions already exist in shape. Missing: multiple missions, client request ids, idempotent submit, event history. Session leases exist (`20260830T000000_session_leases.sql`), also unapplied. Applying migrations is a manual production step. |
| O14 | **Status view (S5)** | `GET /api/mission-control/live` (`app/server/routes/mission_control.py:37,208`, auth-gated): throughput, active sessions, recent completions, queue, pulse | v2.0 §4 mission card; §11 receipt-backed "shipped" | **Extend this route and the Live page; no second dashboard.** "Recent completions" must not mean "shipped": v2 §11 is gaps D, E, I here (RA-7814, RA-7815, RA-7820). v2's S3 (Unite-Group `live-agent-operations.ts`) is outside this repo and not verified here. |
| O15 | **Controller host** | CLAUDE.md POLICY: "Always-on means Railway + Vercel + GitHub Actions only. If a step needs a Mac awake… it is not autonomous." Backend and poller run on Railway | v2.0 §9: Mac Mini "preferred always-on controller… subject to real readiness verification"; "preserve the actual current storage owner" | **Conflict with written policy — resolved by v2's own condition.** Railway remains the canonical mission service and controller until a Mac Mini controller passes readiness and single-writer proof; the Mac Mini, PC and MacBook join as admitted workers (existing `mesh/` fleet code). Changing the always-on policy is Phill's direction decision, taken only after that proof. |
| O16 | **Phase labels** | UNI-2517 lifecycle (O4) | v2.0 §4: labels are a presentation of the existing lifecycle | **Agree.** Mapping: Understanding = `IDEA`/`DISCOVERED`; Planning and writing = `PLANNED`; Building = `BUILD_AUTHORISED`→`LOCALLY_VERIFIED`; Checking = `PR_OPEN`→`CI_GREEN`/`STAGING_VERIFIED`; Ready for release = `RELEASE_READY`; Releasing = `SHIP_AUTHORISED`/`PRODUCTION`; Shipped and verified = `POST_DEPLOY_VERIFIED`/`COMPLETE`. Planning-only ends at "Planning delivered". |
| O17 | **Grants, Jev, review** | D0 human merge (RA-7818); O5 Jev budget conflict; model policy `OPUS_ALLOWED_ROLES` | v2.0 §7–8: scoped grants, no standing merge/production grant, no paid route activated, cross-provider review | **Agree**, and v2 restates the packet's Jev rule ("Live or shadow provider calls need an authorised route, data policy and budget"), so the O5 founder decision covers both. |

## 4. Rules the adoption adds

### 4.1 Deriving a register row from receipts (O2)

Applied in order; the first rule that matches wins. "Required" means required by the row's level
in the control set; a NOT_APPLICABLE receipt is only valid with a written reason and is then
dropped from the required set.

1. Any required receipt **FAIL** on the current revision → **CONFLICTING**.
2. No required receipt exists at all, and no code exists → **MISSING**.
3. No required receipt exists, code exists but only structure has been checked → **STRUCTURAL_ONLY**.
4. Every required receipt is **PASS** and current (same SHA and config) → **VERIFIED**.
5. Some required receipts PASS and the rest are NOT_RUN / BLOCKED / STALE → **PARTIAL**.
6. Anything else, including receipts that disagree with each other → **UNKNOWN**.

A STALE PASS never counts as PASS (T03). Nothing but rule 4 can yield VERIFIED (T13).

### 4.2 What "NOT_ASSESSED_BY_THIS_RUN" means for MC

The packet's phrase (`:81`) describes the packet's own preparation run: no product tests were run
in writing it. It is not a claim about MC's state, and this repo does not contradict it. What this
repo adds is that MC was assessed separately, at shallow depth: see §5 of the corrections below.

### 4.3 Harness acceptance tests T01–T14 against this repo

| Test | Required result (packet) | Here today | Status |
|---|---|---|---|
| T01 | Ambiguous alias blocks the action | `projects.json` routes on unique `id`, never `repo` (CLAUDE.md, Linear routing) | Partial equivalent; not a seeded test |
| T02 | Advertised stub blocks the release | MC Customer Promise Register not started | Gap (MC-PROMISE) |
| T03 | Review for a different SHA is stale | Pre-push review receipt bound to `head_sha` (pathway stage 6); MC receipts carry SHA (check 4) | Mapped |
| T04 | Missing context is retrieved, not asked | No equivalent test | Gap (portfolio, CP-06) |
| T05 | Expired mandate denies the side effect | No mandate model here | Gap (CP-00/CP-03) |
| T06 | 200 without the downstream effect fails | MC checks 2, 3, 12 | Mapped (checks not yet run) |
| T07 | Self-review cannot pass independent review | Human-merge-only (RA-7818); two non-author audits are NOT_RUN | Partial |
| T08 | Replayed Linear sync makes no duplicate | No sync exists yet | Gap (CP-05) |
| T09 | Crash after a side effect does not repeat it | `supabase/migrations/20260830T000000_session_leases.sql` is a candidate; not tested for this | Unverified |
| T10 | Quota boundary checkpoints, no paid fallback | Jev ledger records spend; cap removed by founder | **Conflict** (O5) |
| T11 | No support/rollback proof → no COMPLETE | Gaps D, E (RA-7814, RA-7815) | Gap |
| T12 | Cleanup cannot delete active work | No equivalent test | Gap (CP-09) |
| T13 | Unknown test cannot become PASS or AAA | MC level rule: a level needs every check passing; rows are ungraded until evidence exists | Mapped |
| T14 | Release that drops an entitlement is blocked | No entitlement model for MC (single operator) | NOT_APPLICABLE for MC; applies to customer tracks |

The packet's extra fault seeds (`:1307-1312`: killed monitor, corrupt receipt, prompt injection in
page text, racing workers, hidden paginated exception, duplicate payment callback, zero tests with
exit 0, stale cache after deploy) are all unassigned today; they belong to CP-04.

## 5. Everything else in the packet — placed or disposed of

| Packet item | Placement here |
|---|---|
| R01–R14 (spec §11, `:512-542`) | Portfolio contracts. Each is verified through its T-test (trace `:771-784`), so §4.3 is the MC status of all fourteen. |
| CP-00 authority/identity | Portfolio; D0 (RA-7818) and O6's lane reconciliation are MC inputs. |
| CP-01 ten-track inventory | Portfolio; MC's contribution is [coverage-register.md](../mission-control/coverage-register.md). |
| CP-02 Customer Promise Registers | MC-PROMISE: [promise-register.md](../mission-control/promise-register.md). |
| CP-03 environment and provider-lane admission | RA-7832 secrets; Jev admission (O5). |
| CP-04 evidence adapter + self-tests | Idea-to-live gaps and §4.3 gaps feed it; Jev triage is an advisory input only. |
| CP-05 Linear projection | O8. Needs a separate write grant. |
| CP-06 golden-path pilot | Not chosen. MC is a candidate (single operator, no payments), not a decision. |
| CP-07 staged release + RANA handover | MC-RELEASE. |
| CP-08 adapters and portfolio delivery | Portfolio; nothing MC-specific. |
| CP-09 monitoring, regression, cleanup | MC-OBSERVE (WP-11 nightly run); retention below. |
| Milestones M0–M4 (plan §6, `:748-760`) | Programme-level. MC's part of M0 is the register plus a next release contract (not yet written). |
| Founder view (spec §10, `:496-500`) | **Mission Control is the natural home** — it is already the founder cockpit. Recorded as a future MC surface, not built; it must show evidence age and avoid a single portfolio percentage. |
| RANA view (`:502`) | Needs RANA's identity and hours, which this repo does not hold (`:1895`). Not assumed. |
| R0–R4 (production-live, `:1474-1495`) | MC is at **R0 at most**: identity and inventory exist, next release scope does not. R1 needs the MC browser suite (WP-06/07) and the independent audits. |
| Common customer journey (testing §4, `:1173`) | Mostly NOT_APPLICABLE to MC (no signup, payment or cancellation); applies to customer tracks. |
| Connector proof ladder (testing §6, `:1257`) | Adopted as the vocabulary for MC's integrations (Linear, Supabase, Railway, Jev) when WP-06 records them. |
| Separate commercial / technical / operational / authority states (intent §9, `:276-277`) | Founder-view fields; not modelled in MC yet. |
| P0/P1 severity (production-live §5, `:1584`) | The packet says reconcile with an existing policy first; no repo-wide severity policy was found in this pass. Reconcile at CP-00. |
| Retention and cleanup (production-live, `:1640-1644`) | Existing: `TAO_GC_MAX_AGE` for sessions (CLAUDE.md). No policy for receipts yet; the packet's default (preserve and report) applies. |
| Controlled fleet expansion (plan §5, `:732-744`) | Overlaps the existing `mesh/` fleet code (`fleet_state.py`, `claim_lifecycle.py`, `heartbeat.py`). Reuse it; do not build a second orchestrator (CP-08 exit rule). |

## 6. Corrections the repo can supply to the packet

Factual, from this repo, for the packet's next revision (not edits to the imported copy):

1. **I07 / spec §6 — "local SPM path returned 404".** `.claude/skills/spm` is a git symlink
   (mode 120000) to `.agents/skills/spm`; the GitHub file API does not follow symlinks, so the
   fetch 404s while the skill is present. Re-derive: `git ls-files -s .claude/skills/spm`.
2. **MC has been assessed, at shallow depth.** A 20-row evidence register exists
   ([coverage-register.md](../mission-control/coverage-register.md)): 0 VERIFIED, 18 PARTIAL,
   1 STRUCTURAL_ONLY, 1 CONFLICTING. Eight defects where a screen showed a failure as a normal
   state were repaired — 2 merged in PR #809, 6 in PR #818 awaiting merge. Seven of the eight have
   a test shown failing before the fix; the eighth (MC-00, the ZTE score) was a missing route and
   has route tests only.
3. **Jev reachability.** This cloud environment cannot reach `api.typesafe.ai` (proxy 403,
   28–29 Sept). Admission needs a runner with egress (RA-7832).

## 7. Register of inputs

| Input | Received | Layer | Home | Status |
|---|---|---|---|---|
| Model and plan routing (28 Sept) | 28 Sept | 1 Method | plan-to-done `references/model-and-plan-routing.md` | Imported; reconciled in [routing-reconciliation.md](../idea-to-live/routing-reconciliation.md) |
| plan-to-done v1.1 package | 28 Sept | 1 Method | [plan-to-done-v1.1/](../plan-to-done-v1.1/README.md) | Imported, quarantined; v1.2 fixes RA-7819 |
| Idea → live pathway | 28 Sept | 4 Pathway | [idea-to-live/](../idea-to-live/intent.md) | Written; gaps ticketed (O8) |
| Mission Control AAA plan | 28 Sept | 3 Track (MC) | [mission-control/](../mission-control/README.md) | Written; now the MC instance of this packet |
| Mission Control readiness plan (19 Sept) | earlier | 3 Track (MC) | `docs/plans/mission-control-readiness*.md` | Superseded as the plan; kept as evidence (its "never manufacture a readiness score" rule is carried into aaa-rating.md) |
| Mission Control Jev next five (earlier) | earlier | 3 Track (MC) | `docs/plans/mission-control-jev-next-five.md` | Source of MC's accepted outcome statement (README.md); Jev parts superseded by jev-decision-contracts.md |
| NEXUS-RELEASE-HARNESS v1.0 | 29 Sept | 2 Portfolio | this folder | Imported (truncated); adopted by this file |
| /spm v2.0 — one command, one mission | 29 Sept | 3 Track (MC), with a Method-layer change routed to skills-library | [spm-mission-design-v2.0-as-received.md](../mission-control/spm-mission-design-v2.0-as-received.md) | Text imported; package (source ledger, acceptance cases, candidate skill) not received; adopted by O10–O17 |
| MC Customer Promise Register | 29 Sept | 3 Track (MC) | [promise-register.md](../mission-control/promise-register.md) | Written (33 promises, 0 proven) |
| *next input* | — | classify first | — | add a row here and an O-row in §3 before any new file |

## 8. Open items

- **Founder decision (money): Jev budget.** Does "no daily cap" override the packet's rule that a
  budget is recorded before any Jev call? Interim: dry-run only (O5).
- **/spm v2.0 package:** the source ledger (S1–S5), `acceptance-cases.json` and the candidate skill
  were referenced but not received. S1 and S5 are confirmed from this repo (O11, O14); S2 matches the
  quarantined plan-to-done; S3 and S4 are outside this repo and unverified here.
- **Complete the packet:** Parts 12–13, the rest of source I10, and sources W01–W12 were cut off in
  transit. Send the modular ZIP; it replaces the as-received file and is hash-checked like
  plan-to-done.
- **Canonical home:** the packet names Unite-Group governance and P-UNI-39. If it is also filed
  there, keep one copy canonical and make the other a pointer — do not maintain two.
- **Admission gates the packet lists** (independent planning review, engineering gate, runtime
  baselines, entitlement checks) remain NOT_RUN. First execution package after admission: CP-00.
