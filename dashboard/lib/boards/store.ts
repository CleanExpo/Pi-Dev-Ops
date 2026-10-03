// RA-7898 — where saved boards live. One interface; one implementation today
// (this browser's localStorage). Server-side storage is a founder decision
// (spec §11): it would be a second implementation of this same interface, with
// no change to the page.

import { parseBoard, parseBoardText, type Board } from "./board";
import { DEFAULT_BOARD_ID, PRESETS } from "./presets";

export interface BoardSet {
  order: string[];
  boards: Record<string, Board>;
  active: string;
}

export type ImportResult = { ok: true; id: string } | { ok: false; error: string };

export interface BoardStore {
  /** Every saved board, in tab order, plus which one is open. */
  load(): BoardSet;
  /** Persist the whole set. Returns false when storage refused the write. */
  saveAll(set: BoardSet): boolean;
  exportJSON(set: BoardSet, id: string): string | null;
  /** Validates first; an invalid file changes nothing. */
  importJSON(set: BoardSet, text: string, id: string): { set: BoardSet; result: ImportResult };
}

export const STORAGE_KEY = "pi-boards-v1";

const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

export function presetSet(): BoardSet {
  const boards: Record<string, Board> = {};
  for (const [id, board] of PRESETS) boards[id] = clone(board);
  return { order: [...PRESETS.keys()], boards, active: DEFAULT_BOARD_ID };
}

/** Parse a stored set; any invalid board is dropped, never trusted. */
export function parseSet(raw: unknown): BoardSet | null {
  const s = raw as Partial<BoardSet> | null;
  if (!s || typeof s !== "object" || !Array.isArray(s.order) || !s.boards || typeof s.boards !== "object") return null;
  const boards: Record<string, Board> = {};
  const order: string[] = [];
  for (const id of s.order) {
    if (typeof id !== "string" || order.includes(id)) continue;
    const parsed = parseBoard((s.boards as Record<string, unknown>)[id]);
    if (parsed.ok) { boards[id] = parsed.board; order.push(id); }
  }
  if (order.length === 0) return null;
  const active = typeof s.active === "string" && boards[s.active] ? s.active : order[0];
  return { order, boards, active };
}

type StorageLike = Pick<Storage, "getItem" | "setItem">;

function browserStorage(): StorageLike | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export class LocalBoardStore implements BoardStore {
  constructor(private readonly storage: () => StorageLike | null = browserStorage) {}

  load(): BoardSet {
    try {
      const text = this.storage()?.getItem(STORAGE_KEY);
      if (!text) return presetSet();
      return parseSet(JSON.parse(text)) ?? presetSet();
    } catch {
      return presetSet();
    }
  }

  saveAll(set: BoardSet): boolean {
    try {
      const storage = this.storage();
      if (!storage) return false;
      storage.setItem(STORAGE_KEY, JSON.stringify(set));
      return true;
    } catch {
      return false;
    }
  }

  exportJSON(set: BoardSet, id: string): string | null {
    const board = set.boards[id];
    return board ? JSON.stringify(board, null, 2) : null;
  }

  importJSON(set: BoardSet, text: string, id: string): { set: BoardSet; result: ImportResult } {
    const parsed = parseBoardText(text);
    if (!parsed.ok) return { set, result: parsed };
    const next = clone(set);
    next.boards[id] = parsed.board;
    if (!next.order.includes(id)) next.order.push(id);
    next.active = id;
    return { set: next, result: { ok: true, id } };
  }
}
