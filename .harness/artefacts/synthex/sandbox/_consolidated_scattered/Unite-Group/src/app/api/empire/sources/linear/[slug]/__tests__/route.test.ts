// Pillar 3 (UNI-1947) — Linear adapter tests.

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

function makeParams(slug: string) {
  return { params: Promise.resolve({ slug }) };
}

// Helper: build a fetch mock that returns a Linear GraphQL team payload with
// the given issue-state counts.
function mockLinearFetch({
  inProgress,
  backlog,
  done,
}: {
  inProgress: number;
  backlog: number;
  done: number;
}) {
  global.fetch = jest.fn(
    async () =>
      new Response(
        JSON.stringify({
          data: {
            team: {
              id: 'team-uuid',
              key: 'RA',
              name: 'RestoreAssist',
              organization: { urlKey: 'unite-group' },
              activeIssues: { nodes: Array.from({ length: inProgress }, (_, i) => ({ id: `a${i}` })) },
              backlogIssues: { nodes: Array.from({ length: backlog }, (_, i) => ({ id: `b${i}` })) },
              doneIssues: { nodes: Array.from({ length: done }, (_, i) => ({ id: `d${i}` })) },
            },
          },
        }),
        { status: 200 }
      )
  ) as unknown as typeof fetch;
}

beforeEach(() => {
  supabaseSingle.mockReset();
  process.env.LINEAR_API_KEY = 'lin_test_xxx';
});

afterEach(() => {
  global.fetch = realFetch;
});

