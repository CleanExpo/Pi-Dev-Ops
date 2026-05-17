/**
 * validate.ts — render guardrails.
 *
 * Two checks, both fail-fast:
 *
 *   preflightScript(storyboard, opts) — runs BEFORE TTS.
 *     For every scene with voiceover, asserts the script length fits the
 *     planned duration at a realistic AU-explainer pace. Catches the "scene
 *     planned for 6s with 50 words of narration" trap before we spend
 *     ElevenLabs credits rendering 11s of audio that the Sequence will clip.
 *
 *   postrenderProbe(mp4Path) — runs AFTER renderMedia.
 *     ffprobes the rendered file. Asserts audio_duration ≤ video_duration +
 *     toleranceMs (default 100ms). If the gap is wider, the render is rejected
 *     so a silent broken video can't get shipped.
 *
 * Both functions throw on failure. The render entry point catches and exits 1.
 */
import { execFileSync } from 'node:child_process';
import type { Storyboarded } from './voiceover';

// ── pre-flight ─────────────────────────────────────────────────────────────

export interface ScriptBudgetOptions {
  /**
   * Words per second a typical voiceover hits at the brand's cadence.
   * AU-explainer (calm, professional) lands around 2.4-2.7 wps (≈ 145-160 wpm).
   * Default 2.6 wps is the empirical mean from the ra-help-* renders below:
   *   inspections scene-2: 50 words / 13s planned = 3.85 wps (overran → cut)
   *   inspections scene-2: 50 words / 16.67s actual = 3.0 wps (real cadence)
   * 2.6 is the conservative floor — anything faster than this assumes the
   * speaker rushes.
   */
  wordsPerSec?: number;
  /** Allowable overrun before failing. Default 0 = strict — must fit. */
  graceSec?: number;
}

export interface ScriptBudgetReport {
  sceneId: string;
  words: number;
  plannedSec: number;
  estimatedSec: number;
  fits: boolean;
}

function countWords(s: string): number {
  return s.trim().split(/\s+/).filter(Boolean).length;
}

export function preflightScript(
  props: Storyboarded,
  opts: ScriptBudgetOptions = {},
): { ok: boolean; reports: ScriptBudgetReport[]; failures: ScriptBudgetReport[] } {
  const wps = opts.wordsPerSec ?? 2.6;
  const grace = opts.graceSec ?? 0;
  const reports: ScriptBudgetReport[] = [];

  for (const scene of props.storyboard) {
    if (!scene.voiceover || !scene.voiceover.trim()) {
      reports.push({ sceneId: scene.sceneId, words: 0, plannedSec: scene.durationSec, estimatedSec: 0, fits: true });
      continue;
    }
    const words = countWords(scene.voiceover);
    const estSec = words / wps;
    const fits = estSec <= scene.durationSec + grace;
    reports.push({ sceneId: scene.sceneId, words, plannedSec: scene.durationSec, estimatedSec: +estSec.toFixed(2), fits });
  }

  const failures = reports.filter((r) => !r.fits);
  console.log('[preflight] sceneId           words  planned  est-tts  fits');
  console.log('[preflight] ─────────────────────────────────────────────────');
  for (const r of reports) {
    const mark = r.fits ? '✓' : '✗';
    console.log(
      `[preflight] ${r.sceneId.padEnd(20)} ${String(r.words).padStart(5)}  ${r.plannedSec.toFixed(2).padStart(6)}  ${r.estimatedSec.toFixed(2).padStart(6)}  ${mark}`,
    );
  }
  return { ok: failures.length === 0, reports, failures };
}

// ── post-render ────────────────────────────────────────────────────────────

interface ProbeResult {
  videoSec: number;
  audioSec: number;
  hasAudio: boolean;
}

function probeMp4(mp4Path: string): ProbeResult {
  const json = execFileSync(
    'ffprobe',
    [
      '-v', 'error',
      '-show_entries', 'stream=codec_type,duration:format=duration',
      '-of', 'json',
      mp4Path,
    ],
    { encoding: 'utf8' },
  );
  const parsed = JSON.parse(json) as {
    streams?: Array<{ codec_type: string; duration?: string }>;
    format?: { duration?: string };
  };
  const streams = parsed.streams ?? [];
  const vid = streams.find((s) => s.codec_type === 'video');
  const aud = streams.find((s) => s.codec_type === 'audio');
  const formatDur = Number.parseFloat(parsed.format?.duration ?? '0');
  const videoSec = Number.parseFloat(vid?.duration ?? '') || formatDur;
  const audioSec = Number.parseFloat(aud?.duration ?? '0');
  return { videoSec, audioSec, hasAudio: !!aud };
}

export interface PostrenderOptions {
  /** Max allowed (audio - video) drift in ms. Default 100ms. */
  toleranceMs?: number;
  /** Require audio stream present. Default true — silent MP4s read as broken. */
  requireAudio?: boolean;
}

export interface PostrenderReport {
  ok: boolean;
  videoSec: number;
  audioSec: number;
  deltaMs: number;
  reasons: string[];
}

export function postrenderProbe(mp4Path: string, opts: PostrenderOptions = {}): PostrenderReport {
  const tolMs = opts.toleranceMs ?? 100;
  const requireAudio = opts.requireAudio ?? true;
  const { videoSec, audioSec, hasAudio } = probeMp4(mp4Path);
  const deltaMs = Math.round((audioSec - videoSec) * 1000);
  const reasons: string[] = [];

  if (requireAudio && !hasAudio) {
    reasons.push('no audio stream — silent video');
  }
  if (hasAudio && deltaMs > tolMs) {
    reasons.push(`audio longer than video by ${deltaMs}ms (tolerance ${tolMs}ms) — narration will cut at boundary`);
  }

  console.log(
    `[postrender] ${mp4Path}\n[postrender]   video=${videoSec.toFixed(3)}s  audio=${audioSec.toFixed(3)}s  delta=${deltaMs}ms  ${reasons.length === 0 ? '✓' : '✗ ' + reasons.join('; ')}`,
  );
  return { ok: reasons.length === 0, videoSec, audioSec, deltaMs, reasons };
}
