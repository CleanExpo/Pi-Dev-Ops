# Proof Discipline: thesis, repair path and negative controls

Moved from SKILL.md. Read in full before trusting a green control or repairing a failing one.

## THE THESIS — a control's health tells you about the control's AIM, not about the world

Every structural limit above is an instance of one statement:

> **A green control reports that the control found nothing where it looked. It says nothing
> about whether it looked at the right thing.**

Health and correctness are different claims, and a control can only ever make the first. The
second requires knowing the aim was right, which no control checks about itself.

**Four instances, all found on 2026-08-02, in unrelated systems:**

1. **The kill switch displayed `state: "OFF"`.** That value came from `fallback()` after the
   upstream call failed. The dashboard reported the swarm as stopped because it could not ask,
   and "OFF" is the reassuring answer. A failure rendered as a reading.
2. **Control 1b hashed the wrong file.** It existed to detect a reviewer widening its own
   permissions, and it watched `~/.codex/config.toml`. The permissions lived in
   `~/.codex/hooks.json`. It reported "unchanged" truthfully, all day, about a file that did
   not hold the capability.
3. **The smoke contract certified the hole.** `kill-switch-status-nosig` asserted
   `expected_status: 200` for an unauthenticated GET, and the route's own comment cited that
   surface as the reason the GET could stay public. The test justified the code and the code
   justified the test. Neither referenced a requirement.
4. **A positive control passed on a wrong target.** Searching for `middleware.ts`, finding
   none, and confirming the glob worked — while Next.js 16 had renamed it `proxy.ts`. The
   instrument was verified; the aim never was. See failure mode 7.

**What follows.** Ask of any green check: *what would this look like if it were pointed at
nothing?* If the answer is "the same", you have measured the instrument, not the world. The
escape is always the same shape — go around the check and ask reality directly. Every one of
these four was broken open by an external observation, never by more careful reading of the
same source.

## THE REPAIR PATH REMOVES THE CONTROL

A control fails honestly. The obvious repair is reasonable. Applying it deletes coverage, and
the suite goes green with **less** protection than before the failure.

This is the nastier sibling of *the test that encodes pre-fix behaviour*. There, the test
argues for reverting the fix, and the argument is visible — you can see the test defending the
bug. Here nothing argues with you: the failure is genuine, the repair is correct-looking, and
the loss is silent.

**The instance (2026-08-04, Pi-Dev-Ops).** The API auth classifier walked `app/api` with a
hardcoded `/api` URL prefix. Moving a route out of that root made it **undiscovered, not
unclassified** — and "every surface is classified" only inspects what was discovered. What
*did* fail was phantom detection: declared entries with no handler on disk. The obvious repair
is to delete the stale declarations. Do that, and the moved routes — the ones about to be
exposed at a public front door — are outside classification entirely, with a green suite.

**Ask, on every failing control, before repairing it:** *does this repair restore the
property, or only silence the report?* If the fix is "delete the assertion / delete the
declaration / narrow the scope", you are removing the control. Repair the aim instead.

**Two corollaries earned in the same change:**
- **A floor cannot detect a relocation.** `SURFACES.length > 10` passed at 28 surfaces while
  the moved ones were invisible; the survivors hold the count up. Replace floors with a
  **relocation canary** — plant an artefact on the surface the claim covers, outside the old
  scope, and require discovery to find it. Prove it both ways: narrow the scope, watch it fail
  by name; restore, watch it pass.
- **Discover by what a thing IS, not where it lives.** A walk root is a fixed list of one, and
  adding a second root makes it a fixed list of two. A fixed list is legitimate only when it
  enumerates *rules*, never *surfaces*.

### Negative controls: use the tool, do not hand-roll it

A mutation that silently fails to apply reads exactly like a control that is working. This
recurred three times before being wired, which is the signal that prose was the wrong
container — **a lesson that keeps recurring does not need restating, it needs a tool.**

    ~/.claude/skills/proof-discipline/mutate-assert.py \
      --file <path> --find <regex> --replace <text> --run "<cmd>" --expect-fail

**Three answers, not two.** Exit 2 means the target never matched and **nothing was run**.
Exit 3 means the mutated program did not RUN - a syntax, name or import error the mutation
itself introduced. Exit 1 means the control stayed green with its subject broken, which is
the real finding. Under `--expect-fail` a crashing mutant makes the command fail, so before
exit 3 existed it printed *PASS - the control fired* over a program that never ran. The tool
re-runs the ORIGINAL when it sees a crash signature, so a command that was already broken is
reported as such rather than credited to the mutation. The file is restored byte-identically
in a `finally`, so it will not renormalise line endings. Do not open-code a
mutate-run-restore loop; that is the exact shape that failed.

