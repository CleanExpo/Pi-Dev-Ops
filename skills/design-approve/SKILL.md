---
name: design-approve
description: Labelling + cache step. Once the user approves a variant in design-iterate, this skill writes the canonical brand spec files (`{slug}.design.md`, `{slug}.motion.md`, optional `{slug}.scene.md`), generates the standalone `{slug}.html` preview file, snapshots the iteration to the approved-variant cache, and triggers `remotion-brand-codify` to write the BrandConfig.ts runtime fields. Treats approval as a commit point.
automation: automatic
intents: approve-design, ship-design, finalise-brand-design, label-variant
---

# design-approve

Treat approval as a commit. Once the user picks a variant + label, this skill makes that variant canonical.

## Triggers

- `design-iterate` calls when user approves a variant.
- User directly says "approve variant 2 from {jobId} as 'precision-trust'".
- User points at an existing iteration directory and a variant name.

## Inputs

- `slug` — brand slug
- `jobId` — iteration job ID (e.g. `acme-1`)
- `variant` — variant identifier (e.g. `variant-2`)
- `label` — short kebab-case name the user assigns ("precision-trust", "field-instrument", etc.)
- `notes` (optional) — final founder notes for the snapshot

## Method

1. **Validate inputs** — `.research/design/iterations/{jobId}/{variant}.design.md` exists; `{variant}.motion.md` exists; `{variant}.scene.md` exists OR is intentionally absent.

2. **Re-run validators** as a final gate:
   - `npx --prefix Pi-Dev-Ops/remotion-studio design.md lint {variant}.design.md` → 0 errors required
   - `loadMotion(...)` → no zod errors
   - `loadScene(...)` → no zod errors (if file exists)
   - Block on any failure. Do NOT silently fix.

3. **Write canonical specs** to `Synthex/packages/brand-config/src/brands/`:
   - `cp {variant}.design.md → {slug}.design.md`
   - `cp {variant}.motion.md → {slug}.motion.md`
   - `cp {variant}.scene.md → {slug}.scene.md` (if present)

4. **Mirror to runtime location** at `Pi-Dev-Ops/packages/brand-config/src/brands/`:
   - `cp` the same three files into the runtime mirror dir (used by `loadDesign` / `loadMotion` / `loadScene`)

5. **Generate the standalone HTML preview** by invoking `design-canvas-html` with the slug. Output: `Synthex/packages/brand-config/src/brands/{slug}.html` (a self-contained file the user can open in any browser).

6. **Snapshot the iteration** to the approved-variant cache:

   ```
   .research/design/approved/{slug}-{label}-{YYYY-MM-DD}.snapshot.json
   ```

   Snapshot contains:

   ```jsonc
   {
     "slug": "acme",
     "label": "precision-trust",
     "approvedAt": "2026-05-07T12:34:56Z",
     "iteration": "acme-1",
     "variant": "variant-2",
     "approvedBy": "founder",
     "notes": "client wanted the trust-led direction with mono accents",
     "spec": {
       "design": <full .design.md tokens>,
       "motion": <full .motion.md tokens>,
       "scene": <full .scene.md tokens or null>
     },
     "boardTranscript": {
       "round1": [...persona papers],
       "round2": [...persona memos],
       "round3": [...synthesis + critique]
     }
   }
   ```

7. **Trigger remotion-brand-codify** for the runtime fields:
   - Invoke `remotion-brand-codify` with the brand-research dossier + the just-approved `.design.md` + `.motion.md`
   - It writes `Synthex/packages/brand-config/src/brands/{slug}.ts` containing only runtime/behaviour fields per CONTRACT.md
   - It regenerates the 9-section human-readable projection at `Pi-Dev-Ops/remotion-studio/src/brands/{slug}.md`

8. **Reload the canvas** by hitting `preview-canvas` at `/brand/{slug}` — the new brand should now render. Take a confirmation screenshot.

