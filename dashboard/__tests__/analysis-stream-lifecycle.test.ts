import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSSE } from "@/hooks/useSSE";
class MockEventSource {
  static instances: MockEventSource[] = [];
  onerror: (() => void) | null = null;
  addEventListener = vi.fn(); close = vi.fn();
  constructor() { MockEventSource.instances.push(this); }
}
beforeEach(() => { vi.useFakeTimers(); MockEventSource.instances = []; vi.stubGlobal("EventSource", MockEventSource); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
describe("analysis stream lifecycle", () => {
  it("does not replay a mutation-bearing analysis request after a disconnect", async () => {
    const { result } = renderHook(() => useSSE());
    act(() => result.current.start("https://github.com/org/project"));
    act(() => MockEventSource.instances[0].onerror?.());
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(MockEventSource.instances).toHaveLength(1);
    expect(result.current.status).toBe("error");
  });
  it("closes observation when the analysis view unmounts", () => {
    const { result, unmount } = renderHook(() => useSSE());
    act(() => result.current.start("https://github.com/org/project"));
    unmount();
    expect(MockEventSource.instances[0].close).toHaveBeenCalled();
  });
});
