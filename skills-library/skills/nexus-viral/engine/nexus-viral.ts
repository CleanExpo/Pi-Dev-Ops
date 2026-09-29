// nexus-viral — orchestrator for the viral short-form generator.
//
// This is a COMPOSITION layer. It owns sequencing + viral judgement and delegates
// every heavy operation to something that already exists:
//   - Brief Grill / Broadcast Grill  -> video-director (Gate A / Gate B)
//   - generation, routing, quota      -> Synthex engine (lib/services/ai/video)
//   - hooks + captions                -> nexus-copywriter
//   - platform cuts                   -> lib/video/social-derivation (via ./repurpose)
//   - trend/competitor signal         -> Apify actors (see references/intelligence.md)
//
// It adds NOTHING those layers already provide. Do not re-implement gates or providers here.

import {
  runBriefGrill,
  generateWithGates,
  runBroadcastGrill,
  type GateResult,
} from "../../video-director/engine/video-director"; // shared gates — reuse, do not fork
import { scoreTopicQueue, type ScoredAngle } from "./intelligence";
import { deriveEightCuts, type PlatformCut } from "./repurpose";
import viralCards from "./cards/viral-method-cards.json";

// Canonical Synthex platform ids — these are the ids the publish queue and
// platform connectors speak. The short-form SURFACE on each platform is a
// derivation detail (youtube -> Shorts, instagram -> Reels), never the id.
// Order encodes the money-maker doctrine: all roads lead to YouTube and
// Google/Bing — youtube and instagram cuts are derived and enqueued first.
export type ViralPlatform =
  | "youtube" | "instagram" | "tiktok" | "linkedin"
  | "x" | "facebook" | "pinterest" | "snapchat";

export interface ViralJob {
  orgId: string;
  jobId: string;
  topic: string | "auto";               // "auto" pulls the top-scored video_topic_queue row
  platforms?: ViralPlatform[];          // default: all eight (the 1->8 set)
  heroModel?: string;                   // optional override; default = registry routes, draft-first
  referenceAssetId?: string;            // brand character / product still for cross-cut consistency
}

// nexus-copywriter handoff. nexus-viral NEVER writes the words itself.
export interface CopyBundle {
  hook: string;                         // <=7s spoken/text hook
  captionTrack: { t: number; text: string }[];  // burned on-screen captions
  platformCaptions: Record<ViralPlatform, string>;
}
export type CopywriterFn = (args: {
  orgId: string; jobId: string; angle: ScoredAngle; platforms: ViralPlatform[];
}) => Promise<CopyBundle>;

export interface ViralResult {
  status: "completed" | "blocked" | "gate_failed";
  reason?: string;
  heroAssetId?: string;
  qaReportId?: string;
  cuts?: PlatformCut[];                  // enqueued to publish_queue, human-gated
}

const ALL_PLATFORMS: ViralPlatform[] = [
  "youtube", "instagram", "tiktok", "linkedin", "x", "facebook", "pinterest", "snapchat",
];

export async function runNexusViral(
  job: ViralJob,
  deps: { callCopywriter: CopywriterFn },
): Promise<ViralResult> {
  const platforms = job.platforms?.length ? job.platforms : ALL_PLATFORMS;

  // ---- Stage 1: Intelligence + Brief Grill (scope before spend) ----
  const angle: ScoredAngle = await scoreTopicQueue({ orgId: job.orgId, topic: job.topic });
  const briefGrill: GateResult = await runBriefGrill({
    orgId: job.orgId,
    brief: {
      topic: angle.topic,
      angle: angle.rationale,
      platforms,
      trendSignalRef: angle.queueRef,
      tier: job.heroModel ? "premium" : "draft", // premium only if explicitly overridden
    },
  });
  if (!briefGrill.pass) return { status: "blocked", reason: `Brief Grill: ${briefGrill.reason}` };

  // ---- Stage 2: Hook (delegate) + generate hero through the engine ----
  const copy = await deps.callCopywriter({ orgId: job.orgId, jobId: job.jobId, angle, platforms });
  if (!copy?.hook) return { status: "blocked", reason: "nexus-copywriter returned no hook" };

  const hero = await generateWithGates({
    orgId: job.orgId,
    jobId: job.jobId,
    aspect: "9:16",
    card: viralCards.cards.find((c) => c.id === "viral-hero-short"),
    hook: copy.hook,
    captionTrack: copy.captionTrack,
    referenceAssetId: job.referenceAssetId,
    modelId: job.heroModel,             // undefined => registry routes, Artlist-prepaid first
    safeZone: (viralCards as any).safeZone,
  });

  // ---- Stage 3: Broadcast Grill (quality before publish; terminal on FAIL) ----
  const broadcast: GateResult = await runBroadcastGrill({
    orgId: job.orgId,
    assetId: hero.assetId,
    lenses: "viral",                    // adds the retention/thumb-stop lenses over Gate B
  });
  if (!broadcast.pass) {
    return { status: "gate_failed", reason: broadcast.reason, qaReportId: broadcast.qaReportId };
  }

  // ---- Stage 4: Repurpose 1 -> N (native cuts; human-gated publish) ----
  const cuts = await deriveEightCuts({
    orgId: job.orgId,
    jobId: job.jobId,
    heroAssetId: hero.assetId,
    platforms,
    platformCaptions: copy.platformCaptions,
  });

  return {
    status: "completed",
    heroAssetId: hero.assetId,
    qaReportId: broadcast.qaReportId,
    cuts, // each already enqueued to publish_queue as queued_human_gated by deriveEightCuts
  };
}
