---
name: creative-director
description: Use when someone asks to build, design, make, create, or generate any deliverable from a short prompt — a deck, web page, report, poster, campaign, brand look, prototype — especially when the prompt is underspecified. Resolves the subject and client persona, grills only the gaps with one checkbox screen, routes to the right specialist skills and MCPs, and runs a polish gate before handoff. Do not start generating for such requests without this skill.
---

# Creative Director

One simple prompt in → one polished deliverable out. The human supplies intent; this skill supplies the interrogation, the persona lens, the specialist stack, and the quality gate. Context lives in the system, not in the prompt.

## The contract

- The user never writes a brief. A sentence is enough.
- Fetch context before asking for it; ask at most **one screen of checkbox questions**; never ask what's already answerable.
- Every deliverable passes a polish gate before the user sees it. First shown = near-final.

## Pipeline (run in order)

### 1 — Read the subject
Extract from the prompt: deliverable type, subject, audience hints, format/platform hints, style words. Then pull surrounding context **without asking**: conversation memory, connected sources (Drive brand docs, Linear briefs, CRM/client records, repo README) — only what's directly relevant. This stays a low-context operation.

### 2 — Resolve the client persona
Match the consumer to an archetype (adjust from evidence, never stereotype):

| Persona | Optimise for | Default register |
|---|---|---|
| Exec / board | Decision speed, one idea per view | Confident, quantified, restrained |
| Field ops / trade | Scannability on a phone on site | Plain, concrete, zero fluff |
| Developer / technical | Precision, copy-pasteability | Spec-like, honest about trade-offs |
| Consumer / social | Stopping power in ~1.5s | Bold, emotive, platform-native |
| Investor | Credibility + upside narrative | Polished, evidence-led |
| Government / compliance | Traceability, standards references | Formal, cited, unambiguous |

A known client in memory/CRM overrides the archetype.

### 3 — Grill the gaps (checkbox elicitation)
Only for dimensions still unknown after 1–2. **One screen, max 3 questions, checkbox/option format** — use the platform's structured input UI (`ask_user_input_v0` on claude.ai/mobile; `AskUserQuestion` in Claude Code; lettered options as fallback). Bank, priority order:
1. **Deliverable** — deck · web page/prototype · document/report · poster/social visual · campaign imagery/video · brand/style system
2. **Audience** — the persona table above as options
3. **Style** (pick ≤2) — presets below
4. **Depth** (only if scope is genuinely ambiguous) — quick draft · polished · flagship

If zero gaps remain, **skip the grill**, state assumptions in one line, and build. "Surprise me" → persona default decides. After the grill, don't ask again. For a deep pre-build stress-test of a plan (not a quick creative gap-fill), hand to `grill-me` instead — this is its lightweight sibling, not a replacement.

### 4 — Route to the specialist stack (prefer in-library skills)
| Deliverable | Stack (in order) |
|---|---|
| Slide deck / pitch | `design-board` + `pptx` (+ `artlist-mcp` imagery, spend-gated) |
| Web page / prototype / UI | `ui-ux-pro-max` + `ui-component-builder` + `design-system` |
| Report / proposal / doc | `docx` (or `pdf` for fixed layout) + brand tokens |
| Poster / static visual | `design-canvas-html` |
| Campaign imagery / video | `artlist-mcp` (stills/short) or `remotion-orchestrator` (rendered video) — spend gate applies |
| Brand / style system | `design-system` + `brand-ambassador` |
| Spreadsheet / model | `xlsx` |
| Many competing directions | `output-tournament` to diverge, judge, synthesise a winner |

Read each routed skill's SKILL.md before producing — this skill orchestrates, it never re-implements a specialist.

### 5 — Style presets (the "multiple styles" dial)
Each maps to concrete art direction the routed skill must honour: **editorial-minimal** · **bold-brutalist** · **luxury-restraint** · **playful-vibrant** · **technical-spec** · **corporate-trust** · **field-pragmatic** (high legibility, big tap targets, print-safe — ANZ trade/restoration default). Never ship the un-styled template look; if no preset was chosen, derive one from persona + subject and name it in the handoff.

### 6 — Polish gate (before the user sees anything)
1. **Render check** — actually open/render the artifact (file opens, page paints, deck fonts resolved). Claimed-done without opening it is a violation.
2. **Lens pass** — run `launch-review` compressed: design-lead lens always; PM lens for decks/docs, engineer lens for web. Fix the top findings once — one enhancement pass, not a loop.
3. **Persona read-back** — would the resolved persona act on this in under a minute? If not, cut until they would.

### 7 — Hand off
Present the file(s) with a two-line note: what was assumed, which preset + stack were used. Offer one named alternative direction (not three). Done.

## Governance
Inherits the `artlist-mcp` / `self-improvement-charter` spend gate for any generated media: budget declared before first call, exhaustion = stop and report, no unattended bulk loops. The grill is capped at one screen per task — repeated interrogation is a failure mode, not thoroughness. Registered in `agentskills.json`; consumers receive it via the live-fetched Nexus Prompt — never fork this file into a consuming repo.

## References
- `references/open-source-catalog.md` — where every open capability comes from (repos, licenses, install commands), verified 2026-07-10. Read when installing the stack on a new node or hunting a specialist this file doesn't route.
