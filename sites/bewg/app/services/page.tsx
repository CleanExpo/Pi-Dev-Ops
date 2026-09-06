import type { Metadata } from 'next';
import Link from 'next/link';
import { services } from '@/lib/content';
import { Reading } from '@/components/primitives';
import { CtaBand } from '@/components/site-chrome';

export const metadata: Metadata = {
  title: 'Building science investigation services',
  description:
    'Mould and IAQ investigation, moisture mapping, condensation diagnosis, hygrothermal modelling, ' +
    'building defect investigation, timber floor moisture, air leakage testing and major loss assessment.',
};

export default function ServicesPage() {
  return (
    <>
      <section className="border-b border-border bg-panel-2 py-16">
        <div className="wrap">
          <p className="text-[0.9rem] text-muted-foreground">
            <Link href="/" className="underline underline-offset-4">Home</Link> / Services
          </p>
          <h1 className="mt-4 text-[length:var(--text-display-lg)]">Services</h1>
          <p className="measure mt-6 text-[length:var(--text-body-lg)] text-muted-foreground">
            Each investigation sets out what it is for, the signs that point to it, how it is carried
            out and exactly what you receive. If your situation spans more than one, say so — most real
            problems do.
          </p>
        </div>
      </section>

      <section className="wrap py-16">
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {services.map((s, i) => (
            <Link
              key={s.slug}
              href={`/services/${s.slug}/`}
              className="group flex flex-col rounded-[12px] border border-border bg-panel p-6 no-underline transition-colors hover:border-primary"
            >
              <Reading className="text-[0.72rem] text-muted-foreground">
                {String(i + 1).padStart(2, '0')}
              </Reading>
              <h2 className="mt-3 text-[1.08rem] font-bold group-hover:text-primary">{s.title}</h2>
              <p className="mt-3 text-[0.94rem] text-muted-foreground">{s.short}</p>
              <span className="mt-auto pt-5 text-[0.92rem] font-bold text-primary">
                What this involves →
              </span>
            </Link>
          ))}
        </div>
      </section>

      <CtaBand />
    </>
  );
}