9. **Emit completion summary** with:
   - Paths of all four files written (`{slug}.design.md`, `{slug}.motion.md`, `{slug}.scene.md` or "—", `{slug}.html`)
   - Snapshot path
   - Canvas URL: `http://localhost:3030/brand/{slug}`
   - One-line note for `~/.claude/projects/-Users-phill-mac-Pi-CEO/memory/` if this is a new family pattern worth remembering

## Reusing approved variants

The snapshot at `.research/design/approved/{slug}-{label}-{date}.snapshot.json` is a labelled checkpoint. Other skills can reference it:

- `apply-variant precision-trust to acme` → re-applies the snapshot's spec
- `compare-variants precision-trust vs field-instrument` → diff between two labelled snapshots
- `family-coherence safety` (the design-family-coherence skill) → uses snapshots to detect drift

## Output

```
Synthex/packages/brand-config/src/brands/{slug}.design.md       (canonical)
Synthex/packages/brand-config/src/brands/{slug}.motion.md       (canonical)
Synthex/packages/brand-config/src/brands/{slug}.scene.md        (canonical, optional)
Synthex/packages/brand-config/src/brands/{slug}.html            (standalone preview)
Synthex/packages/brand-config/src/brands/{slug}.ts              (runtime, via remotion-brand-codify)
Pi-Dev-Ops/packages/brand-config/src/brands/{slug}.{design,motion,scene}.md   (runtime mirrors)
Pi-Dev-Ops/remotion-studio/src/brands/{slug}.md                 (9-section projection, regenerated)
.research/design/approved/{slug}-{label}-{date}.snapshot.json  (cache)
```

### Required SDA visual evidence before canonical approval

For rendered app UI, web screens, business-card films, video art or visual media:
- Set PI_DEV_OPS_ROOT to an absolute **clean, exact SHA-reviewed Pi-Dev-Ops
  checkout** and verify its HEAD against the signed independent review.
  Do not call an installed gate unless its source hash is independently
  proven identical to the reviewed source; mismatches are HOLD.
- Run `visual-qa` with real Playwright captures in three viewports, real asset
  decode and actual-video frame inspection as applicable.
- Declare deliverable_type=web for static website/UI evidence or
  deliverable_type=film for moving media, then run `python3
  "$PI_DEV_OPS_ROOT/skills/visual-qa/scripts/sda_evidence_gate.py"
  /path/to/manifest.json --release --baseline-record /path/to/prior-approved-record.json
  --scope-record /path/to/independent-scope.json` against immutable, SHA-verified
  evidence. Web approvals use an exact SHA-bound PNG candidate, never
  dummy video/audio. Film approvals require actual film and sound evidence.
- A passing automated gate verifies *records*, not aesthetic merit. Require
  genuine SDA critique, different independent challenger, rights evidence and
  founder acceptance of the exact master hash.
- If any item is missing, report **DESIGN REVIEW HOLD**, leave the existing
  approved variant untouched and stop before step 3's canonical writes.
- Three targeted iterations maximum; change direction if still rejected.

## Boundaries

- **Never approve without all validators passing.** No "force-approve" mode.
- **Never overwrite a previously approved brand silently.** Diff the existing canonical files; warn the user; require explicit "yes overwrite" before clobbering.
- **Never write `BrandConfig.ts` directly.** Always delegate to `remotion-brand-codify` so runtime/behaviour fields go through the codify path.

## Reused

- `design-iterate` — caller
- `design-canvas-html` — generates the `{slug}.html`
- `remotion-brand-codify` — writes `BrandConfig.ts` runtime fields
- `Pi-Dev-Ops/remotion-studio/src/brands/loadMotion.ts` / `loadScene.ts` — final validators
- `npx design.md lint` — final design.md validator

## Hands off to

`design-family-coherence` (post-merge audit) and the user (with the canvas link).


**Scope guard:** Every technical pass also requires `--scope-record` from
a page inventory outside the candidate evidence directory, otherwise
the candidate can omit inconvenient screens and still seem to pass.
This record is evidence of test scope, NOT actual creative approval.
