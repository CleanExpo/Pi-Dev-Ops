# Adopting NEXUS-RELEASE-HARNESS v1.0 without duplicating what exists

**Date:** 29 September 2026. **Packet:** [packet-v1.0-as-received.md](packet-v1.0-as-received.md)
(DRAFT_FOR_INDEPENDENT_REVIEW; truncated on receipt — see §6).
**Status of this file:** adoption decisions, made so the packet becomes the layer *above* the work
already in this repo rather than a second copy of it. Nothing here grants build, Linear-write or
release authority; the packet's own admission gates still apply.

## 1. The one rule for this and every later input

Every planning input lands in exactly one of four layers, and extends the layer below it by
reference. A new input may add rows, replace a definition (saying so here), or record a conflict.
It may not start a parallel tree for something a layer already owns.

| Layer | Owns | Canonical file(s) |
|---|---|---|
| **1. Method** — how plans are written | Planning procedure, evidence states, review ladder | [plan-to-done v1.1](../plan-to-done-v1.1/plan-to-done/SKILL.md) (candidate) + existing `/spm`, engineering-requirements (skills-library) |
| **2. Portfolio** — all ten tracks | Programme packages CP-00…CP-09, AAA rubric, release stages R0–R4, RANA support model, Linear pathway, harness acceptance tests T01–T14 | **This packet** |
| **3. Track** — one product | That product's inventory, promises, control set, work packages | [mission-control/](../mission-control/README.md) is the **MC track** instance |
| **4. Pathway** — idea → live lifecycle | Stage evidence and breaks between stages | [idea-to-live/](../idea-to-live/pathway.md), mapped onto the canonical UNI-2517 lifecycle |

The next input you send is classified into one layer, gets a row in §5, and its overlaps are
resolved here before any file is added.

## 2. What the packet adds that did not exist here

- **Portfolio scope:** ten tracks (DR, NRPG, HALL, RA, CARSI, SYN, ATO, CCW, UG, MC). This repo
  only ever planned MC.
- **Customer Promise Register** (intent §4): every advertised capability must have a working
  journey, support and current evidence. New concept for MC.
- **Staged release R0–R4 and RANA support model** (production-live.md). Nothing equivalent here.
- **Two-provider independent audit** as a release requirement (scoring §4). Here it was only
  recorded as `NOT_RUN`.
- **Harness self-tests T01–T14** (testing §7): the harness must reject seeded false-greens before
  its results count.
- **Receipt model** (engineering §1): evidence tied to candidate SHA, artifact, config and schema
  digests, invalidated when any changes.
- **Critical-path method** (plan §4): unknown durations stay unknown; resource-constrained
  forecast reported separately.

## 3. Where it overlaps existing work — decision for each

| # | Topic | Already here | Packet | Decision |
|---|---|---|---|---|
| O1 | **AAA meaning** | [aaa-rating.md](../mission-control/aaa-rating.md): per-surface tiers A/AA/AAA, lowest surface sets the grade, 3 nightly runs | scoring.md: weighted evidence score 100/100 over frozen control groups, mandatory blockers outside the score, **AAA-RELEASE-READY** and **AAA-LIVE-VERIFIED**, two independent audits | **Packet's rubric is the only AAA.** The MC file is re-expressed as the MC track's *control set*: its checks become control groups under the packet's six dimensions, and its tiers are renamed Levels 1–3 so "AAA" has one meaning. Crosswalk in aaa-rating.md. |
| O2 | **Evidence vocabulary** | Register rows: VERIFIED / PARTIAL / STRUCTURAL_ONLY / MISSING / UNKNOWN / CONFLICTING (plan-to-done) | Receipts: PASS / FAIL / NOT_RUN / BLOCKED / STALE / NOT_APPLICABLE | **Both kept, different jobs.** Receipts record a single check; a register row's state is *derived* from its receipts: VERIFIED only if every required receipt is current PASS; any FAIL → CONFLICTING; NOT_RUN/BLOCKED/STALE → PARTIAL or UNKNOWN. |
| O3 | **Work packages** | MC WP-01…WP-12; idea-to-live gaps A–L | CP-00…CP-09 + per-track `P-DISCOVER → PROMISE → VERIFY → REPAIR → AUDIT → RELEASE → OBSERVE` | **MC WPs become the MC track's instance of that chain** (table in work-packages.md). No renumbering, no new tickets. Idea-to-live gaps feed CP-04 (evidence/anti-false-completion) and CP-07 (release + live proof). |
| O4 | **Lifecycle** | pathway.md 10 stages | UNI-2517 earned lifecycle `IDEA → … → POST_DEPLOY_VERIFIED → COMPLETE` | **UNI-2517 is canonical.** pathway.md keeps its evidence per stage and gains a column mapping each stage to the UNI-2517 state it earns. |
| O5 | **Jev** | Founder, 28 Sept: use Jev for large-scale Mission Control testing, **daily cap lifted**. [jev-decision-contracts.md](../mission-control/jev-decision-contracts.md); `scripts/jev_triage.py` (dry-run default, advisory only) | Jev optional advisory; "no live Jev call or paid activation is authorised **here**" (i.e. by the packet); admission needs pricing, provider, data handling, held-out benchmark; outputs `PROPOSE(candidate_id)` / `ABSTAIN` | **Compatible.** The founder instruction is the money and data-egress admission for MC test triage; the packet's remaining admission items (held-out benchmark before labels are trusted, deterministic route when disabled) are already in the contracts. Added: J1–J4 map `NO_MATCH`/low confidence to `ABSTAIN`, a chosen option to `PROPOSE`. Jev never counts as either audit reviewer. |
| O6 | **Model lanes** | Verified 28 Sept: Codex models are GPT-5.6 Sol/Terra/Luna; `gpt-6-sol` does not exist ([routing-verification](../idea-to-live/routing-verification-2026-09-28.json)) | Requests "GPT-5.6 family"; resolve exact IDs at admission | **Agree.** The packet already carries the correction. plan-to-done still pins `gpt-6-sol` (RA-7819). |
| O7 | **Merge / release authority** | D0 decided (RA-7818): Pi-Dev-Ops is human-merge-only; cross-model audit is evidence, not acceptance | Board release controller + signed mandate; nothing widened | **Agree.** Both say an audit receipt is not an approval. |
| O8 | **Linear** | Tickets in project Pi-Dev-Ops: RA-7832 (AAA blockers), RA-7811–RA-7822 (idea-to-live gaps), RA-7818/7819 | MC home = P-RA-21 (Pi-Dev-Ops) + P-UNI-45 (Mission Control); candidate parent P-UNI-39; stable dedup key `nexus-release:<project>:<release>:<fingerprint>`; no writes without a grant | **Reuse existing tickets.** On an authorised sync they are linked under the MC first-release epic with dedup keys; none are recreated. No Linear write is made by this adoption. |
| O9 | **Harness acceptance tests** | MC Level checks (e.g. "zero hidden 4xx/5xx", "label honesty", "no required unknown becomes green") | T01–T14 | **Mapped, not duplicated:** MC check 2 (no hidden 4xx/5xx) and check 12 (label honesty) → T06 (a success response without the intended effect fails); ungraded-until-evidence rule → T13; Jev budget ledger → T10 (without the paid-fallback part, now uncapped by founder decision). |

