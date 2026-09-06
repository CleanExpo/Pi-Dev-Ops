import type { MetadataRoute } from 'next';
import { site, services } from '@/lib/content';

export const dynamic = 'force-static';

export default function sitemap(): MetadataRoute.Sitemap {
  const paths = ['/', '/services/', '/assessment-finder/', '/about/', '/contact/',
    ...services.map((s) => `/services/${s.slug}/`)];
  return paths.map((p) => ({ url: `${site.baseUrl}${p}`, lastModified: new Date() }));
}
