# Known issues — command centre migration

Carried deliberately. Each is a decision, not an oversight. Fixing any of these is
its own work with its own cross-model review — never folded into a port.

---

## KI-001 · hermes-control-panel renders 8 of 13 modules

**Status:** open · **Raised:** 2026-08-01 · **Ruled by:** founder
**Capability:** 1 — hermes-control-panel

The page renders only the first `DECK_LIST_CAP = 8` of 13 registry modules, followed by a
`+N more` line.

**The cap is in the source, not introduced by the port.** `DECK_LIST_CAP` comes from the
source's own `DeckDetails`. So the Authority-Site page has always shown a capped list while
its header describes it as one that *"mirrors the Hermes web admin module list"*. The source
does not satisfy its own header, and never has.

**Ruling:** port faithfully, keep the cap. The migration's job is to move behaviour, not to
change it. Un-capping is a behaviour change and needs its own spec, its own build and its own
review.

**How it surfaced:** cross-vendor review (Codex gpt-5.5) of capability 1, attempt 3 — it read
the header as a requirement and correctly found the rendered output did not meet it. The
finding was true; the spec was wrong to imply the source was uncapped.

**Fix later:** decide whether 13 modules should render in full, paginate, or stay capped with
clearer wording. Then change the header to match whatever is chosen, so the contract and the
code agree.

---

## KI-002 · WikiEnhanceControl omitted from the knowledge port

**Status:** open (deliberate deviation) · **Raised:** 2026-08-01 · **Ruled by:** founder
**Capability:** 2 — knowledge

`WikiEnhanceControl` and its route `/api/command-centre/lanes/wiki/enhance` are **not**
ported. This is a knowing deviation from port-faithfully, recorded rather than silent.

**Why the route could not be rebuilt as-is.** It `.insert(`s into `operator_jobs` on
`lksfwktwtmyznckodsau` — a production database on the fence list — and it calls
`enqueueWikiEnhance(user.id)`. There is no `user.id` here: this app is single-operator
behind one shared password with no per-user identity. Building it would have required
inventing an identity to satisfy a signature **and** creating a production write path.
Refused on both grounds independently.

**Why absent rather than stubbed.** A 501 stub is one line-change from live; an absent
route cannot be silently filled in. That is the same absence-versus-guard distinction
that made operator-gateway a rebuild — a guard can be deleted or inverted, an absence
cannot. A control that renders while doing nothing also misrepresents what the surface
can do.

**Consequence:** the knowledge deck is read-only here. The enhance action exists only in
the source app.

**Fix later:** if the action is wanted in this dashboard, it needs an identity decision
first (what replaces `user.id`) and an explicit ruling on the dashboard holding a write
path into a production job queue. Both are design decisions, not porting work.

---

## KI-003 / KI-004 — two defects inherited verbatim from the baseline

`components/command-centre/wiki-graph/WikiGraphCanvas.tsx` **was** byte-identical to
`D:/Authority-Site/apps/web/src/components/command-centre/wiki-graph/WikiGraphCanvas.tsx` when
this entry was written — `diff` returned empty — and that is how the two defects below were
established as inherited rather than introduced.

**It is no longer byte-identical.** KI-005 removed the node-click path, and these entries added
comments. The inherited-not-introduced finding still stands: it was verified
against the baseline at the time and both defects remain at their original lines. But do not
re-derive it by diffing today and expecting an empty result — the claim is a record of a check
that was run, not a property you can re-observe now.

It carries two real defects, both present at the same lines in the source:

- **KI-003 — listener leak.** `canvas.addEventListener('pointerleave', () => {…})` is
  anonymous and the effect's cleanup removes only pointerdown/move/up. The effect reruns on
  `[nodes, edges, nodeAtScreen]` (was `[…, router]` before KI-005), so pointerleave handlers accumulate on the same
  canvas. Flagged by cross-vendor review as a hard standards violation. It is one.
- **KI-004 — ref read during render.** `sizeRef.current.w` is read inside the tooltip's
  `style` prop. `react-hooks/refs` errors on it, and that error is what turned the repo's
  `lint-dashboard` gate red.

