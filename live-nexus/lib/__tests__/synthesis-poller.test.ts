import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { SynthesisPoller } from "../synthesis-poller";

describe("SynthesisPoller", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function mockOk(payload: object) {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify(payload), { status: 200 })
    );
  }

  it("calls /api/synthesize after intervalMs", async () => {
    mockOk({ topics: ["X"], actions: [] });
    const onUpdate = vi.fn();
    const poller = new SynthesisPoller({
      intervalMs: 1000,
      getState: () => ({ transcript: "hi", topics: [], actions: [] }),
      onUpdate,
    });
    poller.start();
    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(0);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/synthesize",
      expect.objectContaining({ method: "POST" })
    );
    expect(onUpdate).toHaveBeenCalledWith({ topics: ["X"], actions: [] });
    poller.stop();
  });

  it("passes current state in request body", async () => {
    mockOk({ topics: [], actions: [] });
    const poller = new SynthesisPoller({
      intervalMs: 1000,
      getState: () => ({
        transcript: "new chunk",
        topics: ["prior"],
        actions: [{ title: "a", description: "", priority: 3 }],
      }),
      onUpdate: vi.fn(),
    });
    poller.start();
    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(0);
    const callBody = JSON.parse(
      (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].body
    );
    expect(callBody.transcript).toBe("new chunk");
    expect(callBody.current_topics).toEqual(["prior"]);
    expect(callBody.current_actions[0].title).toBe("a");
    poller.stop();
  });

  it("emits pause event after 3 consecutive failures", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("net"));
    const onPause = vi.fn();
    const poller = new SynthesisPoller({
      intervalMs: 1000,
      getState: () => ({ transcript: "x", topics: [], actions: [] }),
      onUpdate: vi.fn(),
      onPause,
    });
    poller.start();
    for (let i = 0; i < 3; i++) {
      await vi.advanceTimersByTimeAsync(1000);
      await vi.advanceTimersByTimeAsync(0);
    }
    expect(onPause).toHaveBeenCalledTimes(1);
    poller.stop();
  });

  it("stop() prevents further polls", async () => {
    mockOk({ topics: [], actions: [] });
    const onUpdate = vi.fn();
    const poller = new SynthesisPoller({
      intervalMs: 1000,
      getState: () => ({ transcript: "x", topics: [], actions: [] }),
      onUpdate,
    });
    poller.start();
    poller.stop();
    await vi.advanceTimersByTimeAsync(2000);
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it("flush() forces an immediate poll", async () => {
    mockOk({ topics: ["forced"], actions: [] });
    const onUpdate = vi.fn();
    const poller = new SynthesisPoller({
      intervalMs: 100000,
      getState: () => ({ transcript: "x", topics: [], actions: [] }),
      onUpdate,
    });
    poller.start();
    await poller.flush();
    expect(onUpdate).toHaveBeenCalledWith({ topics: ["forced"], actions: [] });
    poller.stop();
  });
});
