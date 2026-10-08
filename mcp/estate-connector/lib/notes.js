import { randomUUID } from "node:crypto";
import { ToolError, assertSystem, cleanText } from "./validate.js";

const NOTE_CAP = 500;

export async function listNotes(ctx, { system, limit }) {
  const take = clampLimit(limit);
  if (system) assertSystem(ctx.systems, system);
  return ctx.store.read((state) => {
    const notes = state.notes
      .slice()
      .reverse()
      .filter((note) => !system || note.system === system)
      .slice(0, take);
    return { count: notes.length, notes };
  });
}

export async function addNote(ctx, bot, system, text) {
  assertSystem(ctx.systems, system);
  const clean = cleanText(text, "text");
  const note = {
    id: randomUUID(),
    ts: new Date().toISOString(),
    bot,
    system,
    text: clean,
  };
  return ctx.store.update((state) => {
    state.notes.push(note);
    if (state.notes.length > NOTE_CAP) state.notes.splice(0, state.notes.length - NOTE_CAP);
    return note;
  });
}

function clampLimit(limit) {
  const n = Number(limit ?? 30);
  if (!Number.isInteger(n) || n < 1 || n > 100) {
    throw new ToolError("limit must be a whole number from 1 to 100.");
  }
  return n;
}
