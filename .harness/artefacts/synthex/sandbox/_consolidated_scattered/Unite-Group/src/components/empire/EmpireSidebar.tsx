'use client';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  CommandCenterMark, ClientsMark, ActivityMark,
  BarChartMark, TrendUpMark, WikiMark, FeedMark,
  ReportsMark, UsersMark, ChevronRightMark,
} from '@/components/ui/marks';

// Canonical portfolio slugs — these MUST match the slugs returned by
// /api/empire/businesses and the dynamic segment of /empire/businesses/[slug].
// Past versions had `dr-platform` and `nrpg` which both 404 — the real routes
// are `disaster-recovery` and `dr-nrpg`.
const BUSINESS_SLUGS: Record<string, { slug: string; domain: string }> = {
  'RestoreAssist': { slug: 'restoreassist',     domain: 'restoreassist.app' },
  'Synthex':       { slug: 'synthex',           domain: 'synthex.social' },
  'CCW-CRM':       { slug: 'ccw-crm',           domain: 'carpetcleanerswarehouse.com.au' },
  'DR Platform':   { slug: 'disaster-recovery', domain: 'disasterrecovery.com.au' },
  'NRPG':          { slug: 'dr-nrpg',           domain: 'nrpg.com.au' },
  'CARSI':         { slug: 'carsi',             domain: 'carsi.com.au' },
};

const AUTH_ROUTES = ['/login', '/register', '/reset-password', '/update-password'];
const CLIENT_ROUTES = ['/clients/']; // client portals get their own clean layout

const NAV = [
  { href: '/empire',      mark: CommandCenterMark, label: 'Command Center' },
  { href: '/clients/ccw', mark: ClientsMark,       label: 'CCW Portal'     },
];

const INTELLIGENCE_NAV = [
  { href: '/wiki',                mark: WikiMark,      label: 'Knowledge Base'   },
  { href: '/sources',             mark: FeedMark,      label: 'Sources Pipeline' },
  { href: '/pi-ceo/activity',     mark: ActivityMark,  label: 'Activity Log'     },
  { href: '/empire/developers',   mark: UsersMark,     label: 'Developers'       },
  { href: '/pi-ceo/health',       mark: ReportsMark,   label: 'Health History'   },
  { href: '/pi-ceo/reports',      mark: BarChartMark,  label: 'SEO Reports'      },
];

const BUSINESSES = [
  { label: 'RestoreAssist', color: '#0E7C7B', status: 'building'    },
  { label: 'Synthex',       color: '#6366F1', status: 'operational' },
  { label: 'CCW-CRM',       color: '#DC2626', status: 'operational' },
  { label: 'DR Platform',   color: '#2563EB', status: 'operational' },
  { label: 'NRPG',          color: '#16A34A', status: 'building'    },
  { label: 'CARSI',         color: '#D97706', status: 'operational' },
];

const STATUS_COLOR: Record<string, string> = {
  operational: '#16a34a',
  building:    '#f59e0b',
  degraded:    '#d97706',
  down:        '#dc2626',
};

const stripLocale = (path: string) => path.replace(/^\/(en|es|fr)(?=\/|$)/, '');

