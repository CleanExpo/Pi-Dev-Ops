// Pillar 3 (UNI-1947) — Supabase Management adapter tests.

import { GET } from '../route';

// ---- Mocks ----

// requireAdmin calls createClient() → cookies(), which throws outside a
// Next.js request scope. Short-circuit it to "always authorized" so the
// route's real logic is what gets exercised.
jest.mock('@/lib/security/require-admin', () => ({
  requireAdmin: jest
    .fn()
    .mockResolvedValue({ ok: true, actorEmail: 'test@unite-group.com' }),
}));

const supabaseSingle = jest.fn();

jest.mock('@/lib/supabase/admin', () => ({
  getAdminClient: () => ({
    from: () => ({
      select: () => ({
        eq: () => ({
          not: () => ({
            order: () => ({
              limit: () => ({
                maybeSingle: supabaseSingle,
              }),
            }),
          }),
        }),
      }),
    }),
  }),
}));

const realFetch = global.fetch;

function makeParams(slug: string) {
  return { params: Promise.resolve({ slug }) };
}

beforeEach(() => {
  supabaseSingle.mockReset();
  process.env.SUPABASE_ACCESS_TOKEN = 'test-token';
});

afterEach(() => {
  global.fetch = realFetch;
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

// Helper to build a happy-path fetch mock that responds based on URL.
function mockFetchByUrl(handler: (url: string) => Response) {
  global.fetch = jest.fn(async (input: RequestInfo | URL) => handler(String(input))) as unknown as typeof fetch;
}

// ---- Test cases ----

describe('GET /api/empire/sources/supabase/[slug]', () => {
  it('returns unknown when supabase_project_ref is NULL', async () => {
    supabaseSingle.mockResolvedValue({ data: { supabase_project_ref: null }, error: null });
    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.source).toBe('supabase');
    expect(body.status).toBe('unknown');
    expect(body.summary).toBe('Supabase not configured');
    expect(body.last_update).toBeNull();
  });

  it('returns err when SUPABASE_ACCESS_TOKEN is missing', async () => {
    delete process.env.SUPABASE_ACCESS_TOKEN;
    supabaseSingle.mockResolvedValue({
      data: { supabase_project_ref: 'abc' },
      error: null,
    });
    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toMatch(/SUPABASE_ACCESS_TOKEN missing/);
  });

  it('returns ok when ACTIVE_HEALTHY + 0 advisors', async () => {
    supabaseSingle.mockResolvedValue({
      data: { supabase_project_ref: 'abc' },
      error: null,
    });
    mockFetchByUrl((url) => {
      if (url.endsWith('/v1/projects/abc')) {
        return jsonResponse({
          id: 'abc',
          name: 'Synthex',
          region: 'ap-southeast-1',
          status: 'ACTIVE_HEALTHY',
          created_at: '2025-08-04T00:32:37Z',
        });
      }
      if (url.includes('/advisors/security')) return jsonResponse({ lints: [] });
      if (url.includes('/advisors/performance')) return jsonResponse({ lints: [] });
      throw new Error('Unexpected URL ' + url);
    });

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('ok');
    expect(body.summary).toContain('ap-southeast-1');
    expect(body.summary).toContain('ACTIVE_HEALTHY');
    expect(body.summary).toContain('0 advisors');
    expect(body.url).toBe('https://supabase.com/dashboard/project/abc');
  });

  it('returns warn when ACTIVE_HEALTHY but <=5 actionable advisors', async () => {
    supabaseSingle.mockResolvedValue({
      data: { supabase_project_ref: 'abc' },
      error: null,
    });
    mockFetchByUrl((url) => {
      if (url.endsWith('/v1/projects/abc')) {
        return jsonResponse({
          id: 'abc',
          name: 'Synthex',
          region: 'ap-southeast-1',
          status: 'ACTIVE_HEALTHY',
        });
      }
      if (url.includes('/advisors/security')) {
        return jsonResponse({
          lints: [
            { level: 'ERROR', name: 'x' },
            { level: 'WARN', name: 'y' },
            { level: 'INFO', name: 'z' }, // INFO not counted
          ],
        });
      }
      if (url.includes('/advisors/performance')) {
        return jsonResponse({ lints: [{ level: 'WARN', name: 'p' }] });
      }
      throw new Error('Unexpected URL ' + url);
    });

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('warn');
    expect(body.summary).toContain('3 advisors');
  });

  it('returns err when ACTIVE_HEALTHY but > 5 actionable advisors', async () => {
    supabaseSingle.mockResolvedValue({
      data: { supabase_project_ref: 'abc' },
      error: null,
    });
    mockFetchByUrl((url) => {
      if (url.endsWith('/v1/projects/abc')) {
        return jsonResponse({
          id: 'abc',
          name: 'Synthex',
          region: 'ap-southeast-1',
          status: 'ACTIVE_HEALTHY',
        });
      }
      if (url.includes('/advisors/security')) {
        const lints = Array.from({ length: 4 }, () => ({ level: 'ERROR' }));
        return jsonResponse({ lints });
      }
      if (url.includes('/advisors/performance')) {
        const lints = Array.from({ length: 3 }, () => ({ level: 'WARN' }));
        return jsonResponse({ lints });
      }
      throw new Error('Unexpected URL ' + url);
    });

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toContain('7 advisors');
  });

  it('returns warn for COMING_UP status', async () => {
    supabaseSingle.mockResolvedValue({
      data: { supabase_project_ref: 'abc' },
      error: null,
    });
    mockFetchByUrl((url) => {
      if (url.endsWith('/v1/projects/abc')) {
        return jsonResponse({
          id: 'abc',
          name: 'Synthex',
          region: 'ap-southeast-1',
          status: 'COMING_UP',
        });
      }
      if (url.includes('/advisors/')) return jsonResponse({ lints: [] });
      throw new Error('Unexpected URL ' + url);
    });

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('warn');
    expect(body.summary).toContain('COMING_UP');
  });

  it('returns err when project is INACTIVE', async () => {
    supabaseSingle.mockResolvedValue({
      data: { supabase_project_ref: 'abc' },
      error: null,
    });
    mockFetchByUrl((url) => {
      if (url.endsWith('/v1/projects/abc')) {
        return jsonResponse({
          id: 'abc',
          name: 'Synthex',
          region: 'ap-southeast-1',
          status: 'INACTIVE',
        });
      }
      if (url.includes('/advisors/')) return jsonResponse({ lints: [] });
      throw new Error('Unexpected URL ' + url);
    });

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
  });

  it('degrades gracefully when advisor endpoints fail but project endpoint succeeds', async () => {
    supabaseSingle.mockResolvedValue({
      data: { supabase_project_ref: 'abc' },
      error: null,
    });
    mockFetchByUrl((url) => {
      if (url.endsWith('/v1/projects/abc')) {
        return jsonResponse({
          id: 'abc',
          name: 'Synthex',
          region: 'ap-southeast-1',
          status: 'ACTIVE_HEALTHY',
        });
      }
      // Both advisor endpoints fail
      return new Response('Not Found', { status: 404 });
    });

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('ok'); // ACTIVE_HEALTHY + advisor null treated as 0
    expect(body.summary).toContain('advisors unknown');
  });

  it('returns err when project endpoint returns 404', async () => {
    supabaseSingle.mockResolvedValue({
      data: { supabase_project_ref: 'missing' },
      error: null,
    });
    global.fetch = jest.fn(async () => new Response('Not Found', { status: 404 })) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toContain('404');
  });

  it('returns err on network failure', async () => {
    supabaseSingle.mockResolvedValue({
      data: { supabase_project_ref: 'abc' },
      error: null,
    });
    global.fetch = jest.fn(async () => {
      throw new Error('ECONNREFUSED');
    }) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toBe('Supabase unreachable');
    expect(body.error).toContain('ECONNREFUSED');
  });
});
