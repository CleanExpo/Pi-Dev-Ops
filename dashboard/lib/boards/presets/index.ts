// RA-7898 — repo presets. The kiosk resolves only these until server storage exists.

import { parseBoard, type Board } from "../board";
import desk from "./desk.json";
import founderBrief from "./founder-brief.json";
import wall1 from "./wall-1.json";
import wall2 from "./wall-2.json";
import wall3 from "./wall-3.json";
import wall4 from "./wall-4.json";
import wall5 from "./wall-5.json";
import wall6 from "./wall-6.json";

const RAW: Record<string, unknown> = {
  desk, "founder-brief": founderBrief,
  "wall-1": wall1, "wall-2": wall2, "wall-3": wall3, "wall-4": wall4, "wall-5": wall5, "wall-6": wall6,
};

function load(): ReadonlyMap<string, Board> {
  const out = new Map<string, Board>();
  for (const [id, raw] of Object.entries(RAW)) {
    const parsed = parseBoard(raw);
    // A broken preset is a build defect; __tests__/boards-presets.test.ts fails on it first.
    if (parsed.ok) out.set(id, parsed.board);
  }
  return out;
}

export const PRESETS: ReadonlyMap<string, Board> = load();
export const PRESET_IDS: readonly string[] = [...PRESETS.keys()];
export const PRESET_RAW: Readonly<Record<string, unknown>> = RAW;
export const DEFAULT_BOARD_ID = "desk";
