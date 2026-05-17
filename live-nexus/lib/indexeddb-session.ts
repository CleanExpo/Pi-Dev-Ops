import type { Action, TranscriptLine } from "./markdown-composer";

export interface StoredSession {
  meetingId: string;
  title: string;
  startedAt: string;
  endedAt: string;
  transcript: TranscriptLine[];
  topics: string[];
  actions: Action[];
  brand: string;
  lastUpdated: number;
}

const DB_NAME = "live-nexus";
const STORE = "session";
const KEY = "current";

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function saveSession(session: StoredSession): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put({ ...session, lastUpdated: Date.now() }, KEY);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

export async function loadSession(): Promise<StoredSession | null> {
  const db = await openDb();
  const result = await new Promise<StoredSession | undefined>((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).get(KEY);
    req.onsuccess = () => resolve(req.result as StoredSession | undefined);
    req.onerror = () => reject(req.error);
  });
  db.close();
  return result ?? null;
}

export async function clearSession(): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(KEY);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

export async function hasFreshSession(maxAgeMs: number): Promise<boolean> {
  const s = await loadSession();
  if (!s) return false;
  return Date.now() - s.lastUpdated < maxAgeMs;
}
