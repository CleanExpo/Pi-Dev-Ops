// RA-7898 — the board format, its validation, and the edits a board allows.
//
// A board is nothing more than this JSON (docs/specs/modular-boards.md §5):
// { name, skin, items: [{ id, module, view }], layouts: { lg, md, sm: [{ i, x, y, w, h }] } }

import { MODULES } from "./registry";

export const SKINS = ["paper", "graphite", "slate", "wall"] as const;
export type Skin = (typeof SKINS)[number];
export const SKIN_LABEL: Record<Skin, string> = { paper: "Paper", graphite: "Graphite", slate: "Slate", wall: "Wall" };

export const BREAKPOINTS = { lg: 960, md: 600, sm: 0 } as const;
export const COLS = { lg: 12, md: 8, sm: 4 } as const;
export type Breakpoint = keyof typeof COLS;
export const BREAKPOINT_IDS: readonly Breakpoint[] = ["lg", "md", "sm"];

export interface BoardItem { id: string; module: string; view: string }
export interface BoardCell { i: string; x: number; y: number; w: number; h: number }
export type BoardLayouts = Partial<Record<Breakpoint, BoardCell[]>>;
export interface Board { name: string; skin: Skin; items: BoardItem[]; layouts: BoardLayouts }

export type ParseResult = { ok: true; board: Board } | { ok: false; error: string };

const isInt = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v >= 0;
const isText = (v: unknown): v is string => typeof v === "string" && v.trim().length > 0 && v.length <= 200;

function parseItems(raw: unknown): BoardItem[] | string {
  if (!Array.isArray(raw)) return "items must be a list";
  const items: BoardItem[] = [];
  for (const entry of raw) {
    const e = entry as Record<string, unknown> | null;
    if (!e || !isText(e.id) || !isText(e.module) || !isText(e.view)) return "every item needs text id, module and view";
    items.push({ id: e.id, module: e.module, view: e.view });
  }
  if (new Set(items.map((i) => i.id)).size !== items.length) return "item ids must be unique";
  return items;
}

function parseCells(raw: unknown, bp: Breakpoint): BoardCell[] | string {
  if (!Array.isArray(raw)) return `layouts.${bp} must be a list`;
  const cells: BoardCell[] = [];
  for (const entry of raw) {
    const c = entry as Record<string, unknown> | null;
    if (!c || !isText(c.i) || !isInt(c.x) || !isInt(c.y) || !isInt(c.w) || !isInt(c.h) || c.w < 1 || c.h < 1) {
      return `layouts.${bp} cells need i and whole-number x, y, w, h`;
    }
    if (c.x >= COLS[bp]) return `layouts.${bp} cell "${c.i}" starts outside the ${COLS[bp]} columns`;
    cells.push({ i: c.i, x: c.x, y: c.y, w: Math.min(c.w, COLS[bp]), h: c.h });
  }
  return cells;
}

/** The one parser for any board from storage, a file or a preset. Never throws. */
export function parseBoard(value: unknown): ParseResult {
  const b = value as Record<string, unknown> | null;
  if (!b || typeof b !== "object" || Array.isArray(b)) return { ok: false, error: "A board must be a JSON object." };
  if (!isText(b.name)) return { ok: false, error: "A board needs a name." };
  if (!SKINS.includes(b.skin as Skin)) return { ok: false, error: `Look must be one of ${SKINS.join(", ")}.` };
  const items = parseItems(b.items);
  if (typeof items === "string") return { ok: false, error: items };
  const rawLayouts = b.layouts as Record<string, unknown> | null;
  if (!rawLayouts || typeof rawLayouts !== "object") return { ok: false, error: "A board needs layouts." };
  const layouts: BoardLayouts = {};
  for (const bp of BREAKPOINT_IDS) {
    if (rawLayouts[bp] === undefined) continue;
    const cells = parseCells(rawLayouts[bp], bp);
    if (typeof cells === "string") return { ok: false, error: cells };
    const orphan = cells.find((c) => !items.some((i) => i.id === c.i));
    if (orphan) return { ok: false, error: `layouts.${bp} has a cell "${orphan.i}" for an item the board does not have.` };
    layouts[bp] = cells;
  }
  if (!layouts.lg) return { ok: false, error: "A board needs an lg layout." };
  return { ok: true, board: { name: b.name.trim(), skin: b.skin as Skin, items, layouts } };
}

