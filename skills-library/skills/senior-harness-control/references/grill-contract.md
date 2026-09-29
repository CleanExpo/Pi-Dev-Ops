# Senior Harness Grill-Me contract

This contract governs the shaping interview that precedes delivery. A Grill-Me session resolves a
real sketch; it does not authorize or perform delivery work.

## Intake binding

`start_session` requires all of the following:

- the literal, non-empty objective;
- an existing file under a `Sketches` root, bound by its resolved absolute path and
  SHA-256 digest;
- an explicit Markdown materialization path below the sibling `Grills` root; and
- a non-empty, acyclic decision tree.

Each leaf is typed as either `evidence-fact` or `human-decision`. Facts that an authoritative source
can answer must be resolved with an evidence receipt; they must never be presented as a business
choice. Human decisions alone carry a recommendation and rationale, both non-empty.

## Dependency and turn rules

The machine stable-topologically orders the leaves. It exposes only the first dependency-ready leaf.
An `interviewing` state contains exactly one `pending_question`; an `awaiting-evidence` state contains
exactly one `pending_evidence` query and no human question. A child cannot be answered before all of
its parents are resolved.

Human answers are retained verbatim and accept only these exact terminal labels:

- `DECIDED`
- `RABBIT_HOLE`
- `NO_GO`

Evidence answers are retained verbatim as `EVIDENCED` and bind at least one source ID and SHA-256
digest. This separate label prevents a discovered fact from masquerading as a human decision.

## Confirmation and materialization

The transcript and domain-language updates remain inside `buffer` throughout the interview. Before
confirmation, `materialization.content` is always null. Confirmation fails while any leaf is
unresolved and requires this exact, explicit phrase:

> I confirm this is our shared understanding.

Successful confirmation makes a Markdown payload available at `materialization.content`; the pure
state machine does not write it. The caller may write those exact bytes only to the receipt-bound
`materialization.path`. The path is already constrained beneath the sibling `Grills` root.

## Authority and integrity

Every transition validates the prior state's public integrity digest and returns a new value; it
does not mutate the caller's object. The confirmation receipt binds the objective, sketch path and
digest, resolved decision tree, transcript, domain updates, exact confirmation phrase, output path,
and output digest.

The session and receipt always carry:

```json
{
  "mutation_authority": false,
  "business_authority": false,
  "irreversible_authority": false
}
```

The receipt proves only that the bound interview reached shared understanding. It is not a mutation
lease, approval to implement, business approval, deployment approval, or irreversible-action grant.
