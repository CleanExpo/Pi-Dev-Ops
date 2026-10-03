"use client";
// RA-7898 — the one frame every module renders inside (spec §4).
//
// It owns the kicker, title, ⋯ menu (Show as / source / Remove), freshness and
// the five states, so no view re-implements them. A read-only view renders only
// while its module is live; an action view renders in every state but loading,
// so a safety control never disappears because a read failed.

import { useEffect, useRef, useState, type ReactNode } from "react";

import { moduleStatus, STATE_LABEL, type ModuleStatus } from "@/lib/boards/module-state";
import { MODULES } from "@/lib/boards/registry";
import { FEEDS } from "@/lib/boards/sources/feeds";
import { useSources } from "@/lib/boards/sources/useSources";
import { ago, useNow } from "@/lib/boards/use-now";
import type { ModuleDef, ViewProps } from "@/lib/boards/registry/types";
import styles from "./boards.module.css";

export interface FrameItem {
  id: string;
  module: string;
  view: string;
}

interface FrameProps {
  item: FrameItem;
  editing?: boolean;
  onView?: (itemId: string, view: string) => void;
  onRemove?: (itemId: string) => void;
  viewProps?: ViewProps;
  /** False on a locked surface (the kiosk): no ⋯ menu at all. */
  menu?: boolean;
}

export default function ModuleFrame(props: FrameProps) {
  const def = MODULES.get(props.item.module);
  if (!def) return <UnknownFrame {...props} />;
  return <KnownFrame def={def} {...props} />;
}

function KnownFrame({ def, item, editing = false, onView, onRemove, viewProps, menu = true }: FrameProps & { def: ModuleDef }) {
  const status = moduleStatus(useSources(def.sources));
  const viewId = def.views[item.view] ? item.view : Object.keys(def.views)[0];
  const view = def.views[viewId];
  const View = view.component;
  const showView = status.state === "live" || (view.action === true && status.state !== "loading");
  return (
    <article className={styles.card} data-module={def.id} data-view={viewId} data-state={status.state} aria-label={def.name}>
      <FrameHead def={def} status={status} viewId={viewId} menu={menu} onView={(v) => onView?.(item.id, v)} onRemove={() => onRemove?.(item.id)} />
      {showView && status.state !== "live" && <StateBanner status={status} />}
      <div className={showView && (view.action || def.id.startsWith("wall")) ? styles.panelBody : styles.body}>
        {showView ? <View {...viewProps} /> : <StateBody status={status} />}
      </div>
      {editing && Object.keys(def.views).length > 1 && (
        <div className={`${styles.viewStrip} mc-nodrag`} aria-label={`Views for ${def.name}`}>
          {Object.entries(def.views).map(([key, v]) => (
            <button key={key} type="button" aria-pressed={key === viewId} onClick={() => onView?.(item.id, key)}>{v.label}</button>
          ))}
        </div>
      )}
    </article>
  );
}

function freshness(status: ModuleStatus, now: number): string | null {
  if (status.clock === "local") return null;
  if (status.freshAt === null) return null;
  return status.clock === "server" ? `updated ${ago(status.freshAt, now)}` : `fetched ${ago(status.freshAt, now)}`;
}

function FrameHead({ def, status, viewId, menu, onView, onRemove }: {
  def: ModuleDef; status: ModuleStatus; viewId: string; menu: boolean; onView: (v: string) => void; onRemove: () => void;
}) {
  const now = useNow(1_000);
  const fresh = freshness(status, now);
  return (
    <header className={styles.head}>
      <div className={`${styles.titles} mc-drag`}>
        <div className={styles.kicker} data-testid="module-kicker">
          <span className={styles.dot} data-tone={status.state} aria-hidden />
          <span>{def.sector} · {STATE_LABEL[status.state]}{def.action ? " · Action" : ""}</span>
          {fresh && <span title={status.clock === "server" ? "Server clock" : "Browser time of the last fetch"}>· {fresh}</span>}
        </div>
        <h3 className={styles.title}>{def.name}</h3>
      </div>
      {menu && <FrameMenu def={def} viewId={viewId} status={status} onView={onView} onRemove={onRemove} />}
    </header>
  );
}

function FrameMenu({ def, viewId, status, onView, onRemove }: {
  def: ModuleDef; viewId: string; status: ModuleStatus; onView: (v: string) => void; onRemove: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div ref={ref} className="mc-nodrag">
      <button type="button" className={styles.menuBtn} aria-label={`Options for ${def.name}`} aria-haspopup="menu"
        aria-expanded={open} onClick={() => setOpen(!open)}>⋯</button>
      {open && (
        <div className={styles.menu} role="menu">
          <h4>Show as</h4>
          {Object.entries(def.views).map(([key, v]) => (
            <button key={key} type="button" role="menuitemradio" aria-checked={key === viewId}
              onClick={() => { onView(key); setOpen(false); }}>{v.label}</button>
          ))}
          <div className={styles.sep} />
          <div className={styles.src}>
            Source: {def.sources.map((id) => <code key={id}>{FEEDS.get(id)?.url ?? id} </code>)}
            {status.clock === "browser" && <div>Freshness is the browser&apos;s fetch time.</div>}
          </div>
          <div className={styles.sep} />
          <button type="button" role="menuitem" className={styles.danger} onClick={() => { setOpen(false); onRemove(); }}>
            Remove from board
          </button>
        </div>
      )}
    </div>
  );
}

function stateText(status: ModuleStatus): { head: string; detail: string | null } {
  switch (status.state) {
    case "loading": return { head: "Loading…", detail: null };
    case "stale": return { head: "Stale — showing nothing until a fresh read arrives.", detail: status.reason };
    case "unreachable": return { head: "Unreachable.", detail: status.reason };
    case "no_source": return { head: "No source yet.", detail: status.reason };
    default: return { head: "", detail: null };
  }
}

function StateBody({ status }: { status: ModuleStatus }) {
  const { head, detail } = stateText(status);
  return (
    <div className={styles.state} role="status" data-testid="module-state">
      <strong>{head}</strong>
      {detail && <span>{detail}</span>}
    </div>
  );
}

function StateBanner({ status }: { status: ModuleStatus }) {
  const { head, detail } = stateText(status);
  return (
    <div className={styles.banner} data-tone={status.state} role="status" data-testid="module-state">
      {head}{detail ? ` ${detail}` : ""}
    </div>
  );
}

function UnknownFrame({ item, onRemove, menu = true }: FrameProps): ReactNode {
  return (
    <article className={`${styles.card} ${styles.unknown}`} data-module={item.module} data-state="unknown" aria-label="Unknown module">
      <header className={styles.head}>
        <div className={styles.titles}>
          <div className={styles.kicker}><span className={styles.dot} data-tone="no_source" aria-hidden /> <span>Unknown module</span></div>
          <h3 className={styles.title}>Unknown module “{item.module}”</h3>
        </div>
      </header>
      <div className={styles.body}>
        <div className={styles.state} role="status">
          <span>This board names a module that is not registered. It has no data and no actions.</span>
          {menu && onRemove && (
            <button type="button" className="mc-nodrag" onClick={() => onRemove(item.id)}>Remove from board</button>
          )}
        </div>
      </div>
    </article>
  );
}
