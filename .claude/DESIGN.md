# DESIGN.md — Pi-Dev-Ops

> The brand contract every AI agent (Claude Code, Claude Design, Cursor, v0, Aura)
> reads before producing UI, copy, motion, or skill output for this repo.
>
> **Special note:** Pi-Dev-Ops is the central infrastructure repo for the
> Unite-Group autonomous agency — Hermes cron jobs, 108+ skills, the swarm,
> review-board, agent prompts, and developer-facing dashboards live here. It
> does not have one "consumer-facing brand" — instead, it enforces brand
> standards on every artefact the agents produce *for any portfolio brand*.
>
> Default voice / tokens follow the Unite-Group parent brand (the empire's
> operating layer). Per-brand outputs must defer to the relevant brand's
> DESIGN.md or BrandConfig.
>
> Updated: 2026-05-11. Spec: Google DESIGN.md v1 (community implementation).

---

## Brand Voice

- **Operating layer for:** Unite Group (parent)
- **Audience (primary):** Phill (CEO), agents in the swarm, future operators
  joining the agency
- **Tone:** founder-led, empire-building, long-term thinking. Decision-focused.
- **Cadence:** medium. Surfaces here are for the CEO and the swarm — be
  direct, no startup-speak.
- **Voice register:** the swarm speaks to the CEO. Every message earns its
  place. No filler. No emojis unless the user requests them.
- **Skill output voice:** when an individual skill produces content for a
  portfolio brand (DR, NRPG, RA, CARSI, CCW, Synthex), the skill MUST read
  the relevant BrandConfig (`Synthex/packages/brand-config/src/brands/{slug}.ts`)
  and the brand's DESIGN.md in its own repo, not improvise.

---

## Visual Tokens

> When Pi-Dev-Ops renders developer-facing surfaces (Studio dashboards,
> board-reports, status pages, Hermes monitoring) the **CEO register**
> dominates. Per-brand surfaces use the brand's tokens.

### CEO-Surface Tokens (Phill Rule 6 — Gun Metal + Candy Red)

| Token | Hex | Use |
|---|---|---|
| `--canvas` | `#0e1014` | Gun Metal base — all CEO views |
| `--red-500` | `#b30000` | Candy Red primary — CEO action |
| `--orange-400` | `#e07020` | CEO secondary |
| `--green-500` | `#00a854` | CEO success indicator |

### Unite-Group Fallback Tokens

When a developer surface needs colour beyond the CEO register, fall back to
Unite-Group's brand tokens:

| Token | Hex | Use |
|---|---|---|
| `--unite-primary` | `#E55A2B` | Candy orange dark |
| `--unite-secondary` | `#1E293B` | Slate-800 |
| `--unite-accent` | `#FBBF24` | Amber — signal |
| `--neutral-50` | `#F8FAFC` | Canvas (light register) |
| `--neutral-900` | `#0F172A` | Body text (light register) |

### Typography
- **Display:** Inter, weight 700.
- **Body:** Inter, weight 400.
- **Mono:** JetBrains Mono, weight 500 (for code surfaces and skill output).

### Radius
- **CEO register (default for this repo): 4–6px (sharp).**

### Motion
- **Signature (Unite-Group):** rise.
- For Pi-Dev-Ops own dashboards: no decorative motion. Motion exists to
  communicate state change, never for flair.

---

## Forbidden Patterns

### Icons (Phill Rule 1)
- **NO Lucide, HeroIcons, FontAwesome, or any other icon library in app code.**
- Pi-Dev-Ops contributes UI to remotion-studio, dev dashboards, and the
  agency's developer surfaces — all of which must use custom geometric marks.
- Internal dev-only scripts that have no UI surface (Python CLIs, shell
  helpers, JSONL log readers) are exempt.

### AI-Slop Phrases (brand-guardian global banned list)
- "In today's fast-paced world", "Game-changer", "Seamless" (unless quoting),
  "Leverage" (as verb), "Robust", "Cutting-edge", "State-of-the-art",
  "Dive into" / "delve into", "It's worth noting", "In conclusion" / "To
  summarise" as paragraph openers, "Our passionate team", "End-to-end
  solution", "Best-in-class", "Empower" / "empowering", "Unlock [potential]",
  rhetorical question paragraph openers.
- This applies especially to skill prompts and skill output templates — a
  banned phrase in a skill's prompt template propagates to every artifact
  that skill produces.

### Pi-Dev-Ops-Specific Forbidden
- No startup-speak in skill names, agent names, or commit messages.
- No emojis in committed source files unless the user explicitly requested
  them (per `~/.claude/CLAUDE.md`).
