/**
 * RA-7898 T3 + T4 — presets validate; the board parser, the edits and the
 * BoardStore behave as docs/specs/modular-boards.md §5 says.
 */
import { describe, expect, it } from "vitest";

import { addItem, COLS, parseBoard, parseBoardText, removeItem, setLayouts, setView, type Board } from "@/lib/boards/board";
import { PRESET_IDS, PRESET_RAW, PRESETS } from "@/lib/boards/presets";
import { MODULES } from "@/lib/boards/registry";
import { createBoardsStore } from "@/lib/boards/state";
import { LocalBoardStore, presetSet, STORAGE_KEY } from "@/lib/boards/store";

describe("presets (T3)", () => {
  it("are exactly Desk, Founder brief and Wall screens 1-6", () => {
    expect([...PRESET_IDS].sort()).toEqual(["desk", "founder-brief", "wall-1", "wall-2", "wall-3", "wall-4", "wall-5", "wall-6"]);
  });
  it.each(Object.keys(PRESET_RAW))("%s parses, names registered modules and views, and respects min sizes", (id) => {
    const parsed = parseBoard(PRESET_RAW[id]);
    expect(parsed.ok).toBe(true);
    const board = PRESETS.get(id)!;
    for (const item of board.items) {
      const def = MODULES.get(item.module);
      expect(def, `${id}: unknown module ${item.module}`).toBeDefined();
      expect(def!.views[item.view], `${id}: unknown view ${item.view}`).toBeDefined();
      const cell = board.layouts.lg!.find((c) => c.i === item.id);
      expect(cell, `${id}: no lg cell for ${item.id}`).toBeDefined();
      expect(cell!.w).toBeGreaterThanOrEqual(def!.minSize.w);
      expect(cell!.h).toBeGreaterThanOrEqual(def!.minSize.h);
      expect(cell!.x + cell!.w).toBeLessThanOrEqual(COLS.lg);
    }
    expect(board.layouts.lg!.length).toBe(board.items.length);
  });
  it("wall presets use the Wall look", () => {
    for (const id of PRESET_IDS.filter((p) => p.startsWith("wall-"))) expect(PRESETS.get(id)!.skin).toBe("wall");
  });
});

const tiny: Board = { name: "T", skin: "paper", items: [{ id: "a", module: "fleet", view: "tile" }], layouts: { lg: [{ i: "a", x: 0, y: 0, w: 4, h: 5 }] } };

describe("board parser (T4)", () => {
  it.each([
    ["not JSON", "{", "That is not valid JSON."],
    ["an array", "[]", "A board must be a JSON object."],
    ["no name", JSON.stringify({ ...tiny, name: "" }), "A board needs a name."],
    ["a bad look", JSON.stringify({ ...tiny, skin: "candy" }), "Look must be one of paper, graphite, slate, wall."],
    ["duplicate ids", JSON.stringify({ ...tiny, items: [tiny.items[0], tiny.items[0]] }), "item ids must be unique"],
    ["a fractional cell", JSON.stringify({ ...tiny, layouts: { lg: [{ i: "a", x: 0.5, y: 0, w: 4, h: 5 }] } }), "layouts.lg cells need i and whole-number x, y, w, h"],
    ["no lg layout", JSON.stringify({ ...tiny, layouts: {} }), "A board needs an lg layout."],
  ])("refuses %s with a message", (_n, text, error) => {
    expect(parseBoardText(text)).toEqual({ ok: false, error });
  });
  it("keeps an unknown module id: it renders the grey frame (boards-registry.test.tsx, G1)", () => {
    const parsed = parseBoard({ ...tiny, items: [...tiny.items, { id: "z", module: "nope", view: "v" }] });
    expect(parsed.ok && parsed.board.items.map((i) => i.module)).toEqual(["fleet", "nope"]);
  });
  it("keeps an unknown view id: the frame falls back to the first view (boards-registry.test.tsx)", () => {
    const parsed = parseBoard({ ...tiny, items: [{ id: "a", module: "fleet", view: "nope" }] });
    expect(parsed.ok && parsed.board.items[0].view).toBe("nope");
  });
  it("refuses a layout cell for an item the board does not have", () => {
    expect(parseBoard({ ...tiny, layouts: { lg: [...tiny.layouts.lg!, { i: "ghost", x: 0, y: 9, w: 1, h: 1 }] } }))
      .toEqual({ ok: false, error: 'layouts.lg has a cell "ghost" for an item the board does not have.' });
  });
  it("refuses a cell that starts outside the columns", () => {
    expect(parseBoard({ ...tiny, layouts: { lg: [{ i: "a", x: 12, y: 0, w: 1, h: 1 }] } }))
      .toEqual({ ok: false, error: 'layouts.lg cell "a" starts outside the 12 columns' });
  });
  it("clamps a cell wider than the breakpoint's columns", () => {
    const parsed = parseBoard({ ...tiny, layouts: { lg: tiny.layouts.lg, sm: [{ i: "a", x: 0, y: 0, w: 12, h: 5 }] } });
    expect(parsed.ok && parsed.board.layouts.sm![0].w).toBe(COLS.sm);
  });
});

