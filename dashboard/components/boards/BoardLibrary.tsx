"use client";
// RA-7898 — the module library: every registered module by sector; pick a view to add.

import { MODULE_LIST } from "@/lib/boards/registry";
import { SECTORS } from "@/lib/boards/registry/types";
import type { BoardItem } from "@/lib/boards/board";
import styles from "./chrome.module.css";

interface LibraryProps {
  items: readonly BoardItem[];
  onAdd: (module: string, view: string) => void;
  onClose: () => void;
  onDone: () => void;
}

export function BoardLibrary({ items, onAdd, onClose, onDone }: LibraryProps) {
  const counts = new Map<string, number>();
  for (const item of items) counts.set(item.module, (counts.get(item.module) ?? 0) + 1);
  return (
    <aside className={styles.library} aria-label="Module library">
      <div className={styles.libHead}>
        <h2>Add to board</h2>
        <span>
          <button type="button" className={styles.ghost} onClick={onClose}>Close</button>
          <button type="button" className={styles.ghost} onClick={onDone}>Done</button>
        </span>
      </div>
      <p className={styles.libSub}>Pick how a module should look and it lands at the bottom of the board. The same module can appear twice in different views.</p>
      {SECTORS.map((sector) => {
        const modules = MODULE_LIST.filter((m) => m.sector === sector);
        if (modules.length === 0) return null;
        return (
          <section key={sector} className={styles.sector} aria-label={sector}>
            <h3>{sector}</h3>
            {modules.map((m) => (
              <div key={m.id} className={styles.libItem} data-library-module={m.id}>
                <div className={styles.libTop}>
                  <strong>{m.name}</strong>
                  <small>{counts.get(m.id) ? `On board ×${counts.get(m.id)}` : m.action ? "Action" : ""}</small>
                </div>
                <p>{m.blurb}</p>
                <div className={styles.addRow}>
                  {Object.entries(m.views).map(([key, v]) => (
                    <button key={key} type="button" onClick={() => onAdd(m.id, key)} aria-label={`Add ${m.name} as ${v.label}`}>
                      + {v.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </section>
        );
      })}
    </aside>
  );
}
