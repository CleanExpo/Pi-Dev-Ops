import fs from "node:fs";
import path from "node:path";
import { randomBytes } from "node:crypto";

const QUEUE_CAP = 500;
const LOG_CAP = 2000;
const LOG_KEEP = 1000;

export function createStore(dir) {
  fs.mkdirSync(dir, { recursive: true });
  const queuePath = path.join(dir, "queue.json");
  const activityPath = path.join(dir, "activity.jsonl");
  const auditPath = path.join(dir, "audit.jsonl");
  let chain = Promise.resolve();

  function locked(fn) {
    const run = chain.then(fn, fn);
    chain = run.then(() => undefined, () => undefined);
    return run;
  }

  function readQueue() {
    try {
      const parsed = JSON.parse(fs.readFileSync(queuePath, "utf8"));
      if (parsed && parsed.items && typeof parsed.items === "object") return parsed.items;
    } catch {
      // Missing or torn file: start empty rather than crash a read.
    }
    return {};
  }

  function writeQueue(items) {
    const tmp = `${queuePath}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify({ items }));
    fs.renameSync(tmp, queuePath);
  }

  function appendCapped(file, record) {
    fs.appendFileSync(file, `${JSON.stringify(record)}\n`);
    const lines = fs.readFileSync(file, "utf8").split("\n").filter(Boolean);
    if (lines.length <= LOG_CAP) return;
    fs.writeFileSync(file, `${lines.slice(-LOG_KEEP).join("\n")}\n`);
  }

  function tail(file, limit) {
    if (!fs.existsSync(file)) return [];
    const lines = fs.readFileSync(file, "utf8").split("\n").filter(Boolean);
    const out = [];
    for (const line of lines.slice(-limit)) {
      try {
        out.push(JSON.parse(line));
      } catch {
        // Skip a torn line.
      }
    }
    return out.reverse();
  }

  return {
    listQueue(system) {
      return locked(() => {
        const items = Object.values(readQueue());
        const filtered = system ? items.filter((item) => item.system === system) : items;
        filtered.sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
        return filtered;
      });
    },

    upsert(input) {
      return locked(() => {
        const items = readQueue();
        const existing = items[input.id];
        if (!existing && !input.title) return { ok: false, error: "title is required to add a queue item" };
        if (!existing && Object.keys(items).length >= QUEUE_CAP) return { ok: false, error: "queue is full (500)" };
        const now = new Date().toISOString();
        const next = {
          id: input.id,
          title: input.title || existing.title,
          system: input.system || existing?.system || "mc",
          status: input.status || existing?.status || "open",
          owner: existing?.owner || null,
          note: input.note !== undefined ? input.note : (existing?.note || ""),
          created_at: existing?.created_at || now,
          updated_at: now,
          updated_by: input.actor,
        };
        items[input.id] = next;
        writeQueue(items);
        return { ok: true, created: !existing, item: next };
      });
    },

    claim(id, actor) {
      return locked(() => {
        const items = readQueue();
        const item = items[id];
        if (!item) return { ok: false, error: "queue item not found" };
        if (item.owner && item.owner !== actor) return { ok: false, error: `already claimed by ${item.owner}` };
        const next = { ...item, owner: actor, status: "claimed", updated_at: new Date().toISOString(), updated_by: actor };
        items[id] = next;
        writeQueue(items);
        return { ok: true, item: next };
      });
    },

    release(id, actor) {
      return locked(() => {
        const items = readQueue();
        const item = items[id];
        if (!item) return { ok: false, error: "queue item not found" };
        if (item.status === "done") return { ok: false, error: "done items stay on the record" };
        if (!item.owner) return { ok: false, error: "not claimed" };
        if (item.owner !== actor) return { ok: false, error: `only ${item.owner} can release this` };
        const next = { ...item, owner: null, status: "open", updated_at: new Date().toISOString(), updated_by: actor };
        items[id] = next;
        writeQueue(items);
        return { ok: true, item: next };
      });
    },

    addActivity(record) {
      return locked(() => {
        const row = {
          id: `act_${randomBytes(8).toString("hex")}`,
          ts: new Date().toISOString(),
          ...record,
        };
        appendCapped(activityPath, row);
        return row;
      });
    },

    listActivity(limit) {
      return locked(() => tail(activityPath, limit));
    },

    addAudit(record) {
      return locked(() => {
        const row = { ts: new Date().toISOString(), ...record };
        appendCapped(auditPath, row);
        return row;
      });
    },

    listAudit(limit) {
      return locked(() => tail(auditPath, limit));
    },
  };
}
