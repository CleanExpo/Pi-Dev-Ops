# Release lanes — who merges

The default lane stops for human merge. The sole founder-ratified exception is
`UG-AUTONOMY-001` (24/07/2026) for **CleanExpo/Unite-Group, CARSI and RestoreAssist**. In those
repositories only, an automatic merge controller may merge the exact reviewed PR head without
another routine founder confirmation when all of these bind to the same immutable final SHA:

- frozen acceptance criteria are complete;
- every independently defined deterministic required check is present, current and passing;
- every rejection is resolved and independently re-reviewed;
- Claude built and standalone Codex independently reviewed, or explicitly assigned different
  model families filled those roles;
- 100% of the eligible hash-bound Board roster approves;
- the deterministic constitutional verifier passes;
- no new or increased direct cost is introduced;
- no constitutional amendment is included;
- no required credential or privilege is missing;
- no unresolved authority conflict remains;
- branch protection and repository rules remain satisfied;
- rollback and post-action verification evidence are present; and
- the controller uses an exact-head compare-and-swap guard so head drift fails closed.

**The twelve conditions are not one class (founder, 03/08/2026).** Five are AUTHORITY
constraints — genuinely non-negotiable, no degradation path: no new/increased direct cost;
no constitutional amendment; no missing credential or privilege; no unresolved authority
conflict; rollback evidence for anything irreversible. The other seven (frozen acceptance
criteria, deterministic checks present and passing, rejections re-reviewed, dual-family
build/review, Board roster approval, constitutional verifier, branch protection, CAS
guard) are QUALITY constraints: when one is UNSATISFIABLE — not merely unsatisfied, e.g.
a roster member is structurally unavailable or a required check cannot exist for this
change class — the lane degrades to STOP FOR HUMAN MERGE with the unsatisfiable condition
named, rather than blocking forever. Twelve ANDs are twelve chances to be stuck; the
degradation path is the exit the P2 stopping rule proved this lane needs.

Any missing, stale, malformed, duplicate, ambiguous or mismatched evidence blocks the merge.
Failed checks and reviewer findings return to repair; they are not founder-approval requests.
New/increased cost, constitutional amendments, missing credentials/privileges, unresolved
authority conflicts, or irreversible actions without tested rollback still stop for Phill.
A candidate changing constitutional or release-authority controls cannot use the exception to
authorise itself. Outside the three named repositories, human merge remains mandatory.
`UG-AUTONOMY-001` changes only the final merge actor for its three named repositories; it does
not waive any gate.
