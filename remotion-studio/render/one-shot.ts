import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { preflightScript } from './validate';
import { remotionOneShotBriefSchema, RemotionImageAsset, RemotionOneShotBrief } from './brief-schema';

interface Args {
  brief: RemotionOneShotBrief;
  jobId: string;
  dryRun: boolean;
  outDir: string;
}

interface Scene {
  sceneId: string;
  sceneType: 'hook' | 'body' | 'cta' | 'stat' | 'flow' | 'comparison' | 'keypoints';
  durationSec: number;
  voiceover: string;
  onScreenText: string;
  data?: { eyebrow?: string; keypoints?: string[]; footnote?: string };
  image?: { path: string; alt: string; prompt?: string; provider?: string };
}

function parseArgs(argv = process.argv.slice(2)): Args {
  const raw: Record<string, string> = {};
  for (const arg of argv) {
    if (!arg.startsWith('--')) continue;
    const [key, ...rest] = arg.slice(2).split('=');
    raw[key] = rest.join('=');
  }
  if (!raw.brief) throw new Error('--brief=<json> required');
  const brief = remotionOneShotBriefSchema.parse(JSON.parse(raw.brief));
  const slug = `${brief.brand}-${brief.channel}-${Date.now()}`;
  return {
    brief,
    jobId: raw.jobId || slug,
    dryRun: raw.dryRun !== 'false',
    outDir: path.resolve(raw.outDir || path.join('.harness', 'remotion')),
  };
}

function sentence(input: string): string {
  return input.trim().replace(/\s+/g, ' ').replace(/[<>]/g, '');
}

function assetFor(sceneId: string, assets: RemotionImageAsset[]): RemotionImageAsset | undefined {
  return assets.find((asset) => asset.sceneId === sceneId);
}

function attachImage(scene: Scene, assets: RemotionImageAsset[]): Scene {
  const asset = assetFor(scene.sceneId, assets);
  if (!asset) return scene;
  return {
    ...scene,
    image: {
      path: asset.path,
      alt: asset.alt,
      prompt: asset.prompt,
      provider: asset.provider,
    },
  };
}

function buildStoryboard(brief: RemotionOneShotBrief): Scene[] {
  const base = sentence(brief.brief);
  const goal = sentence(brief.goal);
  const audience = sentence(brief.audience);
  const cta = sentence(brief.cta);
  const total = brief.durationSec;
  const scale = total / 60;
  const durations = [8, 12, 16, 16, 8].map((n) => Math.max(4, Math.round(n * scale)));
  const delta = total - durations.reduce((s, n) => s + n, 0);
  durations[2] += delta;
  const scenes: Scene[] = [
    {
      sceneId: 'hook',
      sceneType: 'hook',
      durationSec: durations[0],
      voiceover: `${brief.brand.toUpperCase()} helps ${audience} move from idea to shipped marketing without losing momentum.`,
      onScreenText: goal,
      data: { eyebrow: 'One-shot marketing video' },
    },
    {
      sceneId: 'problem',
      sceneType: 'body',
      durationSec: durations[1],
      voiceover: 'The problem is not ideas. The problem is turning scripts, visuals, timing, voice, and edits into one clean production path.',
      onScreenText: 'Ideas are easy. Production discipline is the bottleneck.',
    },
    {
      sceneId: 'mechanism',
      sceneType: 'flow',
      durationSec: durations[2],
      voiceover: `${base} The system creates the script, directs the scenes, checks the edit, keeps one voice, and prepares a render packet before production.`,
      onScreenText: 'Script → Direction → Edit → Voice → Render',
      data: { keypoints: ['Script', 'Direction', 'Editing', 'Single voice', 'Render gate'] },
    },
    {
      sceneId: 'proof',
      sceneType: 'keypoints',
      durationSec: durations[3],
      voiceover: 'Every job carries timing evidence, a single Synthex ElevenLabs voice policy, and a reproducible Remotion command so the render can be checked instead of guessed.',
      onScreenText: 'Evidence-backed production, not guesswork.',
      data: { keypoints: ['Timing budget', 'Single voice', 'Render evidence'] },
    },
    {
      sceneId: 'cta',
      sceneType: 'cta',
      durationSec: durations[4],
      voiceover: `${cta}.`,
      onScreenText: cta,
      data: { eyebrow: 'Next step' },
    },
  ];
  return scenes.map((scene) => attachImage(scene, brief.imageAssets));
}

function writeFile(file: string, text: string): void {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text, 'utf8');
}