describe("board edits (T4)", () => {
  it("add places the module at the bottom with its view's default size", () => {
    const next = addItem(tiny, "clock", "digital", "c1");
    expect(next.items.at(-1)).toEqual({ id: "c1", module: "clock", view: "digital" });
    expect(next.layouts.lg!.at(-1)).toEqual({ i: "c1", x: 0, y: 5, w: 3, h: 3 });
    expect(tiny.items).toHaveLength(1);
  });
  it("add of an unregistered module changes nothing", () => {
    expect(addItem(tiny, "nope", "v", "x")).toBe(tiny);
  });
  it("remove drops the item from items and every layout", () => {
    const next = removeItem({ ...tiny, layouts: { lg: tiny.layouts.lg, md: [{ i: "a", x: 0, y: 0, w: 4, h: 5 }] } }, "a");
    expect(next.items).toEqual([]);
    expect(next.layouts).toEqual({ lg: [], md: [] });
  });
  it("setView switches the view and refuses an unknown one", () => {
    expect(setView(tiny, "a", "nope")).toBe(tiny);
  });
  it("setView to a wider view slides a right-edge card left so it stays inside the columns", () => {
    const desk = PRESETS.get("desk")!;
    const before = desk.layouts.lg!.find((c) => c.i === "models-1")!;
    expect(before.x + before.w).toBe(COLS.lg); // positive control: the card touches the right edge
    const cell = setView(desk, "models-1", "table").layouts.lg!.find((c) => c.i === "models-1")!;
    expect(cell.w).toBe(5);
    expect(cell.x + cell.w).toBeLessThanOrEqual(COLS.lg);
  });
  it("setLayouts keeps only known ids and the five fields", () => {
    const next = setLayouts(tiny, { lg: [{ i: "a", x: 2, y: 1, w: 5, h: 6, minW: 3 } as never, { i: "ghost", x: 0, y: 0, w: 1, h: 1 }] });
    expect(next.layouts.lg).toEqual([{ i: "a", x: 2, y: 1, w: 5, h: 6 }]);
  });
});

function memoryStorage(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return { data, storage: { getItem: (k: string) => data[k] ?? null, setItem: (k: string, v: string) => { data[k] = v; } } };
}

describe("BoardStore (T4)", () => {
  it("empty storage loads the presets", () => {
    const { storage } = memoryStorage();
    expect(new LocalBoardStore(() => storage).load()).toEqual(presetSet());
  });
  it("storage that throws falls back to presets, and a refused save says so", () => {
    const broken = { getItem: () => { throw new Error("denied"); }, setItem: () => { throw new Error("quota"); } };
    const store = new LocalBoardStore(() => broken);
    expect(store.load()).toEqual(presetSet());
    expect(store.saveAll(presetSet())).toBe(false);
  });
  it("unreadable storage falls back to presets, is reported, and is copied aside before any save", () => {
    const { data, storage } = memoryStorage({ [STORAGE_KEY]: "not json" });
    const store = new LocalBoardStore(() => storage);
    expect(store.load()).toEqual(presetSet());
    expect(store.quarantined()[0].error).toContain("not readable");
    expect(data[`${STORAGE_KEY}.unreadable`]).toBe("not json");
  });
  it("an invalid saved board is refused, reported, not shown, and survives the next save unchanged", () => {
    const bad = { name: "", skin: "paper", items: [], layouts: { lg: [] } };
    const good = presetSet().boards.desk;
    const { data, storage } = memoryStorage({ [STORAGE_KEY]: JSON.stringify({ order: ["good", "bad"], active: "bad", boards: { good, bad } }) });
    const store = new LocalBoardStore(() => storage);
    const set = store.load();
    expect(set.order).toEqual(["good"]);
    expect(set.active).toBe("good");
    expect(store.quarantined()).toEqual([{ id: "bad", error: "A board needs a name." }]);
    store.saveAll(set);
    expect(JSON.parse(data[STORAGE_KEY]).quarantine).toEqual({ bad });
    const again = new LocalBoardStore(() => storage);
    again.load();
    expect(again.quarantined().map((q) => q.id)).toEqual(["bad"]);
  });
  it("an invalid import is refused and storage is left unchanged", () => {
    const { data, storage } = memoryStorage();
    const store = new LocalBoardStore(() => storage);
    store.saveAll(presetSet());
    const before = data[STORAGE_KEY];
    const { set, result } = store.importJSON(presetSet(), '{"name":"x"}', "imported");
    expect(result.ok).toBe(false);
    expect(set).toEqual(presetSet());
    expect(data[STORAGE_KEY]).toBe(before);
  });
  it("export then import round-trips a board", () => {
    const store = new LocalBoardStore(() => memoryStorage().storage);
    const text = store.exportJSON(presetSet(), "desk")!;
    const { set, result } = store.importJSON(presetSet(), text, "copy");
    expect(result).toEqual({ ok: true, id: "copy" });
    expect(set.boards.copy).toEqual(presetSet().boards.desk);
    expect(set.active).toBe("copy");
  });
  it("save then load restores the same set", () => {
    const { storage } = memoryStorage();
    const store = new LocalBoardStore(() => storage);
    const edited = presetSet();
    edited.boards.desk = removeItem(edited.boards.desk, "clock-1");
    store.saveAll(edited);
    expect(store.load()).toEqual(edited);
  });
});

describe("remove and reset can be undone (RA-1109: destructive actions get undo)", () => {
  it("remove, then restore, brings the card back", () => {
    const store = createBoardsStore(new LocalBoardStore(() => memoryStorage().storage));
    const before = store.getState().boards.desk;
    store.getState().remove("clock-1");
    expect(store.getState().boards.desk.items.some((i) => i.id === "clock-1")).toBe(false);
    store.getState().restore();
    expect(store.getState().boards.desk).toEqual(before);
    expect(store.getState().undo).toBeNull();
  });
  it("reset, then restore, brings the edited board back", () => {
    const store = createBoardsStore(new LocalBoardStore(() => memoryStorage().storage));
    store.getState().remove("clock-1");
    const edited = store.getState().boards.desk;
    store.getState().reset();
    expect(store.getState().boards.desk.items.some((i) => i.id === "clock-1")).toBe(true);
    store.getState().restore();
    expect(store.getState().boards.desk).toEqual(edited);
  });
});
