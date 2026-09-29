# The ten categories — worked examples

Every example below is lifted from `~/ug-hermes-board-design/spec.md` §6 (Authority-Site CRM),
the one spec in this estate that already does this properly. It is the calibration exemplar:
if Boris blocks that spec, he is too aggressive.

The pattern to copy is not the prose — it is the **shape**: a named mechanism, a `path:line`
citation, and an evidence tag (`[VERIFIED]` / `[UNCONFIRMED]` / `[INFERENCE]`).

---

## 1. `data_model` — who writes this, who reads it, who owns the row

**Good, because it names ownership as law and states cascade behaviour explicitly:**

> Source-of-truth law (locked): Supabase = CRM truth; Stripe = billing truth; Linear = execution
> truth. `crm_contacts` links to lead/client/business via `linked_*_id`, all `ON DELETE SET NULL`
> — `…103000.sql:15-17`. `[VERIFIED]`

**What the absence looks like:** a table is described by its columns, and nothing says which
system wins when two of them disagree, or what happens to the children when the parent is deleted.

## 2. `invariants` — what must never be true

**Good, because it is testable and pinned to a mechanism:**

> `crm_opportunities` carries an in-schema comment "forecast-only … not billing truth", enforcing
> the Stripe source-of-truth law. `[VERIFIED]`
> A consent=true write with no provenance is **rejected (422)**. `do_not_contact` is a hard
> server-side block on any send/sequence path.

**What the absence looks like:** validation described as "we validate the input" with no statement
of the condition that must never hold.

## 3. `failure_modes` — what breaks, and how far the damage travels

**Good, because it names the blast radius, not just the bug:**

> `agent_actions` grants `FOR SELECT TO authenticated USING (true)` (`…nexus_agent_actions.sql:37`)
> — every authenticated principal can read the entire cross-entity audit/timeline trail.
> `[VERIFIED]`

Note the second clause. "The policy is too broad" is a bug report; "every authenticated principal
can read the entire audit trail" is a blast radius.

## 4. `interface_contract` — the shape, and what happens to existing callers

**Good, because the contract is versioned against a named consumer:**

> The V1 conversion flow MUST run inside a single `SECURITY DEFINER` Postgres RPC
> `crm_convert_lead_to_contact()` … Request/response JSON schema in §7.5.

**What the absence looks like:** an endpoint described by what it does, with no schema, no
error shape, and no statement of what happens to callers when a field is removed.

## 5. `concurrency` — two of these at once, and the retry

**The single best example in the estate — it names the exact race and the exact fix:**

> Add a partial UNIQUE index on `dedupe_email_key` (where not null) so the DB is the backstop, not
> the route's race-prone `SELECT … limit 1` (`…contacts/route.ts:180-202`). `[VERIFIED gap]`
>
> The supabase-js client has **no multi-statement transaction**, so chained SDK calls cannot be
> atomic and will ship orphaned-contact partial commits. `[VERIFIED — route read]`

This is precisely the class of requirement a founder cannot be expected to raise: it requires
knowing that check-then-insert is not atomic and that the client library has no transaction.

## 6. `migration` — how existing data reaches the new shape

**Good, because it is an ordered, gated procedure rather than an intention:**

> Migration law (locked): every schema change is written in `apps/web/supabase/migrations/`,
> validated on a Supabase database branch (never against prod), and promoted to prod ONLY by
> merging an approved branch. Contacts before opportunities, single transaction, security advisor,
> post-promote `gen:types` + `pg_policies`/`rowsecurity` assertions. `[VERIFIED]`

## 7. `rollback` — the 3am sequence

The CRM spec is **weakest here**, which is itself instructive: it locks a forward promotion path
but never states the reverse. A good answer names the exact sequence and its data consequence:

> Revert = re-point `linked_*` FKs to the archived winner and re-run the timeline backfill; the
> merge executor is reversible via audit. `[INFERENCE — grounded in the V2 approval model]`

**What the absence looks like:** "we can roll back the deploy." That is not a rollback plan if
the migration already ran.

## 8. `observability` — how you learn it broke without a customer telling you

**Good, because it names the assertion and when it runs:**

> M1.1 exit assertion that an authenticated-non-founder key returns 0 rows from `agent_actions`.

**What the absence looks like:** "we'll add logging."

## 9. `budget` — the number it must stay under

State a number and who enforces it. In the CRM spec this shows up as bounded shapes rather than
latency targets — `qualification_score` 0–100 CHECK, `probability` 0–100 CHECK,
`value_amount numeric ≥0 CHECK` `[VERIFIED file]`. For a request path, the equivalent is a p95
and the query plan that sustains it.

**What the absence looks like:** an unindexed lookup that is fine at 100 rows and is never
described at 10 million.

## 10. `test_oracle` — what proves it works, and what would prove it doesn't

**Good, because it names the artifact that carries the proof:**

> Both tables are drafted in one migration (`…103000.sql`), guarded by a static test
> (`tests/unit/margot-crm-contacts-opportunities-migration.test.ts`). **Neither has been applied
> to a database branch or prod.** `[VERIFIED]`

The second sentence is the oracle doing its job: the test passes, and the thing is still not live.
A test that cannot distinguish "written" from "applied" is not an oracle.

---

## Evidence tags

| Tag | Means | Must carry |
|---|---|---|
| `[VERIFIED]` | Boris opened the file | `path:line` **and the quoted line** |
| `[UNCONFIRMED]` | could not be checked from here | the command that would confirm it |
| `[INFERENCE]` | reasoned, not read | the mechanism, and where it has failed before |

A finding with no tag is not a finding. A `[VERIFIED]` without its quote is read as
`[UNCONFIRMED]` — a bare `path:line` can be grepped up by a model that never read the code, and a
quoted line either supports the claim or exposes it.

On greenfield work `[INFERENCE]` is the *expected* tag and carries full weight. When a spec creates
something that does not exist yet there is nothing to cite, and judgement about how this class of
thing fails is the whole deliverable.

---

## DECIDED vs PRESCRIBED — the distinction that took a rewrite to enforce

`DECIDED` means *the spec already answers it*, and the section must quote the spec's answering
sentence as a `> ` blockquote. `PRESCRIBED` means *Boris is supplying the answer the spec never
gave*. They looked interchangeable while both were prose, so the validator now checks the quote
against the spec text.

The proof this matters is the CRM review itself. Boris filed all ten categories as `DECIDED`. Under
the quote check, **not one of them could quote the spec** — because he was not confirming what the
spec said, he was supplying answers about a different application tree. All ten were `PRESCRIBED`
all along, and the old contract had no way to see it. An invented latency budget filed as `DECIDED`
is how a number nobody chose ends up on a dashboard as fact.
