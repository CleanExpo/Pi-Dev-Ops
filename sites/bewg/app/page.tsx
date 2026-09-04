import Link from 'next/link';
import { site, services } from '@/lib/content';
import { ButtonLink, Eyebrow, Reading, Chip } from '@/components/primitives';
import { CtaBand } from '@/components/site-chrome';

const PILLARS = [
  {
    title: 'Measured, not estimated',
    body: 'Calibrated metering, thermal imaging and psychrometry, with reference readings taken from ' +
      'unaffected areas so a number can be interpreted rather than merely reported.',
  },
  {
    title: 'Independent of the repair',
    body: 'The rectification we recommend is not work we quote for. The finding is not shaped by who ' +
      'stands to win the remediation.',
  },
  {
    title: 'Written to be acted on',
    body: 'A scope a contractor can price, evidence an insurer can assess, and reasoning that holds ' +
      'when the other side reads it.',
  },
];

export default function HomePage() {
  return (
    <>
      <section className="thermal text-white">
        <div className="wrap py-20 lg:py-28">
          <p className="reading mb-6 text-[0.75rem] uppercase tracking-[0.18em] text-white/65">
            {site.legalName}
          </p>
          <h1 className="max-w-[17ch] text-[length:var(--text-display-xl)]">
            The mould is the symptom. We find what keeps it wet.
          </h1>
          <p className="measure mt-7 text-[length:var(--text-body-lg)] text-white/80">
            Independent building science investigation across Australia. Moisture, condensation, indoor
            air quality and building defect — diagnosed by measurement and laboratory analysis.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-4">
            <ButtonLink href="/assessment-finder/">Find the right assessment</ButtonLink>
            <ButtonLink href={`tel:${site.phoneHref}`} variant="onDark">
              Call {site.phone}
            </ButtonLink>
          </div>
          <ul className="mt-12 flex flex-wrap gap-2.5">
            {['NATA-accredited laboratory analysis', 'Attendance Australia-wide',
              'Reports for insurers, strata and disputes'].map((c) => (
              <li
                key={c}
                className="reading rounded-full border border-white/22 bg-white/10 px-3.5 py-1.5 text-[0.78rem] text-white/85"
              >
                {c}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="wrap py-20">
        <Eyebrow>The problem with most damp reports</Eyebrow>
        <h2 className="max-w-[22ch] text-[length:var(--text-display-md)]">
          A report that names the mould but not the moisture is worth nothing.
        </h2>
        <p className="measure mt-6 text-[length:var(--text-body-lg)] text-muted-foreground">
          Remediation without a documented moisture source fails, usually within a season. Every
          investigation starts by establishing the mechanism keeping the building wet — where the water
          comes from, why it stays, and what it will take to stop it. Laboratory work quantifies the
          consequence. It never replaces the diagnosis.
        </p>
        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {PILLARS.map((p) => (
            <article key={p.title} className="rounded-[12px] border border-border bg-panel p-6">
              <h3 className="text-[1.08rem]">{p.title}</h3>
              <p className="mt-3 text-[0.96rem] text-muted-foreground">{p.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="border-y border-border bg-panel-2 py-20">
        <div className="wrap">
          <Eyebrow>Services</Eyebrow>
          <h2 className="max-w-[20ch] text-[length:var(--text-display-md)]">
            Eight investigations, one discipline.
          </h2>
          <p className="measure mt-6 text-[length:var(--text-body-lg)] text-muted-foreground">
            Each answers the same underlying question: where is the water, why is it there, and what
            does the evidence support doing about it.
          </p>
          <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {services.map((s, i) => (
              <Link
                key={s.slug}
                href={`/services/${s.slug}/`}
                className="group flex flex-col rounded-[12px] border border-border bg-panel p-6 no-underline transition-colors hover:border-primary"
              >
                <Reading className="text-[0.72rem] text-muted-foreground">
                  {String(i + 1).padStart(2, '0')}
                </Reading>
                <h3 className="mt-3 text-[1.08rem] group-hover:text-primary">{s.title}</h3>
                <p className="mt-3 text-[0.94rem] text-muted-foreground">{s.short}</p>
                <span className="mt-auto pt-5 text-[0.92rem] font-bold text-primary">
                  What this involves →
                </span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="wrap py-20">
        <Eyebrow>Coverage</Eyebrow>
        <h2 className="max-w-[24ch] text-[length:var(--text-display-md)]">
          Attendance anywhere in Australia, metro and regional.
        </h2>
        <p className="measure mt-6 text-[length:var(--text-body-lg)] text-muted-foreground">
          {site.lab} Sampling is interpreted against the building conditions measured on site, never
          read out in isolation.
        </p>
        <div className="mt-8 flex flex-wrap gap-2.5">
          <Chip>{site.phone}</Chip>
          <Chip>{site.email}</Chip>
        </div>
      </section>

      <CtaBand />
    </>
  );
}
