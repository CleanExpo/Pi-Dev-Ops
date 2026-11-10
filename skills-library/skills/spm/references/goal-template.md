# Goal template

Emit only after the engineering gate exits 0 and the Done contract is locked.

```text
/goal Implement the accepted SPM spec at <spec path>. Completion condition: <observable end state>;
Done contract <id> verifies AC-1..AC-n on the exact final commit; <verification commands> exit 0.
Crew: <builder agent + model>; review via <lane> (never the builder's lane); gates on <node>.
Constraints: no unrelated files; no secrets; no destructive or production action; phases advance
only when their validation passes. Stop and run /session-handoff if blocked by credentials,
external access, founder-only decisions or a third repeat of the same defect class. Queue protected
actions (push, PR, merge, deploy, spend, outreach) for Phill in one batch.
```

A strong goal names one measurable end state, the proof command, the crew, the constraints, the
stop condition and the handoff condition.

Bad: `/goal Build the feature properly.`

Good: `/goal Implement the accepted SPM spec at ~/.local/state/gs/projects/CARSI/spm/2026-10-14-annual-checkout/spec.md. Completion condition: /pricing shows "Join — A$795/yr" and opens Stripe Checkout for price carsi_pro_annual; Done contract verifies AC-1..AC-6 on the final commit; npm run type-check, npm run test:unit and scripts/verify-go-live-readiness.mjs exit 0. Crew: crew-builder (sonnet); review via codex lane; gates on the mini. Stop and hand off if the DigitalOcean env change is still pending.`
