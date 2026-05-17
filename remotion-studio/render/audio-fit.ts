/**
 * audio-fit.ts — make composition match the audio it will actually play.
 *
 * Root cause this fixes: ElevenLabs returns whatever duration the speech ran
 * for, which routinely overruns the storyboard's planned `durationSec`. Inside
 * `<Sequence durationInFrames={dur}><Audio /></Sequence>`, when the Sequence
 * ends Remotion unmounts the Audio mid-sentence — narration cuts, visuals drift.
 *
 * After TTS synthesis but before rendering, this module:
 *   1. ffprobes each scene's audio file
 *   2. Rewrites `scene.durationSec = max(planned, actualAudio + tailSec)`
 *      so the Sequence always outlives the audio it contains
 *   3. Logs a per-scene delta so overruns are visible
 *
 * The composition's `calculateMetadata` in Root.tsx already sums durationSec
 * to compute total frames, so total video length auto-grows to fit.
 *
 * Constraint: never shortens a planned scene (visual pacing was deliberate);
 * only extends. A scene with no audio is left at its planned duration.
 */
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import type { Storyboarded } from './voiceover';

const DEFAULT_TAIL_SEC = 0.5;

function probeDurationSec(audioPath: string): number {
  // ffprobe -v error -show_entries format=duration -of csv=p=0 <file>
  const out = execFileSync(
    'ffprobe',
    [
      '-v', 'error',
      '-show_entries', 'format=duration',
      '-of', 'csv=p=0',
      audioPath,
    ],
    { encoding: 'utf8' },
  ).trim();
  const n = Number.parseFloat(out);
  if (!Number.isFinite(n) || n <= 0) {
    throw new Error(`audio-fit: ffprobe returned non-numeric duration for ${audioPath}: ${out}`);
  }
  return n;
}

export interface AudioFitOptions {
  /** Extra silence after audio ends, before the Sequence cuts. Default 0.5s. */
  tailSec?: number;
}

export interface AudioFitReport {
  sceneId: string;
  plannedSec: number;
  audioSec: number | null;
  finalSec: number;
  grewBySec: number;
}

export function fitStoryboardToAudio(
  props: Storyboarded,
  rootDir: string,
  opts: AudioFitOptions = {},
): AudioFitReport[] {
  const tail = opts.tailSec ?? DEFAULT_TAIL_SEC;
  const reports: AudioFitReport[] = [];

  for (const scene of props.storyboard) {
    const planned = scene.durationSec;
    if (!scene.voiceoverAudioPath) {
      reports.push({ sceneId: scene.sceneId, plannedSec: planned, audioSec: null, finalSec: planned, grewBySec: 0 });
      continue;
    }
    // voiceoverAudioPath is relative to public/ (e.g. "audio/<jobId>/scene-0.mp3").
    const abs = path.join(rootDir, 'public', scene.voiceoverAudioPath);
    const audioSec = probeDurationSec(abs);
    const needed = audioSec + tail;
    const finalSec = Math.max(planned, needed);
    scene.durationSec = finalSec;
    reports.push({
      sceneId: scene.sceneId,
      plannedSec: planned,
      audioSec,
      finalSec,
      grewBySec: +(finalSec - planned).toFixed(3),
    });
  }

  // Pretty-log the table.
  const total = reports.reduce((s, r) => s + r.finalSec, 0);
  console.log('[audio-fit] sceneId           planned   audio    final    +grew');
  console.log('[audio-fit] ─────────────────────────────────────────────────────');
  for (const r of reports) {
    const a = r.audioSec === null ? '   —   ' : r.audioSec.toFixed(2).padStart(7);
    console.log(
      `[audio-fit] ${r.sceneId.padEnd(20)} ${r.plannedSec.toFixed(2).padStart(7)}  ${a}  ${r.finalSec.toFixed(2).padStart(7)}  ${(r.grewBySec >= 0 ? '+' : '') + r.grewBySec.toFixed(2)}`,
    );
  }
  console.log(`[audio-fit] total composition duration: ${total.toFixed(2)}s`);
  return reports;
}