function buildImagePrompts(brief: RemotionOneShotBrief, storyboard: Scene[]): string {
  const provider = brief.imageProvider;
  const basePrompt = brief.imagePrompt || `Professional marketing image for ${brief.brand}: ${brief.goal}`;
  const lines = [
    `# Image prompts for ${brief.brand}`,
    '',
    `Provider: ${provider}`,
    `Global prompt: ${basePrompt}`,
    '',
    'Use existing approved image-generation access only. Do not create new vendor accounts.',
    '',
  ];
  for (const scene of storyboard) {
    lines.push(`## ${scene.sceneId}`);
    lines.push(`Provider: ${scene.image?.provider || provider}`);
    lines.push(`Prompt: ${scene.image?.prompt || `${basePrompt}. Scene: ${scene.onScreenText}`}`);
    if (scene.image?.path) lines.push(`Asset path: ${scene.image.path}`);
    lines.push('');
  }
  return `${lines.join('\n')}\n`;
}

function main(): void {
  const args = parseArgs();
  const jobDir = path.join(args.outDir, args.jobId);
  const storyboard = buildStoryboard(args.brief);
  const props = {
    brand: args.brief.brand,
    hookSec: storyboard[0]?.durationSec ?? 8,
    ctaSec: storyboard[storyboard.length - 1]?.durationSec ?? 8,
    storyboard,
  };
  const packet = {
    jobId: args.jobId,
    brief: args.brief,
    composition: 'Explainer',
    props,
    voicePolicy: {
      provider: 'elevenlabs',
      source: 'Synthex',
      voiceProfile: 'synthex_default_single_voice',
      voiceCount: 1,
    },
    imagePolicy: {
      provider: args.brief.imageProvider,
      status: args.dryRun ? 'dry-run' : 'render-requested',
      assets: args.brief.imageAssets,
      prompt: args.brief.imagePrompt,
      allowedProviders: ['chatgpt', 'nano-banana-2-pro', 'none'],
    },
  };
  const renderCommand = [
    'npx tsx render/render.ts',
    '--comp=Explainer',
    `--out=output/${args.jobId}.mp4`,
    `--jobId=${args.jobId}`,
    `--props='${JSON.stringify(props).replace(/'/g, "'\\''")}'`,
  ].join(' ');
  const preflight = preflightScript({ brand: args.brief.brand, storyboard: storyboard.map((s) => ({ ...s })) });

  fs.mkdirSync(jobDir, { recursive: true });
  writeFile(path.join(jobDir, 'production-packet.json'), `${JSON.stringify({ ...packet, renderCommand }, null, 2)}\n`);
  writeFile(path.join(jobDir, 'image-prompts.md'), buildImagePrompts(args.brief, storyboard));
  const scriptBody = storyboard
    .map((s) => `## ${s.sceneId}\n\n${s.voiceover}\n\nOn screen: ${s.onScreenText}\n${s.image ? `\nImage: ${s.image.path} (${s.image.alt})\n` : ''}`)
    .join('\n');
  writeFile(path.join(jobDir, 'script.md'), `# ${args.jobId} script\n\n${scriptBody}\n`);
  const preflightRows = preflight.reports
    .map((r) => `| ${r.sceneId} | ${r.words} | ${r.plannedSec} | ${r.estimatedSec} | ${r.fits ? 'yes' : 'no'} |`)
    .join('\n');
  writeFile(
    path.join(jobDir, 'preflight-report.md'),
    `# Remotion preflight\n\n- Job: ${args.jobId}\n- Dry run: ${args.dryRun}\n- Single voice: Synthex ElevenLabs\n- Image provider: ${args.brief.imageProvider}\n- Preflight: ${preflight.ok ? 'PASS' : 'WARN'}\n\n| Scene | Words | Planned | Estimated | Fits |\n|---|---:|---:|---:|---|\n${preflightRows}\n`,
  );
  writeFile(path.join(jobDir, 'render-command.sh'), `#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")/../../.."\n${renderCommand}\n`);

  if (!args.dryRun) {
    const rendered = spawnSync('npx', ['tsx', 'render/render.ts', '--comp=Explainer', `--out=output/${args.jobId}.mp4`, `--jobId=${args.jobId}`, `--props=${JSON.stringify(props)}`], {
      cwd: path.resolve(__dirname, '..'),
      encoding: 'utf8',
      stdio: 'pipe',
    });
    const renderLog = `${rendered.stdout}\n${rendered.stderr}`.slice(0, 4000);
    writeFile(
      path.join(jobDir, 'render-report.md'),
      `# Render report\n\nStatus: ${rendered.status === 0 ? 'PASS' : 'FAILED'}\n\n\`\`\`\n${renderLog}\n\`\`\`\n`,
    );
    if (rendered.status !== 0) process.exit(rendered.status ?? 1);
  }

  console.log(`[one-shot] wrote ${jobDir}`);
}

main();
