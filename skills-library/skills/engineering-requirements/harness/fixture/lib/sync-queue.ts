// Offline capture queue for field technicians.
const RETRY_BACKOFF_MS = [1000, 2000, 5000, 10000, 30000]; // exponential backoff
const MAX_RETRY_COUNT = 5;

export type Entry = {
  id: string;
  status: "pending" | "failed";
  retryCount: number;
  nextAttemptAt: number | null;
  endpoint: string;
  payload: unknown;
};

async function incrementRetry(db: IDBDatabase, entry: Entry) {
  const nextAttempt = Date.now() + RETRY_BACKOFF_MS[Math.min(entry.retryCount, 4)];
  await put(db, {
    ...entry,
    retryCount: entry.retryCount + 1,
    nextAttemptAt: nextAttempt,
  });
}

export async function drainQueue(db: IDBDatabase) {
  const index = db.transaction("queue").objectStore("queue").index("status");
  const entries: Entry[] = await getAll(index, "pending");

  for (const entry of entries) {
    if (entry.retryCount >= MAX_RETRY_COUNT) {
      await markFailed(db, entry.id);
      continue;
    }
    try {
      const response = await fetch(entry.endpoint, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(entry.payload),
      });
      if (!response.ok) await incrementRetry(db, entry);
      else await removeEntry(db, entry.id);
    } catch {
      await incrementRetry(db, entry);
    }
  }
}

export async function getSyncStatus(db: IDBDatabase) {
  const pendingCount = await count(db, "pending");
  const conflictCount = await count(db, "conflict");
  if (conflictCount > 0) return "SYNC_CONFLICT";
  if (pendingCount > 0) return "PENDING_SYNC";
  return "SYNCED";
}

declare function put(db: IDBDatabase, e: Entry): Promise<void>;
declare function getAll(i: IDBIndex, s: string): Promise<Entry[]>;
declare function markFailed(db: IDBDatabase, id: string): Promise<void>;
declare function removeEntry(db: IDBDatabase, id: string): Promise<void>;
declare function count(db: IDBDatabase, s: string): Promise<number>;
