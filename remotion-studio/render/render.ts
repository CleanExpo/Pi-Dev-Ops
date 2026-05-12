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

interface Args {
  comp: string;
  out: string;
  props: Record<string, unknown>;
  jobId: string;
  skipTts: boolean;
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
  };
}

async function main() {
  const args = parseArgs();
  const root = path.resolve(__dirname, '..');

  // Standard: voiceover is mandatory for production deliverables.
  // --skipTts=true is allowed ONLY for validation flights and must be
  // followed by a full re-render with TTS before shipping. Loud warning
  // when invoked so agents can't pass it silently.
  if (args.skipTts) {
    console.warn('');
    console.warn('  ⚠️  --skipTts=true → SILENT MP4 (validation-only)');
    console.warn('  ⚠️  Standard: production renders MUST include voiceover.');
    console.warn('  ⚠️  Re-render without --skipTts before declaring this deliverable complete.');
    console.warn('');
  }

  // 1. Voiceover synthesis (drops MP3s into public/audio/{jobId}/scene-N.mp3 and
  //    mutates props.storyboard[i].voiceoverAudioPath in place).
  if (!args.skipTts && isStoryboarded(args.props)) {
    await synthesiseStoryboard(args.props, args.jobId, root);
  }

  // 2. Bundle the project (entry: src/index.ts).
  const entryPoint = path.join(root, 'src/index.ts');
  console.log(`[render] bundling ${entryPoint}`);
  const serveUrl = await bundle({ entryPoint, webpackOverride: (c) => c });

  // 3. Pick the composition.
  console.log(`[render] selecting composition ${args.comp}`);
  const composition = await selectComposition({
    serveUrl,
    id: args.comp,
    inputProps: args.props,
  });

  // 4. Render.
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
}

main().catch((err) => {
  console.error('[render] FAILED', err);
  process.exit(1);
});