**Ruling (founder, 2026-08-01): declare, do not fix.** The governing instruction for this
migration is *port faithfully, including existing behaviour* — a difference from the source
is a defect whether or not the source's behaviour is ideal. Fixing either one here forks the
port from its baseline and makes the conformance comparison lie about what was carried over.
KI-004 is suppressed with a **single-line** scoped `eslint-disable`, so a *new*
ref-in-render anywhere in this file still fails lint; KI-003 is annotated in place.

**Fix later:** upstream, in Authority-Site. This port inherits the fix when the baseline
moves. Both are client-side only — no data exposure, no write path.

**Note on the cost of this ruling:** the repo's lint gate is now green because a real error
is suppressed, not because it was fixed. That is the deliberate trade. It is recorded here
so nobody later reads a green gate as "this component is clean".

## KI-005 — wiki-graph node clicks REMOVED (not retargeted)

`WikiGraphCanvas` called ``router.push(`/founder/wiki/${slug}`)``. That route does not exist in
this app, so **every node click 404'd**. Found by cross-vendor review on attempt 3, not by the
harness: the route-existence check scanned `href=` and `fetch(` string literals, and this is a
template literal inside `router.push()`. The check now covers that form and tests the static
prefix before the first `${`.

**First fix retargeted every click to `/command-centre/knowledge`. The founder overruled it,
and was right.** A click that appears to navigate somewhere specific and always lands somewhere
unrelated is a lie about interactivity. Offering nothing beats offering a control that
misrepresents what it does. The click path is removed: handlers, listeners, and the orphaned
`useRouter` import.

**This is the same rule as KI-002, and the two should be read as one.** `WikiEnhanceControl` was
made *absent* rather than stubbed because a control that renders while doing nothing
misrepresents what the surface can do. A control that renders and navigates *somewhere wrong*
fails the identical test. The principle is not "prefer absence" — it is that **a surface must
not claim a capability it does not have**, and both a no-op stub and a wrong destination make
that claim. Absence is honest and cannot be silently filled in.

**Not a declare-not-fix case** like KI-003/004. Those are defects inherited verbatim from a
baseline where they work correctly. This was a link whose destination does not exist *here*.

**Restore the click when** a per-node destination exists — a per-page wiki route, or a knowledge
deck that accepts a slug to deep-link into. Until then the graph is hover-and-explore only, and
the caption says so.

**Footnote worth keeping:** removing `useRouter` made its provenance entry phantom, and the
map-vs-reality check built in the previous commit failed on it within seconds. The apparatus
caught its own author. That is the first evidence any of these checks has bitten someone other
than the reviewer who demanded it.

## KI-006 — `provider-test` OMITTED, absent not stubbed (capability 4)

`/api/command-centre/provider-test` is **not** ported and has no stub.

**Why there is no gated version.** Its whole function is to spend. `provider-test/route.ts`
imports `executeChat` from `lib/provider-pool/execute.ts`, which posts to `api.openai.com`,
`api.minimax.io`, `openrouter.ai` and `generativelanguage.googleapis.com` with a resolved API
key. A "test" button here is a live billable completion.

Founder ruling 2026-08-02: **there is no version that is a button with a gate.** Ported into
this app it becomes a spend path reachable over HTTP by anything holding the shared dashboard
password — including our own agents — on a surface the fence cannot see. The fence gates what it
can observe; an HTTP route inside the dashboard is not that. Same rule as KI-002.

**The route back, stated so this is a deferral and not a dead end.** The real question a test
button answers is *"is this credential valid"*, and that is answerable against a **non-billable**
endpoint — a models-list or account-status call. If the button is wanted later it gets **built
against one of those**, not by porting the completion call and putting a gate in front of it.
Different construction, not the same code with a guard.

---

## KI-007 — provider credential custody DEFERRED, bound to per-capability tokens

`credentials_vault` access and the `provider_accounts` write paths are **not** ported.

**Why not today.** This app is single-operator behind one shared password. Holding provider keys
here would mean: no per-capability scoping, no audit of which capability read which key, and no
identity to attribute a read to. That is the same identity gap that blocked KI-002's enhance
route — the missing thing is not a table, it is a subject.

**Bound to a specific unblock.** Per-capability tokens are what make *"which capability may read
the vault"* an answerable question. Revisited **after tokens land**, not before, and not on a
judgement call that the risk seems small.

