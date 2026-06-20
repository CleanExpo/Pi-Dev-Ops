/**
 * RA-Launch-NIR — RestoreAssist National Inspection Report explainer (SYN-921).
 *
 * 90s / 1920×1080 / LinkedIn. Five 18s scenes, sweep transitions, en-AU VO
 * (voiceId Sarah). This is a thin storyboard over the data-driven `Explainer`
 * composition — no forked render logic, so it inherits the brand-locked motion,
 * colour, and scene renderers. The creative lives entirely in the storyboard.
 *
 * Brand-voice guards (brand-voice-enforce):
 *  - never the abbreviation "RA" in VO or on-screen titles — always "RestoreAssist"
 *  - AI is an assistant that records + documents, never assesses or diagnoses
 *  - Australian English · Grade 4–6 · active voice · no artificial urgency
 *  - the only CTA is the App Store
 */
import {
  Explainer,
  explainerSchema,
  type ExplainerProps,
} from './Explainer';

export const raLaunchNirSchema = explainerSchema;

/** Reuses the Explainer renderer; the NIR creative is the storyboard below. */
export const RALaunchNIR = Explainer;

export const defaultRaLaunchNirProps: ExplainerProps = {
  brand: 'ra',
  hookSec: 18,
  ctaSec: 18,
  storyboard: [
    {
      sceneId: 'hook',
      sceneType: 'hook',
      durationSec: 18,
      onScreenText: '50 formats. One claim.',
      voiceover:
        'Across Australia, restoration teams document the same job in dozens of different report formats.',
      data: { eyebrow: 'The problem' },
    },
    {
      sceneId: 'stat-cost',
      sceneType: 'stat',
      durationSec: 18,
      onScreenText: 'Re-inspections add up.',
      voiceover:
        'When the formats do not match, re-inspections follow — and each one adds two to five thousand dollars to a claim.',
      data: {
        eyebrow: 'The cost',
        stats: [
          { value: '20–30%', label: 'of jobs need a re-inspection' },
          { value: '$2,000–$5,000', label: 'added cost per re-inspection' },
        ],
      },
    },
    {
      sceneId: 'keypoints-standard',
      sceneType: 'keypoints',
      durationSec: 18,
      onScreenText: 'One report. IICRC-grounded.',
      voiceover:
        'The National Inspection Report is one shared format, grounded in IICRC standards.',
      data: {
        eyebrow: 'The standard',
        keypoints: [
          'S500 — water damage',
          'S520 — mould',
          'S700 — fire and smoke',
        ],
      },
    },
    {
      sceneId: 'flow-pipeline',
      sceneType: 'flow',
      durationSec: 18,
      onScreenText: 'Captured once. Documented end to end.',
      voiceover:
        'The field technician captures the details once. The assistant organises and documents them — through scoping, estimating, and reporting.',
      data: {
        eyebrow: 'The flow',
        flowSteps: [
          'Inspection',
          'AI Summary',
          'Scoping',
          'Estimating',
          'Reporting',
        ],
      },
    },
    {
      sceneId: 'cta',
      sceneType: 'cta',
      durationSec: 18,
      onScreenText: 'One System. Fewer Gaps. More Confidence.',
      voiceover:
        'RestoreAssist. One system, grounded in the standards. Now on the App Store.',
      data: { eyebrow: 'RestoreAssist', footnote: 'Now on the App Store' },
    },
  ],
};
