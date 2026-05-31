// Tests for the rewritten /api/empire/tickets/[slug] route — verifies the
// DB-driven team_id lookup replacing the broken hardcoded TEAM_MAP.

import { GET } from '../route';

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

function makeReq() {
  return new Request('http://x') as unknown as Parameters<typeof GET>[0];
}
function makeParams(slug: string) {
  return { params: Promise.resolve({ slug }) };
}

beforeEach(() => {
  supabaseSingle.mockReset();
  process.env.LINEAR_API_KEY = 'lin_test_xxx';
});

afterEach(() => {
  global.fetch = realFetch;
});

describe('GET /api/empire/tickets/[slug]', () => {
  it('returns empty tickets with explicit error when team_id is NULL', async () => {
    supabaseSingle.mockResolvedValue({ data: { linear_team_id: null }, error: null });
    const res = await GET(makeReq(), makeParams('synthex-unconfigured'));
    const body = await res.json();
    expect(body.tickets).toEqual([]);
    expect(body.error).toBe('Linear team not configured');
  });

  it('returns empty tickets when LINEAR_API_KEY is missing', async () => {
    delete process.env.LINEAR_API_KEY;
    supabaseSingle.mockResolvedValue({
      data: { linear_team_id: 'team-uuid' },
      error: null,
    });
    const res = await GET(makeReq(), makeParams('synthex-nokey'));
    const body = await res.json();
    expect(body.tickets).toEqual([]);
    expect(body.error).toBe('Linear not configured');
  });

  it('maps Linear issues to ticket objects on success', async () => {
    supabaseSingle.mockResolvedValue({
      data: { linear_team_id: 'team-uuid' },
      error: null,
    });

    global.fetch = jest.fn(
      async () =>
        new Response(
          JSON.stringify({
            data: {
              team: {
                issues: {
                  nodes: [
                    {
                      id: 'i1',
                      identifier: 'SYN-100',
                      title: 'Fix the thing that breaks the other thing',
                      state: { name: 'In Progress', type: 'started' },
                      priority: 2,
                      url: 'https://linear.app/unite-group/issue/SYN-100',
                      updatedAt: '2026-05-13T00:00:00Z',
                    },
                  ],
                },
              },
            },
          }),
          { status: 200 }
        )
    ) as unknown as typeof fetch;

    const res = await GET(makeReq(), makeParams('synthex-ok-unique'));
    const body = await res.json();
    expect(body.tickets).toHaveLength(1);
    expect(body.tickets[0]).toMatchObject({
      id: 'SYN-100',
      stateType: 'started',
      url: 'https://linear.app/unite-group/issue/SYN-100',
    });
  });

  it('returns empty list with error on Linear API non-2xx', async () => {
    supabaseSingle.mockResolvedValue({
      data: { linear_team_id: 'team-uuid' },
      error: null,
    });
    global.fetch = jest.fn(
      async () => new Response('upstream boom', { status: 502 })
    ) as unknown as typeof fetch;

    const res = await GET(makeReq(), makeParams('synthex-502-unique'));
    const body = await res.json();
    expect(body.tickets).toEqual([]);
    expect(body.error).toMatch(/Linear API 502/);
  });
});
