import servicesJson from '@/content/services.json';
import triageJson from '@/content/triage.json';
import siteJson from '@/content/site.json';

export interface Service {
  slug: string;
  title: string;
  nav: string;
  short: string;
  headline: string;
  intro: string;
  signs: string[];
  method: string[];
  deliverables: string[];
  standards: string[];
  related: string[];
}

export interface TriageOption {
  value: string;
  weights: Record<string, number>;
}

export interface TriageQuestion {
  id: string;
  label: string;
  help?: string;
  multi: boolean;
  required: boolean;
  options: TriageOption[];
}

export interface Triage {
  intro: string;
  questions: TriageQuestion[];
  urgency: { high: string; normal: string };
}

export interface Site {
  name: string;
  legalName: string;
  tagline: string;
  email: string;
  phone: string;
  phoneHref: string;
  coverage: string;
  lab: string;
  baseUrl: string;
}

export const site = siteJson as Site;
export const services = servicesJson as Service[];
export const triage = triageJson as Triage;

export function getService(slug: string): Service | undefined {
  return services.find((s) => s.slug === slug);
}

export function relatedTo(service: Service): Service[] {
  return service.related
    .map((slug) => getService(slug))
    .filter((s): s is Service => Boolean(s));
}

/**
 * Content invariants enforced at build time. Next runs this during the static
 * export, so a broken link or an unreachable service fails the build rather
 * than shipping. Mirrors the guarantees the old generator made.
 */
export function assertContentValid(): void {
  const slugs = new Set(services.map((s) => s.slug));
  const errors: string[] = [];

  if (slugs.size !== services.length) errors.push('duplicate service slug');

  for (const s of services) {
    if (!/^[a-z0-9-]+$/.test(s.slug)) errors.push(`bad slug: ${s.slug}`);
    for (const key of ['signs', 'method', 'deliverables', 'standards'] as const) {
      if (!s[key]?.length) errors.push(`${s.slug}: empty "${key}"`);
    }
    for (const r of s.related) {
      if (!slugs.has(r)) errors.push(`${s.slug}: related "${r}" is not a service`);
      if (r === s.slug) errors.push(`${s.slug}: related links to itself`);
    }
  }

  const routable = new Set<string>();
  for (const q of triage.questions) {
    if (!q.options.length) errors.push(`triage "${q.id}": no options`);
    for (const o of q.options) {
      for (const w of Object.keys(o.weights)) {
        if (!slugs.has(w)) errors.push(`triage "${q.id}" → "${o.value}": unknown service "${w}"`);
        routable.add(w);
      }
    }
  }

  /* A service the finder can never recommend is a page nobody is routed to. */
  for (const s of services) {
    if (!routable.has(s.slug)) errors.push(`${s.slug}: no triage answer routes to it`);
  }

  if (errors.length) {
    throw new Error(`BEWG content invalid:\n  - ${errors.join('\n  - ')}`);
  }
}
