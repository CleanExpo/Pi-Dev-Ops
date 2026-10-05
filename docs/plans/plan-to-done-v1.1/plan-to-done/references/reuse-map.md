# Reuse map and capability boundaries

## Proposed composition

One new user-facing skill, plan-to-done, writes and reconciles the complete planning packet.
It does not introduce an orchestrator, scheduler, database or second completion engine.
Specialist methods are loaded on demand, not permanently attached to every task.

## Inspected and referenced capabilities

The source snapshot is recorded in source-ledger.md. A file being inspected establishes its
written contract, not successful installation or execution on the Mac Mini, MacBook or PC.

| Capability | Existing entry | Intended planning use | Evidence status |
|---|---|---|---|
| Skill authoring | skill-authoring-standard | Apply the Library's format and review requirements | Full skill and three supporting references read |
| Skill discovery | skill-selector | Find and selectively load relevant instructions | Full skill read |
| Intent capture | capture-intent | Preserve the five-section founder contract | Repository search exposed entry and parser contract |
| Project specification | spm | Reuse the established specification responsibilities | Full skill read |
| Engineering requirements | engineering-requirements | Cover data, invariants, failures, interfaces, concurrency, migration, recovery, observability, budget and test oracle | Skill read through its scope section |
| Strategic framing | nexus; judge; wayfinder; ceo-board | Reuse established strategic methods when the goal warrants them | nexus read; remaining entries referenced by selector |
| Plan writing | superpowers:writing-plans | Translate accepted specification into actionable packages | Referenced by selector; local resolution not verified |
| Skill evaluation | superpowers:writing-skills | Baseline and pressure-test the reusable planning skill | Upstream source read; installed local version not verified |
| Test/control design | control-design; proof-discipline | Specify falsifiable checks and honest evidence claims | Excerpts/selector references; full live behaviour not audited |
| Release planning | pr-release-gate; readiness-architect | Describe existing pre-PR and release obligations | Release skill read through reporting rule; readiness referenced by selector |
| Continuation | session-handoff; resume-from-handoff; goal-circuit-breaker | Write a resumable planning handoff and bounded loop policy | Referenced in inspected library entries; runtime not tested |
| TypeSafe design | typesafe-ai | Design optional typed questions and evaluation | Pinned upstream skill read; estate installation unknown |

## Upstream TypeSafe adoption

Do not create a second home for the same vendor skill. The existing skill-selector contract
uses reviewed external-source registration, exact commit pins and per-task loading from a
vault. Keep that intake route, unless a later authorised repository decision supersedes it.
Copying this planning skill does not install the upstream dependency or activate Jev.

## Do not add these as new skills merely to complete a diagram

Do not create another SPM, QA lead, build orchestrator, release gate or done judge. The new
responsibility is whole-project coverage reconciliation plus written handoff consistency.
Use domain specialists only where the project's risks justify them; names and role counts
are not evidence of independent review.

## Unresolved bindings to verify before adoption

- Resolve the live /goal implementation through the actual host command registry. A direct
  lookup at skills/goal/SKILL.md returned 404 at the inspected library snapshot, while SPM
  references /goal. This does not establish that the command is absent.
- Resolve Waterline's policy and auditor bindings independently of any similarly named intent
  entry command. Do not assume one command name proves every role mentioned in older plans.
- Read the installed versions of referenced external skills and relevant host permissions.
- Confirm the canonical project planning path and the current engineering validator invocation.

These are integration checks, not permission to build new replacements or block all planning.
