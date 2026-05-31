---
name: design-iterate
description: Iteration loop driver for brand design. Calls design-board to generate N variants, renders each at three breakpoints (mobile/tablet/desktop) via the preview-canvas + Claude Preview MCP, presents screenshots to the client (the user) via AskUserQuestion, captures feedback, refines, and repeats until the user approves a variant. The visible canvas the client uses to actually SEE designs.
automation: manual
intents: design-iterate, iterate-design, design-loop, refine-brand-design, run-design-board-loop
---

# design-iterate

The iteration loop. This is the skill the client (the user) drives when they say "design a brand for {x}" or "give me 3 variants for {y} and let me pick".

## Triggers

- User says "design a brand for {x}", "iterate the design for {y}", "give me design variants for {z}", "let me see designs for {brand}".
- After `remotion-brand-research` produces a dossier for a NEW brand (orchestrator wave 0).
- User wants to refresh an EXISTING brand's identity (passes existing slug).

## Inputs

- `brief` — design brief (free text or path to research dossier)
- `slug` — brand slug (existing or new)
- `variantCount` (default 3) — variants per iteration
- `maxIterations` (default 5) — hard ceiling on the loop
- `family` (optional) — colour family for the new brand

## Method

```
iteration = 1
notes = []
forbid = []

while iteration <= maxIterations:
  1. Invoke design-board:
       inputs: brief, slug, variantCount, iteration, notes, forbid, family
       output: .research/design/iterations/{slug}-{iteration}/{variant-N.{design,motion,scene,rationale}.md, variants-summary.md}

  2. Validate every variant:
       - npx --prefix Pi-Dev-Ops/remotion-studio design.md lint variant-N.design.md
       - tsx -e "loadMotion(variant-N.motion.md)" (zod-validate)
       - tsx -e "loadScene(variant-N.scene.md)" if .scene.md exists
     Block on any validation error. Re-run design-board with the error in `notes`.

  3. Capture variants in the visible canvas:
       - preview_start preview-canvas (idempotent — server reused if running)
       - For each breakpoint in [mobile 375, tablet 768, desktop 1440]:
           preview_resize { width: bp, height: 900 }
           preview_eval "window.location.href = '/board/{slug}-{iteration}'"
           preview_screenshot
       - End up with 3 screenshots (one per breakpoint, each showing the N variants side-by-side)

  4. Show variants to the user:
       AskUserQuestion {
         question: "Iteration {iteration}: which direction? Notes for refinement (or `approve {variant}` to ship).",
         header: "Iteration {iteration}",
         options: [
           { label: "Approve variant 1", description: "{variant-1 one-line school}" },
           { label: "Approve variant 2", description: "{variant-2 one-line school}" },
           { label: "Approve variant 3", description: "{variant-3 one-line school}" },
           { label: "Refine — give notes", description: "Continue iterating with my notes" }
         ]
       }
       Pass the 3 screenshots inline so the user can see them.

  5. If user picks "Approve variant N":
       Hand off the chosen variant to design-approve {slug, variant: N, iteration, label: <user-provided label or auto>}
       break

  6. Else (Refine):
       Append the user's notes to `notes`
       If user named a direction to forbid, append to `forbid`
       iteration += 1
       continue

If iteration > maxIterations and no approval:
  Emit a status report listing what was tried, what the user rejected, and the strongest 2 variants from the last round. Ask the user whether to continue or pause.
```

## Inputs the design-board needs from this loop

`notes` is a list of structured feedback items:

```
[
  { iteration: 1, target: "variant-2", note: "palette is too muted; client wants more energy" },
  { iteration: 2, target: "all", note: "no serif typefaces; we considered Lora and rejected" },
]
```

`forbid` is a list of free-text directions the user has explicitly ruled out:

```
[
  "any glassmorphism",
  "any dark-mode-first hero",
  "any pulse signature motion"
]
```

design-board reads both before Round 1 and uses them as hard constraints.

## Output

While iterating: variants land in `.research/design/iterations/{slug}-{iteration}/` (one subdir per iteration).

On approval: hands off to `design-approve` which writes the canonical `Synthex/packages/brand-config/src/brands/{slug}.{design,motion,scene}.md` files + `{slug}.html` + the snapshot JSON.

## Boundaries

- **Never skip the validation step (#2).** A variant the user can't tell is broken is worse than a refusal.
- **Never present more than {variantCount} variants per iteration.** Decision fatigue is real; the Critic's job is to keep the count honest.
- **Never auto-approve.** The user explicitly approves a variant by name. No "we picked the highest-scoring for you".
- **Never recycle a variant the user already rejected** unless they re-open it with notes.
- **Never write to canonical paths inside the iteration loop.** Only `design-approve` writes to `Synthex/packages/brand-config/src/brands/`.

## Reused

- `design-board` — the deliberation skill (mandatory)
- `mcp__Claude_Preview__preview_*` — `preview_start`, `preview_resize`, `preview_screenshot`, `preview_eval`
- `Pi-Dev-Ops/preview-canvas/app/board/[jobId]/page.tsx` — the variant-comparison view
- `design-canvas-html` — generates the standalone HTML preview file the canvas reads
- `design-approve` — hand-off after approval

## Hands off to

`design-approve` with `{ slug, jobId, approvedVariant, label }`.
