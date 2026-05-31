/**
 * Re-render every brand video with the new richer Explainer composition.
 *
 * Reuses the existing voiceover audio cache (no ElevenLabs spend). Each video
 * gets a packed storyboard mixing VO scenes with extra visual-only scenes
 * (stat blocks, 5-step flows, comparisons, keypoints) to fix the dead-air
 * issue and lift content density.
 *
 * Usage:
 *   npx tsx scripts/rerender-brand-videos.ts                  # render all
 *   npx tsx scripts/rerender-brand-videos.ts --only ra        # one brand
 *   npx tsx scripts/rerender-brand-videos.ts --dry-run        # preview only
 */
import path from 'node:path';
import fs from 'node:fs';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const studioRoot = path.resolve(__dirname, '..');

interface SceneData {
  stats?: Array<{ value: string; label: string }>;
  flowSteps?: string[];
  comparisonRows?: Array<{ them: string; us: string }>;
  keypoints?: string[];
  eyebrow?: string;
  footnote?: string;
}

interface Scene {
  sceneId: string;
  sceneType: 'hook' | 'body' | 'cta' | 'stat' | 'flow' | 'comparison' | 'keypoints';
  durationSec: number;
  voiceover: string;
  onScreenText: string;
  voiceoverAudioPath?: string;
  data?: SceneData;
}

interface Job {
  jobId: string;
  brand: 'dr' | 'nrpg' | 'ra' | 'carsi' | 'ccw' | 'synthex' | 'unite';
  outputName: string;
  storyboard: Scene[];
}

// ── Storyboards ────────────────────────────────────────────────────────────
//
// Each VO scene's `durationSec` is the audio length + ~0.4s breath.
// Visual-only scenes (no `voiceoverAudioPath`) pad with rich content beats.
// Total runtime is intentionally TIGHT — feel of "1 minute of content" instead
// of "30s of VO floating in 60s of dead air".

