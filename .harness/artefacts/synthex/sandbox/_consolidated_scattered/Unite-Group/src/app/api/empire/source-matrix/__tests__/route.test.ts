// UNI-1947 Pillar 3 — Brand × Source matrix aggregator tests.

import { GET } from '../route';
import { resetCache } from '../_helpers';

// ---- Auth mock ----
// requireAdmin calls createClient() → cookies(), which throws outside a
// Next.js request scope. Short-circuit it to "always authorized" so the
// route's real logic is what gets exercised.
jest.mock('@/lib/security/require-admin', () => ({
  requireAdmin: jest
    .fn()
    .mockResolvedValue({ ok: true, actorEmail: 'test@unite-group.com' }),
}));

// ---- Supabase mock ----

const supabaseOrder = jest.fn();

jest.mock('@/lib/supabase/admin', () => ({
  getAdminClient: () => ({
    from: () => ({
      select: () => ({
        in: () => ({
          not: () => ({
            order: supabaseOrder,
          }),
        }),
      }),
    }),
  }),
}));

const realFetch = global.fetch;

function brandRows(slugs: string[]) {
  return slugs.map((slug, i) => ({
    slug,
    name: slug.toUpperCase(),
    created_at: `2026-05-${10 - i}T00:00:00Z`,
    is_sandbox: false,
  }));
}

function adapterCell(source: string, status: 'ok' | 'warn' | 'err' | 'unknown', extra: Record<string, unknown> = {}) {
  return {
    source,
    status,
    summary: `${source} ${status}`,
    last_update: '2026-05-13T00:00:00Z',
    ...extra,
  };
}

let fetchSpy: jest.Mock;

beforeEach(() => {
  resetCache();
  supabaseOrder.mockReset();
  fetchSpy = jest.fn(async (url: string) => {
    // Parse the kind from the URL — /api/empire/sources/<kind>/<slug>
    const m = String(url).match(/\/api\/empire\/sources\/(\w+)\//);
    const kind = m?.[1] ?? 'unknown';
    return new Response(JSON.stringify(adapterCell(kind, 'ok')), { status: 200 });
  });
  global.fetch = fetchSpy as unknown as typeof fetch;
});

afterEach(() => {
  global.fetch = realFetch;
});

// ---- Tests ----

describe('GET /api/empire/source-matrix', () => {
  it('returns 6 brands × 5 sources = 30 cells in the happy path', async () => {
    supabaseOrder.mockResolvedValue({
      data: brandRows(['synthex', 'restoreassist', 'disaster-recovery', 'dr-nrpg', 'carsi', 'ccw-crm']),
      error: null,
    });

    const res = await GET(new Request('http://localhost/api/empire/source-matrix'));
    const body = await res.json();

    expect(body.brands).toHaveLength(6);
    const totalCells = body.brands.reduce(
      (n: number, b: { cells: Record<string, unknown> }) => n + Object.keys(b.cells).length,
      0,
    );
    expect(totalCells).toBe(30);
    // 30 adapter fetches = 6 brands × 5 sources.
    expect(fetchSpy).toHaveBeenCalledTimes(30);
    // computed_at is an ISO timestamp.
    expect(body.computed_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it('returns an empty brand list when the businesses query fails', async () => {
    supabaseOrder.mockResolvedValue({ data: null, error: { message: 'boom' } });

    const res = await GET(new Request('http://localhost/api/empire/source-matrix'));
    const body = await res.json();

    expect(body.brands).toEqual([]);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('surfaces partial adapter failure as err cells, not a thrown error', async () => {
    supabaseOrder.mockResolvedValue({
      data: brandRows(['synthex']),
      error: null,
    });
    // GitHub crashes, the other four return ok.
    fetchSpy.mockImplementation(async (url: string) => {
      if (String(url).includes('/sources/github/')) {
        throw new Error('ECONNREFUSED');
      }
      const m = String(url).match(/\/api\/empire\/sources\/(\w+)\//);
      return new Response(JSON.stringify(adapterCell(m?.[1] ?? 'x', 'ok')), { status: 200 });
    });

    const res = await GET(new Request('http://localhost/api/empire/source-matrix'));
    const body = await res.json();

    expect(body.brands).toHaveLength(1);
    const cells = body.brands[0].cells;
    expect(cells.github.status).toBe('err');
    expect(cells.github.error).toContain('ECONNREFUSED');
    expect(cells.linear.status).toBe('ok');
    expect(cells.vercel.status).toBe('ok');
    expect(cells.railway.status).toBe('ok');
    expect(cells.supabase.status).toBe('ok');
  });

  it('?force=1 bypasses the in-memory cache', async () => {
    supabaseOrder.mockResolvedValue({
      data: brandRows(['synthex']),
      error: null,
    });

    // First call populates the cache (5 adapter fetches for 1 brand).
    await GET(new Request('http://localhost/api/empire/source-matrix'));
    expect(fetchSpy).toHaveBeenCalledTimes(5);

    // Second call without force — served from cache.
    const cached = await GET(new Request('http://localhost/api/empire/source-matrix'));
    expect(cached.headers.get('X-Source-Matrix-Cache')).toBe('hit');
    expect(fetchSpy).toHaveBeenCalledTimes(5);

    // Third call with force=1 — re-fetches every cell.
    const forced = await GET(new Request('http://localhost/api/empire/source-matrix?force=1'));
    expect(forced.headers.get('X-Source-Matrix-Cache')).toBe('force');
    expect(fetchSpy).toHaveBeenCalledTimes(10);
  });

  it('only returns non-sandbox brands (sandbox rows are pre-filtered by the query)', async () => {
    // Mock returns only the 4 non-sandbox rows the .not('is_sandbox', 'is', true) clause would pass.
    supabaseOrder.mockResolvedValue({
      data: brandRows(['synthex', 'restoreassist', 'carsi', 'ccw-crm']),
      error: null,
    });

    const res = await GET(new Request('http://localhost/api/empire/source-matrix'));
    const body = await res.json();

    expect(body.brands).toHaveLength(4);
    expect(body.brands.map((b: { slug: string }) => b.slug)).toEqual([
      'synthex', 'restoreassist', 'carsi', 'ccw-crm',
    ]);
    // 4 brands × 5 sources = 20 adapter calls.
    expect(fetchSpy).toHaveBeenCalledTimes(20);
  });
});
