import type { Metadata } from 'next';
import Link from 'next/link';
import { triage, services, site } from '@/lib/content';
import { AssessmentFinder } from '@/components/assessment-finder';

export const metadata: Metadata = {
  title: 'Assessment finder',
  description:
    'Answer six questions about what you are seeing in your building. Find out which building science ' +
    'assessment fits, what it involves, and get a written brief to send us.',
};

export default function AssessmentFinderPage() {
  return (
    <>
      <section className="border-b border-border bg-panel-2 py-14">
        <div className="wrap">
          <p className="text-[0.9rem] text-muted-foreground">
            <Link href="/" className="underline underline-offset-4">Home</Link> / Assessment finder
          </p>
          <h1 className="mt-4 max-w-[18ch] text-[length:var(--text-display-lg)]">
            Which assessment do you actually need?
          </h1>
          <p className="measure mt-5 text-[length:var(--text-body-lg)] text-muted-foreground">
            {triage.intro}
          </p>
        </div>
      </section>

      <section className="wrap py-14">
        <div className="mx-auto max-w-4xl">
          <AssessmentFinder triage={triage} services={services} email={site.email} />
          <p className="mt-8 text-[0.94rem] text-muted-foreground">
            Prefer to talk it through? Call{' '}
            <a href={`tel:${site.phoneHref}`} className="font-bold text-primary underline underline-offset-4">
              {site.phone}
            </a>{' '}
            or email{' '}
            <a href={`mailto:${site.email}`} className="font-bold text-primary underline underline-offset-4">
              {site.email}
            </a>.
          </p>
        </div>
      </section>
    </>
  );
}
