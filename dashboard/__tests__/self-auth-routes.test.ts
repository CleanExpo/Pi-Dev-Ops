/**
 * Do the routes that check auth themselves check it for real?
 *
 * margot/bubble, phone/gate and phone/progress used to accept any request whose Cookie header
 * merely CONTAINED the text "tao_session=" — a substring test, not a verification. The real
 * dashboard session cookie is pi_session. margot/bubble then attached TAO_WEBHOOK_SECRET and
 * ran a paid Margot turn upstream. cron/analyze compared against `Bearer ${CRON_SECRET}`, which
 * is the literal "Bearer undefined" when the secret is unset.
 *
 * Public routes that authenticate by their own secret must fail closed when it is unset;
 * those are checked at the bottom.
 *
 * POSITIVE CONTROLS: a valid pi_session must get PAST auth, or every 401 here only proves the
 * route is dead.
 */
import { describe, it, expect, beforeAll, afterEach, vi } from "vitest";
import { NextRequest } from "next/server";
import { createHmac, randomBytes } from "node:crypto";

vi.mock("@/lib/supabase/settings", () => ({
  getSettings: async () => ({ cronRepos: [], webhookSecret: "" }),
}));

// Generated per run, never literals (the secrets scanner cannot tell a fixture from a key).
const PASSWORD = randomBytes(24).toString("hex");

beforeAll(() => {
  process.env.DASHBOARD_PASSWORD = PASSWORD;
  delete process.env.TAO_WEBHOOK_SECRET;
  delete process.env.CRON_SECRET;
  delete process.env.INTAKE_WEBHOOK_SECRET;
  delete process.env.WEBHOOK_SECRET;
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.CRON_SECRET;
});

function validSession(): string {
  const issuedAt = String(Math.floor(Date.now() / 1000));
  const sig = createHmac("sha256", PASSWORD).update(issuedAt).digest("hex");
  return `pi_session=${issuedAt}.${sig}`;
}

const FORGED = [
  ["no cookie", {}],
  ["a forged tao_session cookie", { cookie: "tao_session=x" }],
  ["tao_session= buried in another cookie", { cookie: "a=tao_session=1; b=2" }],
  ["a forged pi_session cookie", { cookie: `pi_session=${Math.floor(Date.now() / 1000)}.deadbeef` }],
] as const;

function req(path: string, method: string, headers: Record<string, string> = {}) {
  return new NextRequest(`https://pi.invalid${path}`, {
    method,
    headers: { "content-type": "application/json", ...headers },
    body: method === "GET" ? undefined : JSON.stringify({ message: "hi" }),
  });
}

function stubFetch() {
  const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("margot/bubble", () => {
  const call = async (headers: Record<string, string>) => {
    const { POST } = await import("../app/api/margot/bubble/route");
    return POST(req("/api/margot/bubble", "POST", headers));
  };

  for (const [name, headers] of FORGED) {
    it(`401s ${name} and never calls upstream`, async () => {
      const fetchMock = stubFetch();
      expect((await call(headers as Record<string, string>)).status).toBe(401);
      expect(fetchMock).not.toHaveBeenCalled();
    });
  }

  it("CONTROL: a valid pi_session gets past auth (503: TAO_WEBHOOK_SECRET unset in test)", async () => {
    expect((await call({ cookie: validSession() })).status).toBe(503);
  });
});

for (const [path, mod, methods] of [
  ["/api/phone/gate", "gate", ["GET", "POST"]],
  ["/api/phone/progress", "progress", ["POST"]],
] as const) {
  describe(path, () => {
    for (const method of methods) {
      const call = async (headers: Record<string, string>) => {
        const route = mod === "gate"
          ? await import("../app/api/phone/gate/route")
          : await import("../app/api/phone/progress/route");
        const handler = (route as unknown as Record<string, (r: NextRequest) => Promise<Response>>)[method];
        return handler(req(path, method, headers));
      };

      for (const [name, headers] of FORGED) {
        it(`${method} 401s ${name} and never calls upstream`, async () => {
          const fetchMock = stubFetch();
          expect((await call(headers as Record<string, string>)).status).toBe(401);
          expect(fetchMock).not.toHaveBeenCalled();
        });
      }

      it(`CONTROL: ${method} with a valid pi_session reaches upstream`, async () => {
        const fetchMock = stubFetch();
        expect((await call({ cookie: validSession() })).status).toBe(200);
        expect(fetchMock).toHaveBeenCalledTimes(1);
      });
    }
  });
}

describe("cron/analyze", () => {
  const call = async (headers: Record<string, string>) => {
    const { GET } = await import("../app/api/cron/analyze/route");
    return GET(req("/api/cron/analyze", "GET", headers));
  };

  it("refuses 'Bearer undefined' when CRON_SECRET is unset", async () => {
    expect((await call({ authorization: "Bearer undefined" })).status).toBe(401);
  });

  it("refuses an empty bearer when CRON_SECRET is unset", async () => {
    expect((await call({ authorization: "Bearer " })).status).toBe(401);
    expect((await call({})).status).toBe(401);
  });

  it("refuses a wrong bearer when CRON_SECRET is set", async () => {
    process.env.CRON_SECRET = randomBytes(16).toString("hex");
    expect((await call({ authorization: "Bearer wrong" })).status).toBe(401);
  });

  it("CONTROL: the right bearer gets past auth", async () => {
    const secret = randomBytes(16).toString("hex");
    process.env.CRON_SECRET = secret;
    const res = await call({ authorization: `Bearer ${secret}` });
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ skipped: true });
  });
});

describe("public secret-authenticated routes fail closed when their secret is unset", () => {
  it("webhook/github refuses (no webhook secret configured)", async () => {
    const { POST } = await import("../app/api/webhook/github/route");
    expect((await POST(req("/api/webhook/github", "POST", { "x-hub-signature-256": "sha256=" }))).status)
      .toBeGreaterThanOrEqual(400);
  });

  it("webhook/intake refuses with INTAKE_WEBHOOK_SECRET unset", async () => {
    const { POST } = await import("../app/api/webhook/intake/route");
    expect((await POST(req("/api/webhook/intake", "POST", { "x-intake-secret": "" }))).status)
      .toBeGreaterThanOrEqual(400);
  });

  it("webhook/morning-intel refuses with WEBHOOK_SECRET unset", async () => {
    const { POST } = await import("../app/api/webhook/morning-intel/route");
    expect((await POST(req("/api/webhook/morning-intel", "POST", { "x-pi-ceo-secret": "" }))).status)
      .toBeGreaterThanOrEqual(400);
  });
});
