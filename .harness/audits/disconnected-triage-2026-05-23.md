# Disconnected-Skill Triage — 2026-05-23 (audit-only, propose-never-modify)

Read-only triage run on `main` @ launch-crew-merged state. Nothing modified, nothing committed,
no skill rewired. This is a MAP for human approval, not a cleanup.

## Method (evidence basis)
A skill is "statically disconnected" if, on current `main`, it is: not in `_INTENT_SKILLS`
(auto-routing), not referenced by name (hyphen or underscore) in `src/ swarm/ app/ mcp/ scripts/`,
not cross-referenced by another SKILL.md, and not a manifest dependency. Each candidate was then
checked repo-wide for **dynamic-by-name invocation** (string literal in code/config) and for a
**superseding code implementation** (a `swarm/bots/<role>.py` that implements the capability).

## Freshly re-derived list (NOT trusting the prior paste)
8 skills (not 9). `analyzing-customer-patterns` is **no longer** statically disconnected on current
`main` (it now has a reference), so it drops off the list.

## Verdicts

| Skill | Verdict | Evidence | Recommended action (for approval) |
|---|---|---|---|
| **curator-scheduled-tasks-unknown** | **ABANDONED** | `status: proposed`; auto-generated "-unknown" name; zero refs outside its own SKILL.md + manifest; overlaps the existing `scheduled-tasks` skill | **Retire** (or finalize + rename + merge into `scheduled-tasks`). Strongest cleanup candidate. |
| **margot-sandcastle-bridge** | **NEEDS-DECISION — built-disconnected (spec-only)** | wave-5 skill that claims "this is what makes Margot autonomous", but `swarm/bots/margot.py` is only 74 lines with **no `sandcastle` implementation**; margot is **not** in the orchestrator bot list (`orchestrator.py:142` = cfo, cmo, cto, cs). The autonomy flow it describes is **not wired**. | **Decide:** build the bridge (research→Linear→autonomy→sandcastle-runner) or label the skill `status: proposed`/not-yet-implemented so it stops reading as live. |
| **cmo-growth** | **NEEDS-DECISION — live via code bot** | Spec for `swarm/bots/cmo.py` (279 lines), imported + run by `orchestrator.py:140-142,304`. Capability is LIVE; static-orphan only because the bot is hardcoded, not loaded via the skill router. | **Keep.** Optionally cross-link skill↔bot. Not a deletion candidate. |
| **cs-tier1** | **NEEDS-DECISION — live via code bot** | Spec for `swarm/bots/cs.py` (236 lines), orchestrated alongside cmo/cfo/cto. | **Keep.** Same as cmo-growth. |
| **ui-ux-pro-max** | **NEEDS-DECISION — intentional manual** | `automation: manual`, `intents: design, feature, review`. Explicit-invoke by design; correctly NOT in auto-routing. | **Keep.** Disconnected-from-auto-routing is intended. |
| **tao-skills** | **NEEDS-DECISION — intentional index** | Description: "Master index of all 31 TAO skills"; referenced as the index in `README.md` + `.harness/spec.md`. Reference doc, not meant to be invoked. | **Keep** as documentation/index. |
| **claude-runtime** | **NEEDS-DECISION — reference doc** | "Rules for invoking Claude correctly (subprocess vs SDK)"; doc-only mention in `spec.md`; likely overlaps `claude-max-runtime`. | **Decide:** keep as reference vs merge into `claude-max-runtime`. |
| **product-manager** | **NEEDS-DECISION — possibly redundant** | Senior-PM persona; no code bot; doc-only mention in `spec.md`. Overlaps the new PM lens in `launch-review`. | **Decide:** retire as redundant vs keep as a manual reference persona. |

## Headline
**Only 1 of 8 is genuinely abandoned** (`curator-scheduled-tasks-unknown`). The rest "only looked
disconnected": 2 are live via orchestrated code bots, 2 are intentional manual/index skills, 2 are
reference docs awaiting a keep/merge decision, and 1 (`margot-sandcastle-bridge`) is a real
built-disconnected spec — written but not wired. **No dynamically-invoked-by-name skills were found**
(the personas are implemented as code bots, not loaded by name).

## Other built-disconnected items surfaced (report-only)
- **`hermes-plugins/`** — present in the repo but not loaded by repo runtime (0 code refs to the
  plugin path; no loader). It mirrors `~/.hermes/plugins/`; only `unite-group/` exists. (Re-confirmed.)
- **`margot-sandcastle-bridge`** (above) is itself a built-disconnected *spec*.
- `analyzing-customer-patterns` left the disconnected set vs the prior run — now has a reference;
  no action needed, noted for accuracy.

## Recommended next step (for human approval — NOT done here)
Approve a single low-risk action: retire/merge `curator-scheduled-tasks-unknown`. Defer all others
to a deliberate keep/link/build decision. No skill should be deleted or rewired without sign-off,
and not before credential isolation + sandbox are in place.
