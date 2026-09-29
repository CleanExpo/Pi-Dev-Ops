# Synthex integration — what nexus-viral reuses vs adds

nexus-viral is an orchestration layer. It owns viral judgement (scoring, retention grading,
repurpose fit) and composes everything else. This map is the contract.

## Reuses (never rebuilt)

| Need | Reuses | Path |
| --- | --- | --- |
| Provider calls, routing, quota | Synthex engine | `lib/services/ai/video/{registry,fal-adapter,quota,generation-service}.ts` |
| Pre-paid Artlist tier | video-director adapter | `engine/artlist-adapter.ts` (video-director package) |
| Shot cards / modifiers | Synthex cards | `lib/services/ai/video/cards/*` |
| The two gates | video-director | Brief Grill (Gate A) + Broadcast Grill (Gate B) |
| Quality scoring + QA rows | quality gate | `lib/video/quality-gate` → `marketing_agency_qa_reports` |
| Hooks + captions | nexus-copywriter | `skills-library/skills/nexus-copywriter` |
| Platform cuts | social derivation | `lib/video/social-derivation` |
| Trend/competitor pull | Apify actors | see `references/intelligence.md` |
| Publish | publish queue | `publish_queue` (human-gated) |
| Audit | append-only log | `audit_events_immutable` |

## Adds (this skill's own surface)

- **Viral scoring** on `video_topic_queue` rows (freshness/fit/hookability/repurpose reach).
- **Viral method cards** — `engine/cards/viral-method-cards.json` (pattern-interrupt open,
  3-beat retention, loop-back close).
- **Retention grading** — the viral lenses layered onto Gate B (`broadcast-grill-viral.md`).
- **Repurpose matrix** — the 1→8 platform specs and derivation rules.
- **Orchestrator** — `engine/nexus-viral.ts`, which sequences the four gated stages.

## Tables touched (reused, none new required)

Reads/writes existing tables only: `video_topic_queue`, `content_topic_suggestions`,
`tracked_competitors`, `brand_dna`, `video_generations`, `video_assets`, `publish_queue`,
`marketing_agency_qa_reports`, `audit_events_immutable`, `organization_video_quotas`.
The `video_grill_reports` table from the video-director package (if applied) is reused for
grill detail; nexus-viral adds no migration of its own.

## Governance boundary

Schema inspection only against production (`list_tables` / `list_branches`) — no
`execute_sql`. Generation obeys `organization_video_quotas` and the MCP daily sub-cap,
draft-first. Nothing here forks the Nexus Prompt; it is fetched live from Pi-Dev-Ops.
