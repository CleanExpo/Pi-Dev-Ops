// UNI-1948 — Tests for the shared GitHub metrics helper.

import { fetchGithubMetrics } from '../fetchGithubMetrics';

const realFetch = global.fetch;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  process.env.GITHUB_TOKEN = 'test-token';
});

afterEach(() => {
  global.fetch = realFetch;
  jest.restoreAllMocks();
});

describe('fetchGithubMetrics', () => {
  it('returns metrics on the happy path', async () => {
    global.fetch = jest.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/repos/CleanExpo/Synthex')) {
        return jsonResponse({
          default_branch: 'main',
          html_url: 'https://github.com/CleanExpo/Synthex',
          archived: false,
          pushed_at: '2026-05-12T10:00:00Z',
        });
      }
      if (url.includes('/commits/main')) {
        return jsonResponse({
          sha: 'abc',
          commit: {
            message: 'fix: portal copy\n\nlonger body',
            author: { name: 'phill', date: '2026-05-12T10:00:00Z' },
          },
        });
      }
      if (url.includes('/actions/runs')) {
        return jsonResponse({
          workflow_runs: [
            { status: 'completed', conclusion: 'success', updated_at: '2026-05-12T11:00:00Z' },
          ],
        });
      }
      if (url.includes('/dependabot/alerts')) {
        return jsonResponse([{ state: 'open' }, { state: 'open' }, { state: 'open' }]);
      }
      if (url.includes('/pulls')) {
        return jsonResponse([{ state: 'open' }, { state: 'open' }]);
      }
      throw new Error('Unexpected URL ' + url);
    }) as unknown as typeof fetch;

    const metrics = await fetchGithubMetrics('CleanExpo/Synthex');
    expect(metrics.repo).toBe('CleanExpo/Synthex');
    expect(metrics.default_branch).toBe('main');
    expect(metrics.archived).toBe(false);
    expect(metrics.dep_alerts_open).toBe(3);
    expect(metrics.ci_state).toBe('success');
    expect(metrics.open_prs).toBe(2);
    expect(metrics.latest_commit_at).toBe('2026-05-12T10:00:00Z');
    expect(metrics.latest_commit_message).toBe('fix: portal copy');
  });

  it('throws when repo is malformed', async () => {
    await expect(fetchGithubMetrics('')).rejects.toThrow(/invalid repo/);
    await expect(fetchGithubMetrics('no-slash')).rejects.toThrow(/invalid repo/);
  });

  it('returns dep_alerts_open=null when dependabot returns 403', async () => {
    global.fetch = jest.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/repos/owner/repo')) {
        return jsonResponse({
          default_branch: 'main',
          html_url: 'https://github.com/owner/repo',
          archived: false,
          pushed_at: '2026-05-12T10:00:00Z',
        });
      }
      if (url.includes('/commits/main')) {
        return jsonResponse({
          sha: 'x',
          commit: { message: 'c', author: { name: 'a', date: '2026-05-12T10:00:00Z' } },
        });
      }
      if (url.includes('/actions/runs')) {
        return jsonResponse({ workflow_runs: [] });
      }
      if (url.includes('/dependabot/alerts')) {
        return new Response('Forbidden', { status: 403 });
      }
      if (url.includes('/pulls')) {
        return jsonResponse([]);
      }
      throw new Error('Unexpected URL ' + url);
    }) as unknown as typeof fetch;

    const metrics = await fetchGithubMetrics('owner/repo');
    expect(metrics.dep_alerts_open).toBeNull();
    expect(metrics.ci_state).toBe('unknown');
  });

  it('throws on network failure during repo lookup', async () => {
    global.fetch = jest.fn(async () => {
      throw new Error('ECONNREFUSED');
    }) as unknown as typeof fetch;

    await expect(fetchGithubMetrics('owner/repo')).rejects.toThrow(/ECONNREFUSED/);
  });

  it('throws when GITHUB_TOKEN is missing and keychain fails', async () => {
    delete process.env.GITHUB_TOKEN;
    jest.spyOn(require('child_process'), 'execSync').mockImplementation(() => {
      throw new Error('no keychain');
    });
    await expect(fetchGithubMetrics('owner/repo')).rejects.toThrow(/GITHUB_TOKEN missing/);
  });
});
