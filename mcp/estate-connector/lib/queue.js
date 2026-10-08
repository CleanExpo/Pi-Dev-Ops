import { ToolError, assertSystem, cleanId, cleanText } from "./validate.js";

const QUEUE_CAP = 200;
const UPDATE_STATUS = new Set(["open", "blocked", "done"]);

export async function listQueue(ctx, system) {
  if (system) assertSystem(ctx.systems, system);
  return ctx.store.read((state) => {
    const items = state.queue.filter((item) => !system || item.system === system);
    return { count: items.length, items };
  });
}

export async function upsertItem(ctx, bot, input) {
  const id = cleanId(input.id);
  const system = input.system === undefined ? undefined : assertSystem(ctx.systems, input.system);
  if (input.status && !UPDATE_STATUS.has(input.status)) {
    throw new ToolError("status must be open, blocked, or done. Use claim to take an item.");
  }
  const title = input.title === undefined ? undefined : cleanText(input.title, "title", 200);
  const note = input.note === undefined ? undefined : cleanText(input.note, "note");
  const change = { id, system, title, note, status: input.status, bot };
  return ctx.store.update((state) => applyUpsert(state, change, ctx.systems));
}

export async function claimItem(ctx, bot, id) {
  const clean = cleanId(id);
  return ctx.store.update((state) => {
    const item = requireItem(state, clean);
    if (item.status === "done") throw new ToolError("That item is already done.");
    if (item.status === "claimed" && item.owner !== bot) {
      throw new ToolError("Another bot already claimed that item.");
    }
    return touch(item, bot, { status: "claimed", owner: bot });
  });
}

export async function releaseItem(ctx, bot, id) {
  const clean = cleanId(id);
  return ctx.store.update((state) => {
    const item = requireItem(state, clean);
    if (item.owner && item.owner !== bot) {
      throw new ToolError("Only the bot that claimed this item can release it.");
    }
    if (item.status !== "claimed") return { ...item };
    return touch(item, bot, { status: "open", owner: null });
  });
}

function requireItem(state, id) {
  const item = state.queue.find((row) => row.id === id);
  if (!item) throw new ToolError("No queue item with that id.");
  return item;
}

function applyUpsert(state, change, systems) {
  const item = state.queue.find((row) => row.id === change.id);
  if (!item) return createItem(state, change, systems);
  if (item.status === "claimed" && item.owner !== change.bot) {
    throw new ToolError("Another bot has claimed that item.");
  }
  if (change.title) item.title = change.title;
  if (change.note !== undefined) item.note = change.note;
  if (change.system) item.system = change.system;
  if (change.status) {
    item.status = change.status;
    if (change.status === "open") item.owner = null;
  }
  return touch(item, change.bot, {});
}

function createItem(state, change, systems) {
  if (!change.title) throw new ToolError("title is required for a new item.");
  if (state.queue.length >= QUEUE_CAP) {
    throw new ToolError("The shared queue is full (200). Mark items done before adding more.");
  }
  const system = assertSystem(systems, change.system || "mc");
  const item = {
    id: change.id,
    title: change.title,
    system,
    status: change.status || "open",
    owner: null,
    note: change.note || "",
    updated_at: new Date().toISOString(),
    updated_by: change.bot,
  };
  state.queue.push(item);
  return { ...item };
}

function touch(item, bot, patch) {
  Object.assign(item, patch, { updated_at: new Date().toISOString(), updated_by: bot });
  return { ...item };
}
