/**
 * MargotBubble — loaded, empty and error states (AAA check 7, MC-00).
 * The bubble reads nothing until a message is sent to /api/margot/bubble;
 * its data is Margot's reply. A failure must be said as a failure, not as a
 * reply.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import MargotBubble from "@/components/margot/MargotBubble";

function serve(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

async function ask(text: string) {
  render(<MargotBubble />);
  fireEvent.click(screen.getByRole("button", { name: "Open Margot personal assistant" }));
  fireEvent.change(screen.getByPlaceholderText("Ask Margot about portfolio ops…"), { target: { value: text } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
}

beforeAll(() => {
  // jsdom has no layout, so no scrollIntoView; the bubble scrolls to the newest message.
  Element.prototype.scrollIntoView = () => {};
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("MargotBubble", () => {
  it("LOADED: a reply from Margot appears after the question", async () => {
    serve({ reply: "Three builds shipped today." });
    await ask("What shipped?");
    expect(await screen.findByText("Three builds shipped today.")).toBeTruthy();
    expect(screen.getByText("What shipped?")).toBeTruthy();
  });

  it("EMPTY: an empty reply says none was received", async () => {
    serve({ reply: "   " });
    await ask("Anything?");
    expect(await screen.findByText("No reply received.")).toBeTruthy();
  });

  it("ERROR: a refused request shows the server's reason", async () => {
    serve({ error: "Margot is rate limited." }, 429);
    await ask("Status?");
    expect(await screen.findByText("Margot is rate limited.")).toBeTruthy();
  });

  it("ERROR: a network failure says the connection failed", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    await ask("Status?");
    expect(await screen.findByText("Connection error — check Pi-CEO backend reachability.")).toBeTruthy();
  });
});