const jobs: Job[] = [
  // ── RestoreAssist · App Store preview ─────────────────────────────────────
  {
    jobId: 'ra-appstore-001',
    brand: 'ra',
    outputName: 'ra-app-store-preview.mp4',
    storyboard: [
      {
        sceneId: 'hook',
        sceneType: 'hook',
        durationSec: 5.0,
        voiceoverAudioPath: '/audio/ra-appstore-001/scene-0.mp3',
        voiceover: '',
        onScreenText: 'One National Inspection Standard.',
        data: { eyebrow: 'For Australian restoration' },
      },
      {
        sceneId: 'stat-1',
        sceneType: 'stat',
        durationSec: 5.0,
        voiceover: '',
        onScreenText: 'The fragmentation tax on every claim',
        data: {
          eyebrow: 'By the numbers',
          stats: [
            { value: '50+', label: 'distinct report formats in active use' },
            { value: '20–30%', label: 'of jobs require re-inspection' },
            { value: '$2–5k', label: 'cost per re-inspection cycle' },
          ],
        },
      },
      {
        sceneId: 'body-1',
        sceneType: 'body',
        durationSec: 5.8,
        voiceoverAudioPath: '/audio/ra-appstore-001/scene-1.mp3',
        voiceover: '',
        onScreenText: 'The National Inspection Report standardises every job, every insurer, every assessor.',
        data: { eyebrow: 'The fix' },
      },
      {
        sceneId: 'flow-1',
        sceneType: 'flow',
        durationSec: 6.0,
        voiceover: '',
        onScreenText: 'One workflow, end to end',
        data: {
          eyebrow: 'How it runs',
          flowSteps: ['Inspection', 'AI Analysis', 'Scoping', 'Estimating', 'Reporting'],
        },
      },
      {
        sceneId: 'body-2',
        sceneType: 'keypoints',
        durationSec: 4.4,
        voiceoverAudioPath: '/audio/ra-appstore-001/scene-2.mp3',
        voiceover: '',
        onScreenText: 'What changes for your team',
        data: {
          eyebrow: 'On the truck, in the office',
          keypoints: [
            'Field tech captures once · system does the rest',
            'No double-handling between scope and report',
            'IICRC-grounded · audit-defensible by default',
          ],
        },
      },
      {
        sceneId: 'cta',
        sceneType: 'cta',
        durationSec: 4.0,
        voiceoverAudioPath: '/audio/ra-appstore-001/scene-3.mp3',
        voiceover: '',
        onScreenText: 'One System. Fewer Gaps. More Confidence.',
        data: { eyebrow: 'Now on the App Store' },
      },
    ],
  },

  // ── Disaster Recovery · platform demo ─────────────────────────────────────
  {
    jobId: 'dr-demo-001',
    brand: 'dr',
    outputName: 'dr-platform-demo.mp4',
    storyboard: [
      {
        sceneId: 'hook',
        sceneType: 'hook',
        durationSec: 7.2,
        voiceoverAudioPath: '/audio/dr-demo-001/scene-0.mp3',
        voiceover: '',
        onScreenText: 'When water hits at 4am, the response can\'t wait for office hours.',
        data: { eyebrow: 'Emergency response · Australia + NZ' },
      },
      {
        sceneId: 'stat-1',
        sceneType: 'stat',
        durationSec: 5.0,
        voiceover: '',
        onScreenText: 'Why response time decides the outcome',
        data: {
          eyebrow: 'The first 48 hours',
          stats: [
            { value: '< 2hr', label: 'on-site response in metro areas' },
            { value: '24/7', label: 'dispatch · weekends + public holidays' },
            { value: '500+', label: 'certified contractors · AU + NZ' },
          ],
        },
      },
      {
        sceneId: 'body-1',
        sceneType: 'body',
        durationSec: 10.4,
        voiceoverAudioPath: '/audio/dr-demo-001/scene-1.mp3',
        voiceover: '',
        onScreenText: 'One call. The right contractor. The right scope. From mitigation through to claim close.',
        data: { eyebrow: 'How it works' },
      },
      {
        sceneId: 'body-2',
        sceneType: 'body',
        durationSec: 7.8,
        voiceoverAudioPath: '/audio/dr-demo-001/scene-2.mp3',
        voiceover: '',
        onScreenText: 'Built around the homeowner\'s timeline, not the insurer\'s queue.',
      },
      {
        sceneId: 'compare',
        sceneType: 'comparison',
        durationSec: 6.0,
        voiceover: '',
        onScreenText: 'How the experience changes',
        data: {
          eyebrow: 'Before / After',
          comparisonRows: [
            { them: 'Hours on hold · disconnected loop', us: 'One number · always answered' },
            { them: 'Multiple assessors · multiple visits', us: 'One inspection · NIR-grounded' },
            { them: 'Weeks of uncertainty', us: 'Real-time job status' },
          ],
        },
      },
      {
        sceneId: 'body-3',
        sceneType: 'keypoints',
        durationSec: 6.8,
        voiceoverAudioPath: '/audio/dr-demo-001/scene-3.mp3',
        voiceover: '',
        onScreenText: 'What you actually get',
        data: {
          keypoints: [
            'Live job status — no chasing for updates',
            'IICRC-certified contractors · vetted insurer panels',
            'Direct billing to your insurer',
          ],
        },
      },
      {
        sceneId: 'cta',
        sceneType: 'cta',
        durationSec: 5.4,
        voiceoverAudioPath: '/audio/dr-demo-001/scene-4.mp3',
        voiceover: '',
        onScreenText: 'Disaster Recovery. Always answered.',
        data: { eyebrow: '24/7 · 1300 309 361' },
      },
    ],
  },

  // ── NRPG · community intro ────────────────────────────────────────────────
  {
    jobId: 'nrpg-intro-001',
    brand: 'nrpg',
    outputName: 'nrpg-community-intro.mp4',
    storyboard: [
      {
        sceneId: 'hook',
        sceneType: 'hook',
        durationSec: 6.2,
        voiceoverAudioPath: '/audio/nrpg-intro-001/scene-0.mp3',
        voiceover: '',
        onScreenText: 'The independent voice for Australian restoration practitioners.',
        data: { eyebrow: 'Member-owned · industry-led' },
      },
      {
        sceneId: 'stat-1',
        sceneType: 'stat',
        durationSec: 5.0,
        voiceover: '',
        onScreenText: 'A network with reach',
        data: {
          stats: [
            { value: '500+', label: 'IICRC-certified members' },
            { value: '12', label: 'state + territory chapters' },
            { value: '40+', label: 'CPD events per year' },
          ],
        },
      },
      {
        sceneId: 'body-1',
        sceneType: 'body',
        durationSec: 10.4,
        voiceoverAudioPath: '/audio/nrpg-intro-001/scene-1.mp3',
        voiceover: '',
        onScreenText: 'Standards advocacy. Continuing education. Insurer panel access. Peer support.',
        data: { eyebrow: 'What members get' },
      },
      {
        sceneId: 'body-2',
        sceneType: 'keypoints',
        durationSec: 8.4,
        voiceoverAudioPath: '/audio/nrpg-intro-001/scene-2.mp3',
        voiceover: '',
        onScreenText: 'Why membership matters now',
        data: {
          keypoints: [
            'IICRC S500 / S520 / S700 advocacy',
            'Insurer-panel referrals · paid faster',
            'Mentoring + peer review · industry-led',
          ],
        },
      },
      {
        sceneId: 'body-3',
        sceneType: 'comparison',
        durationSec: 9.5,
        voiceoverAudioPath: '/audio/nrpg-intro-001/scene-3.mp3',
        voiceover: '',
        onScreenText: 'Member vs non-member outcomes',
        data: {
          comparisonRows: [
            { them: 'Solo on insurer compliance', us: 'Industry voice on every standard' },
            { them: 'Cold-called by panel managers', us: 'Direct insurer-panel access' },
            { them: 'Self-funded CPD', us: 'Subsidised CPD + assessment' },
          ],
        },
      },
      {
        sceneId: 'cta',
        sceneType: 'cta',
        durationSec: 4.0,
        voiceoverAudioPath: '/audio/nrpg-intro-001/scene-4.mp3',
        voiceover: '',
        onScreenText: 'NRPG. The voice of the practitioner.',
        data: { eyebrow: 'Apply now' },
      },
    ],
  },

  // ── CARSI · compliance explainer ──────────────────────────────────────────
  {
    jobId: 'carsi-explainer-001',
    brand: 'carsi',
    outputName: 'carsi-compliance-explainer.mp4',
    storyboard: [
      {
        sceneId: 'hook',
        sceneType: 'hook',
        durationSec: 6.3,
        voiceoverAudioPath: '/audio/carsi-explainer-001/scene-0.mp3',
        voiceover: '',
        onScreenText: 'Compliance training built for the real work of restoration.',
        data: { eyebrow: 'CARSI · accredited learning' },
      },
      {
        sceneId: 'stat-1',
        sceneType: 'stat',
        durationSec: 5.0,
        voiceover: '',
        onScreenText: 'Why compliance is the bottleneck',
        data: {
          stats: [
            { value: '7+', label: 'IICRC standards in active use' },
            { value: '3', label: 'Australian Standards mandated for water work' },
            { value: '12mo', label: 'CPD cycle to maintain certification' },
          ],
        },
      },
      {
        sceneId: 'body-1',
        sceneType: 'body',
        durationSec: 8.8,
        voiceoverAudioPath: '/audio/carsi-explainer-001/scene-1.mp3',
        voiceover: '',
        onScreenText: 'Modular CPD. Field-relevant. Built around how technicians actually learn.',
        data: { eyebrow: 'How CARSI is different' },
      },
      {
        sceneId: 'body-2',
        sceneType: 'keypoints',
        durationSec: 8.2,
        voiceoverAudioPath: '/audio/carsi-explainer-001/scene-2.mp3',
        voiceover: '',
        onScreenText: 'The course structure',
        data: {
          keypoints: [
            'IICRC-aligned · S500 / S520 / S700 covered',
            'Self-paced video + assessor-marked practicals',
            'CPD points logged · industry-recognised cert',
          ],
        },
      },
      {
        sceneId: 'compare',
        sceneType: 'comparison',
        durationSec: 5.0,
        voiceover: '',
        onScreenText: 'CARSI vs the typical compliance course',
        data: {
          eyebrow: 'What changes',
          comparisonRows: [
            { them: 'Generic OH&S slide deck', us: 'Field-grounded · IICRC-aligned' },
            { them: 'Tick-box assessment', us: 'Practical assessment · assessor review' },
            { them: 'Cert that no insurer recognises', us: 'Recognised across panel insurers' },
          ],
        },
      },
      {
        sceneId: 'cta',
        sceneType: 'cta',
        durationSec: 3.0,
        voiceoverAudioPath: '/audio/carsi-explainer-001/scene-3.mp3',
        voiceover: '',
        onScreenText: 'CARSI. Compliance, done properly.',
        data: { eyebrow: 'Enrol now' },
      },
    ],
  },

  // ── CCW · trade signup ────────────────────────────────────────────────────
  {
    jobId: 'ccw-signup-001',
    brand: 'ccw',
    outputName: 'ccw-trade-signup.mp4',
    storyboard: [
      {
        sceneId: 'hook',
        sceneType: 'hook',
        durationSec: 6.8,
        voiceoverAudioPath: '/audio/ccw-signup-001/scene-0.mp3',
        voiceover: '',
        onScreenText: 'Wholesale pricing for the trade. Direct from the warehouse.',
        data: { eyebrow: 'Carpet Cleaners Warehouse' },
      },
      {
        sceneId: 'stat-1',
        sceneType: 'stat',
        durationSec: 5.0,
        voiceover: '',
        onScreenText: 'What trade members save',
        data: {
          stats: [
            { value: '15–35%', label: 'off list · across the catalogue' },
            { value: '24hr', label: 'metro dispatch · most stock items' },
            { value: '30-day', label: 'account terms for verified trades' },
          ],
        },
      },
      {
        sceneId: 'body-1',
        sceneType: 'body',
        durationSec: 6.8,
        voiceoverAudioPath: '/audio/ccw-signup-001/scene-1.mp3',
        voiceover: '',
        onScreenText: 'Chemicals. Equipment. Consumables. The full kit, account-priced.',
        data: { eyebrow: 'What\'s in scope' },
      },
      {
        sceneId: 'body-2',
        sceneType: 'keypoints',
        durationSec: 6.8,
        voiceoverAudioPath: '/audio/ccw-signup-001/scene-2.mp3',
        voiceover: '',
        onScreenText: 'Built for restoration crews',
        data: {
          keypoints: [
            'IICRC-recommended chemistry in stock',
            'Equipment finance available for verified members',
            'Australian-owned · Australian-warehoused',
          ],
        },
      },
      {
        sceneId: 'body-3',
        sceneType: 'body',
        durationSec: 6.8,
        voiceoverAudioPath: '/audio/ccw-signup-001/scene-3.mp3',
        voiceover: '',
        onScreenText: 'Apply once. ABN-verified in 24 hours. Order on terms after that.',
      },
      {
        sceneId: 'cta',
        sceneType: 'cta',
        durationSec: 6.0,
        voiceoverAudioPath: '/audio/ccw-signup-001/scene-4.mp3',
        voiceover: '',
        onScreenText: 'CCW. The trade\'s warehouse.',
        data: { eyebrow: 'Apply for an account' },
      },
    ],
  },

  // ── Synthex · product demo ────────────────────────────────────────────────
  {
    jobId: 'synthex-demo-001',
    brand: 'synthex',
    outputName: 'synthex-product-demo.mp4',
    storyboard: [
      {
        sceneId: 'hook',
        sceneType: 'hook',
        durationSec: 5.5,
        voiceoverAudioPath: '/audio/synthex-demo-001/scene-0.mp3',
        voiceover: '',
        onScreenText: 'Marketing automation. Built for Australian + NZ small business.',
        data: { eyebrow: 'Synthex' },
      },
      {
        sceneId: 'stat-1',
        sceneType: 'stat',
        durationSec: 5.0,
        voiceover: '',
        onScreenText: 'Why local SMBs are switching',
        data: {
          stats: [
            { value: '8 hr', label: 'saved per week on content + scheduling' },
            { value: '6+', label: 'channels · one calendar' },
            { value: 'AU/NZ', label: 'tax · timezone · spelling · all native' },
          ],
        },
      },
      {
        sceneId: 'body-1',
        sceneType: 'body',
        durationSec: 7.3,
        voiceoverAudioPath: '/audio/synthex-demo-001/scene-1.mp3',
        voiceover: '',
        onScreenText: 'AI content. Multi-channel posting. Performance attribution. One dashboard.',
      },
      {
        sceneId: 'flow-1',
        sceneType: 'flow',
        durationSec: 6.0,
        voiceover: '',
        onScreenText: 'How a campaign runs end-to-end',
        data: {
          eyebrow: 'The loop',
          flowSteps: ['Brief', 'Generate', 'Schedule', 'Publish', 'Measure'],
        },
      },
      {
        sceneId: 'body-2',
        sceneType: 'body',
        durationSec: 6.6,
        voiceoverAudioPath: '/audio/synthex-demo-001/scene-2.mp3',
        voiceover: '',
        onScreenText: 'BYOK on every AI feature. Your provider, your spend, your control.',
        data: { eyebrow: 'Bring your own key' },
      },
      {
        sceneId: 'body-3',
        sceneType: 'keypoints',
        durationSec: 6.2,
        voiceoverAudioPath: '/audio/synthex-demo-001/scene-3.mp3',
        voiceover: '',
        onScreenText: 'What makes it native',
        data: {
          keypoints: [
            'Australian English by default',
            'AEDT / NZDT scheduling · public holidays mapped',
            'GST-aware billing · ABN invoicing',
          ],
        },
      },
      {
        sceneId: 'body-4',
        sceneType: 'body',
        durationSec: 8.4,
        voiceoverAudioPath: '/audio/synthex-demo-001/scene-4.mp3',
        voiceover: '',
        onScreenText: 'Connect your brands once. Run them all from one dashboard.',
      },
      {
        sceneId: 'cta',
        sceneType: 'cta',
        durationSec: 5.6,
        voiceoverAudioPath: '/audio/synthex-demo-001/scene-5.mp3',
        voiceover: '',
        onScreenText: 'Synthex. Marketing automation, properly local.',
        data: { eyebrow: 'synthex.social' },
      },
    ],
  },

  // ── Unite Group · build update ────────────────────────────────────────────
  {
    jobId: 'unite-update-20260508',
    brand: 'unite',
    outputName: 'unite-group-build-update-20260508.mp4',
    storyboard: [
      {
        sceneId: 'hook',
        sceneType: 'hook',
        durationSec: 8,
        voiceoverAudioPath: '/audio/unite-update-20260508/scene-0.mp3',
        voiceover: '',
        onScreenText: 'Build update · 8 May 2026',
        data: { eyebrow: 'Unite Group · weekly update' },
      },
      {
        sceneId: 'body-1',
        sceneType: 'body',
        durationSec: 13,
        voiceoverAudioPath: '/audio/unite-update-20260508/scene-1.mp3',
        voiceover: '',
        onScreenText: 'RestoreAssist shipped to the App Store this week.',
        data: { eyebrow: 'This week' },
      },
      {
        sceneId: 'body-2',
        sceneType: 'body',
        durationSec: 13,
        voiceoverAudioPath: '/audio/unite-update-20260508/scene-2.mp3',
        voiceover: '',
        onScreenText: 'Synthex Vision Board landed · 9-panel review surface for the launch.',
      },
      {
        sceneId: 'body-3',
        sceneType: 'body',
        durationSec: 13,
        voiceoverAudioPath: '/audio/unite-update-20260508/scene-3.mp3',
        voiceover: '',
        onScreenText: 'Brain-2 vault wired across Pi-CEO ↔ Synthex with live observability.',
      },
      {
        sceneId: 'body-4',
        sceneType: 'body',
        durationSec: 13,
        voiceoverAudioPath: '/audio/unite-update-20260508/scene-4.mp3',
        voiceover: '',
        onScreenText: 'CARSI + CCW design systems committed to brand-config.',
      },
      {
        sceneId: 'body-5',
        sceneType: 'body',
        durationSec: 13,
        voiceoverAudioPath: '/audio/unite-update-20260508/scene-5.mp3',
        voiceover: '',
        onScreenText: 'HERMES org-impersonation fix shipped · cross-business switching working.',
      },
      {
        sceneId: 'body-6',
        sceneType: 'body',
        durationSec: 13,
        voiceoverAudioPath: '/audio/unite-update-20260508/scene-6.mp3',
        voiceover: '',
        onScreenText: 'Wave 9 cross-system connections committed to main.',
      },
      {
        sceneId: 'cta',
        sceneType: 'cta',
        durationSec: 12,
        voiceoverAudioPath: '/audio/unite-update-20260508/scene-7.mp3',
        voiceover: '',
        onScreenText: 'Unite Group. Building together.',
        data: { eyebrow: 'Next week · NRPG community launch' },
      },
    ],
  },
];

