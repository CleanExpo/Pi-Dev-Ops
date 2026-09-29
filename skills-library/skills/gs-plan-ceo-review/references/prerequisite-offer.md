# Prerequisite Skill Offer + Mid-session detection

$SLUG and $BRANCH, and the design doc check, are in SKILL.md.

When the design doc check prints "No design doc found," offer the prerequisite via
AskUserQuestion (recommend A for a new product idea, B for a well-formed plan):

> "No design doc found for this branch. `/gs-office-hours` produces a structured problem
> statement, premise challenge, and explored alternatives — it gives this review much
> sharper input to work with. Takes about 10 minutes. The design doc is per-feature,
> not per-product — it captures the thinking behind this specific change."

- A) Run /gs-office-hours now (we'll pick up the review right after)
- B) Skip — proceed with standard review

If they skip: "No worries — standard review. If you ever want sharper input, try
/gs-office-hours first next time." Then proceed normally. Do not re-offer later.

If A: say "Running /gs-office-hours inline. Once the design doc is ready, I'll pick up
the review right where we left off." Read `~/.claude/skills/gs-office-hours/SKILL.md`
(if unreadable: "Could not load /gs-office-hours — skipping." and continue). Follow it
top to bottom, skipping its Estate rules block (already handled here). When it
completes, re-run the design doc check; if a doc is now found, read it and continue.

**Mid-session detection (0A):** If the user cannot articulate a stable problem, says "I'm not sure"
or is exploring rather than reviewing, offer `/gs-office-hours`:

> "It sounds like you're still figuring out what to build — that's totally fine, but
> that's what /gs-office-hours is designed for. Want to run /gs-office-hours right now?
> We'll pick up right where we left off."

Options: A) Yes, run /gs-office-hours now. B) No, keep going.
If they keep going, proceed normally — no guilt, no re-asking. If A, load it as above,
note current Step 0A progress so you don't re-ask questions already answered, then
re-run the design doc check and resume the review.

