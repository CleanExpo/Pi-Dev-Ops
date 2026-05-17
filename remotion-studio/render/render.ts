/**
 * Render entry — Node API.
 *
 * Usage:
 *   npx tsx render/render.ts \
 *     --comp=Explainer \
 *     --out=output/ra-nir-explainer.mp4 \
 *     --props='{"brand":"ra","storyboard":[...]}'
 *
 * Pre-flight: typecheck, voiceover synthesis (if storyboard scenes lack voiceoverAudioPath),
 *             then bundle + render.
 */
import path from 'node:path';
import fs from 'node:fs';
import { bundle } from '@remotion/bundler';
import { renderMedia, selectComposition } from '@remotion/renderer';
import { synthesiseStoryboard, Storyboarded } from './voiceover';
import { fitStoryboardToAudio } from './audio-fit';
import { preflightScript, postrenderProbe } from './validate';

interface Args {
  comp: string;
  out: string;
  props: Record<string, unknown>;
  jobId: string;
  skipTts: boolean;
  skipValidate: boolean;
}

function isStoryboarded(p: unknown): p is Storyboarded {
  return (
    typeof p === 'object' &&
    p !== null &&
    'brand' in p &&
    'storyboard' in p &&
    Array.isArray((p as { storyboard: unknown }).storyboard)
  );
}

function parseArgs(): Args {
  const args: Record<string, string> = {};
  for (const a of process.argv.slice(2)) {
    if (!a.startsWith('--')) continue;
    const [k, ...rest] = a.slice(2).split('=');
    args[k] = rest.join('=');
  }
  if (!args.comp) throw new Error('--comp=<id> required');
  if (!args.out) throw new Error('--out=<path> required');
  return {
    comp: args.comp,
    out: path.resolve(args.out),
    props: args.props ? JSON.parse(args.props) : {},
    jobId: args.jobId ?? `job-${Date.now()}`,
    skipTts: args.skipTts === 'true',
    skipValidate: args.skipValidate === 'true',
  };
}

async function main() {
  const args = parseArgs();
  const root = path.resolve(__dirname, '..');

  // 1. Pre-flight script budget check — fail fast BEFORE we spend on TTS if a
  //    scene's voiceover obviously can't fit its planned duration.
  if (!args.skipValidate && isStoryboarded(args.props)) {
    const pf = preflightScript(args.props);
    if (!pf.ok) {
      console.warn(
        `[preflight] WARN ${pf.failures.length} scene(s) overrun their planned duration. audio-fit will extend them post-TTS so narration is not clipped.`,
      );
    }
  }

  // 2. Voiceover synthesis (drops MP3s into public/audio/{jobId}/scene-N.mp3 and
  //    mutates props.storyboard[i].voiceoverAudioPath in place).
  if (!args.skipTts && isStoryboarded(args.props)) {
    await synthesiseStoryboard(args.props, args.jobId, root);
  }

  // 3. Audio-fit — measure each TTS mp3 and extend scene.durationSec so the
  //    Sequence outlives the Audio it contains. Without this, ElevenLabs
  //    overruns cause mid-sentence cuts at scene boundaries.
  if (isStoryboarded(args.props)) {
    fitStoryboardToAudio(args.props, root);
  }

  // 4. Bundle the project (entry: src/index.ts).
  const entryPoint = path.join(root, 'src/index.ts');
  console.log(`[render] bundling ${entryPoint}`);
  const serveUrl = await bundle({ entryPoint, webpackOverride: (c) => c });

  // 5. Pick the composition.
  console.log(`[render] selecting composition ${args.comp}`);
  const composition = await selectComposition({
    serveUrl,
    id: args.comp,
    inputProps: args.props,
  });

  // 6. Render.
  fs.mkdirSync(path.dirname(args.out), { recursive: true });
  console.log(`[render] rendering -> ${args.out}`);
  await renderMedia({
    serveUrl,
    composition,
    codec: 'h264',
    outputLocation: args.out,
    inputProps: args.props,
    concurrency: 4,
    pixelFormat: 'yuv420p',
  });
  console.log(`[render] done: ${args.out}`);

  // 7. Post-render validation — ffprobe the file, fail if audio overruns video.
  if (!args.skipValidate) {
    const report = postrenderProbe(args.out);
    if (!report.ok) {
      throw new Error(
        `[postrender] validation failed: ${report.reasons.join('; ')}. ` +
          `Render written to ${args.out} but does NOT pass the gate.`,
      );
    }
  }
}

main().catch((err) => {
  console.error('[render] FAILED', err);
  process.exit(1);
});
