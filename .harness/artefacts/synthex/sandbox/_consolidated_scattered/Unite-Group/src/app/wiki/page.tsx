'use client';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { supabaseClient } from '@/lib/supabase/client';
import { WikiMark, SearchMark, ChevronRightMark, ClockMark, TagMark } from '@/components/ui/marks';

interface WikiPage {
  id: string;
  title: string;
  word_count: number;
  tags: string[];
  updated_at: string;
}

interface WikiPageFull extends WikiPage {
  content: string;
}

// ── Category definitions ────────────────────────────────────────────────────

const CATEGORIES: { label: string; key: string; tags: string[] }[] = [
  { label: 'FOUNDATION',  key: 'foundation',  tags: ['founder', 'businesses-overview', 'exit-thesis'] },
  { label: 'SYSTEM',      key: 'system',      tags: ['pi-ceo-architecture', 'wave-roadmap', 'decision-frameworks'] },
  { label: 'BUSINESSES',  key: 'businesses',  tags: ['synthex', 'restore-assist', 'dr-nrpg', 'carsi', 'ccw', 'unite-crm'] },
  { label: 'INTELLIGENCE',key: 'intelligence', tags: ['tech-drops-q2-2026', 'seo-linkable-assets', 'creator-radar'] },
  { label: 'QUALITY',     key: 'quality',     tags: ['qa-lead', 'brand-guardian'] },
  { label: 'NEXUS',       key: 'nexus',       tags: ['unite-group-nexus-architecture', 'nexus-team-composition', 'nexus-design-system'] },
];

function getCategory(tags: string[]): string {
  if (!tags || tags.length === 0) return 'other';
  for (const cat of CATEGORIES) {
    if (tags.some(t => cat.tags.includes(t))) return cat.key;
  }
  return 'other';
}

// ── Markdown renderer ────────────────────────────────────────────────────────

import DOMPurify from 'isomorphic-dompurify';

