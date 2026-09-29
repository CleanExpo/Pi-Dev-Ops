/**
 * TerminalPanel — loaded / empty / error states, and the exact proxy paths it
 * requests. Every path must pass the /api/pi-ceo allowlist, or the live panel
 * is 403'd before the backend is ever asked.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TerminalPanel from "@/components/control/TerminalPanel";
import { allowed } from "@/lib/pi-ceo-proxy-allowlist";

const PREFIX = "/api/pi-ceo";

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

function stubFetch(handler: Handler): string[] {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      urls.push(url);
      return handler(url, init);
    }),
  );
  return urls;
}

describe("TerminalPanel", () => {
  it("LOADED: lists sessions and renders the selected pane's lines", async () => {
    const urls = stubFetch((url) => {
      if (url.startsWith(`${PREFIX}/api/terminal/sessions`)) {
        return jsonResponse({ sessions: [{ name: "pi-main", attached: true }, { name: "pi-worker" }] });
      }
      if (url.startsWith(`${PREFIX}/api/terminal/tail`)) {
        return jsonResponse({ session: "pi-main", lines: ["$ make build", "build ok"] });
      }
      return jsonResponse({}, 404);
    });
    render(<TerminalPanel />);
    expect(await screen.findByText(/pi-worker/)).toBeTruthy();
    expect(await screen.findByText(/build ok/)).toBeTruthy();
    expect(screen.getByText("● live")).toBeTruthy();
    expect(urls).toContain(`${PREFIX}/api/terminal/sessions`);
    expect(urls).toContain(`${PREFIX}/api/terminal/tail?session=pi-main&lines=200`);
  });

  it("EMPTY: an empty fleet says so explicitly", async () => {
    stubFetch(() => jsonResponse({ sessions: [] }));
    render(<TerminalPanel />);
    expect(await screen.findByText("No tmux sessions on this node.")).toBeTruthy();
  });

  it.each([
    [500, "HTTP 500"],
    [403, "HTTP 403"],
  ])("ERROR: backend %i is shown, not an empty fleet", async (status, text) => {
    stubFetch(() => jsonResponse({ detail: "nope" }, status));
    render(<TerminalPanel />);
    expect(await screen.findByText(`No sessions — ${text}`)).toBeTruthy();
    expect(screen.queryByText("No tmux sessions on this node.")).toBeNull();
  });

  it("ERROR: a rejected fetch is shown, not an empty fleet", async () => {
    stubFetch(() => {
      throw new Error("network down");
    });
    render(<TerminalPanel />);
    expect(await screen.findByText("No sessions — HTTP error")).toBeTruthy();
    expect(screen.queryByText("No tmux sessions on this node.")).toBeNull();
  });

  it("ERROR: a proxy placeholder (X-Upstream-Status) reads as unreachable", async () => {
    stubFetch(() => jsonResponse({ sessions: [] }, 200, { "X-Upstream-Status": "502" }));
    render(<TerminalPanel />);
    expect(await screen.findByText("No sessions — Pi-CEO backend unreachable")).toBeTruthy();
  });

  it("ERROR: a tail failure after sessions load is visible", async () => {
    stubFetch((url) =>
      url.includes("/api/terminal/sessions")
        ? jsonResponse({ sessions: [{ name: "pi-main" }] })
        : jsonResponse({ detail: "forbidden" }, 403),
    );
    render(<TerminalPanel />);
    expect(await screen.findByText("HTTP 403")).toBeTruthy();
  });

  it("every requested path is accepted by the proxy allowlist", async () => {
    const urls = stubFetch((url) =>
      url.includes("/api/terminal/sessions")
        ? jsonResponse({ sessions: [{ name: "pi main/1" }] })
        : jsonResponse({ lines: ["x"] }),
    );
    render(<TerminalPanel />);
    await waitFor(() => expect(urls.some((u) => u.includes("/api/terminal/tail"))).toBe(true));
    expect(urls.length).toBeGreaterThanOrEqual(2);
    for (const u of urls) {
      expect(u.startsWith(PREFIX)).toBe(true);
      expect(allowed(u.slice(PREFIX.length)), u).toBe(true);
    }
  });
});
