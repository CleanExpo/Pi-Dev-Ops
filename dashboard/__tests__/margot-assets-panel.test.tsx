/**
 * MargotAssetsPanel — loaded / empty / error states, preview, the build-packet
 * POST, and the exact proxy paths it requests. The panel's sub-paths were once
 * all 403'd by the /api/pi-ceo allowlist, so every requested path is checked
 * against allowed().
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import MargotAssetsPanel from "@/components/control/MargotAssetsPanel";
import { allowed } from "@/lib/pi-ceo-proxy-allowlist";

const PREFIX = "/api/pi-ceo";
const BASE = `${PREFIX}/api/margot/assets`;

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

interface Call {
  url: string;
  method: string;
}
type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

function stubFetch(handler: Handler): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, method: init?.method ?? "GET" });
      return handler(url, init);
    }),
  );
  return calls;
}

const OPTIONS = {
  model: "gpt-image-1",
  canonical_asset_exists: true,
  projects: ["unite-group", "restoreassist"],
  variants: ["avatar", "banner"],
  matrix_item_count: 4,
};
const PACKETS = {
  packets: [{ filename: "packet-20260928.json", modified_at: new Date().toISOString(), item_count: 4, mode: "dry" }],
};
const GENERATED = {
  assets: [{ filename: "unite-avatar.png", modified_at: new Date().toISOString(), size_bytes: 2048, has_provenance: true }],
};
const PREVIEW = {
  project: "unite-group",
  variant: "avatar",
  payload: { model: "gpt-image-1", prompt: "Margot, navy blazer, studio light", size: "1024x1024" },
  provenance: { prompt_sha256: "abcdef0123456789" },
};

/** A healthy backend; `over` replaces the response for any URL containing its key. */
function backend(over: Record<string, () => Response> = {}): Handler {
  return (url, init) => {
    for (const [key, fn] of Object.entries(over)) if (url.includes(key)) return fn();
    if (init?.method === "POST") return jsonResponse({ filename: "packet-new.json", item_count: 4 });
    if (url.startsWith(`${BASE}/options`)) return jsonResponse(OPTIONS);
    if (url.startsWith(`${BASE}/packets?`)) return jsonResponse(PACKETS);
    if (url.startsWith(`${BASE}/generated`)) return jsonResponse(GENERATED);
    if (url.startsWith(`${BASE}/preview`)) return jsonResponse(PREVIEW);
    if (url.startsWith(`${BASE}/packets/`)) {
      return jsonResponse({ item_count: 2, items: [{ project: "unite-group", variant: "avatar" }, { project: "restoreassist", variant: "banner" }] });
    }
    return jsonResponse({ detail: "not found" }, 404);
  };
}

