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

/** A saved board that failed validation: kept in storage untouched, never shown. */
export interface Quarantined { id: string; error: string }

export type ImportResult = { ok: true; id: string } | { ok: false; error: string };

export interface BoardStore {
  /** Every saved board, in tab order, plus which one is open. */
  load(): BoardSet;
  /** Saved boards the last load refused, with why. They stay in storage unchanged. */
  quarantined(): Quarantined[];
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

interface StoredSet extends Partial<BoardSet> { quarantine?: Record<string, unknown> }

/**
 * Parse a stored set. An invalid board is never trusted: it is reported and
 * its raw JSON is kept so the next save writes it back unchanged.
 */
export function parseSet(raw: unknown): { set: BoardSet; refused: Quarantined[]; raw: Record<string, unknown> } | null {
  const s = raw as StoredSet | null;
  if (!s || typeof s !== "object" || !Array.isArray(s.order) || !s.boards || typeof s.boards !== "object") return null;
  const boards: Record<string, Board> = {};
  const order: string[] = [];
  const refused: Quarantined[] = [];
  const kept: Record<string, unknown> = { ...(s.quarantine ?? {}) };
  for (const id of s.order) {
    if (typeof id !== "string" || order.includes(id)) continue;
    const value = (s.boards as Record<string, unknown>)[id];
    const parsed = parseBoard(value);
    if (parsed.ok) { boards[id] = parsed.board; order.push(id); }
    else { refused.push({ id, error: parsed.error }); kept[id] = value; }
  }
  for (const id of Object.keys(s.quarantine ?? {})) {
    if (!refused.some((r) => r.id === id)) refused.push({ id, error: "kept from an earlier load: not valid" });
  }
  if (order.length === 0) return { set: presetSet(), refused, raw: kept };
  const active = typeof s.active === "string" && boards[s.active] ? s.active : order[0];
  return { set: { order, boards, active }, refused, raw: kept };
}

interface StorageLike { getItem(key: string): string | null; setItem(key: string, value: string): void }

function browserStorage(): StorageLike | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export class LocalBoardStore implements BoardStore {
  private refused: Quarantined[] = [];
  private kept: Record<string, unknown> = {};

  constructor(private readonly storage: () => StorageLike | null = browserStorage) {}

  load(): BoardSet {
    this.refused = [];
    this.kept = {};
    try {
      const text = this.storage()?.getItem(STORAGE_KEY);
      if (!text) return presetSet();
      let parsed: ReturnType<typeof parseSet> = null;
      try { parsed = parseSet(JSON.parse(text)); } catch { parsed = null; }
      if (!parsed) return this.backUp(text);
      this.refused = parsed.refused;
      this.kept = parsed.raw;
      return parsed.set;
    } catch {
      this.refused = [{ id: STORAGE_KEY, error: "this browser's storage could not be read" }];
      return presetSet();
    }
  }

  /** Unreadable saved boards are copied aside before anything can overwrite them. */
  private backUp(text: string): BoardSet {
    const key = `${STORAGE_KEY}.unreadable`;
    try { this.storage()?.setItem(key, text); } catch { /* the original stays where it was */ }
    this.refused = [{ id: STORAGE_KEY, error: `saved boards were not readable; a copy is kept under "${key}"` }];
    return presetSet();
  }

  quarantined(): Quarantined[] {
    return [...this.refused];
  }

  saveAll(set: BoardSet): boolean {
    try {
      const storage = this.storage();
      if (!storage) return false;
      // Boards that failed validation ride along untouched, so a save never destroys them.
      const stored = Object.keys(this.kept).length ? { ...set, quarantine: this.kept } : set;
      storage.setItem(STORAGE_KEY, JSON.stringify(stored));
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
