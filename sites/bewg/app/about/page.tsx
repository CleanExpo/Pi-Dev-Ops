import type { Metadata } from 'next';
import Link from 'next/link';
import { site } from '@/lib/content';
import { ButtonLink, Marked, Reading } from '@/components/primitives';
import { CtaBand } from '@/components/site-chrome';

export const metadata: Metadata = {
  title: 'How we work',
  description:
    'Independent building science investigation across Australia. Measurement before opinion, ' +
    'independent of the rectification, reports written to be acted on.',
};

const LIMITS = [
  'No medical advice and no interpretation of health outcomes. Building conditions and exposure ' +
    'indicators are reported; clinical questions belong with a medical practitioner.',
  'No building is certified as safe. What was measured is reported, where, and under what conditions.',
  'No finding is written to suit the party paying for it.',
];

export default function AboutPage() {
  return (
    <>
      <section className="border-b border-border bg-panel-2 py-14">
        <div className="wrap">
          <p className="text-[0.9rem] text-muted-foreground">
            <Link href="/" className="underline underline-offset-4">Home</Link> / How we work
          </p>
          <h1 className="mt-4 text-[length:var(--text-display-lg)]">How we work</h1>
          <p className="measure mt-5 text-[length:var(--text-body-lg)] text-muted-foreground">
            {site.tagline} {site.coverage}
          </p>
        </div>
      </section>

      <section className="wrap grid gap-12 py-16 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,0.95fr)]">
        <div>
          <p className="max-w-[32ch] border-l-4 border-accent pl-6 text-[length:var(--text-headline)] font-bold text-primary">
            Hired to answer a question, not to sell the answer&rsquo;s remedy.
          </p>
          <p className="measure mt-8 text-[length:var(--text-body-lg)] text-muted-foreground">
            {site.legalName} investigates moisture, condensation, indoor air quality and building
            defect across Australia. The work is diagnostic: establish what is happening inside the
            building, establish why, and set out what the evidence supports doing about it.
          </p>

          <h2 className="mt-14 text-[length:var(--text-headline)]">Independent of the rectification</h2>
          <p className="measure mt-5 text-muted-foreground">
            The remediation recommended here is not remediation carried out here, and no margin is
            taken on it. That matters most in the cases where the honest finding is that a proposed
            scope is larger than the evidence supports.
          </p>

          <h2 className="mt-12 text-[length:var(--text-headline)]">Measurement before opinion</h2>
          <p className="measure mt-5 text-muted-foreground">
            Calibrated moisture metering, thermal imaging, psychrometry and pressurisation testing,
            with reference readings from unaffected areas so a number can be interpreted rather than
            merely reported. Where a question needs laboratory work, samples go to a NATA-accredited
            laboratory and results are read against the building conditions measured on site.
          </p>

          <h2 className="mt-12 text-[length:var(--text-headline)]">Written for whoever must act on it</h2>
          <p className="measure mt-5 text-muted-foreground">
            A report has to survive a contractor pricing the work, an insurer assessing the claim and,
            sometimes, an expert engaged by the other side. Every finding shows the evidence chain from
            observation to conclusion, and the recommended scope can be priced without a further round
            of questions.
          </p>

          <h2 className="mt-12 text-[length:var(--text-headline)]">What is out of scope</h2>
          <Marked items={LIMITS} />
        </div>

        <aside className="h-fit rounded-[12px] border border-border bg-panel p-6 lg:sticky lg:top-28">
          <h2 className="text-[1.05rem]">Coverage</h2>
          <p className="mt-3 text-[0.94rem] text-muted-foreground">{site.coverage}</p>
          <h3 className="mt-6 text-[1.02rem]">Laboratory</h3>
          <p className="mt-3 text-[0.94rem] text-muted-foreground">{site.lab}</p>
          <h3 className="mt-6 text-[1.02rem]">Start here</h3>
          <div className="mt-4">
            <ButtonLink href="/assessment-finder/" className="w-full">Find the right assessment</ButtonLink>
          </div>
          <p className="mt-5">
            <a href={`tel:${site.phoneHref}`} className="no-underline">
              <Reading className="text-[1.05rem] font-bold text-primary">{site.phone}</Reading>
            </a>
          </p>
        </aside>
      </section>

      <CtaBand />
    </>
  );
}
