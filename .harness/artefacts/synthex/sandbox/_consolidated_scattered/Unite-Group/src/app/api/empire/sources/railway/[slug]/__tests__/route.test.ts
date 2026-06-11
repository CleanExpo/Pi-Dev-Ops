// Pillar 3 (UNI-1947) — Railway adapter tests.

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
  process.env.RAILWAY_API_TOKEN = 'test-token';
});

afterEach(() => {
  global.fetch = realFetch;
});

// ---- Test cases ----

describe('GET /api/empire/sources/railway/[slug]', () => {
  it('returns unknown when railway_service_id is NULL', async () => {
    supabaseSingle.mockResolvedValue({ data: { railway_service_id: null }, error: null });
    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.source).toBe('railway');
    expect(body.status).toBe('unknown');
    expect(body.summary).toBe('Railway not configured');
    expect(body.last_update).toBeNull();
  });

  it('returns err when RAILWAY_API_TOKEN is missing', async () => {
    delete process.env.RAILWAY_API_TOKEN;
    supabaseSingle.mockResolvedValue({
      data: { railway_service_id: 'svc-1' },
      error: null,
    });
    const res = await GET(new Request('http://x'), makeParams('ccw-crm'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toMatch(/RAILWAY_API_TOKEN missing/);
  });

  it('returns ok on SUCCESS deployment', async () => {
    supabaseSingle.mockResolvedValue({
      data: { railway_service_id: 'svc-1' },
      error: null,
    });

    global.fetch = jest.fn(async () =>
      new Response(
        JSON.stringify({
          data: {
            service: {
              id: 'svc-1',
              name: 'ccw-backend',
              project: { id: 'proj-1', name: 'determined-playfulness' },
              deployments: {
                edges: [
                  {
                    node: {
                      id: 'dep-1',
                      status: 'SUCCESS',
                      createdAt: new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
                      staticUrl: 'ccw-backend-production.up.railway.app',
                      url: null,
                    },
                  },
                ],
              },
            },
          },
        }),
        { status: 200 }
      )
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('ccw-crm'));
    const body = await res.json();
    expect(body.status).toBe('ok');
    expect(body.summary).toContain('ccw-backend');
    expect(body.summary).toContain('SUCCESS');
    expect(body.url).toBe('https://railway.com/project/proj-1/service/svc-1');
  });

  it('returns err on FAILED deployment', async () => {
    supabaseSingle.mockResolvedValue({
      data: { railway_service_id: 'svc-1' },
      error: null,
    });

    global.fetch = jest.fn(async () =>
      new Response(
        JSON.stringify({
          data: {
            service: {
              id: 'svc-1',
              name: 'ccw-backend',
              project: { id: 'proj-1', name: 'determined-playfulness' },
              deployments: {
                edges: [
                  {
                    node: {
                      id: 'dep-2',
                      status: 'FAILED',
                      createdAt: new Date().toISOString(),
                      staticUrl: null,
                      url: null,
                    },
                  },
                ],
              },
            },
          },
        }),
        { status: 200 }
      )
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('ccw-crm'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toContain('FAILED');
  });

  it('returns warn on BUILDING / DEPLOYING', async () => {
    supabaseSingle.mockResolvedValue({
      data: { railway_service_id: 'svc-1' },
      error: null,
    });

    global.fetch = jest.fn(async () =>
      new Response(
        JSON.stringify({
          data: {
            service: {
              id: 'svc-1',
              name: 'ccw-backend',
              project: { id: 'proj-1', name: 'determined-playfulness' },
              deployments: {
                edges: [
                  {
                    node: {
                      id: 'dep-3',
                      status: 'BUILDING',
                      createdAt: new Date().toISOString(),
                      staticUrl: null,
                      url: null,
                    },
                  },
                ],
              },
            },
          },
        }),
        { status: 200 }
      )
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('ccw-crm'));
    const body = await res.json();
    expect(body.status).toBe('warn');
    expect(body.summary).toContain('BUILDING');
  });

  it('returns err when GraphQL returns errors array', async () => {
    supabaseSingle.mockResolvedValue({
      data: { railway_service_id: 'svc-bad' },
      error: null,
    });

    global.fetch = jest.fn(async () =>
      new Response(
        JSON.stringify({
          errors: [{ message: 'Not authorized to access service' }],
        }),
        { status: 200 }
      )
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('ccw-crm'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toBe('Railway GraphQL error');
    expect(body.error).toContain('Not authorized');
  });

  it('returns unknown when service has no deployments', async () => {
    supabaseSingle.mockResolvedValue({
      data: { railway_service_id: 'svc-1' },
      error: null,
    });
    global.fetch = jest.fn(async () =>
      new Response(
        JSON.stringify({
          data: {
            service: {
              id: 'svc-1',
              name: 'ccw-backend',
              project: { id: 'proj-1', name: 'determined-playfulness' },
              deployments: { edges: [] },
            },
          },
        }),
        { status: 200 }
      )
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('ccw-crm'));
    const body = await res.json();
    expect(body.status).toBe('unknown');
    expect(body.summary).toContain('no deployments');
  });

  it('returns err on network failure', async () => {
    supabaseSingle.mockResolvedValue({
      data: { railway_service_id: 'svc-1' },
      error: null,
    });
    global.fetch = jest.fn(async () => {
      throw new Error('ECONNREFUSED');
    }) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('ccw-crm'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toBe('Railway unreachable');
    expect(body.error).toContain('ECONNREFUSED');
  });

  it('returns err on 5xx from Railway', async () => {
    supabaseSingle.mockResolvedValue({
      data: { railway_service_id: 'svc-1' },
      error: null,
    });
    global.fetch = jest.fn(async () =>
      new Response('Internal Server Error', { status: 500 })
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('ccw-crm'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toContain('500');
  });
});
