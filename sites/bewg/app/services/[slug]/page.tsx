import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { services, getService, relatedTo, site } from '@/lib/content';
import { ButtonLink, Chip, Marked, Steps, Reading } from '@/components/primitives';

export function generateStaticParams() {
  return services.map((s) => ({ slug: s.slug }));
}

export async function generateMetadata(
  { params }: { params: Promise<{ slug: string }> }
): Promise<Metadata> {
  const service = getService((await params).slug);
  if (!service) return {};
  return { title: service.title, description: service.short };
}

export default async function ServicePage({ params }: { params: Promise<{ slug: string }> }) {
  const service = getService((await params).slug);
  if (!service) notFound();
  const related = relatedTo(service);

  return (
    <>
      <section className="border-b border-border bg-panel-2 py-14">
        <div className="wrap">
          <p className="text-[0.9rem] text-muted-foreground">
            <Link href="/" className="underline underline-offset-4">Home</Link> /{' '}
            <Link href="/services/" className="underline underline-offset-4">Services</Link> /{' '}
            {service.nav}
          </p>
          <h1 className="mt-4 max-w-[20ch] text-[length:var(--text-display-lg)]">{service.title}</h1>
          <p className="measure mt-5 text-[length:var(--text-body-lg)] text-muted-foreground">
            {service.short}
          </p>
        </div>
      </section>

      <section className="wrap grid gap-12 py-16 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,0.95fr)]">
        <div>
          <p className="max-w-[34ch] border-l-4 border-accent pl-6 text-[length:var(--text-headline)] font-bold text-primary">
            {service.headline}
          </p>
          <p className="measure mt-8 text-[length:var(--text-body-lg)] text-muted-foreground">
            {service.intro}
          </p>

          <h2 className="mt-14 text-[length:var(--text-headline)]">Signs you need this assessment</h2>
          <Marked items={service.signs} />

          <h2 className="mt-14 text-[length:var(--text-headline)]">How the investigation runs</h2>
          <Steps items={service.method} />

          <h2 className="mt-14 text-[length:var(--text-headline)]">What you receive</h2>
          <Marked items={service.deliverables} />

          <h2 className="mt-14 text-[length:var(--text-headline)]">Standards and methods applied</h2>
          <ul className="mt-6 flex flex-wrap gap-2.5">
            {service.standards.map((s) => <li key={s}><Chip>{s}</Chip></li>)}
          </ul>
        </div>

        <aside className="h-fit rounded-[12px] border border-border bg-panel p-6 lg:sticky lg:top-28">
          <h2 className="text-[1.05rem]">Is this the right assessment?</h2>
          <p className="mt-3 text-[0.94rem] text-muted-foreground">
            If you are not certain, the finder takes about a minute, tells you which investigation fits,
            and writes a brief you can send us.
          </p>
          <div className="mt-5">
            <ButtonLink href="/assessment-finder/" className="w-full">Find the right assessment</ButtonLink>
          </div>

          <h3 className="mt-8 text-[1.02rem]">Speak to someone</h3>
          <p className="mt-3">
            <a href={`tel:${site.phoneHref}`} className="no-underline">
              <Reading className="text-[1.05rem] font-bold text-primary">{site.phone}</Reading>
            </a>
          </p>
          <p className="mt-1.5 text-[0.94rem]">
            <a href={`mailto:${site.email}`} className="text-primary underline underline-offset-4">
              {site.email}
            </a>
          </p>

          {related.length > 0 && (
            <>
              <h3 className="mt-8 text-[1.02rem]">Often runs alongside</h3>
              <ul className="mt-3 space-y-2.5">
                {related.map((r) => (
                  <li key={r.slug} className="flex gap-3 text-[0.94rem]">
                    <span className="mt-2 size-1.5 shrink-0 rotate-45 bg-accent" aria-hidden />
                    <Link href={`/services/${r.slug}/`} className="text-primary underline underline-offset-4">
                      {r.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
        </aside>
      </section>
    </>
  );
}
