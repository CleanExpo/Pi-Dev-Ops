import { describe, it, expect, vi, beforeEach } from "vitest";

describe("/api/session", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal("fetch", vi.fn());
  });

  it("returns 500 when ASSEMBLYAI_API_KEY missing", async () => {
    delete process.env.ASSEMBLYAI_API_KEY;
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", { method: "POST" }));
    expect(res.status).toBe(500);
  });

  it("calls AssemblyAI token endpoint with correct headers", async () => {
    process.env.ASSEMBLYAI_API_KEY = "fake_key_123";
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ token: "tmp_abc" }), { status: 200 })
    );
    const { POST } = await import("../route");
    await POST(new Request("http://x", { method: "POST" }));

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "https://api.assemblyai.com/v2/realtime/token",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ Authorization: "fake_key_123" }),
      })
    );
  });

  it("never leaks the real key in response body", async () => {
    process.env.ASSEMBLYAI_API_KEY = "fake_key_super_secret";
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ token: "tmp_abc" }), { status: 200 })
    );
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", { method: "POST" }));
    const text = await res.text();
    expect(text).not.toContain("fake_key_super_secret");
    expect(text).toContain("tmp_abc");
  });

  it("returns ws_url and expires_at alongside token", async () => {
    process.env.ASSEMBLYAI_API_KEY = "k";
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ token: "tmp_abc" }), { status: 200 })
    );
    const { POST } = await import("../route");
    const res = await POST(new Request("http://x", { method: "POST" }));
    const body = await res.json();
    expect(body.token).toBe("tmp_abc");
    expect(body.ws_url).toBe("wss://api.assemblyai.com/v2/realtime/ws");
    expect(typeof body.expires_at).toBe("number");
  });
});
