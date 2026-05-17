import { describe, it, expect, vi, beforeEach } from "vitest";

function anthropicToolUseResponse(
  topics: string[],
  actions: Array<{ title: string; description: string; priority: number }>
) {
  return {
    id: "msg_1",
    type: "message",
    role: "assistant",
    content: [
      {
        type: "tool_use",
        id: "toolu_1",
        name: "update_synthesis",
        input: { topics, actions },
      },
    ],
    stop_reason: "tool_use",
  };
}

describe("/api/synthesize", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal("fetch", vi.fn());
    process.env.ANTHROPIC_API_KEY = "sk-ant-test";
  });

  it("returns 500 when ANTHROPIC_API_KEY missing", async () => {
    delete process.env.ANTHROPIC_API_KEY;
    const { POST } = await import("../route");
    const res = await POST(
      new Request("http://x", {
        method: "POST",
        body: JSON.stringify({ transcript: "hi", current_topics: [], current_actions: [] }),
      })
    );
    expect(res.status).toBe(500);
  });

  it("parses topics + actions from tool_use response", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(
        JSON.stringify(
          anthropicToolUseResponse(
            ["Q2 pricing"],
            [{ title: "Send proposal", description: "Friday", priority: 2 }]
          )
        )
      )
    );
    const { POST } = await import("../route");
    const res = await POST(
      new Request("http://x", {
        method: "POST",
        body: JSON.stringify({
          transcript: "we discussed Q2 pricing",
          current_topics: [],
          current_actions: [],
        }),
      })
    );
    const body = await res.json();
    expect(body.topics).toEqual(["Q2 pricing"]);
    expect(body.actions[0].title).toBe("Send proposal");
  });

  it("returns 502 when Anthropic returns non-2xx", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response("rate limit", { status: 429 })
    );
    const { POST } = await import("../route");
    const res = await POST(
      new Request("http://x", {
        method: "POST",
        body: JSON.stringify({ transcript: "x", current_topics: [], current_actions: [] }),
      })
    );
    expect(res.status).toBe(502);
  });

  it("returns empty arrays when no tool_use block in response", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ content: [{ type: "text", text: "refusing" }] }))
    );
    const { POST } = await import("../route");
    const res = await POST(
      new Request("http://x", {
        method: "POST",
        body: JSON.stringify({ transcript: "x", current_topics: [], current_actions: [] }),
      })
    );
    const body = await res.json();
    expect(body.topics).toEqual([]);
    expect(body.actions).toEqual([]);
  });

  it("passes current_topics + current_actions in the Anthropic prompt", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify(anthropicToolUseResponse([], [])))
    );
    const { POST } = await import("../route");
    await POST(
      new Request("http://x", {
        method: "POST",
        body: JSON.stringify({
          transcript: "new text",
          current_topics: ["already discussed"],
          current_actions: [{ title: "existing action", description: "", priority: 3 }],
        }),
      })
    );
    const callBody = JSON.parse(
      (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].body
    );
    expect(JSON.stringify(callBody)).toContain("already discussed");
    expect(JSON.stringify(callBody)).toContain("existing action");
  });
});
