"use client";
// RA-7898 — the grid. react-grid-layout v2: Responsive + useContainerWidth,
// rendered only once the container is measured. Locked unless `editing`.

import "react-grid-layout/css/styles.css";

import { useMemo } from "react";
import { Responsive, useContainerWidth, type Layout, type ResponsiveLayouts } from "react-grid-layout";

import { BREAKPOINT_IDS, BREAKPOINTS, COLS, withDerivedLayouts, type Board, type BoardLayouts, type Breakpoint } from "@/lib/boards/board";
import { MODULES } from "@/lib/boards/registry";
import type { ViewProps } from "@/lib/boards/registry/types";
import { ModuleFrame } from "./ModuleFrame";
import canvas from "./canvas.module.css";

interface CanvasProps {
  board: Board;
  editing: boolean;
  onLayouts?: (layouts: BoardLayouts) => void;
  onView?: (itemId: string, view: string) => void;
  onRemove?: (itemId: string) => void;
  viewProps?: ViewProps;
  /** False on the kiosk: cards have no menu. */
  menus?: boolean;
}

const ROW_HEIGHT = 54;
const MARGIN: readonly [number, number] = [14, 14];

/** Board cells plus each module's minimum size, clamped to the breakpoint. */
function withMinimums(board: Board): ResponsiveLayouts<Breakpoint> {
  const moduleOf = new Map(board.items.map((i) => [i.id, i.module]));
  const out: ResponsiveLayouts<Breakpoint> = {};
  const all = withDerivedLayouts(board);
  for (const bp of BREAKPOINT_IDS) {
    const cells = all[bp];
    if (!cells) continue;
    out[bp] = cells.map((c) => {
      const min = MODULES.get(moduleOf.get(c.i) ?? "")?.minSize ?? { w: 2, h: 2 };
      return { ...c, minW: Math.min(min.w, COLS[bp]), minH: min.h };
    });
  }
  return out;
}

export function BoardCanvas({ board, editing, onLayouts, onView, onRemove, viewProps, menus = true }: CanvasProps) {
  const { width, containerRef, mounted } = useContainerWidth();
  const layouts = useMemo(() => withMinimums(board), [board]);
  const onLayoutChange = (_layout: Layout, all: ResponsiveLayouts<Breakpoint>) => {
    if (!onLayouts) return;
    const next: BoardLayouts = {};
    for (const bp of BREAKPOINT_IDS) {
      const list = all[bp];
      if (list) next[bp] = list.map(({ i, x, y, w, h }) => ({ i, x, y, w, h }));
    }
    onLayouts(next);
  };
  return (
    <div ref={containerRef} className={`${canvas.canvas} ${editing ? canvas.editing : ""}`} data-testid="board-canvas">
      {board.items.length === 0 ? (
        <div className={canvas.empty}>
          <strong>This board is empty</strong>
          {editing ? "Pick a module in the library to add your first card." : "Press Customize to add modules."}
        </div>
      ) : mounted && width > 0 && (
        <Responsive
          width={width}
          layouts={layouts}
          breakpoints={BREAKPOINTS}
          cols={COLS}
          rowHeight={ROW_HEIGHT}
          margin={MARGIN}
          containerPadding={[0, 0]}
          dragConfig={{ enabled: editing, handle: ".mc-drag", cancel: ".mc-nodrag" }}
          resizeConfig={{ enabled: editing, handles: ["se"] }}
          onLayoutChange={onLayoutChange}
        >
          {board.items.map((item) => (
            <div key={item.id} data-item={item.id}>
              <ModuleFrame item={item} editing={editing} onView={onView} onRemove={onRemove} viewProps={viewProps} menu={menus} />
            </div>
          ))}
        </Responsive>
      )}
    </div>
  );
}
