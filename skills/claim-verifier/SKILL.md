---
name: claim-verifier
description: The runnable cite-or-cut gate for FINISHED Nexus copy — walks every checkable factual claim in a completed asset, resolves each to a substantiation record or cuts it, runs the Australian Consumer Law excluded-tactics deny-list, and freezes the Substantiation Ledger before publish. Use as the last gate before any copy asset ships — landing page, service page, ad, email, franchise-recruitment copy. Triggers on "cite-or-cut", "substantiate this copy", "claim check", "can we publish this", "freeze the ledger", "is every claim proven", "ACL check the copy". NOT research (that is `storm`), NOT trust scoring (that is `eeat`).
---

# claim-verifier — the cite-or-cut gate

The runnable enforcement of the Nexus doctrine's spine: **an unprovable claim cannot
physically reach publication.** It takes a *finished* draft plus its substantiation set and
returns one of two things — a frozen, ship-ready **Substantiation Ledger**, or a **cut-list +
BLOCK**. It executes doctrine gates **3 (cite-or-cut)**, **4 (excluded-tactics)** and **6
(freeze ledger)** as a repeatable audit. The ledger schema and the full Excluded-Tactics list
are defined in [`../nexus-copywriter/references/DOCTRINE.md`](../nexus-copywriter/references/DOCTRINE.md); this skill is the *procedure* that runs them.

## Why this is not an existing skill
- **`storm`** sources facts *forward* (research → a new cited article) and is explicitly not for
  marketing copy. This audits finished copy *backward* — each existing claim → its record. storm
  is doctrine stage 0; this is stages 3/4/6.
- **`eeat`** *scores* trust signals holistically ("does this look credible") and **advises, does
  not gate**. It never walks each claim to a record, never *cuts* the unprovable, and enforces no
  claim law. This is a hard, per-claim gate with Australian Consumer Law inside it.
- **`specialist-council` / `boardroom`** deliberate and triangulate *decisions*; neither checks
  a claim against evidence.
- **`marketing-copywriter`** writes the words; this verifies them.

## When to use
- The final step before any Nexus copy asset ships, once craft + eeat are done.
- Any time a claim's basis may have lapsed (review count, SLA, certificate, price history) and
  the frozen ledger must be re-verified.

## When NOT to use
- Before facts exist — source them first via `storm` (doctrine stage 0). This gate assumes a
  substantiation set is already on file.
- Pure trust/authorship polish → `eeat`. Pure wording → `marketing-copywriter`.

## Inputs
- **draft** — the finished copy. Ideally claim-tagged from doctrine stage 2; if untagged, this
  gate tags it in step 1.
- **substantiation set** — the records on file: invoice/dispatch-log exports, review exports,
  certificates, test results, dated price history, licence numbers, credential docs (storm
  output + client records). A record is a URL or document ID, **never a memory**.

## Method

### 1. Extract & tag every checkable claim
Read the draft sentence by sentence. Give every sentence that asserts a **checkable fact** a
`Claim-ID`. Mark obvious subjective opinion as **puffery** (untagged, legal, but never counted
as proof). Flag **forward-looking** claims ("we'll save you X", "on-site within 60 min") — they
need reasonable grounds *held at publish time*, not just a past record.
- **Completion:** no factual sentence is untagged; every non-puffery sentence has a Claim-ID.

### 2. Cite-or-cut — resolve each Claim-ID to a record
Walk every Claim-ID against the substantiation set. Each resolves to exactly one outcome:
- **has a concrete record** → keep, cite inline, carry the record into the ledger;
- **no record, or only round-number/"trust-me"/legend** → **cut** (delete) or **demote to
  puffery** if a subjective rephrase is honest. No "verify later", no "probably".
Superlatives ("best / #1 / fastest / most trusted") need *dated, provable* evidence or they are
cut on sight.
- **Completion:** every Claim-ID is either recorded or on the cut-list. Zero unresolved.

### 3. Excluded-tactics / ACL deny-list pass
A claim can be truthfully *sourced* yet *deployed* illegally. Run the draft against the
Excluded Tactics + quick-deny list in [`../nexus-copywriter/references/DOCTRINE.md`](../nexus-copywriter/references/DOCTRINE.md) — invented urgency /
resetting timers / phantom scarcity; "was/now" without a genuine prior sale period; fake,
connected-undisclosed, or incentivised-undisclosed reviews; unqualified green/"Australian Made"
claims; non-Code-compliant franchise earnings implications; material silence that changes the
overall impression (s18 needs no intent). Any hit is a **hard stop** — the tactic is removed,
not softened.
- **Completion:** no deny-list hit survives in the draft.

### 4. Set expiry / review dates
Substantiation decays. Assign each shipping claim a **review/expiry date** — reviews +90d, SLAs
and response-time promises per current ops, certificates per their expiry, price history per the
next price change.
- **Completion:** every shipping claim carries an expiry.

### 5. Freeze the ledger & emit the verdict
Produce the **Substantiation Ledger** (`Claim-ID | claim text | record/basis-at-time | expiry`)
and a verdict:
- **SHIP-READY** — every claim recorded, deny-list clean, ledger frozen and attached to travel
  with the asset for its life.
- **BLOCK** — a cut-list of every claim removed/demoted and every deny-list hit, with what
  record or rewrite would clear it. The asset does not ship until re-run clean.
Apply the **skeptic test**: a skeptical regulator, journalist, and customer each fact-check the
piece line by line. If any claim can't survive all three, it is not SHIP-READY.
- **Completion:** ledger frozen or cut-list returned; a verdict is emitted.

## Hard rules
- A claim with no ledger row does not appear in the copy. Full stop.
- The gate cannot be waived by deadline, client pressure, or a good-sounding line.
- A record is a source URL or document ID — never a memory, never a round number.
- This gate *verifies*; it never writes new claims or invents records. Missing facts go back to
  `storm`, not into the ledger.