describe("MargotAssetsPanel", () => {
  it("LOADED: renders options, packets and generated assets from the API", async () => {
    const calls = stubFetch(backend());
    render(<MargotAssetsPanel />);
    expect(await screen.findByText("packet-20260928.json")).toBeTruthy();
    expect(screen.getByText(/unite-avatar\.png/)).toBeTruthy();
    expect(screen.getByText(/gpt-image-1 · 4 matrix items/)).toBeTruthy();
    expect(screen.getByText("present")).toBeTruthy();
    expect(calls.map((c) => c.url).sort()).toEqual(
      [`${BASE}/generated?limit=6`, `${BASE}/options`, `${BASE}/packets?limit=8`].sort(),
    );
  });

  it("EMPTY: no packets says so explicitly", async () => {
    stubFetch(
      backend({
        "/options": () => jsonResponse({ ...OPTIONS, projects: [], variants: [], matrix_item_count: 0 }),
        "/packets?": () => jsonResponse({ packets: [] }),
        "/generated": () => jsonResponse({ assets: [] }),
      }),
    );
    render(<MargotAssetsPanel />);
    expect(await screen.findByText("No build packets yet.")).toBeTruthy();
    expect(screen.getByText(/0 projects × 0 variants/)).toBeTruthy();
  });

  it.each([
    [500, "HTTP 500"],
    [403, "HTTP 403"],
  ])("ERROR: backend %i is shown, not a blank panel", async (status, text) => {
    stubFetch(() => jsonResponse({ error: undefined }, status));
    render(<MargotAssetsPanel />);
    expect(await screen.findByText(`⚠ ${text}`)).toBeTruthy();
    expect(screen.queryByText("No build packets yet.")).toBeNull();
  });

  it("ERROR: a rejected fetch is shown", async () => {
    stubFetch(() => {
      throw new Error("network down");
    });
    render(<MargotAssetsPanel />);
    expect(await screen.findByText("⚠ HTTP error")).toBeTruthy();
  });

  it("ERROR: a packet-list failure alone is visible, not an empty list", async () => {
    stubFetch(backend({ "/packets?": () => jsonResponse({ detail: "x" }, 500) }));
    render(<MargotAssetsPanel />);
    expect(await screen.findByText("Build packets unavailable: HTTP 500")).toBeTruthy();
    expect(screen.queryByText("No build packets yet.")).toBeNull();
  });

  it("preview GETs /preview with project+variant and shows the prompt", async () => {
    const calls = stubFetch(backend());
    render(<MargotAssetsPanel />);
    await screen.findByText("packet-20260928.json");
    fireEvent.click(screen.getByRole("button", { name: "Preview prompt" }));
    expect(await screen.findByText(/Margot, navy blazer, studio light/)).toBeTruthy();
    expect(calls.map((c) => c.url)).toContain(`${BASE}/preview?project=unite-group&variant=avatar`);
  });

  it("ERROR: a failed preview is visible, not a silent no-op", async () => {
    stubFetch(backend({ "/preview": () => jsonResponse({ detail: "denied" }, 403) }));
    render(<MargotAssetsPanel />);
    await screen.findByText("packet-20260928.json");
    fireEvent.click(screen.getByRole("button", { name: "Preview prompt" }));
    expect(await screen.findByText("Preview failed: HTTP 403")).toBeTruthy();
  });

  it("build packet POSTs to /api/pi-ceo/api/margot/assets/packets and shows success", async () => {
    const calls = stubFetch(backend());
    render(<MargotAssetsPanel />);
    await screen.findByText("packet-20260928.json");
    fireEvent.change(screen.getByPlaceholderText("e.g. navy accents"), { target: { value: " navy " } });
    fireEvent.click(screen.getByRole("button", { name: /Build full packet/ }));
    expect(await screen.findByText("✓ Wrote packet-new.json (4 items)")).toBeTruthy();
    const post = calls.filter((c) => c.method === "POST");
    expect(post).toEqual([{ url: `${BASE}/packets`, method: "POST" }]);
    const fetchMock = vi.mocked(globalThis.fetch);
    const postInit = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")?.[1];
    expect(postInit?.body).toBe(JSON.stringify({ notes: "navy" }));
  });

  it("build packet failure shows the backend's detail", async () => {
    stubFetch(backend({ "/packets": () => jsonResponse({ detail: "packet dir not writable" }, 500) }));
    render(<MargotAssetsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /Build full packet/ }));
    expect(await screen.findByText("Build failed: packet dir not writable")).toBeTruthy();
  });

  it("build packet network rejection is visible", async () => {
    const healthy = backend();
    stubFetch((url, init) => {
      if (init?.method === "POST") throw new Error("offline");
      return healthy(url, init);
    });
    render(<MargotAssetsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /Build full packet/ }));
    expect(await screen.findByText("Build failed: Error: offline")).toBeTruthy();
  });

  it("expanding a packet GETs /packets/<file> and lists its items", async () => {
    const calls = stubFetch(backend());
    render(<MargotAssetsPanel />);
    fireEvent.click(await screen.findByText("packet-20260928.json"));
    expect(await screen.findByText("restoreassist/banner")).toBeTruthy();
    expect(calls.map((c) => c.url)).toContain(`${BASE}/packets/packet-20260928.json`);
  });

  it("ERROR: a failed packet expansion is visible, not a silent no-op", async () => {
    stubFetch(backend({ "/packets/": () => jsonResponse({ detail: "gone" }, 404) }));
    render(<MargotAssetsPanel />);
    fireEvent.click(await screen.findByText("packet-20260928.json"));
    expect(await screen.findByText("Packet unavailable: HTTP 404")).toBeTruthy();
  });

  it("every requested path (GET and POST) is accepted by the proxy allowlist", async () => {
    const calls = stubFetch(backend());
    render(<MargotAssetsPanel />);
    fireEvent.click(await screen.findByText("packet-20260928.json"));
    await screen.findByText("restoreassist/banner");
    fireEvent.click(screen.getByRole("button", { name: "Preview prompt" }));
    await screen.findByText(/Margot, navy blazer/);
    fireEvent.click(screen.getByRole("button", { name: /Build full packet/ }));
    await screen.findByText(/✓ Wrote packet-new\.json/);
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(9));
    for (const { url } of calls) {
      expect(url.startsWith(PREFIX)).toBe(true);
      expect(allowed(url.slice(PREFIX.length)), url).toBe(true);
    }
  });
});
