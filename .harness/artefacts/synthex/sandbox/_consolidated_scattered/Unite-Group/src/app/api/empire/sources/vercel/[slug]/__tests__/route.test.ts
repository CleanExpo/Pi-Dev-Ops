// Pillar 3 (UNI-1947) — Vercel adapter tests.

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
  process.env.VERCEL_TOKEN = 'test-token';
});

afterEach(() => {
  global.fetch = realFetch;
});

// ---- Test cases ----

describe('GET /api/empire/sources/vercel/[slug]', () => {
  it('returns unknown when vercel_project is NULL', async () => {
    supabaseSingle.mockResolvedValue({ data: { vercel_project: null }, error: null });
    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.source).toBe('vercel');
    expect(body.status).toBe('unknown');
    expect(body.summary).toBe('Vercel not configured');
    expect(body.last_update).toBeNull();
  });

  it('returns err when VERCEL_TOKEN is missing', async () => {
    delete process.env.VERCEL_TOKEN;
    supabaseSingle.mockResolvedValue({
      data: { vercel_project: 'prj_abc' },
      error: null,
    });
    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toMatch(/VERCEL_TOKEN missing/);
  });

  it('returns ok with human-readable summary on READY deployment', async () => {
    supabaseSingle.mockResolvedValue({
      data: { vercel_project: 'prj_abc' },
      error: null,
    });

    const recentMs = Date.now() - 12 * 60 * 1000; // 12 min ago
    global.fetch = jest.fn(async () =>
      new Response(
        JSON.stringify({
          deployments: [
            {
              uid: 'dpl_1',
              name: 'synthex',
              url: 'synthex-abc.vercel.app',
              state: 'READY',
              createdAt: recentMs,
              meta: { githubCommitRef: 'main', githubCommitMessage: 'fix: copy' },
            },
          ],
        }),
        { status: 200 }
      )
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('ok');
    expect(body.summary).toContain('main');
    expect(body.summary).toContain('READY');
    expect(body.url).toBe('https://synthex-abc.vercel.app');
  });

  it('returns err when latest deployment state is ERROR', async () => {
    supabaseSingle.mockResolvedValue({
      data: { vercel_project: 'prj_abc' },
      error: null,
    });

    global.fetch = jest.fn(async () =>
      new Response(
        JSON.stringify({
          deployments: [
            {
              uid: 'dpl_1',
              name: 'synthex',
              url: 'synthex-bad.vercel.app',
              state: 'ERROR',
              createdAt: Date.now() - 5 * 60 * 1000,
              meta: { githubCommitRef: 'main' },
            },
          ],
        }),
        { status: 200 }
      )
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toContain('ERROR');
  });

  it('returns warn for BUILDING under 30min', async () => {
    supabaseSingle.mockResolvedValue({
      data: { vercel_project: 'prj_abc' },
      error: null,
    });

    global.fetch = jest.fn(async () =>
      new Response(
        JSON.stringify({
          deployments: [
            {
              uid: 'dpl_1',
              name: 'synthex',
              url: 'synthex-wip.vercel.app',
              state: 'BUILDING',
              createdAt: Date.now() - 2 * 60 * 1000,
              buildingAt: Date.now() - 2 * 60 * 1000,
              meta: { githubCommitRef: 'main' },
            },
          ],
        }),
        { status: 200 }
      )
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('warn');
    expect(body.summary).toContain('BUILDING');
  });

  it('returns err for BUILDING over 30min (stale)', async () => {
    supabaseSingle.mockResolvedValue({
      data: { vercel_project: 'prj_abc' },
      error: null,
    });

    global.fetch = jest.fn(async () =>
      new Response(
        JSON.stringify({
          deployments: [
            {
              uid: 'dpl_1',
              name: 'synthex',
              url: 'synthex-wip.vercel.app',
              state: 'BUILDING',
              createdAt: Date.now() - 45 * 60 * 1000,
              buildingAt: Date.now() - 45 * 60 * 1000,
              meta: { githubCommitRef: 'main' },
            },
          ],
        }),
        { status: 200 }
      )
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
  });

  it('returns unknown when no deployments exist', async () => {
    supabaseSingle.mockResolvedValue({
      data: { vercel_project: 'prj_abc' },
      error: null,
    });
    global.fetch = jest.fn(async () =>
      new Response(JSON.stringify({ deployments: [] }), { status: 200 })
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('unknown');
    expect(body.summary).toContain('no production deployments');
  });

  it('returns err on network failure', async () => {
    supabaseSingle.mockResolvedValue({
      data: { vercel_project: 'prj_abc' },
      error: null,
    });
    global.fetch = jest.fn(async () => {
      throw new Error('ECONNREFUSED');
    }) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toBe('Vercel unreachable');
    expect(body.error).toContain('ECONNREFUSED');
  });

  it('returns err when Vercel API returns 4xx', async () => {
    supabaseSingle.mockResolvedValue({
      data: { vercel_project: 'prj_abc' },
      error: null,
    });
    global.fetch = jest.fn(async () =>
      new Response('Forbidden', { status: 403 })
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toContain('403');
  });
});
