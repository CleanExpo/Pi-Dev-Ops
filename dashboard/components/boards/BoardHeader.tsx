"use client";
// RA-7898 — board header: greeting with a one-line summary, quick-action
// links, one "Updated Xs ago", board tabs, the look switch and Customize.

import Link from "next/link";

import { brisbaneParts } from "@/components/boards/views/founder";
import { SKINS, SKIN_LABEL, type Board, type Skin } from "@/lib/boards/board";
import { MODULES } from "@/lib/boards/registry";
import { useSources } from "@/lib/boards/sources/useSources";
import type { SourceSnapshot } from "@/lib/boards/sources/types";
import { ago, useNow } from "@/lib/boards/use-now";
import styles from "./chrome.module.css";

/** Links to existing pages only: the header itself performs no action. */
const QUICK: readonly { label: string; href: string }[] = [
  { label: "Run a build", href: "/control/build" },
  { label: "Capture an idea", href: "/control#idea-pipeline" },
  { label: "Set a goal", href: "/control/goal" },
  { label: "Open the wall", href: "/control/boards/kiosk?board=wall-1" },
];

function summary(snaps: readonly SourceSnapshot<unknown>[]): string {
  if (snaps.length === 0) return "Nothing on this board yet.";
  const count = (state: string) => snaps.filter((s) => s.state === state).length;
  const parts = [`${count("live")} of ${snaps.length} sources live`];
  if (count("unreachable")) parts.push(`${count("unreachable")} unreachable`);
  if (count("stale")) parts.push(`${count("stale")} stale`);
  if (count("no_source")) parts.push(`${count("no_source")} with no source yet`);
  if (count("loading")) parts.push(`${count("loading")} loading`);
  return parts.join(" · ");
}

interface HeaderProps {
  board: Board;
  order: readonly string[];
  boards: Readonly<Record<string, Board>>;
  active: string;
  editing: boolean;
  onSelect: (id: string) => void;
  onNewBoard: () => void;
  onSkin: (skin: Skin) => void;
  onToggleEdit: () => void;
}

export default function BoardHeader(p: HeaderProps) {
  const now = useNow(1_000);
  const feedIds = [...new Set(p.board.items.flatMap((i) => MODULES.get(i.module)?.sources ?? []))]
    .filter((id) => id !== "local-clock" && id !== "static").sort();
  const snaps = useSources(feedIds);
  const lastFetch = snaps.reduce<number | null>((m, s) => (s.fetchedAt !== null && (m === null || s.fetchedAt > m) ? s.fetchedAt : m), null);
  const t = brisbaneParts(now);
  const greet = t.h < 12 ? "Good morning" : t.h < 17 ? "Good afternoon" : "Good evening";
  return (
    <header className={styles.header}>
      <div className={styles.top}>
        <div className={styles.crumb}><span>Mission Control</span><span aria-hidden>/</span><b>Boards</b></div>
        <span className={styles.updated} data-testid="board-updated">{lastFetch === null ? "Waiting for first read" : `Updated ${ago(lastFetch, now)}`}</span>
        <div className={styles.seg} role="group" aria-label="Board look">
          {SKINS.map((s) => (
            <button key={s} type="button" aria-pressed={p.board.skin === s} onClick={() => p.onSkin(s)}>{SKIN_LABEL[s]}</button>
          ))}
        </div>
      </div>
      <div className={styles.hello}>
        <div>
          <h1>{greet}, Phill</h1>
          <p>{t.label} · {summary(snaps)}</p>
        </div>
        <nav className={styles.actions} aria-label="Quick actions">
          {QUICK.map((q, i) => (
            <Link key={q.href} href={q.href} className={`${styles.chip} ${i === 0 ? styles.chipFirst : ""}`}>{q.label}</Link>
          ))}
        </nav>
      </div>
      <div className={styles.tabsRow}>
        <div className={styles.tabs} role="tablist" aria-label="Boards">
          {p.order.map((id) => (
            <button key={id} type="button" role="tab" aria-selected={p.active === id} className={styles.tab} onClick={() => p.onSelect(id)}>
              {p.boards[id].name}
            </button>
          ))}
          <button type="button" className={styles.tab} onClick={p.onNewBoard}>+ Board</button>
        </div>
        <button type="button" className={`${styles.btn} ${p.editing ? styles.primary : ""}`} aria-pressed={p.editing} onClick={p.onToggleEdit}>
          {p.editing ? "Done" : "Customize"}
        </button>
      </div>
    </header>
  );
}
