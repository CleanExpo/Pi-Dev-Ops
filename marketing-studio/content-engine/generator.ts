/**
 * marketing-studio/content-engine/generator.ts — UNI-2236 content generator.
 *
 * Consults ICP/positioning context and applies eeat + geo quality gates before
 * emitting publisher-ready social post payloads. Unite-Hub content-engine cron
 * should import this module; Pi-CEO Railway bridge mirrors logic in Python
 * (swarm/marketing_content_generator.py).
 */

export interface IcpContext {
  brand: string;
  positioning?: string;
  icpSummary?: string;
  sourceFiles?: string[];
}

export interface QualityScores {
  eeat: { scores: Record<string, number>; verdict: string };
  geo: { score: number; verdict: string; signals: Record<string, unknown> };
  composite: number;
  verdict: "pass" | "needs-work" | "fail";
}

export interface GeneratedPost {
  businessKey: string;
  content: string;
  title: string;
  platforms: string[];
  hashtags: string[];
  scores: QualityScores;
  metadata: Record<string, unknown>;
}

const YMYL_BRANDS = new Set(["restoreassist", "disaster-recovery", "carsi", "nrpg"]);

function countMatches(text: string, patterns: RegExp[]): number {
  const lower = text.toLowerCase();
  return patterns.filter((p) => p.test(lower)).length;
}

export function scoreEeat(content: string, ymyl = false): QualityScores["eeat"] & { ymyl: boolean } {
  const experience = Math.min(100, 20 + countMatches(content, [
    /\b(case study|measured|tested|field|on-site|restor)\w*/,
    /\b\d+%\b/,
    /\b(iicrc|iso|standard)\b/,
  ]) * 15);
  const expertise = Math.min(100, 15 + countMatches(content, [
    /\b(certified|licensed|qualified|years?\s+of\s+experience)\b/,
  ]) * 20);
  const authoritativeness = Math.min(100, 10 + countMatches(content, [
    /https?:\/\//,
    /\b(research|study|report|standard)\b/,
  ]) * 15);
  const trust = Math.min(100, 25 + countMatches(content, [
    /\b(abn|contact|privacy|terms)\b/,
    /\b(according to|source:|cited)\b/,
  ]) * 12);
  const scores = { experience, expertise, authoritativeness, trust };
  let verdict = "pass";
  if (ymyl && trust < 50) verdict = "fail";
  else if (Math.min(...Object.values(scores)) < 40) verdict = "needs-work";
  return { scores, verdict, ymyl };
}

export function scoreGeo(content: string): QualityScores["geo"] {
  const words = content.split(/\s+/);
  const frontLoaded = words.slice(0, 200).length >= 40;
  const hasFaq = /^#{1,3}\s+.*\?/m.test(content) || content.slice(0, 400).includes("?");
  const hasStat = /\b\d+(\.\d+)?%?\b/.test(content.slice(0, 500));
  const h2Sections = (content.match(/^#{2}\s+/gm) ?? []).length;
  let score = 0;
  if (frontLoaded) score += 30;
  if (hasFaq) score += 25;
  if (hasStat) score += 20;
  if (h2Sections >= 1) score += 15;
  if (words.length >= 80 && words.length <= 800) score += 10;
  const verdict = score >= 60 ? "pass" : score >= 40 ? "needs-work" : "fail";
  return {
    score: Math.min(100, score),
    verdict,
    signals: { frontLoaded, hasFaq, hasStat, h2Sections, wordCount: words.length },
  };
}

export function generateSocialPost(args: {
  businessKey: string;
  topic: string;
  body: string;
  channel?: string;
  icp?: IcpContext;
}): GeneratedPost {
  const { businessKey, topic, body, channel = "linkedin", icp } = args;
  const ymyl = YMYL_BRANDS.has(businessKey);
  const preamble = icp?.positioning?.split("\n")[0]?.trim();
  const content = [preamble, body].filter(Boolean).join("\n\n");
  const eeat = scoreEeat(content, ymyl);
  const geo = scoreGeo(content);
  const composite = (Object.values(eeat.scores).reduce((a, b) => a + b, 0) / 4) * 0.55 + geo.score * 0.45;
  const verdict =
    eeat.verdict === "fail" || geo.verdict === "fail"
      ? "fail"
      : eeat.verdict === "needs-work" || geo.verdict === "needs-work"
        ? "needs-work"
        : "pass";
  const platformMap: Record<string, string[]> = {
    linkedin: ["linkedin"],
    x: ["x"],
    twitter: ["x"],
    instagram: ["instagram"],
    tiktok: ["tiktok"],
  };
  const platforms = platformMap[channel.toLowerCase()] ?? ["linkedin"];
  const hashtags = content.match(/#\w+/g) ?? [];
  return {
    businessKey,
    content,
    title: topic.slice(0, 120) || `${businessKey} — ${channel}`,
    platforms,
    hashtags,
    scores: { eeat, geo, composite: Math.round(composite * 10) / 10, verdict },
    metadata: { channel, icpSources: icp?.sourceFiles ?? [], generator: "content-engine/generator" },
  };
}