describe('GET /api/empire/sources/linear/[slug]', () => {
  it('returns unknown when linear_team_id is NULL', async () => {
    supabaseSingle.mockResolvedValue({ data: { linear_team_id: null }, error: null });
    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.source).toBe('linear');
    expect(body.status).toBe('unknown');
    expect(body.summary).toBe('Linear not configured');
    expect(body.last_update).toBeNull();
  });

  it('returns err when LINEAR_API_KEY is missing', async () => {
    delete process.env.LINEAR_API_KEY;
    supabaseSingle.mockResolvedValue({
      data: { linear_team_id: 'team-uuid' },
      error: null,
    });
    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toMatch(/LINEAR_API_KEY missing/);
  });

  it('returns ok with human-readable summary on success', async () => {
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
                id: 'team-uuid',
                key: 'SYN',
                name: 'Synthex',
                organization: { urlKey: 'unite-group' },
                activeIssues: { nodes: [{ id: '1' }, { id: '2' }, { id: '3' }, { id: '4' }, { id: '5' }] },
                backlogIssues: { nodes: Array.from({ length: 12 }, (_, i) => ({ id: `b${i}` })) },
                doneIssues: { nodes: [{ id: 'd1' }, { id: 'd2' }, { id: 'd3' }] },
              },
            },
          }),
          { status: 200 }
        )
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('ok');
    expect(body.summary).toBe('5 in progress · 12 backlog · 3 done this week');
    expect(body.url).toBe('https://linear.app/unite-group/team/SYN/active');
    expect(body.details).toMatchObject({
      in_progress: 5,
      backlog: 12,
      done_last_7d: 3,
    });
  });

  // ── Threshold matrix (re-calibrated May 2026 for high-velocity teams) ──
  //   err  if in_progress > 75 OR backlog > 500 OR (done_7d == 0 && in_progress > 0)
  //   warn if in_progress > 40 OR backlog > 300
  //   ok   otherwise

  it('returns ok for healthy high-throughput state (36 in progress, 143 done 7d — RestoreAssist today)', async () => {
    // The exact false-positive the threshold tune fixes. 36 in-progress is the
    // RestoreAssist live state; 143 done in 7 days proves the team is shipping.
    supabaseSingle.mockResolvedValue({ data: { linear_team_id: 'team-uuid' }, error: null });
    mockLinearFetch({ inProgress: 36, backlog: 250, done: 143 });

    const res = await GET(new Request('http://x'), makeParams('restoreassist'));
    const body = await res.json();
    expect(body.status).toBe('ok');
    expect(body.summary).toBe('36 in progress · 250 backlog · 143 done this week');
  });

  it('returns err when team is stuck (in_progress > 0 AND done_7d == 0)', async () => {
    supabaseSingle.mockResolvedValue({ data: { linear_team_id: 'team-uuid' }, error: null });
    mockLinearFetch({ inProgress: 12, backlog: 80, done: 0 });

    const res = await GET(new Request('http://x'), makeParams('any-brand'));
    const body = await res.json();
    expect(body.status).toBe('err');
  });

  it('returns err when backlog > 500', async () => {
    supabaseSingle.mockResolvedValue({ data: { linear_team_id: 'team-uuid' }, error: null });
    mockLinearFetch({ inProgress: 5, backlog: 510, done: 8 });

    const res = await GET(new Request('http://x'), makeParams('any-brand'));
    const body = await res.json();
    expect(body.status).toBe('err');
  });

  it('returns err when in_progress > 75', async () => {
    supabaseSingle.mockResolvedValue({ data: { linear_team_id: 'team-uuid' }, error: null });
    mockLinearFetch({ inProgress: 76, backlog: 100, done: 50 });

    const res = await GET(new Request('http://x'), makeParams('any-brand'));
    const body = await res.json();
    expect(body.status).toBe('err');
  });

  it('returns warn when in_progress > 40 (and not in err range)', async () => {
    supabaseSingle.mockResolvedValue({ data: { linear_team_id: 'team-uuid' }, error: null });
    mockLinearFetch({ inProgress: 45, backlog: 100, done: 20 });

    const res = await GET(new Request('http://x'), makeParams('any-brand'));
    const body = await res.json();
    expect(body.status).toBe('warn');
  });

  it('returns warn when backlog > 300 (and not in err range)', async () => {
    supabaseSingle.mockResolvedValue({ data: { linear_team_id: 'team-uuid' }, error: null });
    mockLinearFetch({ inProgress: 5, backlog: 350, done: 10 });

    const res = await GET(new Request('http://x'), makeParams('any-brand'));
    const body = await res.json();
    expect(body.status).toBe('warn');
  });

  it('returns ok at modest WIP (15 in progress, 12 done) — old thresholds would have warned', async () => {
    supabaseSingle.mockResolvedValue({ data: { linear_team_id: 'team-uuid' }, error: null });
    mockLinearFetch({ inProgress: 15, backlog: 50, done: 12 });

    const res = await GET(new Request('http://x'), makeParams('any-brand'));
    const body = await res.json();
    expect(body.status).toBe('ok');
  });

  it('returns ok at zero activity (in_progress == 0 && done_7d == 0)', async () => {
    // Brand-new team with nothing in flight is not "stuck" — there's nothing
    // to be stuck on. Only an active+zero-output team gets the err treatment.
    supabaseSingle.mockResolvedValue({ data: { linear_team_id: 'team-uuid' }, error: null });
    mockLinearFetch({ inProgress: 0, backlog: 0, done: 0 });

    const res = await GET(new Request('http://x'), makeParams('any-brand'));
    const body = await res.json();
    expect(body.status).toBe('ok');
  });

  it('returns err on GraphQL-level error', async () => {
    supabaseSingle.mockResolvedValue({
      data: { linear_team_id: 'team-uuid' },
      error: null,
    });
    global.fetch = jest.fn(
      async () =>
        new Response(
          JSON.stringify({ errors: [{ message: 'team not found' }] }),
          { status: 200 }
        )
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toBe('Linear GraphQL error');
    expect(body.error).toContain('team not found');
  });

  it('returns err with helpful summary on network error', async () => {
    supabaseSingle.mockResolvedValue({
      data: { linear_team_id: 'team-uuid' },
      error: null,
    });
    global.fetch = jest.fn(async () => {
      throw new Error('ETIMEDOUT');
    }) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toBe('Linear unreachable');
    expect(body.error).toContain('ETIMEDOUT');
  });

  it('returns err on HTTP 4xx/5xx', async () => {
    supabaseSingle.mockResolvedValue({
      data: { linear_team_id: 'team-uuid' },
      error: null,
    });
    global.fetch = jest.fn(
      async () => new Response('forbidden', { status: 403 })
    ) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toContain('403');
  });
});
