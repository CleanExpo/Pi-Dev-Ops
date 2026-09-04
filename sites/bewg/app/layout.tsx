import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { SiteHeader, SiteFooter } from '@/components/site-chrome';
import { site, assertContentValid } from '@/lib/content';
import './globals.css';

/* Content invariants run once at build time. A dead link, an empty section or a
   service the finder can never reach fails the export rather than shipping. */
assertContentValid();

export const metadata: Metadata = {
  metadataBase: new URL(site.baseUrl),
  title: {
    default: `Moisture, Mould & Building Science Investigation Australia | ${site.name}`,
    template: `%s | ${site.name}`,
  },
  description:
    'Independent building science investigation across Australia. Mould and indoor air quality, ' +
    'moisture mapping, condensation diagnosis, hygrothermal modelling and building defect investigation.',
  openGraph: { type: 'website', locale: 'en_AU', siteName: site.name },
  robots: { index: true, follow: true },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en-AU">
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[100] focus:rounded focus:bg-panel focus:px-4 focus:py-2 focus:font-bold"
        >
          Skip to content
        </a>
        <SiteHeader />
        <main id="main">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