// ── Runner ─────────────────────────────────────────────────────────────────

interface Args {
  only?: string;
  dryRun: boolean;
}

function parseArgs(): Args {
  const args = process.argv.slice(2);
  const out: Args = { dryRun: false };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--only' && args[i + 1]) out.only = args[++i];
    else if (args[i] === '--dry-run') out.dryRun = true;
  }
  return out;
}

async function renderJob(job: Job): Promise<{ ok: boolean; output: string; durationSec: number }> {
  const props = {
    brand: job.brand,
    hookSec: 5,
    ctaSec: 5,
    storyboard: job.storyboard,
  };
  const totalDur = job.storyboard.reduce((s, sc) => s + sc.durationSec, 0);
  const outputPath = path.join(studioRoot, 'output', job.outputName);

  console.log(`\n▶ ${job.jobId}  →  ${job.outputName}  (${job.storyboard.length} scenes, ${totalDur.toFixed(1)}s)`);

  return new Promise(resolve => {
    const child = spawn(
      'npx',
      [
        'tsx',
        path.join(studioRoot, 'render', 'render.ts'),
        `--comp=Explainer`,
        `--out=${outputPath}`,
        `--props=${JSON.stringify(props)}`,
        `--jobId=${job.jobId}`,
        `--skipTts`,
      ],
      { cwd: studioRoot, stdio: 'inherit' },
    );
    child.on('close', code => {
      const ok = code === 0 && fs.existsSync(outputPath);
      resolve({ ok, output: outputPath, durationSec: totalDur });
    });
  });
}