- No "we use AI" framing in any agency-facing copy. The Unite-Group thesis
  is "autonomous agency" — the AI is the substrate, not the headline.

### Visual
- No generic AI aesthetics in any rendered dashboard or status page.
- No placeholder logos or initials for any portfolio business — every
  business's real logo is embedded.
- No Lorem ipsum.

---

## Required Patterns

### Custom Geometric Marks (Phill Rule 2 — Option B)
Where Pi-Dev-Ops renders a UI surface (Studio, board reports, status pages):
- 24×24 viewBox, 1.5px stroke, square caps, miter joins, sharp corners,
  1–3 paths max, derived from the hexagon in the Unite-Group logo mark.

### Skill Authoring Pattern
Every skill in `skills/` that produces brand-aligned output MUST:
1. Read the relevant `Synthex/packages/brand-config/src/brands/{slug}.ts`
   before generating copy or visuals.
2. Read that brand's `.claude/DESIGN.md` if the skill is operating inside a
   portfolio repo.
3. Defer to brand-guardian for any client-facing artefact.
4. Never hardcode a brand colour, voice rule, or forbidden phrase that
   contradicts the typed source.

### Real Logos (Phill Rule 4)
- Skills that embed business identifiers in output (board memos, status
  cards, marketing assets) MUST use real logos from `public/logos/` (or
  the relevant brand repo's logo store), not initials or placeholders.

### CEO-Facing Surfaces (Phill Rule 5)
- Status pages, board reports, swarm dashboards, Hermes telemetry — all
  must show **WHAT TO DO**, not just metrics.
- Health scores in background strips.
- Every metric paired with an action.

### Design Tokens (Phill Rule 6)
- No hardcoded colours in dashboards. Use the CEO register tokens above.

### Autonomy (Phill Rule 7)
- Pi-Dev-Ops is the autonomous-agency substrate — anything that requires
  Phill to lift a finger is a bug. Manual steps in skill output, Hermes
  cron jobs, or swarm operations get ticketed as autonomy-debt.

---

## Approval Gates

Skills, agents, and infrastructure changes in this repo:

1. **PR review on every change to `skills/`** — agents can author skills,
   but a human (or qa-lead skill) reviews before merge.
2. **brand-guardian skill** must return `APPROVED` for any skill output
   template that produces client-facing content.
3. **qa-lead skill** runs on every PR via existing CI.
4. **The $2B filter** — every skill / cron / agent earns its place in the
   stack. If it doesn't move us toward the exit, it gets cut.
5. **`~/Pi-CEO/Pi-Dev-Ops/skills/` is the canonical home for portfolio
   skills.** Changes here are higher-risk than in any other repo because a
   skill change propagates to every portfolio brand. Treat with care.

---

## CI Lint Integration

This repo runs the DESIGN.md lint on every PR via
`.github/workflows/design-lint.yml`. The lint asserts:

1. `.claude/DESIGN.md` exists.
2. All 6 required H2 headings are present.
3. No **net-new** imports from `lucide-react`, `@heroicons/react`, or
   `@fortawesome/*` in any TypeScript / JavaScript app code. Baseline at
   `.github/design-md-lint.baseline.txt`.
4. AI-slop phrase scan (warn-only in v1) across `.md`, `.mdx`, `.ts`, `.tsx`
   — explicitly excludes `skills/brand-guardian/**` (the skill that
   *defines* the banned list) and the `feedback_design_preferences.md` memory.

To run locally: `bash .github/scripts/design-md-lint.sh`.

Existing CI surfaces in this repo: `ci.yml`, `codebase-wiki.yml`,
`dns_takeover_scan.yml`, `ideas_inbox_drain.yml`, `morning_briefing.yml`,
`smoke_pipeline.yml`, `smoke_surface_gate.yml`, `smoke_test.yml`,
`smoke_test_e2e.yml`, `workspace_intel_brief.yml`. design-lint runs
alongside these on every PR.

---

## References

- Source of truth (typed): `Synthex/packages/brand-config/src/brands/unite.ts`
  (default for Pi-Dev-Ops dashboards), and the relevant per-brand config for
  any portfolio output.
- All portfolio BrandConfigs: `Synthex/packages/brand-config/src/brands/`
- Phill's 7 design rules: `~/.claude/projects/-Users-phill-mac-2nd-Brain/memory/feedback_design_preferences.md`
- Brand guardian skill: `~/.claude/skills/brand-guardian/SKILL.md`
- Pattern reference: `~/2nd Brain/2nd Brain/Wiki/design-system-approach.md`
- Exit thesis: `~/2nd Brain/2nd Brain/Wiki/exit-thesis.md`
- Pi-Dev-Ops wiki: `WIKI.md`