export function EmpireSidebar() {
  const pathname = usePathname();
  const isAuthRoute = AUTH_ROUTES.some(r => pathname.endsWith(r));
  const isClientRoute = CLIENT_ROUTES.some(r => pathname.startsWith(r));
  const localeStrippedPath = stripLocale(pathname);
  const isCommandCenterRoute =
    localeStrippedPath === '/command-center' ||
    localeStrippedPath.startsWith('/command-center/');
  // Sidebar now always shows the SEO sub-link under each brand — the accordion
  // toggle was cosmetic (5 of 6 brands revealed nothing). Detail page lives at
  // /empire/businesses/[slug]; SEO audit lives at /businesses/[slug]/seo.
  if (isAuthRoute || isClientRoute) return null;

  return (
    <aside className={isCommandCenterRoute ? 'empire-sidebar empire-sidebar-command-center' : 'empire-sidebar'} style={{ width: 240, minHeight: '100vh', background: '#0c0c0e', border: '1px solid #27272a', borderTop: 'none', borderBottom: 'none', borderLeft: 'none', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>

      {/* Wordmark */}
      <div style={{ height: 64, display: 'flex', alignItems: 'center', padding: '0 20px', borderBottom: '1px solid #27272a' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Image src="/logo-mark.svg" width={32} height={32} alt="Unite Group" style={{ flexShrink: 0 }} />
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#fafafa', letterSpacing: '-0.02em', fontFamily: 'var(--font-display)' }}>Unite Group</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 1 }}>
              <span className="status-dot" style={{ width: 5, height: 5, background: '#f59e0b', color: '#f59e0b' }} />
              <span style={{ fontSize: 10, fontWeight: 600, color: '#f59e0b', letterSpacing: '0.06em', textTransform: 'uppercase' }}>Empire</span>
            </div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: '12px 10px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {NAV.map(({ href, mark: Mark, label }) => {
          const localeStripped = stripLocale(pathname); const active = localeStripped === href || localeStripped.startsWith(href + '/') || pathname === href || pathname.startsWith(href + '/');
          return (
            <Link
              key={href}
              href={href}
              style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
                borderRadius: 8, textDecoration: 'none',
                background: active ? 'rgba(29,78,216,0.12)' : 'transparent',
                borderLeft: active ? '2px solid #f59e0b' : '2px solid transparent',
                transition: 'all 0.12s ease',
              }}
              onMouseEnter={e => { if (!active) (e.currentTarget as HTMLAnchorElement).style.background = 'rgba(255,255,255,0.03)'; }}
              onMouseLeave={e => { if (!active) (e.currentTarget as HTMLAnchorElement).style.background = 'transparent'; }}
            >
              <Mark size={15} color={active ? '#60a5fa' : '#a1a1aa'} />
              <span style={{ fontSize: 13, fontWeight: active ? 500 : 400, color: active ? '#fafafa' : '#a1a1aa', flex: 1 }}>{label}</span>
              {active && <ChevronRightMark size={12} color="#f59e0b" />}
            </Link>
          );
        })}

        {/* Intelligence section */}
        <div style={{ marginTop: 16, marginBottom: 6, padding: '0 10px' }}>
          <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--ink-tertiary)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Intelligence</span>
        </div>
        {INTELLIGENCE_NAV.map(({ href, mark: Mark, label }) => {
          const localeStripped = stripLocale(pathname); const active = localeStripped === href || localeStripped.startsWith(href + '/') || pathname === href || pathname.startsWith(href + '/');
          return (
            <Link
              key={href}
              href={href}
              style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
                borderRadius: 8, textDecoration: 'none',
                background: active ? 'rgba(29,78,216,0.12)' : 'transparent',
                borderLeft: active ? '2px solid #f59e0b' : '2px solid transparent',
                transition: 'all 0.12s ease',
              }}
              onMouseEnter={e => { if (!active) (e.currentTarget as HTMLAnchorElement).style.background = 'rgba(255,255,255,0.03)'; }}
              onMouseLeave={e => { if (!active) (e.currentTarget as HTMLAnchorElement).style.background = 'transparent'; }}
            >
              <Mark size={15} color={active ? '#60a5fa' : '#a1a1aa'} />
              <span style={{ fontSize: 13, fontWeight: active ? 500 : 400, color: active ? '#fafafa' : '#a1a1aa', flex: 1 }}>{label}</span>
              {active && <ChevronRightMark size={12} color="#f59e0b" />}
            </Link>
          );
        })}

        {/* Portfolio section */}
        <div style={{ marginTop: 16, marginBottom: 6, padding: '0 10px' }}>
          <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--ink-tertiary)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Portfolio</span>
        </div>
        {BUSINESSES.map(biz => {
          const meta = BUSINESS_SLUGS[biz.label];
          if (!meta) return null;
          const detailHref = `/empire/businesses/${meta.slug}`;
          const seoHref = `/businesses/${meta.slug}/seo`;
          const detailActive = localeStrippedPath === detailHref || localeStrippedPath.startsWith(detailHref + '/');
          const seoActive = localeStrippedPath === seoHref || pathname === seoHref;
          return (
            <div key={biz.label}>
              {/* Top-level — real link to the business detail page */}
              <Link
                href={detailHref}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8, padding: '5px 10px',
                  borderRadius: 6, textDecoration: 'none',
                  background: detailActive ? 'rgba(29,78,216,0.12)' : 'transparent',
                  borderLeft: detailActive ? '2px solid #f59e0b' : '2px solid transparent',
                  transition: 'background 0.1s ease',
                }}
                onMouseEnter={e => { if (!detailActive) (e.currentTarget as HTMLAnchorElement).style.background = 'rgba(255,255,255,0.03)'; }}
                onMouseLeave={e => { if (!detailActive) (e.currentTarget as HTMLAnchorElement).style.background = 'transparent'; }}
              >
                <span className="status-dot" style={{ width: 6, height: 6, background: STATUS_COLOR[biz.status], color: STATUS_COLOR[biz.status], flexShrink: 0 }} />
                <span style={{ fontSize: 12, color: detailActive ? '#fafafa' : '#a1a1aa', flex: 1, textAlign: 'left' }}>{biz.label}</span>
                {detailActive && <ChevronRightMark size={10} color="#f59e0b" />}
              </Link>

              {/* Always-visible SEO sub-link — works for all 6 brands */}
              <div style={{ paddingLeft: 24, paddingBottom: 4, display: 'flex', flexDirection: 'column', gap: 1 }}>
                <Link
                  href={seoHref}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 7, padding: '4px 10px',
                    borderRadius: 6, textDecoration: 'none', fontSize: 11,
                    color: seoActive ? '#a1a1aa' : 'var(--ink-tertiary)',
                    transition: 'all 0.1s ease',
                    background: seoActive ? 'rgba(29,78,216,0.1)' : 'transparent',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.background = 'rgba(255,255,255,0.04)'; (e.currentTarget as HTMLAnchorElement).style.color = '#a1a1aa'; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.background = seoActive ? 'rgba(29,78,216,0.1)' : 'transparent'; (e.currentTarget as HTMLAnchorElement).style.color = seoActive ? '#a1a1aa' : 'var(--ink-tertiary)'; }}
                >
                  <TrendUpMark size={10} color="var(--ink-tertiary)" />
                  SEO Audit
                </Link>
              </div>
            </div>
          );
        })}

        {/* Clients section */}
        <div style={{ marginTop: 16, marginBottom: 6, padding: '0 10px' }}>
          <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--ink-tertiary)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Clients</span>
        </div>

        {/* CCW — existing client */}
        <Link
          href="/clients/ccw"
          style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '5px 10px',
            borderRadius: 6, textDecoration: 'none', transition: 'all 0.1s ease',
            background: pathname.startsWith('/clients/ccw') ? 'rgba(29,78,216,0.1)' : 'transparent',
          }}
          onMouseEnter={e => { if (!pathname.startsWith('/clients/ccw')) (e.currentTarget as HTMLAnchorElement).style.background = 'rgba(255,255,255,0.03)'; }}
          onMouseLeave={e => { if (!pathname.startsWith('/clients/ccw')) (e.currentTarget as HTMLAnchorElement).style.background = 'transparent'; }}
        >
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#DC2626', display: 'inline-block', flexShrink: 0 }} />
          <span style={{ fontSize: 12, color: '#a1a1aa', flex: 1 }}>CCW</span>
          <span style={{ fontSize: 9, fontWeight: 600, color: '#16a34a', letterSpacing: '0.04em', textTransform: 'uppercase' }}>Active</span>
        </Link>

        {/* Add Client */}
        <Link
          href="/clients"
          style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '5px 10px',
            borderRadius: 6, textDecoration: 'none', transition: 'all 0.1s ease',
            background: pathname === '/clients' ? 'rgba(29,78,216,0.1)' : 'transparent',
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.background = 'rgba(255,255,255,0.03)'; }}
          onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.background = pathname === '/clients' ? 'rgba(29,78,216,0.1)' : 'transparent'; }}
        >
          <span style={{ fontSize: 14, color: 'var(--ink-tertiary)', lineHeight: 1 }}>+</span>
          <span style={{ fontSize: 11, color: 'var(--ink-tertiary)' }}>Add / Manage Clients</span>
        </Link>
      </nav>

      {/* Footer */}
      <div style={{ padding: '12px 10px', borderTop: '1px solid #27272a' }}>
        <Link
          href="/clients"
          style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 8, textDecoration: 'none', transition: 'all 0.12s ease' }}
          onMouseEnter={e => ((e.currentTarget as HTMLAnchorElement).style.background = 'rgba(255,255,255,0.03)')}
          onMouseLeave={e => ((e.currentTarget as HTMLAnchorElement).style.background = 'transparent')}
        >
          <UsersMark size={14} color="var(--ink-tertiary)" />
          <span style={{ fontSize: 12, color: 'var(--ink-tertiary)' }}>Manage Clients</span>
        </Link>
      </div>
    </aside>
  );
}
