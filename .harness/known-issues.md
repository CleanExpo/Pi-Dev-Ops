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

`components/command-centre/wiki-graph/WikiGraphCanvas.tsx` is a **byte-identical** port
(`diff` against `D:/Authority-Site/apps/web/src/components/command-centre/wiki-graph/WikiGraphCanvas.tsx`
returns empty). It carries two real defects, both present at the same lines in the source:

- **KI-003 — listener leak.** `canvas.addEventListener('pointerleave', () => {…})` is
  anonymous and the effect's cleanup removes only pointerdown/move/up. The effect reruns on
  `[nodes, edges, nodeAtScreen, router]`, so pointerleave handlers accumulate on the same
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
