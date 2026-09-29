# Close the current review phase

Read this section afresh when the current phase's review work finishes. Use the
phase, amendment checkpoint and methodology path bound at that phase's exit.
This procedure owns readback, verification and publication as separate operations.

1. **Finish and save the review.** Require the phase's full methodology/section
   Reads, required outputs, successful writes and terminal reviewer results.
   Match a completed native review's INPUT to its voice snapshot. A pending
   reviewer keeps the phase open. Apply the phase's failure policy to failed
   native attempts; unavailable/disabled voices receive no completion credit.
2. **Reconcile accepted requirements.** Record every accepted behavior, condition,
   test and manual checklist in this phase's accepted block. Taste remains
   provisional; User Challenges preserve the original requirements. A `None`
   record must explain why the implementation remains unchanged. Keep the
   amendment checkpoint fixed for this invocation, including after compaction.
3. **Prepare this phase's close packet.** Build it with references/snapshot.md,
   section D, using the exit's phase and checkpoint. This applies nothing by itself:
   write accepted requirements into `## Implementation plan` first, then build the
   packet. It is an immutable input to steps 4–6 below; preparation does not perform them.
4. **Read the complete current packet.** Read `$PACKET` from line 1 through EOF
   (the command printed its line count), in ranges if needed. Finish all ranges. A Read of only the edited tail does not satisfy
   this step; previous snapshots do not satisfy it. If a result is truncated, read
   its missing ranges. If a Read fails, repair it and finish the missing ranges.
   Do not advance on a request without its result. After the final successful Read,
   perform step 5 here.
5. **Verify the current implementation.** Compare the complete current implementation
   with accepted decisions, source requirements, conditions, tests and required outputs.
   Retention checks prove bytes; counts, hashes, keyword probes and a saved “Read-back”
   sentence do not perform this semantic review. Review history stays in Review record.
   Recheck step 1's prerequisites. If any prerequisite is incomplete, keep this phase
   open and finish the missing work. Fix omissions, then regenerate the packet with
   the same checkpoint and Read the entire new packet before publication. Any later
   implementation or accepted-decision edit returns to step 3, including after compaction.
6. **Publish the parent report.** After successful verification, SEND the filled
   report below now as visible parent assistant text, using actual findings and voice
   statuses. This message is the next operation before any next-phase tool call.
   Use the packet's `report` fields for this phase, the actual host's reviewer names,
   and N/A when either review voice is missing; confirmed counts require both voices.
   Use the report fields table in references/snapshot.md, section D.

**Phase <report.number> complete.**
Outside review: <completed: N concerns / unavailable / disabled>. Native subagent: <completed: N issues / unavailable>.
Consensus: <N/A (voice coverage missing) | X/<report.total> native+outside confirmed; Y disagreements → gate>.
Passing to <applicable report.next>.

7. **Return to the driver.** After sending the actual parent report, continue to
   the driver in the same turn. The driver alone advances phases and emits applicable
   skip messages; a skip is never a completion. Do not wait for a “continue” reply.

The sent conversation message is step 6's output. Saving it in ACTIVE_PLAN or
printing it through Bash does not publish it. After compaction, reconcile the bound
packet and actual sent messages: a verified phase without its announcement resumes
at step 6; stale inputs return to step 3. A helper result or Read completes neither
verification nor publication.
