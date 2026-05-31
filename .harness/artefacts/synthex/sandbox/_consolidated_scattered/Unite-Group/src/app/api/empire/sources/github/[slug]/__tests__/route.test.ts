// Pillar 3 (UNI-1947) — GitHub adapter tests.

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
  process.env.GITHUB_TOKEN = 'test-token';
});

afterEach(() => {
  global.fetch = realFetch;
});

// ---- Test cases ----

describe('GET /api/empire/sources/github/[slug]', () => {
  it('returns unknown when github_repo is NULL', async () => {
    supabaseSingle.mockResolvedValue({ data: { github_repo: null }, error: null });
    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.source).toBe('github');
    expect(body.status).toBe('unknown');
    expect(body.summary).toBe('GitHub not configured');
    expect(body.last_update).toBeNull();
  });

  it('returns err when GITHUB_TOKEN is missing', async () => {
    delete process.env.GITHUB_TOKEN;
    supabaseSingle.mockResolvedValue({
      data: { github_repo: 'CleanExpo/Synthex' },
      error: null,
    });
    // Make Keychain fallback fail by mocking child_process.
    jest.spyOn(require('child_process'), 'execSync').mockImplementation(() => {
      throw new Error('no keychain');
    });
    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toMatch(/GITHUB_TOKEN missing/);
  });

  it('returns ok with human-readable summary on success', async () => {
    supabaseSingle.mockResolvedValue({
      data: { github_repo: 'CleanExpo/Synthex' },
      error: null,
    });

    global.fetch = jest.fn(async (url: string) => {
      const u = String(url);
      if (u.endsWith('/repos/CleanExpo/Synthex')) {
        return new Response(
          JSON.stringify({
            default_branch: 'main',
            html_url: 'https://github.com/CleanExpo/Synthex',
            archived: false,
            pushed_at: '2026-05-12T10:00:00Z',
          }),
          { status: 200 }
        );
      }
      if (u.includes('/commits/main')) {
        return new Response(
          JSON.stringify({
            sha: 'abc123',
            commit: {
              message: 'fix: portal copy',
              author: { name: 'phill', date: '2026-05-12T10:00:00Z' },
            },
          }),
          { status: 200 }
        );
      }
      if (u.includes('/actions/runs')) {
        return new Response(
          JSON.stringify({
            workflow_runs: [{ status: 'completed', conclusion: 'success', updated_at: '2026-05-12T10:00:00Z' }],
          }),
          { status: 200 }
        );
      }
      if (u.includes('/dependabot/alerts')) {
        return new Response(JSON.stringify([{ state: 'open' }, { state: 'open' }]), { status: 200 });
      }
      if (u.includes('/pulls')) {
        return new Response(JSON.stringify([{ state: 'open' }]), { status: 200 });
      }
      throw new Error(`Unexpected URL: ${u}`);
    }) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('ok');
    expect(body.summary).toContain('main');
    expect(body.summary).toContain('CI green');
    expect(body.summary).toContain('2 dep alerts');
    expect(body.summary).toContain('1 open PR');
    expect(body.url).toBe('https://github.com/CleanExpo/Synthex');
    expect(body.last_update).toBe('2026-05-12T10:00:00Z');
  });

  it('returns err when latest workflow failed', async () => {
    supabaseSingle.mockResolvedValue({
      data: { github_repo: 'CleanExpo/RestoreAssist' },
      error: null,
    });

    global.fetch = jest.fn(async (url: string) => {
      const u = String(url);
      if (u.endsWith('/repos/CleanExpo/RestoreAssist')) {
        return new Response(
          JSON.stringify({
            default_branch: 'main',
            html_url: 'https://github.com/CleanExpo/RestoreAssist',
            archived: false,
            pushed_at: '2026-05-12T10:00:00Z',
          }),
          { status: 200 }
        );
      }
      if (u.includes('/commits/')) {
        return new Response(
          JSON.stringify({
            sha: 'x',
            commit: { message: 'wip', author: { name: 'p', date: '2026-05-12T10:00:00Z' } },
          }),
          { status: 200 }
        );
      }
      if (u.includes('/actions/runs')) {
        return new Response(
          JSON.stringify({
            workflow_runs: [{ status: 'completed', conclusion: 'failure', updated_at: '2026-05-12T10:00:00Z' }],
          }),
          { status: 200 }
        );
      }
      if (u.includes('/dependabot/alerts')) {
        return new Response('[]', { status: 200 });
      }
      if (u.includes('/pulls')) {
        return new Response('[]', { status: 200 });
      }
      throw new Error(`Unexpected URL: ${u}`);
    }) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('restoreassist'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toContain('CI failing');
  });

  it('returns err with helpful summary on network error', async () => {
    supabaseSingle.mockResolvedValue({
      data: { github_repo: 'CleanExpo/Synthex' },
      error: null,
    });
    global.fetch = jest.fn(async () => {
      throw new Error('ECONNREFUSED');
    }) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toBe('GitHub unreachable');
    expect(body.error).toContain('ECONNREFUSED');
  });

  it('returns err when repo fetch is 4xx', async () => {
    supabaseSingle.mockResolvedValue({
      data: { github_repo: 'CleanExpo/Missing' },
      error: null,
    });
    global.fetch = jest.fn(async () => new Response('Not Found', { status: 404 })) as unknown as typeof fetch;

    const res = await GET(new Request('http://x'), makeParams('synthex'));
    const body = await res.json();
    expect(body.status).toBe('err');
    expect(body.summary).toContain('404');
  });
});
