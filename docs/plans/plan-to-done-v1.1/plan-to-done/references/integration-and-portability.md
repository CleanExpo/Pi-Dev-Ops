# Adoption and portability plan

## Package boundary

This is an original planning-skill candidate and supporting design material. It contains no
installer, hook, service, runtime adapter, API client or credential. Saving the package as a
file does not install it on any machine or prove the planning workflow works.

The intended canonical home after review is CleanExpo/skills-library. Before activation,
keep the candidate in the Library's in-progress area or an approved review workspace. Do not
add it to the active catalogue merely because the files exist.

## Proposed adoption sequence

1. Re-read the current authoring standard, catalogue rules, upstream intake policy and repo
   release gate. Check for a new equivalent skill or name collision before importing.
2. Stage the candidate in the approved review location without touching active instructions.
3. Perform structural checks, baseline/with-skill evaluations and independent review.
4. Obtain explicit authority for the exact catalogue change and any associated repository
   operations. A planning acceptance does not authorise a push, PR, merge or machine install.
5. Follow the existing pre-PR and release lane. Do not relax its checks because the artefact
   is Markdown. The candidate must not modify the gates that decide whether it passes.
6. After promotion, register the canonical skill once. At the inspected snapshot the active
   catalogue is skills/README.md and entry points also receive one skills/index.md row.
   Do not invent a plugin manifest or duplicate the full skill body in an always-loaded file.
7. Use the existing governed distribution route and verify the same content revision on each
   target host. Do not overwrite local edits or run an upstream install script blindly.
8. Test manual invocation, reference loading, write boundaries and reporting on each supported
   host/agent before declaring the skill available there.

These are future adoption steps. None were performed while producing this package.

## Host contract

Mac Mini, MacBook and PC must resolve their own paths, tools and approved accounts. Do not
embed one user's home directory or a machine-specific absolute path. Native agent metadata
such as disable-model-invocation and allowed-tools must be tested on that host; other clients
may ignore fields or interpret them differently.

The user-invoked name plan-to-done is a proposed command after registration, not a shell
program or an existing command guaranteed to run today. On clients without slash-command
support, load the canonical SKILL.md through the established Library entry point.

## Writing permission

Write/Edit tools are needed because the skill produces documents. They do not mean all paths
are permitted. Host controls must restrict project-plan writes and delegated reviewers.
No shell permission is declared by default. Where approved read-only repository commands or
existing document validators are necessary, use the host's separately permitted capability.
If it is unavailable, record the missing check rather than granting a broad shell exception.

Review agents receive read-only inputs and can return findings; the main writer owns the
planning packet. Do not let reviewers mutate product code, test oracles, grants or benchmarks.

## Existing-source tensions discovered

The repository AGENTS.md contains broad historical language about straightforward document
sync, while the inspected pr-release-gate defines strict pre-push and pre-PR checks. Do not
interpret the former as authority to bypass the latter. Resolve any real conflict through the
current authority hierarchy, preserving both records until an authorised reconciliation.

SPM's APPROVE BUILD wording and perfect-score criterion are planning/review language, not
human authority. This candidate explicitly separates check results from grants without editing
SPM or silently redefining its required checks.

The authoring standard documents an operative two-place catalogue rule, while older passages
still mention an aspirational third plugin location. Verify actual files before registration.

## Independent rollback plan

If evaluation or host testing reveals regression, keep or restore the prior approved routing
entry and skill version using the authorised repo process. Retain candidate evidence and the
reason for rejection. Do not delete other skills, disable gates or activate Jev to compensate.
