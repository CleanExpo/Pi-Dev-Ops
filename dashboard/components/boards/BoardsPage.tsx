"use client";
// RA-7898 — /control/boards. Locked by default; Customize unlocks drag,
// resize, add (library on the right), remove and view switching. Every edit
// is saved to this browser through BoardStore and survives a reload.

import { useEffect, useState } from "react";

import { useBoards } from "@/lib/boards/state";
import { useFetchTap } from "@/lib/boards/sources";
import { PRESETS } from "@/lib/boards/presets";
import { BoardCanvas } from "./BoardCanvas";
import { BoardHeader } from "./BoardHeader";
import { BoardLibrary } from "./BoardLibrary";
import styles from "./chrome.module.css";

export function BoardsPage() {
  const s = useBoards();
  const [editing, setEditing] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [message, setMessage] = useState<{ text: string; error?: boolean; undo?: boolean } | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  useEffect(() => { useBoards.getState().hydrate(); }, []);
  useFetchTap();

  const board = s.boards[s.active];
  // Nothing until the saved boards are read: drawing the default first would
  // start every one of its feeds, then restart them for the saved board.
  if (!s.hydrated || !board) return null;

  const toggleEdit = () => { setEditing(!editing); setLibraryOpen(!editing); setImportOpen(false); };
  const say = (text: string, error = false, undo = false) => setMessage({ text, error, undo });

  return (
    <div className={styles.root} data-board-skin={board.skin} data-testid="boards-page">
      <div className={styles.wrap}>
        <BoardHeader
          board={board} order={s.order} boards={s.boards} active={s.active} editing={editing}
          onSelect={(id) => { s.select(id); setMessage(null); }} onNewBoard={() => { s.newBoard(); setEditing(true); setLibraryOpen(true); }}
          onSkin={s.skin} onToggleEdit={toggleEdit}
        />
        {editing && (
          <EditBar
            libraryOpen={libraryOpen} isPreset={PRESETS.has(s.active)}
            onLibrary={() => setLibraryOpen(!libraryOpen)}
            onReset={() => setConfirmReset(true)}
            onExport={() => downloadBoard(s.exportBoard(), board.name, say)}
            onImport={() => setImportOpen(!importOpen)}
          />
        )}
        {confirmReset && (
          <div className={styles.editBar} role="alertdialog" aria-label="Confirm reset">
            <span>{PRESETS.has(s.active) ? "Put this board back to its starting layout? Your changes to it are replaced." : "Remove every card from this board?"}</span>
            <button type="button" className={styles.btn} onClick={() => { s.reset(); setConfirmReset(false); say(useBoards.getState().undo?.what ?? "Done.", false, true); }}>
              {PRESETS.has(s.active) ? "Reset board" : "Clear board"}
            </button>
            <button type="button" className={styles.ghost} onClick={() => setConfirmReset(false)}>Cancel</button>
          </div>
        )}
        {importOpen && <ImportBox onImport={(text) => {
          const result = s.importBoard(text);
          if (result.ok) { setImportOpen(false); say("Board imported and opened."); } else say(`Import refused: ${result.error}`, true);
        }} />}
        {!s.saved && <p className={styles.error} role="alert">This browser refused to save the board. Changes last until the page closes.</p>}
        {s.refused.length > 0 && (
          <p className={styles.error} role="alert">
            {s.refused.length === 1 ? "One saved board" : `${s.refused.length} saved boards`} could not be read and {s.refused.length === 1 ? "is" : "are"} not shown
            ({s.refused.map((r) => `${r.id}: ${r.error}`).join("; ")}). {s.refused.length === 1 ? "It is" : "They are"} kept in this browser unchanged.
          </p>
        )}
        {message && (
          <p className={message.error ? styles.error : styles.notice} role="status">
            {message.text}
            {message.undo && s.undo && (
              <button type="button" className={styles.ghost} onClick={() => { s.restore(); setMessage({ text: "Undone." }); }}>Undo</button>
            )}
          </p>
        )}
        <div className={styles.workspace}>
          <BoardCanvas
            board={board} editing={editing}
            onLayouts={editing ? s.layouts : undefined}
            onView={(id, view) => s.view(id, view)}
            onRemove={(id) => { s.remove(id); say("Removed from board.", false, true); }}
          />
          {editing && libraryOpen && (
            <BoardLibrary items={board.items} onClose={() => setLibraryOpen(false)} onDone={toggleEdit}
              onAdd={(module, view) => { s.add(module, view); say("Added at the bottom of the board."); }} />
          )}
        </div>
      </div>
    </div>
  );
}

function EditBar(p: { libraryOpen: boolean; isPreset: boolean; onLibrary: () => void; onReset: () => void; onExport: () => void; onImport: () => void }) {
  return (
    <div className={styles.editBar}>
      <span>Drag a card by its title. Pull the bottom-right corner to resize. Pick a view under each card.</span>
      <button type="button" className={styles.btn} onClick={p.onLibrary}>{p.libraryOpen ? "Hide modules" : "+ Add module"}</button>
      <button type="button" className={styles.btn} onClick={p.onExport}>Export</button>
      <button type="button" className={styles.btn} onClick={p.onImport}>Import</button>
      <button type="button" className={styles.ghost} onClick={p.onReset}>{p.isPreset ? "Reset to preset" : "Clear board"}</button>
    </div>
  );
}

function ImportBox({ onImport }: { onImport: (text: string) => void }) {
  const [text, setText] = useState("");
  return (
    <div>
      <label htmlFor="board-import" className={styles.notice}>Paste a board&apos;s JSON. It is checked before anything changes.</label>
      <textarea id="board-import" className={styles.importBox} value={text} onChange={(e) => setText(e.target.value)} />
      <button type="button" className={styles.btn} onClick={() => onImport(text)}>Import board</button>
    </div>
  );
}

function downloadBoard(json: string | null, name: string, say: (t: string, e?: boolean) => void) {
  if (!json) return say("Nothing to export.", true);
  try {
    const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.board.json`;
    a.click();
    URL.revokeObjectURL(url);
    say("Board exported as a JSON file.");
  } catch {
    say("This browser blocked the download.", true);
  }
}
