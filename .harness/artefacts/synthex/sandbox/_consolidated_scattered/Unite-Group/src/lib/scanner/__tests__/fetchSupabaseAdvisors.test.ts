// UNI-1948 — Tests for the shared Supabase advisors helper.

import { fetchSupabaseAdvisors } from '../fetchSupabaseAdvisors';

const realFetch = global.fetch;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  process.env.SUPABASE_ACCESS_TOKEN = 'test-token';
});

afterEach(() => {
  global.fetch = realFetch;
});

describe('fetchSupabaseAdvisors', () => {
  it('returns counts on the happy path', async () => {
    global.fetch = jest.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/v1/projects/abc')) {
        return jsonResponse({
          id: 'abc',
          name: 'Synthex',
          region: 'ap-southeast-1',
          status: 'ACTIVE_HEALTHY',
          created_at: '2025-08-04T00:32:37Z',
        });
      }
      if (url.includes('/advisors/security')) {
        return jsonResponse({
          lints: [{ level: 'ERROR' }, { level: 'WARN' }, { level: 'INFO' }],
        });
      }
      if (url.includes('/advisors/performance')) {
        return jsonResponse({ lints: [{ level: 'WARN' }] });
      }
      throw new Error('Unexpected URL ' + url);
    }) as unknown as typeof fetch;

    const advisors = await fetchSupabaseAdvisors('abc');
    expect(advisors.security_count).toBe(2); // INFO not counted
    expect(advisors.performance_count).toBe(1);
    expect(advisors.project_status).toBe('ACTIVE_HEALTHY');
    expect(advisors.region).toBe('ap-southeast-1');
    expect(advisors.created_at).toBe('2025-08-04T00:32:37Z');
  });

  it('throws when token is missing', async () => {
    delete process.env.SUPABASE_ACCESS_TOKEN;
    await expect(fetchSupabaseAdvisors('abc')).rejects.toThrow(/SUPABASE_ACCESS_TOKEN missing/);
  });

  it('degrades advisor counts to null when both endpoints 404', async () => {
    global.fetch = jest.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/v1/projects/abc')) {
        return jsonResponse({
          id: 'abc',
          name: 'Synthex',
          region: 'ap-southeast-1',
          status: 'ACTIVE_HEALTHY',
        });
      }
      return new Response('not found', { status: 404 });
    }) as unknown as typeof fetch;

    const advisors = await fetchSupabaseAdvisors('abc');
    expect(advisors.security_count).toBeNull();
    expect(advisors.performance_count).toBeNull();
    expect(advisors.project_status).toBe('ACTIVE_HEALTHY');
  });
});
