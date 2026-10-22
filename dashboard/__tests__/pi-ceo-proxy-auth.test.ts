/**
 * Does /api/pi-ceo/[...path] check the caller's session itself?
 *
 * This route logs into Pi CEO with the server's own password and forwards the caller's request,
 * including POST /api/build (a paid session) and /api/sessions/<id>/kill. It used to rely on
 * proxy.ts alone, and proxy.ts never ran for paths ending in an image extension: an anonymous
 * "/api/pi-ceo/api/build%3F.png" reached upstream, the "%3F" decoding to "?" so ".png" fell into
 * the query string past the allowlist.
 *
 * POSITIVE CONTROL: a valid pi_session must reach upstream, or every 401 here only proves the
 * route is dead.
 */
import { describe, it, expect, beforeAll, beforeEach, vi } from "vitest";
import { createHmac, randomBytes } from "node:crypto";

// Generated per run, never literals (the secrets scanner cannot tell a fixture from a key).
const PASSWORD = randomBytes(24).toString("hex");

beforeAll(() => {
  process.env.DASHBOARD_PASSWORD = PASSWORD;
});

let upstream: string[] = [];

beforeEach(() => {
  vi.resetModules();
  vi.unstubAllGlobals();
  upstream = [];
  process.env.PI_CEO_URL = "https://upstream.test";
  process.env.PI_CEO_PASSWORD = randomBytes(12).toString("hex");
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    upstream.push(url);
    if (url.endsWith("/api/login")) {
      return new Response("{}", { status: 200, headers: { "set-cookie": "tao_session=t; Path=/" } });
    }
    return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  });
});

function session(): string {
  const issuedAt = String(Math.floor(Date.now() / 1000));
  const sig = createHmac("sha256", PASSWORD).update(issuedAt).digest("hex");
  return `pi_session=${issuedAt}.${sig}`;
}

async function call(method: "GET" | "POST", path: string[], cookie?: string) {
  const mod = await import("../app/api/pi-ceo/[...path]/route");
  const url = `https://pi.invalid/api/pi-ceo/${path.join("/")}`;
  const init: RequestInit = { method, headers: cookie ? { cookie } : {} };
  if (method === "POST") init.body = JSON.stringify({ repo_url: "x", brief: "y" });
  return mod[method](new Request(url, init), { params: Promise.resolve({ path }) });
}

describe("pi-ceo proxy checks the session itself", () => {
  for (const [method, path] of [
    ["GET", ["api", "sessions"]],
    ["POST", ["api", "build"]],
    ["POST", ["api", "sessions", "abc123", "kill"]],
    ["GET", ["api", "sessions?.png"]],
  ] as const) {
    it(`${method} /${path.join("/")} with no session is 401 and never reaches upstream`, async () => {
      expect((await call(method, [...path])).status).toBe(401);
      expect(upstream).toEqual([]);
    });
  }

  it("a forged pi_session is 401", async () => {
    const forged = `pi_session=${Math.floor(Date.now() / 1000)}.deadbeef`;
    expect((await call("POST", ["api", "build"], forged)).status).toBe(401);
    expect(upstream).toEqual([]);
  });

  it("CONTROL: a valid session reaches upstream", async () => {
    expect((await call("GET", ["api", "sessions"], session())).status).toBe(200);
    expect(upstream.some((u) => u.endsWith("/api/sessions"))).toBe(true);
  });

  it("a ? or # decoded into a path segment is refused even with a session", async () => {
    for (const seg of ["build?.png", "build#x"]) {
      expect((await call("POST", ["api", seg], session())).status).toBe(403);
    }
    expect(upstream.filter((u) => !u.endsWith("/api/login"))).toEqual([]);
  });
});
