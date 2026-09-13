/**
 * Can an anonymous caller write through /api/attachments/upload?
 *
 * RA-7487. On current main the named Drive-mint handler is absent, but an
 * anonymous POST still reached the dashboard and returned HTTP 200 HTML
 * because proxy.ts is default-open. This file asserts the refusal, and — the
 * part that makes the refusal meaningful — that a valid session gets past auth.
 *
 * POSITIVE CONTROLS ARE THE POINT. "Returns 401" is also what a broken route
 * returns. If the accepted credential does not get past auth, this file proves
 * only that the endpoint is dead.
 */
import { describe, it, expect, beforeAll, vi } from "vitest";
import { createHmac, randomBytes } from "node:crypto";
import { NextRequest } from "next/server";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

const PASSWORD = randomBytes(24).toString("hex");
const ROOT = resolve(__dirname, "..");

beforeAll(() => {
  process.env.DASHBOARD_PASSWORD = PASSWORD;
});

function sessionCookie(): string {
  const issuedAt = String(Math.floor(Date.now() / 1000));
  const sig = createHmac("sha256", PASSWORD).update(issuedAt).digest("hex");
  return `pi_session=${issuedAt}.${sig}`;
}

async function post(headers: Record<string, string> = {}): Promise<Response> {
  const { POST } = await import("../app/api/attachments/upload/route");
  return POST(
    new Request("https://pi.invalid/api/attachments/upload", {
      method: "POST",
      headers: { "content-type": "application/json", ...headers },
      body: JSON.stringify({ filename: "probe.bin" }),
    }),
  );
}

describe("attachments upload auth", () => {
  it("REFUSES an anonymous upload", async () => {
    const res = await post();
    expect(res.status, "an anonymous POST reached the upload path").toBe(401);
    expect(await res.json()).toEqual({ error: "Unauthorised" });
  });

  it("REFUSES a forged session cookie", async () => {
    const issuedAt = String(Math.floor(Date.now() / 1000));
    expect((await post({ cookie: `pi_session=${issuedAt}.deadbeef` })).status).toBe(401);
  });

  it("REFUSES an expired session cookie", async () => {
    const old = String(Math.floor(Date.now() / 1000) - 90_000);
    const sig = createHmac("sha256", PASSWORD).update(old).digest("hex");
    expect((await post({ cookie: `pi_session=${old}.${sig}` })).status).toBe(401);
  });

  it("does not read the body before refusing an anonymous caller", async () => {
    const { POST } = await import("../app/api/attachments/upload/route");
    const req = new Request("https://pi.invalid/api/attachments/upload", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ filename: "probe.bin" }),
    });
    const json = vi.spyOn(req, "json").mockRejectedValue(new Error("body must not be read"));
    const formData = vi
      .spyOn(req, "formData")
      .mockRejectedValue(new Error("body must not be read"));
    const res = await POST(req);
    expect(res.status).toBe(401);
    expect(json).not.toHaveBeenCalled();
    expect(formData).not.toHaveBeenCalled();
  });

  it("does not mint Drive credentials", () => {
    const src = readFileSync(join(ROOT, "app/api/attachments/upload/route.ts"), "utf8");
    expect(src).not.toMatch(/DRIVE_|mintServiceAccount|googleapis|drive-client/i);
  });

  it("CONTROL: a valid session cookie gets PAST auth", async () => {
    const res = await post({ cookie: sessionCookie() });
    expect(
      res.status,
      "a valid session was rejected — the 401s above would then prove only that the endpoint is broken",
    ).not.toBe(401);
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ error: "Upload not configured" });
  });

  it("CONTROL: proxy refuses an anonymous POST", async () => {
    const { proxy } = await import("../proxy");
    const res = await proxy(
      new NextRequest("https://pi.invalid/api/attachments/upload", { method: "POST" }),
    );
    expect(res.status, "proxy default-open let an anonymous upload through").toBe(401);
  });
});
