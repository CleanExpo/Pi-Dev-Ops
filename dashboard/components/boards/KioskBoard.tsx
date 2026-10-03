"use client";
// RA-7898 — /control/boards/kiosk?board=<preset>&machine=<host>. Full screen,
// Wall look, locked, no edit controls. Resolves repo presets only until
// server-side board storage exists (spec §5, §11).

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";

import { PRESETS, PRESET_IDS } from "@/lib/boards/presets";
import { installFetchTap } from "@/lib/boards/sources";
import BoardCanvas from "./BoardCanvas";
import styles from "./kiosk.module.css";

export default function KioskBoard() {
  const params = useSearchParams();
  const id = params.get("board") ?? "wall-1";
  const machine = params.get("machine");
  const board = PRESETS.get(id);
  useEffect(() => installFetchTap(), []);
  return (
    <div className={styles.kiosk} data-board-skin="wall" data-testid="kiosk">
      {board ? (
        <BoardCanvas board={{ ...board, skin: "wall" }} editing={false} menus={false} viewProps={{ kioskHost: machine }} />
      ) : (
        <div className={styles.error} role="alert">
          <h1>No preset called “{id}”.</h1>
          <p>The kiosk shows repo presets only. Valid ids: {PRESET_IDS.join(", ")}.</p>
        </div>
      )}
    </div>
  );
}
