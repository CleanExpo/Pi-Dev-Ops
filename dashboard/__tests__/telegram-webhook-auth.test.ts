/**
 * Does the Telegram webhook actually require its secret?
 *
 * Until 2026-08-02 it did not. The check read:
 *
 *   if (webhookSecret && incomingSecret && incomingSecret !== webhookSecret) return 403
 *
 * so it rejected only when the server secret was configured AND the caller presented one AND
 * they differed. Two paths fell straight through to the handler: an unset server secret, and
 * — the one that matters — a caller who simply OMITTED the header. The guard was bypassable
 * by not presenting a credential.
 *
 * This is the public inbound edge of the notification channel: `/api/telegram` is in
 * PUBLIC_API_PREFIXES, so the proxy performs no session check and this route's own secret is
 * the only thing standing in front of it.
 *
 * The omission case is asserted FIRST because it is the one the old code got wrong, and a
 * suite that only tests wrong-secret would have passed against the vulnerable version.
 */
import { describe, it, expect, beforeAll } from "vitest";

const SECRET = "telegram-webhook-test-secret";

beforeAll(() => {
  process.env.TELEGRAM_WEBHOOK_SECRET = SECRET;
  // No bot token: the handler cannot reach api.telegram.org even if a test got that far.
  delete process.env.TELEGRAM_BOT_TOKEN;
});

async function post(headers: Record<string, string> = {}) {
  const { POST } = await import("../app/api/telegram/route");
  const { NextRequest } = await import("next/server");
  return POST(
    new NextRequest("https://pi.invalid/api/telegram", {
      method: "POST",
      headers: { "content-type": "application/json", ...headers },
      body: JSON.stringify({
        message: { text: "/status", chat: { id: 999_999 } },
      }),
    }),
  );
}

describe("telegram webhook secret", () => {
  it("REFUSES a request that omits the secret header (the old bypass)", async () => {
    const res = await post();
    expect(
      res.status,
      "a request with NO secret header was accepted. That was the original defect: the guard " +
        "only fired when a secret was presented, so omitting it skipped the check entirely.",
    ).toBe(403);
  });

  it("REFUSES an empty secret header", async () => {
    expect((await post({ "x-telegram-bot-api-secret-token": "" })).status).toBe(403);
  });

  it("REFUSES a whitespace-only secret header", async () => {
    expect((await post({ "x-telegram-bot-api-secret-token": "   " })).status).toBe(403);
  });

  it("REFUSES a wrong secret", async () => {
    expect(
      (await post({ "x-telegram-bot-api-secret-token": "not-the-secret" })).status,
    ).toBe(403);
  });

  it("REFUSES a secret that is a prefix of the real one", async () => {
    expect(
      (await post({ "x-telegram-bot-api-secret-token": SECRET.slice(0, 8) })).status,
    ).toBe(403);
  });

  it("FAILS CLOSED when the server secret is unset", async () => {
    const saved = process.env.TELEGRAM_WEBHOOK_SECRET;
    delete process.env.TELEGRAM_WEBHOOK_SECRET;
    try {
      // An unconfigured secret must not mean "accept anyone", which is what it meant before.
      expect((await post({ "x-telegram-bot-api-secret-token": "anything" })).status).toBe(403);
    } finally {
      process.env.TELEGRAM_WEBHOOK_SECRET = saved;
    }
  });

  // ---- POSITIVE CONTROL — without it, every 403 above is also what a dead route returns.
  //
  // Deliberately paired with an INVALID JSON body. A correct secret plus a valid body runs the
  // whole command handler, which reaches a network path and hangs the test; the first version
  // of this control did exactly that and timed out at 5s inside the gate. Invalid JSON returns
  // `{ ok: true }` on the line immediately after the secret check, so this isolates the one
  // thing being controlled for — did we get past the guard — with no side effects and no I/O.
  it("CONTROL: the correct secret gets PAST the secret check", async () => {
    const { POST } = await import("../app/api/telegram/route");
    const { NextRequest } = await import("next/server");
    const res = await POST(
      new NextRequest("https://pi.invalid/api/telegram", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-telegram-bot-api-secret-token": SECRET,
        },
        body: "{not json",
      }),
    );
    expect(
      res.status,
      "the correct secret was rejected — the refusals above would then show only that the " +
        "endpoint is broken, not that it is guarded.",
    ).not.toBe(403);
    expect(res.status).toBe(200);
  });
});
