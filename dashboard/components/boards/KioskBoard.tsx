"use client";
// RA-7898 — /control/boards/kiosk?board=<preset>&machine=<host>. Full screen,
// Wall look, locked, no edit controls. Resolves repo presets only until
// server-side board storage exists (spec §5, §11).

import { useSearchParams } from "next/navigation";

import { PRESETS, PRESET_IDS } from "@/lib/boards/presets";
import { useFetchTap } from "@/lib/boards/sources";
import { BoardCanvas } from "./BoardCanvas";
import styles from "./kiosk.module.css";

export function KioskBoard() {
  const params = useSearchParams();
  const id = params.get("board") ?? "";
  const machine = params.get("machine");
  const board = PRESETS.get(id);
  useFetchTap();
  return (
    <div className={styles.kiosk} data-board-skin="wall" data-testid="kiosk">
      {board ? (
        <BoardCanvas board={{ ...board, skin: "wall" }} editing={false} menus={false} viewProps={{ kioskHost: machine }} />
      ) : (
        <div className={styles.error} role="alert">
          <h1>{id ? `No preset called “${id}”.` : "Which board? Add ?board=<preset> to the address."}</h1>
          <p>The kiosk shows repo presets only. Valid ids: {PRESET_IDS.join(", ")}.</p>
        </div>
      )}
    </div>
  );
}