**What WAS proven, since the header alone would not have been accepted.** The route header claims
"metadata only — never the key … no secrets cross this boundary". Traced rather than believed:
`credentials_vault` appears nowhere in `lib/provider-pool/repository.ts`; the GET path runs
`listAccounts` + `loadAccounts`, which select from `provider_accounts` and
`provider_quota_events` only, and `vault_entry_id` is carried as an id and never dereferenced.
**The claim is true.**

**Sharpened by cross-vendor review (2026-08-02, PASS).** My statement was that the vault is not
reached from the repository. The reviewer located where it IS reached: `credentials_vault` is
touched **only by the POST registration path** (`provider-accounts/route.ts:69`), never by GET.
That is a more useful form of the same finding — "not reached from here" is weaker evidence than
"reached from exactly there, and nowhere else".

**It still does not port on the same terms as the usage cockpit**, and the reason matters: the
same module carries `.insert()` into `provider_quota_events` — a production write path — and
probes `process.env` provider keys through `hasEnvKey`. Porting it wholesale imports a write path
into this app. If the metadata half is wanted, it needs a **rebuilt read-only repository**, the
way `/api/command-centre/wiki-graph` was rebuilt, not a port. That is a separate piece of work
with its own review.

---

## KI-008 — `CostAllocationTile` and `/api/command-centre/cost-allocation` DEFERRED

**Status:** open (deferred, two named conditions) · **Raised:** 2026-08-02 · **Ruled by:** founder
**Capability:** 4 — providers

Not ported with the read-only half. **Deferred on conditions, not refused** — and the distinction
matters, because unlike KI-006 and KI-007 there is no safety finding here.

**What was traced, so this is a decision on facts rather than on the name.**

- The tile is thin: `react`, `SourceBadge`, and one `fetch('/api/command-centre/cost-allocation')`.
  Nothing in it to assess.
- **The route is genuinely read-only.** Zero write verbs in the entire file — no `insert`,
  `update`, `upsert`, `delete` or `rpc`. Three SELECTs: `cost_source`, `cost_record`,
  `revenue_record`. That is a better position than `provider-accounts` (KI-007), which carried a
  production write path.
- Tile and route **move together or not at all**. Porting the tile without the route gives a
  control that renders and always fails, which is the KI-005 rule.

**Why it is not a straight port.** The source uses `createServiceClient` — service-role, RLS
bypassed **by design** — and does its authorization in the handler with `getUser()`. Those two
halves are a deliberate pair. Ported here the `getUser()` half evaporates, because this app has
no per-user identity, while the RLS-bypassing half remains. That is structurally the same swap
that made `/api/command-centre/wiki-graph` a rebuild rather than a port. The difference is what
it reads: **cost and revenue**.

### Condition 1 — an access-policy ruling, which is the founder's and not the agent's

Porting this means **anyone holding the shared dashboard password can read estate cost and
revenue figures.** No credentials are involved, so this is not KI-007's problem; it is a question
about data sensitivity and who the single shared secret is effectively granting access to.

It is a policy call, not a technical one, and it does not become smaller by being implemented
carefully. **Unblocks when the founder rules that shared-password access legitimately includes
financial figures** — or when per-capability tokens land and the question becomes "which
capability may read the cost tables", which is answerable rather than assumed.

### Condition 2 — do the tables exist in the database this app points at?

Both apps resolve the **same env vars** (`NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`),
so whichever project this dashboard is configured for is what the route would query. Whether
`cost_source`, `cost_record` and `revenue_record` exist there is **unknown and was deliberately
not checked**: answering it means querying a fenced production database, which is a stop under
the operating contract. It is one authorized read-only query away from being answered — it is
simply not the agent's to run unasked.

If the tables are absent, the tile renders a permanently degraded state, which fails the same
"must not claim a capability it does not have" test that removed the wiki-graph node click.

### If both conditions clear

It ports **on the same terms as the wiki-graph rebuild**: a rebuilt route with no `getUser`, auth
enforced by `proxy.ts` — which is now genuinely enforced and asserted by
`command-centre-auth-coverage.test.ts`, not merely claimed — plus provenance entries and a
declared delta for the client swap. The tile itself ports verbatim modulo the alias rewrite.

**Recorded distinction:** KI-006 is refused (its function is to spend). KI-007 is deferred on a
missing mechanism (identity). **KI-008 is deferred on a decision plus a fact** — neither of which
is a defect in the code, and both of which are cheap to resolve.