function renderMarkdown(md: string, highlight?: string): string {
  let html = md
    .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\[\[([^\]]+)\]\]/g, '<span class="wl">$1</span>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
    .replace(/^\d+\. (.+)$/gm, '<oli>$1</oli>')
    .replace(/^---+$/gm, '<hr/>')
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
    .replace(/\n{2,}/g, '\n\n');

  html = html.replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m}</ul>`);
  html = html.replace(/(<oli>.*<\/oli>\n?)+/g, m => `<ol>${m.replace(/<\/?oli>/g, s => s === '<oli>' ? '<li>' : '</li>')}</ol>`);

  html = html.split('\n\n').map(block => {
    if (/^<[h1-6|ul|ol|pre|hr|blockquote]/.test(block.trim())) return block;
    if (!block.trim()) return '';
    return `<p>${block.trim()}</p>`;
  }).join('\n');

  if (highlight) {
    const escaped = highlight.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    html = html.replace(new RegExp(`(${escaped})`, 'gi'), '<mark>$1</mark>');
  }

  // Per UNI-1958 (Pi-SEO scanner finding): wiki content comes from a Supabase
  // table that crosses a trust boundary on render. Even though the renderer
  // only emits tags it constructs from markdown, the input string passes
  // through unchanged — raw `<script>` or `<img onerror=>` in `md` would
  // survive. DOMPurify strips dangerous elements/attrs after our markdown
  // substitutions have produced HTML.
  return DOMPurify.sanitize(html);
}

function relativeDate(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });
}

export default function WikiPage() {
  const router = useRouter();
  const [pages, setPages]           = useState<WikiPage[]>([]);
  const [active, setActive]         = useState<WikiPageFull | null>(null);
  const [search, setSearch]         = useState('');
  const [loading, setLoading]       = useState(true);
  const [pageLoading, setPageLoading] = useState(false);
  const [openCats, setOpenCats]     = useState<Set<string>>(new Set(['foundation', 'system', 'businesses']));
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    supabaseClient.auth.getSession().then(({ data: { session } }) => {
      if (!session) router.push('/login');
    });
  }, [router]);

  useEffect(() => {
    supabaseClient
      .from('wiki_pages')
      .select('id, title, tags, word_count, updated_at')
      .order('title')
      .then(({ data }) => {
        setPages(data || []);
        setLoading(false);
      });
  }, []);

  const openPage = useCallback((id: string) => {
    setPageLoading(true);
    setSidebarOpen(false);
    fetch(`/api/wiki?slug=${encodeURIComponent(id)}`)
      .then(r => r.json())
      .then((data: WikiPageFull) => { setActive(data); setPageLoading(false); })
      .catch(() => setPageLoading(false));
  }, []);

  const toggleCat = (key: string) => {
    setOpenCats(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  // Build category buckets
  const catBuckets = CATEGORIES.map(cat => {
    const catPages = pages.filter(p => getCategory(p.tags) === cat.key);
    const filteredPages = search
      ? catPages.filter(p => p.title.toLowerCase().includes(search.toLowerCase()))
      : catPages;
    return { ...cat, pages: filteredPages };
  }).filter(c => c.pages.length > 0 || !search);

  // Pages not in any category
  const otherPages = pages.filter(p => getCategory(p.tags) === 'other');
  const filteredOther = search
    ? otherPages.filter(p => p.title.toLowerCase().includes(search.toLowerCase()))
    : otherPages;

  // Category overview tiles (for no-page-selected state)
  const overviewTiles = CATEGORIES.map(cat => {
    const catPages = pages.filter(p => getCategory(p.tags) === cat.key);
    const lastUpdated = catPages.length > 0
      ? catPages.reduce((a, b) => new Date(a.updated_at) > new Date(b.updated_at) ? a : b).updated_at
      : null;
    return { ...cat, count: catPages.length, lastUpdated };
  });

  return (
    <div style={{ minHeight: '100vh', background: 'var(--canvas)', display: 'flex', flexDirection: 'column' }}>

      {/* Top bar */}
      <header style={{
        height: 52, display: 'flex', alignItems: 'center', gap: 12,
        padding: '0 20px', borderBottom: '1px solid var(--border-default)',
        background: 'var(--surface-1)', flexShrink: 0,
      }}>
        <WikiMark size={16} color="var(--red-500)" />
        <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink-primary)', letterSpacing: '-0.02em' }}>
          Knowledge Base
        </span>
        <span style={{ fontSize: 11, color: 'var(--ink-tertiary)', fontFamily: 'var(--font-mono)' }}>
          {pages.length} pages
        </span>
        <div style={{ flex: 1 }} />
        <button
          onClick={() => setSidebarOpen(s => !s)}
          className="sidebar-toggle"
          style={{
            display: 'none', background: 'transparent',
            border: '1px solid var(--border-default)', color: 'var(--ink-secondary)',
            borderRadius: 6, padding: '4px 10px', fontSize: 11, cursor: 'pointer',
          }}
        >Pages</button>
      </header>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Sidebar */}
        <aside
          className={`wiki-sidebar${sidebarOpen ? ' open' : ''}`}
          style={{
            width: 260, borderRight: '1px solid var(--border-default)',
            background: 'var(--surface-1)', display: 'flex', flexDirection: 'column',
            flexShrink: 0, overflowY: 'auto',
          }}
        >
          {/* Search */}
          <div style={{ padding: '10px 10px 8px', borderBottom: '1px solid var(--border-default)' }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'var(--canvas)', border: '1px solid var(--border-default)',
              borderRadius: 6, padding: '6px 10px',
            }}>
              <SearchMark size={12} color="var(--ink-tertiary)" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search pages..."
                style={{
                  flex: 1, background: 'transparent', border: 'none', outline: 'none',
                  color: 'var(--ink-primary)', fontSize: 12,
                }}
              />
            </div>
          </div>

          {/* Category tree */}
          <nav style={{ flex: 1, padding: '6px 0' }}>
            {loading ? (
              <div style={{ padding: '16px 14px', color: 'var(--ink-tertiary)', fontSize: 11 }}>Loading...</div>
            ) : (
              <>
                {catBuckets.map(cat => (
                  <div key={cat.key}>
                    {/* Category header */}
                    <button
                      onClick={() => toggleCat(cat.key)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        width: '100%', padding: '5px 14px', border: 'none',
                        background: 'transparent', cursor: 'pointer', textAlign: 'left',
                      }}
                    >
                      <span style={{
                        fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
                        color: 'var(--ink-tertiary)', textTransform: 'uppercase', flex: 1,
                      }}>
                        {cat.label}
                      </span>
                      <span style={{
                        fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--ink-tertiary)',
                        background: 'var(--canvas)', padding: '1px 5px', borderRadius: 3,
                      }}>
                        {cat.pages.length}
                      </span>
                        <span style={{ transform: openCats.has(cat.key) ? 'rotate(90deg)' : 'none', transition: 'transform 0.1s', display: 'inline-flex' }}>
                        <ChevronRightMark size={9} color="var(--ink-tertiary)" />
                      </span>
                    </button>

                    {/* Pages under category */}
                    {openCats.has(cat.key) && cat.pages.map(p => {
                      const isActive = active?.id === p.id;
                      return (
                        <button
                          key={p.id}
                          onClick={() => openPage(p.id)}
                          style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            width: '100%', textAlign: 'left', padding: '5px 14px 5px 22px',
                            border: 'none', cursor: 'pointer',
                            background: isActive ? 'color-mix(in srgb, var(--red-500) 10%, transparent)' : 'transparent',
                            borderLeft: isActive ? '2px solid var(--red-500)' : '2px solid transparent',
                            transition: 'background 0.1s',
                          }}
                        >
                          <span style={{
                            flex: 1, fontSize: 12, lineHeight: 1.4,
                            color: isActive ? 'var(--ink-primary)' : 'var(--ink-secondary)',
                            fontWeight: isActive ? 500 : 400,
                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          }}>
                            {p.title}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                ))}

                {/* Other / uncategorised */}
                {filteredOther.length > 0 && (
                  <div>
                    <div style={{ padding: '5px 14px', fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--ink-tertiary)', textTransform: 'uppercase' }}>
                      OTHER
                    </div>
                    {filteredOther.map(p => {
                      const isActive = active?.id === p.id;
                      return (
                        <button
                          key={p.id}
                          onClick={() => openPage(p.id)}
                          style={{
                            display: 'flex', width: '100%', textAlign: 'left',
                            padding: '5px 14px 5px 22px', border: 'none', cursor: 'pointer',
                            background: isActive ? 'color-mix(in srgb, var(--red-500) 10%, transparent)' : 'transparent',
                            borderLeft: isActive ? '2px solid var(--red-500)' : '2px solid transparent',
                          }}
                        >
                          <span style={{ flex: 1, fontSize: 12, color: isActive ? 'var(--ink-primary)' : 'var(--ink-secondary)', fontWeight: isActive ? 500 : 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {p.title}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </nav>
        </aside>

        {/* Main content */}
        <main style={{ flex: 1, overflowY: 'auto', padding: '32px 40px' }}>
          {pageLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}>
              <div style={{ width: 28, height: 28, border: '2px solid var(--red-500)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
            </div>
          ) : active ? (
            <>
              {/* Page meta */}
              <div style={{ marginBottom: 24 }}>
                <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--ink-primary)', margin: '0 0 10px', letterSpacing: '-0.03em' }}>
                  {active.title}
                </h1>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--ink-tertiary)', fontFamily: 'var(--font-mono)' }}>
                    <ClockMark size={11} color="var(--ink-tertiary)" />
                    {active.word_count?.toLocaleString()} words
                  </span>
                  {active.updated_at && (
                    <span style={{ fontSize: 11, color: 'var(--ink-tertiary)', fontFamily: 'var(--font-mono)' }}>
                      {relativeDate(active.updated_at)}
                    </span>
                  )}
                  {active.tags?.length > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
                      <TagMark size={10} color="var(--ink-tertiary)" />
                      {active.tags.slice(0, 6).map(t => (
                        <span key={t} style={{
                          fontSize: 10, padding: '1px 6px',
                          background: 'var(--surface-2)',
                          color: 'var(--ink-secondary)',
                          borderRadius: 4, border: '1px solid var(--border-default)',
                          fontFamily: 'var(--font-mono)',
                        }}>{t}</span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div style={{ height: 1, background: 'var(--border-default)', marginBottom: 28 }} />

              {/* Rendered markdown */}
              <div
                className="wiki-content"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(active.content || '', search) }}
              />
            </>
          ) : (
            /* No page selected — category overview grid */
            <>
              <div style={{ marginBottom: 28 }}>
                <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink-primary)', margin: '0 0 6px', letterSpacing: '-0.03em' }}>
                  Intelligence Portal
                </h1>
                <p style={{ margin: 0, fontSize: 13, color: 'var(--ink-secondary)' }}>
                  {pages.length} pages across {CATEGORIES.length} categories — select a page or category
                </p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                {overviewTiles.map(tile => (
                  <button
                    key={tile.key}
                    onClick={() => toggleCat(tile.key)}
                    style={{
                      background: 'var(--surface-1)', border: '1px solid var(--border-default)',
                      borderRadius: 'var(--radius-md)', padding: '16px 18px',
                      textAlign: 'left', cursor: 'pointer', transition: 'border-color 0.1s',
                    }}
                  >
                    <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--red-500)', textTransform: 'uppercase', marginBottom: 8 }}>
                      {tile.label}
                    </div>
                    <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink-primary)', fontFamily: 'var(--font-mono)', marginBottom: 4 }}>
                      {tile.count}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--ink-tertiary)' }}>
                      {tile.count === 1 ? 'page' : 'pages'}
                      {tile.lastUpdated && (
                        <span style={{ marginLeft: 8 }}>· {relativeDate(tile.lastUpdated)}</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </>
          )}
        </main>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }

        .wiki-content h1 { font-size: 20px; font-weight: 700; color: var(--ink-primary); margin: 28px 0 10px; letter-spacing: -0.02em; }
        .wiki-content h2 { font-size: 16px; font-weight: 600; color: var(--ink-primary); margin: 24px 0 8px; border-bottom: 1px solid var(--border-default); padding-bottom: 6px; }
        .wiki-content h3 { font-size: 14px; font-weight: 600; color: var(--ink-secondary); margin: 20px 0 6px; }
        .wiki-content h4 { font-size: 11px; font-weight: 600; color: var(--ink-tertiary); margin: 16px 0 4px; text-transform: uppercase; letter-spacing: 0.08em; }
        .wiki-content p  { font-size: 14px; color: var(--ink-secondary); line-height: 1.75; margin: 0 0 14px; }
        .wiki-content ul { list-style: none; padding: 0; margin: 0 0 14px; }
        .wiki-content ul li { font-size: 14px; color: var(--ink-secondary); line-height: 1.7; padding: 2px 0 2px 16px; position: relative; }
        .wiki-content ul li::before { content: "·"; position: absolute; left: 4px; color: var(--ink-tertiary); }
        .wiki-content ol { padding-left: 20px; margin: 0 0 14px; }
        .wiki-content ol li { font-size: 14px; color: var(--ink-secondary); line-height: 1.7; }
        .wiki-content pre { background: var(--surface-2); border: 1px solid var(--border-default); border-radius: var(--radius-md); padding: 14px 16px; overflow-x: auto; margin: 16px 0; }
        .wiki-content code { font-family: var(--font-mono); font-size: 12px; color: var(--ink-primary); background: var(--surface-2); padding: 1px 4px; border-radius: 3px; }
        .wiki-content pre code { background: transparent; padding: 0; color: var(--ink-secondary); }
        .wiki-content a { color: var(--red-500); text-decoration: none; }
        .wiki-content a:hover { text-decoration: underline; }
        .wiki-content strong { color: var(--ink-primary); font-weight: 600; }
        .wiki-content em { color: var(--ink-secondary); font-style: italic; }
        .wiki-content hr { border: none; border-top: 1px solid var(--border-default); margin: 24px 0; }
        .wiki-content blockquote { border-left: 3px solid var(--red-500); padding-left: 14px; margin: 14px 0; color: var(--ink-tertiary); font-size: 14px; }
        .wiki-content .wl { color: var(--ink-secondary); font-weight: 500; text-decoration: underline; text-decoration-style: dotted; }
        .wiki-content mark { background: color-mix(in srgb, gold 25%, transparent); color: var(--ink-primary); border-radius: 2px; padding: 0 2px; }

        @media (max-width: 768px) {
          .sidebar-toggle { display: block !important; }
          .wiki-sidebar { position: fixed !important; top: 52px; left: 0; bottom: 0; z-index: 50; transform: translateX(-100%); transition: transform 0.2s ease; }
          .wiki-sidebar.open { transform: translateX(0); }
        }
      `}</style>
    </div>
  );
}