export function parseBoardText(text: string): ParseResult {
  try {
    return parseBoard(JSON.parse(text));
  } catch {
    return { ok: false, error: "That is not valid JSON." };
  }
}

const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

function bottom(cells: readonly BoardCell[]): number {
  return cells.reduce((max, c) => Math.max(max, c.y + c.h), 0);
}

/** Add a module at the bottom of every layout. Unknown module or view: unchanged. */
export function addItem(board: Board, module: string, view: string, id: string): Board {
  const def = MODULES.get(module);
  const size = def?.views[view]?.size;
  if (!def || !size) return board;
  const next = clone(board);
  next.items.push({ id, module, view });
  for (const bp of BREAKPOINT_IDS) {
    const cells = next.layouts[bp];
    if (!cells) continue;
    cells.push({ i: id, x: 0, y: bottom(cells), w: Math.min(size.w, COLS[bp]), h: size.h });
  }
  return next;
}

export function removeItem(board: Board, id: string): Board {
  const next = clone(board);
  next.items = next.items.filter((i) => i.id !== id);
  for (const bp of BREAKPOINT_IDS) if (next.layouts[bp]) next.layouts[bp] = next.layouts[bp]!.filter((c) => c.i !== id);
  return next;
}

/** Switch a view; the cell grows to the view's default size if smaller. */
export function setView(board: Board, id: string, view: string): Board {
  const next = clone(board);
  const item = next.items.find((i) => i.id === id);
  const size = item ? MODULES.get(item.module)?.views[view]?.size : undefined;
  if (!item || !size) return board;
  item.view = view;
  for (const bp of BREAKPOINT_IDS) {
    const cell = next.layouts[bp]?.find((c) => c.i === id);
    if (!cell) continue;
    cell.w = Math.min(Math.max(cell.w, size.w), COLS[bp]);
    cell.h = Math.max(cell.h, size.h);
    // A wider view slides the card left so it still ends inside the columns.
    cell.x = Math.min(cell.x, COLS[bp] - cell.w);
  }
  return next;
}

export function setLayouts(board: Board, layouts: BoardLayouts): Board {
  const next = clone(board);
  const ids = new Set(next.items.map((i) => i.id));
  for (const bp of BREAKPOINT_IDS) {
    const cells = layouts[bp];
    if (cells) next.layouts[bp] = cells.filter((c) => ids.has(c.i)).map(({ i, x, y, w, h }) => ({ i, x, y, w, h }));
  }
  return next;
}

export function emptyBoard(name: string, skin: Skin = "paper"): Board {
  return { name, skin, items: [], layouts: { lg: [] } };
}

/**
 * Fill in missing md / sm layouts from lg. sm (phones) stacks every card full
 * width in reading order; md scales lg's columns down. Saved layouts win.
 */
export function withDerivedLayouts(board: Board): BoardLayouts {
  const lg = board.layouts.lg ?? [];
  const order = [...lg].sort((a, b) => a.y - b.y || a.x - b.x);
  const out: BoardLayouts = { ...board.layouts };
  if (!out.md) {
    const k = COLS.md / COLS.lg;
    out.md = lg.map((c) => {
      const x = Math.min(COLS.md - 1, Math.round(c.x * k));
      return { ...c, x, w: Math.max(1, Math.min(COLS.md - x, Math.round(c.w * k))) };
    });
  }
  if (!out.sm) {
    let y = 0;
    out.sm = order.map((c) => {
      const cell = { i: c.i, x: 0, y, w: COLS.sm, h: c.h };
      y += c.h;
      return cell;
    });
  }
  return out;
}
