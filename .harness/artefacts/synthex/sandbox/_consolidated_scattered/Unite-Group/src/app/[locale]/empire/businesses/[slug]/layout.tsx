import type { Metadata } from 'next';

// Mirror of the BUSINESS_NAMES map in ./page.tsx — kept here so layout
// metadata can resolve the brand label without converting the page to
// a server component. Update both in lock-step.
const BUSINESS_NAMES: Record<string, string> = {
  'synthex': 'Synthex',
  'restoreassist': 'RestoreAssist',
  'dr-nrpg': 'NRPG',
  'carsi': 'CARSI',
  'ccw-crm': 'CCW-CRM',
  'disaster-recovery': 'DR Platform',
};

export async function generateMetadata(
  { params }: { params: Promise<{ slug: string }> }
): Promise<Metadata> {
  const { slug } = await params;
  const name = BUSINESS_NAMES[slug] ?? slug;
  return {
    title: `${name} — Business Health`,
    description: `Live health metrics and operational status for ${name}.`,
  };
}

export default function BusinessSlugLayout({ children }: { children: React.ReactNode }) {
  return children;
}
