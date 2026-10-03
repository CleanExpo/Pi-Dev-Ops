"use client";
// RA-7898 — the board editor's state. Every edit is saved through BoardStore.

import { create } from "zustand";

import { addItem, emptyBoard, removeItem, setLayouts, setView, type Board, type BoardLayouts, type Skin } from "./board";
import { PRESETS } from "./presets";
import { LocalBoardStore, presetSet, type BoardSet, type BoardStore, type ImportResult } from "./store";

const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;
let counter = 0;
/** Unique, short, and stable enough for a board in one browser. */
export function newId(prefix: string): string {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}${counter.toString(36)}`;
}

interface BoardsState extends BoardSet {
  hydrated: boolean;
  /** False when the browser refused the last save (private mode, quota). */
  saved: boolean;
  hydrate: () => void;
  select: (id: string) => void;
  update: (fn: (board: Board) => Board) => void;
  add: (module: string, view: string) => string;
  remove: (itemId: string) => void;
  view: (itemId: string, view: string) => void;
  layouts: (layouts: BoardLayouts) => void;
  skin: (skin: Skin) => void;
  newBoard: () => void;
  reset: () => void;
  importBoard: (text: string) => ImportResult;
  exportBoard: () => string | null;
}

export function createBoardsStore(store: BoardStore = new LocalBoardStore()) {
  return create<BoardsState>((set, get) => {
    const persist = (next: BoardSet) => {
      const saved = store.saveAll(next);
      set({ ...next, saved });
    };
    const current = (): BoardSet => ({ order: get().order, boards: get().boards, active: get().active });
    return {
      ...presetSet(),
      hydrated: false,
      saved: true,
      hydrate: () => set({ ...store.load(), hydrated: true }),
      select: (id) => { if (get().boards[id]) persist({ ...current(), active: id }); },
      update: (fn) => {
        const s = current();
        persist({ ...s, boards: { ...s.boards, [s.active]: fn(s.boards[s.active]) } });
      },
      add: (module, view) => {
        const id = newId(module);
        get().update((b) => addItem(b, module, view, id));
        return id;
      },
      remove: (itemId) => get().update((b) => removeItem(b, itemId)),
      view: (itemId, view) => get().update((b) => setView(b, itemId, view)),
      layouts: (layouts) => get().update((b) => setLayouts(b, layouts)),
      skin: (skin) => get().update((b) => ({ ...b, skin })),
      newBoard: () => {
        const s = current();
        const id = newId("board");
        persist({ order: [...s.order, id], boards: { ...s.boards, [id]: emptyBoard(`Board ${s.order.length + 1}`) }, active: id });
      },
      reset: () => {
        const preset = PRESETS.get(get().active);
        get().update((b) => (preset ? clone(preset) : { ...b, items: [], layouts: { lg: [] } }));
      },
      importBoard: (text) => {
        const { set: next, result } = store.importJSON(current(), text, newId("board"));
        if (result.ok) persist(next);
        return result;
      },
      exportBoard: () => store.exportJSON(current(), get().active),
    };
  });
}

export const useBoards = createBoardsStore();
