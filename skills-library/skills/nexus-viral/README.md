# nexus-viral

A Nexus specialised skill: turn one idea into a hook-first 9:16 short and repurpose it into
up to 8 platform-native cuts, grounded in live trend + competitor intelligence. Sibling to
`nexus-copywriter` in `skills-library/skills/`.

**It composes, it does not rebuild.** Generation runs through the already-built Synthex
engine, the two gates come from `video-director`, and every hook/caption comes from
`nexus-copywriter`. nexus-viral adds only the viral-specific layer: trend scoring, retention
grading, the shot grammar, and the 1→8 repurpose matrix.

## Placement

```
skills-library/skills/nexus-viral/
├── SKILL.md                         # the contract (house pattern)
├── references/
│   ├── viral-playbook.md            # hook-first grammar, retention shape, 9:16 craft
│   ├── intelligence.md              # Apify actors → video_topic_queue, velocity scoring
│   ├── broadcast-grill-viral.md     # viral lenses layered onto video-director Gate B
│   ├── repurpose-matrix.md          # 1 hero → 8 native cuts, per-platform specs
│   └── synthex-integration.md       # reuse-vs-add contract
└── engine/
    ├── nexus-viral.ts               # orchestrator: 4 gated stages
    ├── intelligence.ts              # score topic queue → top angle
    ├── repurpose.ts                 # derive N native cuts (crops/trims, human-gated)
    └── cards/viral-method-cards.json
```

## Run sequence (four gated stages)

1. **Intelligence** — score `video_topic_queue` (freshness/fit/hookability/repurpose reach),
   present the top angle. **Brief Grill** (video-director Gate A) confirms scope + budget
   before any spend.
2. **Hook + generate** — delegate hook/captions to `nexus-copywriter`; generate the 9:16 hero
   through the Synthex engine (Artlist pre-paid preferred, draft-first).
3. **Broadcast Grill** — viral lenses (`broadcast-grill-viral.md`) over Gate B. FAIL is
   terminal; writes `marketing_agency_qa_reports`; never self-approves.
4. **Repurpose 1→8** — derive native cuts via `lib/video/social-derivation`; land in
   `video_assets`, enqueue to `publish_queue` (human-gated). No auto-post.

## Wiring notes

- `engine/nexus-viral.ts` imports the shared gates from the `video-director` package — keep
  the two packages side by side (or publish video-director's gates as the shared module they
  already are). Do not fork the gate logic.
- `engine/intelligence.ts` and `repurpose.ts` bind to the org data layer, not `execute_sql`
  against production (governance boundary: schema inspection only).
- No migration ships here. Grill detail reuses `video_grill_reports` from the video-director
  package if applied; everything else reuses existing tables.

## Hard rules (inherited)

Reuse the platform, don't rebuild it · never fork the Nexus Prompt (fetch live from
Pi-Dev-Ops) · draft-first, respect `organization_video_quotas` + the MCP daily sub-cap ·
gate every publish, never self-approve · human-gated release only · no fabricated virality.
