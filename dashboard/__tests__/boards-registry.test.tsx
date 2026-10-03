/**
 * RA-7898 G1 + G4 — registry discovery, the five frame states for every view,
 * and the grey frame for an unregistered module id.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SourceSnapshot, SourceState } from "@/lib/boards/sources/types";

const forced: { state: SourceState | null } = { state: null };

vi.mock("@/lib/boards/sources/useSources", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/boards/sources/useSources")>();
  return {
    useSources: (ids: readonly string[]) => {
      const snaps = real.useSources(ids);
      if (forced.state === null) return snaps;
      return snaps.map((s): SourceSnapshot<unknown> => ({
        ...s, state: forced.state as SourceState, seq: forced.state === "loading" ? 0 : 1,
        reason: forced.state === "live" || forced.state === "loading" ? null : `reason-${forced.state}`,
        lastGoodAt: forced.state === "live" ? Date.now() : null,
      }));
    },
  };
});

import ModuleFrame from "@/components/boards/ModuleFrame";
import { MODULE_LIST } from "@/lib/boards/registry";
import { FEEDS } from "@/lib/boards/sources/feeds";

beforeEach(() => {
  // Panels mounted in the live state read their feeds; nothing answers.
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); forced.state = null; });

const VIEWS = MODULE_LIST.flatMap((m) => Object.entries(m.views).map(([view, def]) => ({ module: m, view, def })));

describe("registry discovery (G4)", () => {
  it.each(MODULE_LIST.map((m) => [m.id, m] as const))("%s has a known source, a view and a min size", (_id, m) => {
    expect(m.sources.length).toBeGreaterThan(0);
    for (const s of m.sources) expect(FEEDS.has(s), `unknown feed ${s}`).toBe(true);
    expect(Object.keys(m.views).length).toBeGreaterThan(0);
    expect(m.minSize.w).toBeGreaterThan(0);
    expect(m.minSize.h).toBeGreaterThan(0);
    for (const v of Object.values(m.views)) {
      expect(v.size.w).toBeGreaterThanOrEqual(m.minSize.w);
      expect(v.size.h).toBeGreaterThanOrEqual(m.minSize.h);
    }
    expect(m.name).toBe(m.name.charAt(0).toUpperCase() + m.name.slice(1));
  });

  it("module ids are unique", () => {
    expect(new Set(MODULE_LIST.map((m) => m.id)).size).toBe(MODULE_LIST.length);
  });

  it("action modules are exactly the four that write today, and only their view #1 is an action view", () => {
    expect(MODULE_LIST.filter((m) => m.action).map((m) => m.id).sort()).toEqual(["health", "ideas", "kill-switch", "swarm"]);
    for (const m of MODULE_LIST) {
      const actionViews = Object.values(m.views).filter((v) => v.action);
      expect(actionViews.length).toBe(m.action ? 1 : 0);
    }
  });
});

describe("every view renders all five states through ModuleFrame (G4)", () => {
  const STATES: SourceState[] = ["loading", "live", "stale", "unreachable", "no_source"];
  it.each(VIEWS.flatMap((v) => STATES.map((s) => [`${v.module.id}/${v.view}`, s, v] as const)))("%s in %s", (_n, state, v) => {
    forced.state = state;
    const { container } = render(<ModuleFrame item={{ id: "x", module: v.module.id, view: v.view }} />);
    const card = container.querySelector("article")!;
    expect(card.getAttribute("data-state")).toBe(state);
    // The frame's own title (a view #1 panel may carry its own heading too).
    expect(card.querySelector(":scope > header h3")?.textContent).toBe(v.module.name);
    const stateNode = within(card).queryByTestId("module-state");
    if (state === "live") {
      expect(stateNode).toBeNull();
    } else if (state === "loading") {
      expect(stateNode?.textContent).toContain("Loading");
    } else {
      expect(stateNode?.textContent).toContain(`reason-${state}`);
      if (!v.def.action) {
        // A read-only view is not rendered outside live: the frame's message is the whole body.
        expect(card.querySelector("[data-testid='module-state']")?.parentElement?.children.length).toBe(1);
      }
    }
  });
});

describe("unknown module id (G1, A4)", () => {
  it("renders the grey frame with only a Remove action, and no capability", () => {
    const onRemove = vi.fn();
    render(<ModuleFrame item={{ id: "a", module: "launch-missiles", view: "big-red-button" }} onRemove={onRemove} />);
    expect(screen.getByRole("heading", { name: "Unknown module “launch-missiles”" })).toBeInTheDocument();
    const buttons = screen.getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual(["Remove from board"]);
    buttons[0].click();
    expect(onRemove).toHaveBeenCalledWith("a");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("an unknown view id falls back to the module's first view", () => {
    forced.state = "no_source";
    const { container } = render(<ModuleFrame item={{ id: "a", module: "fleet", view: "nope" }} />);
    expect(container.querySelector("article")?.getAttribute("data-view")).toBe("tile");
  });
});
