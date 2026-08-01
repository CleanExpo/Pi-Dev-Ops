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