async function main(): Promise<void> {
  const args = parseArgs();
  const targets = args.only ? jobs.filter(j => j.brand === args.only || j.jobId.includes(args.only!)) : jobs;
  if (!targets.length) {
    console.error(`No jobs match --only=${args.only}`);
    process.exit(1);
  }

  console.log(`Re-rendering ${targets.length} brand video(s) with new Explainer composition`);
  console.log(`Targets: ${targets.map(t => t.jobId).join(', ')}`);

  if (args.dryRun) {
    for (const j of targets) {
      const total = j.storyboard.reduce((s, sc) => s + sc.durationSec, 0);
      console.log(`\n  ${j.jobId}  · ${j.storyboard.length} scenes · ${total.toFixed(1)}s total`);
      for (const sc of j.storyboard) {
        const has = sc.voiceoverAudioPath ? '🔊' : '🎨';
        console.log(`    ${has} ${sc.sceneId.padEnd(10)} ${sc.sceneType.padEnd(10)} ${sc.durationSec}s`);
      }
    }
    return;
  }

  const results: Array<{ job: Job; ok: boolean; durationSec: number }> = [];
  for (const j of targets) {
    const r = await renderJob(j);
    results.push({ job: j, ok: r.ok, durationSec: r.durationSec });
  }

  console.log('\n=== Summary ===');
  for (const r of results) {
    const tick = r.ok ? '✅' : '❌';
    console.log(`  ${tick}  ${r.job.outputName}  (${r.durationSec.toFixed(1)}s)`);
  }
  const failed = results.filter(r => !r.ok);
  if (failed.length) {
    console.error(`\n${failed.length} job(s) failed`);
    process.exit(1);
  }
}

main().catch(err => {
  console.error('rerender-brand-videos failed:', err);
  process.exit(1);
});
