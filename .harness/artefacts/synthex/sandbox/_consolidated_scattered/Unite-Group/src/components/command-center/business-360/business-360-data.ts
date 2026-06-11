// business-360-data.ts — static seed for Zone 4 Business 360.
//
// PR-3 ships with hand-curated values so the eye sees real shape.
// Live wiring deferred to a follow-up PR that binds to /api/pi-ceo/history
// + Stripe MRR + repo activity per the redesign proposal data-binding list.
//
// Each business has:
//   - id / name / slug          — identity
//   - logoSrc                   — real PNG/SVG path under /public, OR null
//                                 (null → BusinessTile renders a custom
//                                 geometric SVG mark per
//                                 [[feedback-design-preferences]] Option B —
//                                 NEVER a generic placeholder image)
//   - kpiLabel / kpiValue       — single primary KPI shown on tile
//   - kpiSuffix                 — optional unit suffix
//   - series                    — sparkline data points (~14 days)
//   - state                     — running | signal | hush

export type BusinessState = 'running' | 'signal' | 'hush';

export interface Business360Datum {
  id: string;
  name: string;
  slug: string;
  logoSrc: string | null;
  kpiLabel: string;
  kpiValue: number;
  kpiSuffix?: string;
  kpiPrefix?: string;
  series: number[];
  state: BusinessState;
  stateLabel: string;
}

// Series are intentionally hand-shaped so each line has narrative — not
// random walks. CCW trends down (Toby on holidays). RA trends up (RA-2947
// epic shipping). DR-NRPG steady. CARSI ramping. Synthex flat (pre-launch).
// Unite-Group flat baseline.
export const BUSINESS_360_DATA: Business360Datum[] = [
  {
    id: 'ccw-crm',
    name: 'CCW',
    slug: 'ccw-crm',
    logoSrc: '/logos/ccw.png',
    kpiLabel: 'Open tickets',
    kpiValue: 14,
    series: [9, 10, 11, 12, 12, 13, 13, 14, 15, 16, 15, 15, 14, 14],
    state: 'signal',
    stateLabel: 'Toby on holidays · 18 May resume',
  },
  {
    id: 'restoreassist',
    name: 'RestoreAssist',
    slug: 'restoreassist',
    logoSrc: '/logos/restoreassist.png',
    kpiLabel: 'Mandates shipped',
    kpiValue: 47,
    series: [22, 25, 28, 30, 33, 35, 36, 38, 40, 42, 43, 45, 46, 47],
    state: 'running',
    stateLabel: 'RA-2947 floor-plan epic landing',
  },
  {
    id: 'disaster-recovery',
    name: 'Disaster Recovery',
    slug: 'disaster-recovery',
    logoSrc: '/logos/disaster-recovery.png',
    kpiLabel: 'Pipeline jobs',
    kpiValue: 31,
    series: [28, 29, 30, 30, 29, 31, 31, 30, 31, 32, 31, 31, 31, 31],
    state: 'running',
    stateLabel: 'CORE-modelled positioning · steady',
  },
  {
    id: 'dr-nrpg',
    name: 'NRPG',
    slug: 'dr-nrpg',
    logoSrc: '/logos/nrpg.png',
    kpiLabel: 'Members',
    kpiValue: 8,
    series: [3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 7, 8, 8, 8],
    state: 'running',
    stateLabel: 'ANZ trade-body build · founding-30',
  },
  {
    id: 'carsi',
    name: 'CARSI',
    slug: 'carsi',
    logoSrc: '/logos/carsi.png',
    kpiLabel: 'Courses live',
    kpiValue: 12,
    series: [4, 5, 6, 6, 7, 8, 9, 9, 10, 10, 11, 11, 12, 12],
    state: 'running',
    stateLabel: 'IICRC content batch-3 in build',
  },
  {
    id: 'synthex',
    name: 'Synthex',
    slug: 'synthex',
    logoSrc: '/logos/synthex.png',
    kpiLabel: 'Apps wired',
    kpiValue: 6,
    series: [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 5, 6, 6, 6],
    state: 'running',
    stateLabel: 'Brand-config canonical · 6/6 wired',
  },
  {
    id: 'unite-group',
    name: 'Unite-Group',
    slug: 'unite-group',
    // No logo file at /public/logos/unite-group.* — BusinessTile renders
    // the custom geometric mark per design preferences Option B.
    logoSrc: null,
    kpiLabel: 'Clients onboarded',
    kpiValue: 2,
    series: [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 2, 2, 2],
    state: 'running',
    stateLabel: 'CCW + Duncan · hour-1 SLA holding',
  },
];

// Six-tile grid per spec — pick the top six by current strategic priority.
// Unite-Group lives in the parent shell (Zone 1 wordmark), so the 6 tiles
// here are the portfolio brands + first client.
export const BUSINESS_360_TILES = BUSINESS_360_DATA.filter(
  (b) => b.id !== 'unite-group',
);
