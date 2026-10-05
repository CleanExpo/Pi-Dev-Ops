// repurpose — derive N platform-native cuts from one passed hero short.
//
// Reuses lib/video/social-derivation. Does NOT regenerate: aspect changes are crops,
// duration changes trim the tail, captions are placed from nexus-copywriter's set.
// Each cut re-runs only the captions/safe-zone lenses, lands in video_assets linked to
// the hero, and enqueues to publish_queue as queued_human_gated. No auto-post.

import { deriveSocialCut } from "../../../lib/video/social-derivation"; // existing engine path
import type { ViralPlatform } from "./nexus-viral";

// Native specs — see references/repurpose-matrix.md. Aspect is a crop target, not a re-render.
const SPEC: Record<ViralPlatform, {
  aspect: "9:16" | "1:1" | "16:9"; maxSec: number; caption: "upper" | "centre" | "cover";
}> = {
  // Money-makers first: YouTube (Shorts surface) is the searchable, Google/
  // Bing-indexed destination — its cut carries search title/description/tags
  // metadata on the publish_queue row, not just a caption. Instagram (Reels
  // surface) second. Ids are canonical Synthex platform ids.
  youtube:   { aspect: "9:16", maxSec: 60, caption: "upper" },
  instagram: { aspect: "9:16", maxSec: 15, caption: "upper" },
  tiktok:    { aspect: "9:16", maxSec: 15, caption: "upper" },
  linkedin:  { aspect: "1:1",  maxSec: 30, caption: "centre" },
  x:         { aspect: "1:1",  maxSec: 30, caption: "centre" },
  facebook:  { aspect: "9:16", maxSec: 20, caption: "upper" },
  pinterest: { aspect: "9:16", maxSec: 15, caption: "cover" },
  snapchat:  { aspect: "9:16", maxSec: 10, caption: "centre" },
};

export interface PlatformCut {
  platform: ViralPlatform;
  assetId: string;
  publishState: "queued_human_gated";
  reframeFlag?: boolean; // set when a crop would lose the focal subject — needs human re-frame
}

export async function deriveEightCuts(args: {
  orgId: string;
  jobId: string;
  heroAssetId: string;
  platforms: ViralPlatform[];
  platformCaptions: Record<ViralPlatform, string>;
}): Promise<PlatformCut[]> {
  const out: PlatformCut[] = [];

  for (const platform of args.platforms) {
    const spec = SPEC[platform];
    // deriveSocialCut handles the crop/trim/caption-place + the captions/safe-zone re-check,
    // promotes to video_assets, and enqueues to publish_queue (human-gated). Reuse it.
    const cut = await deriveSocialCut({
      orgId: args.orgId,
      heroAssetId: args.heroAssetId,
      target: spec.aspect,
      maxSec: spec.maxSec,
      captionPlacement: spec.caption,
      caption: args.platformCaptions[platform],
      trimFrom: "tail",         // keep the hook, cut the tail
      keepSubjectCentre: true,  // flags reframeFlag if the crop loses the subject
      platform,                 // canonical Synthex id — stamps the publish_queue row
    });

    out.push({
      platform,
      assetId: cut.assetId,
      publishState: "queued_human_gated",
      reframeFlag: cut.subjectLost || undefined,
    });
  }

  return out;
}
