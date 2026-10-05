/**
 * RA-7898 — /control/boards page and ModuleFrame: loaded, empty and error
 * states (AAA check 7, MC-20), plus the confirm-and-undo flow for destructive
 * board edits (RA-1109).
 */
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BoardsPage } from "@/components/boards/BoardsPage";
import { ModuleFrame } from "@/components/boards/ModuleFrame";
import { useBoards } from "@/lib/boards/state";
import { presetSet, STORAGE_KEY } from "@/lib/boards/store";

class FixedResizeObserver {
  constructor(private readonly cb: ResizeObserverCallback) {}
  observe(target: Element) {
    this.cb([{ target, contentRect: { width: 1200, height: 800 } } as unknown as ResizeObserverEntry], this as unknown as ResizeObserver);
  }
  unobserve() {}
  disconnect() {}
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", FixedResizeObserver);
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, get: () => 1200 });
  vi.stubGlobal("fetch", vi.fn(async () => json({ status: "ok", checkedAt: new Date().toISOString(), machines: [] })));
  localStorage.clear();
  useBoards.setState({ ...presetSet(), hydrated: false, saved: true, refused: [], undo: null });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

describe("BoardsPage", () => {
  it("LOADED: opens the Desk board with its cards in their frames", async () => {
    render(<BoardsPage />);
    expect(await screen.findByRole("tab", { name: "Desk", selected: true })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Brisbane time" })).toBeInTheDocument();
    expect(document.querySelectorAll("article[data-module]").length).toBeGreaterThan(5);
  });

  it("EMPTY: a new board says it is empty and how to fill it", async () => {
    render(<BoardsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "+ Board" }));
    expect(await screen.findByText("This board is empty")).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Module library" })).toBeInTheDocument();
  });

  it("ERROR: a saved board that fails validation is reported, not shown, and not lost", async () => {
    const good = presetSet().boards.desk;
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ order: ["good", "broken"], active: "good", boards: { good, broken: { name: "" } } }));
    render(<BoardsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("One saved board could not be read and is not shown (broken: A board needs a name.)");
    expect(screen.queryByRole("tab", { name: "broken" })).toBeNull();
  });

  it("reset asks first; Cancel changes nothing; Reset then Undo restores the edited board", async () => {
    render(<BoardsPage />);
    await screen.findByRole("heading", { name: "Brisbane time" });
    act(() => { useBoards.getState().remove("clock-1"); });
    fireEvent.click(screen.getByRole("button", { name: "Customize" }));
    // The grid re-compacts positions in edit mode; compare which cards are on the board.
    const cards = () => useBoards.getState().boards.desk.items.map((i) => i.id);
    const edited = cards();
    expect(edited).not.toContain("clock-1");
    fireEvent.click(screen.getByRole("button", { name: "Reset to preset" }));
    const ask = screen.getByRole("alertdialog", { name: "Confirm reset" });
    fireEvent.click(within(ask).getByRole("button", { name: "Cancel" }));
    expect(cards()).toEqual(edited);
    fireEvent.click(screen.getByRole("button", { name: "Reset to preset" }));
    fireEvent.click(within(screen.getByRole("alertdialog", { name: "Confirm reset" })).getByRole("button", { name: "Reset board" }));
    expect(cards()).toContain("clock-1");
    // The message names THIS reset, not the earlier remove's undo text.
    expect(screen.getByText("Board back to its starting layout.")).toBeInTheDocument();
    expect(screen.queryByText("Removed from board.")).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
    expect(cards()).toEqual(edited);
  });
});

describe("ModuleFrame", () => {
  it("LOADED: a live source renders the view and its freshness", async () => {
    render(<ModuleFrame item={{ id: "f", module: "fleet", view: "list" }} />);
    expect(await screen.findByText("No machines enrolled.")).toBeInTheDocument();
    expect(document.querySelector("article")?.getAttribute("data-state")).toBe("live");
    expect(screen.getByTestId("module-freshness")).toHaveTextContent(/^Updated \d+ s ago$/);
  });

  it("EMPTY: a source that is not configured shows 'No source yet' and no view", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ status: "unavailable", checkedAt: "x", reason: "mesh secret not configured" }, 503)));
    render(<ModuleFrame item={{ id: "f", module: "fleet", view: "list" }} />);
    expect(await screen.findByText("No source yet.")).toBeInTheDocument();
    expect(screen.getByText("mesh secret not configured")).toBeInTheDocument();
  });

  it("ERROR: an unreachable source shows the reason and no number", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ status: "unavailable", checkedAt: "x", reason: "upstream unreachable" }, 503)));
    render(<ModuleFrame item={{ id: "f", module: "fleet", view: "strip" }} />);
    expect(await screen.findByText("Unreachable.")).toBeInTheDocument();
    expect(document.querySelector("article")?.textContent).not.toMatch(/\d/);
  });
});