## 4. Corrections the repo can supply to the packet

These are factual, from this repo, for the packet's next revision (not edits to the imported copy):

1. **I07 / spec §6 — "local SPM path returned 404".** `.claude/skills/spm` is a git symlink
   (mode 120000) to `.agents/skills/spm`; the GitHub file API does not follow symlinks, so the
   fetch 404s while the skill is present at `.agents/skills/spm/SKILL.md`. Re-derive:
   `git ls-files -s .claude/skills/spm`.
2. **MC track state is richer than "NOT_ASSESSED".** MC already has a 20-row evidence register
   ([coverage-register.md](../mission-control/coverage-register.md)): 0 VERIFIED, 18 PARTIAL,
   1 STRUCTURAL_ONLY, 1 CONFLICTING, 8 false-state defects repaired with failing-first tests
   (2 merged in PR #809; 6 in PR #818, awaiting merge). That is MC-DISCOVER at shallow depth plus part of MC-REPAIR.
3. **Jev reachability.** The cloud environment used here cannot reach `api.typesafe.ai`
   (proxy 403, 28–29 Sept). Admission needs a runner with egress (RA-7832).

## 5. Register of inputs

| Input | Received | Layer | Home | Status |
|---|---|---|---|---|
| Model and plan routing (28 Sept) | 28 Sept | 1 Method | plan-to-done `references/model-and-plan-routing.md` | Imported; reconciled in [routing-reconciliation.md](../idea-to-live/routing-reconciliation.md) |
| plan-to-done v1.1 package | 28 Sept | 1 Method | [plan-to-done-v1.1/](../plan-to-done-v1.1/README.md) | Imported, quarantined; v1.2 fixes RA-7819 |
| Idea → live pathway | 28 Sept | 4 Pathway | [idea-to-live/](../idea-to-live/intent.md) | Written; gaps ticketed RA-7811–7822 |
| Mission Control AAA plan | 28 Sept | 3 Track (MC) | [mission-control/](../mission-control/README.md) | Written; now the MC instance of this packet |
| NEXUS-RELEASE-HARNESS v1.0 | 29 Sept | 2 Portfolio | this folder | Imported (truncated); adopted by this file |
| *next input* | — | classify first | — | add a row here and an O-row in §3 before any new file |

## 6. Open items

- **Complete the packet:** Parts 12–13 and sources W01–W12 were cut off in transit. Send the
  modular ZIP; it replaces the as-received file and is hash-checked like plan-to-done.
- **Canonical home:** the packet names Unite-Group governance and P-UNI-39. If it is also filed
  there, keep one copy canonical and make the other a pointer — do not maintain two.
- **Admission gates the packet lists** (independent planning review, engineering gate, runtime
  baselines, entitlement checks) remain NOT_RUN. First execution package after admission: CP-00.
