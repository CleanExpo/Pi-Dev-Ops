# Senior Harness: governed Grill-Me entry and advisory board

Moved from the Usage section of SKILL.md. Read only for Grill interactions or board composition.

### Governed Grill-Me entry

First create or select a fat-marker sketch in the real Obsidian vault's `Sketches/` directory. Then
freeze the Grill interaction explicitly:

```bash
python ~/.codex/skills/senior-harness/scripts/setup_driver.py start \
  "/grill-me <literal project objective>" --project "<git-root>" --surface codex \
  --interaction grill-me
```

Use `grill-with-docs` for an existing codebase. Build a dependency-ordered decision-tree JSON, then
start the session with `grill_session.py start`. Keep its state below
`$SENIOR_HARNESS_STATE_DIR` or `~/.local/state/senior-harness/`; never store control state in the
project. The machine exposes an evidence query or exactly one human question. Human questions must
carry a recommendation and rationale. Record the user's words verbatim as `DECIDED`, `RABBIT_HOLE`,
or `NO_GO`. Confirmation requires the exact phrase printed by the driver and cannot succeed while a
leaf is unresolved. Only then may `materialize` write the bound transcript under the vault's sibling
`Grills/` directory.

Load [`references/grill-contract.md`](grill-contract.md) for the state schema and authority
boundary. A shared-understanding receipt proves the interview resolved; it grants no mutation,
business, financial, privacy, deployment, or irreversible authority.

### Post-Grill advisory-board composition

After — and only after — a Grill session carries a valid `grill-shared-understanding` receipt, a
strategic task may prepare a five-persona advisory-board **proposal**. It is a decision-support
input, not a delivery, hiring, or agent-activation authority:

```bash
python ~/.codex/skills/senior-harness/scripts/advisory_board.py init \
  --grill-session CONFIRMED_GRILL.json \
  --task-id BOARD_TASK_ID \
  --decision-question "<bounded decision>" \
  --data-class internal \
  --max-cost-usd 20 \
  --deadline-seconds 900
```

The proposal fixes five complementary functional personas: outcome, systems, customer value, risk,
and economics. For each role, approved discovery lanes must benchmark at least two functional
candidate profiles before proposing one. They are prompt cards, not real people, celebrity
simulations, personality diagnoses, or psychometric profiles. A later routed run must return exact
provider/model/usage receipts, five independent first passes, at least two provider families, no
model reuse across personas, an anonymised claim ledger, and an independent top-floor arbiter.
Missing telemetry, silent fallback, an unsourced fact, or unresolved critical risk returns no
decision.

Before any provider dispatch, resolve and bind one approved route for every persona and the arbiter
with `advisory_board.py bind-routes`. Each route fixes provider family, exact model, endpoint,
execution location, provider-registry identity, policy digest, and reserved cost. Every later run
receipt must reproduce those values plus observed token usage and cost; a mismatch is blocked.

`advisory_board.py verify-run` proves only that a supplied run receipt meets the protocol. It never
activates a board, a persona, a worker, or a delivery task. Activation requires independent
verification and explicit owner approval in a trusted authority runtime. Do not administer or claim
Belbin, Hogan, or any other proprietary psychometric assessment; use the custom evidence and
capability matrix in [`references/advisory-board-contract.md`](advisory-board-contract.md).

When the confirmed Grill objective explicitly requests advisory-board composition, create this
proposal before routing board candidates or any downstream delivery. Do not auto-create boards for
unrelated Grill sessions, and do not route provider work until the proposal passes `lint`.
