/**
 * Margot embeddable assistant surfaces — SSOT for per-project bubbles.
 *
 * Same Margot persona + avatar everywhere; role label, welcome copy, and
 * data scope differ per brand. Backend routes must enforce tenant_id /
 * project_slug — UI copy alone is not isolation.
 */

export type MargotSurfaceProject = 'unite-group' | 'restoreassist' | 'carsi';

export interface MargotSurfaceConfig {
  project: MargotSurfaceProject;
  /** Supabase / margot_conversations tenant slug */
  tenantId: string;
  displayName: 'Margot';
  roleLabel: string;
  welcomeMessage: string;
  /** Injected into assistant system prompts — project data boundary */
  scopeLock: string;
  /** Public path to canonical avatar (each site copies to /margot/avatar.png) */
  avatarPath: string;
  /** Bubble launcher accent (hex) — from brand-config theme */
  accentColor: string;
}

export const MARGOT_CANONICAL_AVATAR_PATH = '/margot/avatar.png';

export const MARGOT_DISPLAY_NAME = 'Margot' as const;

export const margotSurfaces: Record<MargotSurfaceProject, MargotSurfaceConfig> = {
  'unite-group': {
    project: 'unite-group',
    tenantId: 'unite-group',
    displayName: 'Margot',
    roleLabel: 'Personal assistant',
    welcomeMessage:
      "Hi — I'm Margot, your Unite-Group personal assistant. Ask about portfolio status, priorities, CRM tasks, or what to route next.",
    scopeLock:
      'You operate ONLY for Unite-Group portfolio context (founder operations, CRM, command centre, cross-business priorities). Do not answer as RestoreAssist, CARSI, or other portfolio products unless the user explicitly asks for a comparison. Never invent client data.',
    avatarPath: MARGOT_CANONICAL_AVATAR_PATH,
    accentColor: '#1D4ED8',
  },
  restoreassist: {
    project: 'restoreassist',
    tenantId: 'restoreassist',
    displayName: 'Margot',
    roleLabel: 'Client help',
    welcomeMessage:
      "Hi — I'm Margot, your RestoreAssist client help assistant. Ask how to create reports, manage clients, pricing, workflows, or platform features.",
    scopeLock:
      'You operate ONLY for RestoreAssist (Australian water-damage restoration platform). Use RestoreAssist features, workflows, and help content only. Do not discuss Unite-Group internal ops, CARSI courses, or unrelated portfolio businesses.',
    avatarPath: MARGOT_CANONICAL_AVATAR_PATH,
    accentColor: '#8A6B4E',
  },
  carsi: {
    project: 'carsi',
    tenantId: 'carsi',
    displayName: 'Margot',
    roleLabel: 'Online assistant',
    welcomeMessage:
      "Hi — I'm Margot, your CARSI online assistant. Ask about courses, IICRC disciplines, enrolment, certificates, or your learning dashboard.",
    scopeLock:
      'You operate ONLY for CARSI (carsi.com.au) published courses, LMS flows, and IICRC learning context. Ground course facts in the server-provided catalogue block only. Do not discuss RestoreAssist restoration workflows or Unite-Group internal operations.',
    avatarPath: MARGOT_CANONICAL_AVATAR_PATH,
    accentColor: '#2490ed',
  },
};

export function getMargotSurface(project: MargotSurfaceProject): MargotSurfaceConfig {
  return margotSurfaces[project];
}
