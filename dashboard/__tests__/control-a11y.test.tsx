// Regression tests for the three axe failures the "Mission Control live"
// workflow reported on /control and /control/boards (9 Nov 2026):
// scrollable-region-focusable, aria-required-children, color-contrast.
// axe-core is already installed (dependency of @axe-core/playwright).
// jsdom has no layout, so the contrast rule is checked by computing the WCAG
// ratio from the tokens in globals.css rather than by axe.
import fs from "node:fs";
import path from "node:path";

import { cleanup, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BoardHeader } from "@/components/boards/BoardHeader";
import WallPanel from "@/components/control/wall/WallPanel";
import { presetSet } from "@/lib/boards/store";

afterEach(cleanup);

async function violationIds(container: Element, rules: string[]): Promise<string[]> {
  const res = await axe.run(container, { runOnly: { type: "rule", values: rules } });
  return res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

describe("BoardHeader tabs (aria-required-children)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({}), { status: 200 })));
  });

  function renderHeader() {
    const set = presetSet();
    return render(
      <BoardHeader
        board={set.boards[set.active]}
        order={set.order}
        boards={set.boards}
        active={set.active}
        editing={false}
        onSelect={() => {}}
        onNewBoard={() => {}}
        onSkin={() => {}}
        onToggleEdit={() => {}}
      />,
    );
  }

  it("holds only role=tab children in the tablist", () => {
    renderHeader();
    const tablist = screen.getByRole("tablist", { name: "Boards" });
    expect(tablist.children.length).toBeGreaterThan(0);
    for (const child of Array.from(tablist.children)) expect(child.getAttribute("role")).toBe("tab");
  });

  it("keeps + Board reachable as a button outside the tablist", () => {
    renderHeader();
    const add = screen.getByRole("button", { name: "+ Board" });
    expect(screen.getByRole("tablist", { name: "Boards" }).contains(add)).toBe(false);
  });

  it("has no axe aria-required-children violation", async () => {
    const { container } = renderHeader();
    expect(await violationIds(container, ["aria-required-children"])).toEqual([]);
  });
});

describe("WallPanel body (scrollable-region-focusable)", () => {
  function renderPanel() {
    return render(
      <WallPanel id="wall-test" title="Test panel" area="fleet" stateText="live" tone="ok">
        <p>content</p>
      </WallPanel>,
    );
  }

  it("makes the scrolling body focusable and named", () => {
    renderPanel();
    const body = screen.getByRole("region", { name: "Test panel content" });
    expect(body.tabIndex).toBe(0);
  });

  it("has no axe focusable-region or naming violation", async () => {
    const { container } = renderPanel();
    expect(
      await violationIds(container, ["scrollable-region-focusable", "aria-allowed-attr", "region"]),
    ).toEqual([]);
  });
});

describe("board text token (color-contrast)", () => {
  const css = fs.readFileSync(path.join(__dirname, "..", "app", "globals.css"), "utf8");
  // The first [data-board-skin] block is the Paper look, which every other look overrides.
  const paper = css.slice(css.indexOf("[data-board-skin] {"));
  const token = (name: string) => {
    const m = paper.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})\\s*;`));
    if (!m) throw new Error(`token ${name} not found in the Paper block of globals.css`);
    return m[1];
  };
  const lum = (hex: string) => {
    const [r, g, b] = [1, 3, 5].map((i) => {
      const c = parseInt(hex.slice(i, i + 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const ratio = (a: string, b: string) => {
    const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };

  it("--board-ink-3 reaches 4.5:1 on the board canvas", () => {
    expect(ratio(token("--board-ink-3"), token("--board-canvas"))).toBeGreaterThanOrEqual(4.5);
  });

  it("--board-ink-3 reaches 4.5:1 on the card", () => {
    expect(ratio(token("--board-ink-3"), token("--board-card"))).toBeGreaterThanOrEqual(4.5);
  });
});
