import Link from 'next/link';
import { site, services } from '@/lib/content';
import { ButtonLink, Reading } from './primitives';

const NAV = [
  { href: '/services/', label: 'Services' },
  { href: '/assessment-finder/', label: 'Assessment finder' },
  { href: '/about/', label: 'How we work' },
  { href: '/contact/', label: 'Contact' },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-panel/92 backdrop-blur-md">
      <div className="wrap flex min-h-[4.5rem] flex-wrap items-center gap-x-8 gap-y-2 py-2">
        <Link href="/" className="group no-underline">
          <span className="block text-[1.2rem] font-extrabold tracking-[0.14em] text-primary">BEWG</span>
          <span className="block text-[0.66rem] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            {site.legalName}
          </span>
        </Link>
        <nav aria-label="Main" className="ml-auto flex flex-wrap items-center gap-x-6 gap-y-1">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className="text-[0.94rem] font-semibold text-muted-foreground no-underline hover:text-primary"
            >
              {n.label}
            </Link>
          ))}
          <a href={`tel:${site.phoneHref}`} className="no-underline">
            <Reading className="text-[0.94rem] font-bold text-primary">{site.phone}</Reading>
          </a>
        </nav>
      </div>
    </header>
  );
}

/** Closing band. One primary action, stated as a question the visitor is actually asking. */
export function CtaBand() {
  return (
    <section className="border-y border-border bg-primary py-16 text-primary-foreground">
      <div className="wrap">
        <h2 className="text-[length:var(--text-display-md)]">Not sure which assessment you need?</h2>
        <p className="measure mt-4 text-[length:var(--text-body-lg)] text-white/80">
          Six questions, about a minute. You get the investigation that fits your situation, what it
          involves, and a written brief you can send us or keep.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-4">
          <ButtonLink href="/assessment-finder/">Find the right assessment</ButtonLink>
          <ButtonLink href={`tel:${site.phoneHref}`} variant="onDark">
            Call {site.phone}
          </ButtonLink>
        </div>
      </div>
    </section>
  );
}

export function SiteFooter() {
  return (
    <footer className="bg-secondary py-14 text-white/70">
      <div className="wrap">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-[1.1rem] font-extrabold tracking-[0.14em] text-white">BEWG</p>
            <p className="mt-3 text-[0.92rem]">{site.tagline}</p>
            <p className="mt-2 text-[0.92rem]">{site.coverage}</p>
          </div>
          <div>
            <h3 className="mb-3 text-[0.76rem] uppercase tracking-[0.14em] text-white">Services</h3>
            <ul className="space-y-2 text-[0.92rem]">
              {services.map((s) => (
                <li key={s.slug}>
                  <Link href={`/services/${s.slug}/`} className="no-underline hover:text-white hover:underline">
                    {s.nav}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="mb-3 text-[0.76rem] uppercase tracking-[0.14em] text-white">Start here</h3>
            <ul className="space-y-2 text-[0.92rem]">
              <li><Link href="/assessment-finder/" className="no-underline hover:text-white hover:underline">Find the right assessment</Link></li>
              <li><Link href="/contact/" className="no-underline hover:text-white hover:underline">Request an assessment</Link></li>
              <li><Link href="/about/" className="no-underline hover:text-white hover:underline">How we work</Link></li>
            </ul>
          </div>
          <div>
            <h3 className="mb-3 text-[0.76rem] uppercase tracking-[0.14em] text-white">Contact</h3>
            <ul className="space-y-2 text-[0.92rem]">
              <li><a href={`tel:${site.phoneHref}`} className="no-underline hover:text-white hover:underline"><Reading>{site.phone}</Reading></a></li>
              <li><a href={`mailto:${site.email}`} className="no-underline hover:text-white hover:underline">{site.email}</a></li>
            </ul>
            <p className="mt-4 text-[0.86rem]">{site.lab}</p>
          </div>
        </div>
        <p className="mt-10 border-t border-white/12 pt-6 text-[0.84rem] text-white/55">
          © {new Date().getFullYear()} {site.legalName}. Independent building science investigation.
          Reports describe building conditions and exposure indicators. They are not medical or legal advice.
        </p>
      </div>
    </footer>
  );
}
