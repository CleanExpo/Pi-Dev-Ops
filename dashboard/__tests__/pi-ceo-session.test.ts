/**
 * The login helper is load-bearing for four routes, one of them a safety control, so it is
 * tested as new code rather than inherited as already-reviewed.
 *
 * The property under test is the one CONSOLIDATION CREATED. The original lived in a single
 * route, where a burst produced a few duplicate logins at worst. Four routes — three of them
 * polled by dashboard panels — can stampede. Upstream locks an IP out after 5 failed logins in
 * 15 minutes (`app/server/auth.py::check_login_lockout`) and Vercel egress IPs are SHARED, so
 * a stampede of failing logins can lock out the whole deployment. That turns an auth fault
 * into an outage and sends the next person to rotate a credential that was never wrong.
 *
 * Single-flight cannot be verified by reading — it is a concurrency property. Hence a test.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

type FetchCall = { url: string; init?: RequestInit };

function installFetch(handler: (url: string) => Response): FetchCall[] {
  const calls: FetchCall[] = [];
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    return handler(url);
  });
  return calls;
}

const loginOk = () =>
  new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "set-cookie": "tao_session=abc123; Path=/; HttpOnly" },
  });

beforeEach(() => {
  vi.resetModules();
  vi.unstubAllGlobals();
  process.env.PI_CEO_URL = "https://upstream.test";
  process.env.PI_CEO_PASSWORD = "correct-horse";
});

describe("pi-ceo-session", () => {
  it("positive control: a single call logs in once and sends the session cookie", async () => {
    const calls = installFetch((url) =>
      url.endsWith("/api/login") ? loginOk() : new Response("{}", { status: 200 }),
    );
    const { piCeoFetch } = await import("../lib/pi-ceo-session");

    const res = await piCeoFetch("/api/swarm/status");
    expect(res?.status).toBe(200);

    const logins = calls.filter((c) => c.url.endsWith("/api/login"));
    expect(logins).toHaveLength(1);

    // The whole defect being fixed: upstream needs the SESSION COOKIE, not the password.
    const upstream = calls.find((c) => c.url.includes("/api/swarm/status"))!;
    const headers = upstream.init!.headers as Record<string, string>;
    expect(headers.Cookie).toBe("tao_session=abc123");
    expect(JSON.stringify(headers)).not.toContain("correct-horse");
  });

  it("SINGLE-FLIGHT: concurrent callers trigger exactly one login", async () => {
    let resolveLogin: (r: Response) => void = () => {};
    const gate = new Promise<Response>((r) => { resolveLogin = r; });

    const calls = installFetch((url) =>
      url.endsWith("/api/login") ? (gate as unknown as Response) : new Response("{}", { status: 200 }),
    );
    const { piCeoFetch } = await import("../lib/pi-ceo-session");

    // Four concurrent callers — one per route that now shares this helper — all arriving
    // before any login has completed. Without single-flight this is four logins, and four
    // FAILING logins is most of the way to a 5-strike lockout from one page load.
    const inflight = [
      piCeoFetch("/api/swarm/status"),
      piCeoFetch("/api/zte/score"),
      piCeoFetch("/api/autonomy/status"),
      piCeoFetch("/api/swarm/curator/proposals"),
    ];
    await new Promise((r) => setTimeout(r, 10));
    resolveLogin(loginOk());
    await Promise.all(inflight);

    const logins = calls.filter((c) => c.url.endsWith("/api/login"));
    expect(logins, `expected 1 login for 4 concurrent callers, got ${logins.length}`).toHaveLength(1);
  });

  it("LOCKOUT: a 429 stops further login attempts instead of deepening it", async () => {
    const calls = installFetch((url) =>
      url.endsWith("/api/login")
        ? new Response(JSON.stringify({ detail: "Too many failed attempts" }), { status: 429 })
        : new Response("{}", { status: 200 }),
    );
    const { piCeoFetch, isLockedOut } = await import("../lib/pi-ceo-session");

    expect(await piCeoFetch("/api/swarm/status")).toBeNull();
    expect(isLockedOut(), "429 must set the cooldown").toBe(true);

    // Retrying into a lockout extends the window. The second call must not reach the wire.
    expect(await piCeoFetch("/api/swarm/status")).toBeNull();
    expect(calls.filter((c) => c.url.endsWith("/api/login"))).toHaveLength(1);
  });

  it("negative control: no password configured means no upstream call at all", async () => {
    process.env.PI_CEO_PASSWORD = "";
    const calls = installFetch(() => new Response("{}", { status: 200 }));
    const { piCeoFetch } = await import("../lib/pi-ceo-session");

    expect(await piCeoFetch("/api/swarm/status")).toBeNull();
    expect(calls, "must not attempt a login with an empty password").toHaveLength(0);
  });
});
