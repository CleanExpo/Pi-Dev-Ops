import type { Metadata } from 'next';
import Link from 'next/link';
import { site } from '@/lib/content';
import { ButtonLink, Marked, Reading } from '@/components/primitives';

export const metadata: Metadata = {
  title: 'Request an assessment',
  description: `Request a building science assessment. Call ${site.phone} or email ${site.email}.`,
};

const HELPS = [
  'What you are seeing or smelling, and where in the building',
  'When it started, and whether it changes with the season or the weather',
  'Building type, age, and how many levels are affected',
  'What has already been done about it, and whether it came back',
  'What the report is for — insurance, strata, a dispute, or getting it fixed',
  'Photographs, if you have them',
];

export default function ContactPage() {
  return (
    <>
      <section className="border-b border-border bg-panel-2 py-14">
        <div className="wrap">
          <p className="text-[0.9rem] text-muted-foreground">
            <Link href="/" className="underline underline-offset-4">Home</Link> / Contact
          </p>
          <h1 className="mt-4 text-[length:var(--text-display-lg)]">Request an assessment</h1>
          <p className="measure mt-5 text-[length:var(--text-body-lg)] text-muted-foreground">
            Describe what you are seeing and you will get the investigation that fits, and what it costs.
          </p>
        </div>
      </section>

      <section className="wrap grid gap-12 py-16 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,0.95fr)]">
        <div>
          <h2 className="text-[length:var(--text-headline)]">The fastest way to an accurate quote</h2>
          <p className="measure mt-5 text-[length:var(--text-body-lg)] text-muted-foreground">
            Run the assessment finder first. It takes about a minute, identifies which investigation
            suits the situation, and produces a written brief. Send that brief and the work can be
            priced without a round of back-and-forth.
          </p>
          <div className="mt-8">
            <ButtonLink href="/assessment-finder/">Find the right assessment</ButtonLink>
          </div>

          <h2 className="mt-14 text-[length:var(--text-headline)]">Or make contact directly</h2>
          <p className="mt-6">
            <a href={`tel:${site.phoneHref}`} className="no-underline">
              <Reading className="text-[1.5rem] font-bold text-primary">{site.phone}</Reading>
            </a>
          </p>
          <p className="mt-2 text-[1.05rem]">
            <a href={`mailto:${site.email}`} className="font-bold text-primary underline underline-offset-4">
              {site.email}
            </a>
          </p>

          <h2 className="mt-14 text-[length:var(--text-headline)]">What helps us quote accurately</h2>
          <Marked items={HELPS} />
        </div>

        <aside className="h-fit rounded-[12px] border border-border bg-panel p-6 lg:sticky lg:top-28">
          <h2 className="text-[1.05rem]">Coverage</h2>
          <p className="mt-3 text-[0.94rem] text-muted-foreground">{site.coverage}</p>
          <h3 className="mt-6 text-[1.02rem]">Active water?</h3>
          <p className="mt-3 text-[0.94rem] text-muted-foreground">
            If water is still entering the building, or an occupant is vulnerable, say so when you make
            contact. It changes how quickly attendance is needed.
          </p>
          <h3 className="mt-6 text-[1.02rem]">Laboratory</h3>
          <p className="mt-3 text-[0.94rem] text-muted-foreground">{site.lab}</p>
        </aside>
      </section>
    </>
  );
}
